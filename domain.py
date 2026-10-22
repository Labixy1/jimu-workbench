"""Durable sources, artifacts and review transactions, separate from Agent history."""
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,title TEXT,content TEXT,url TEXT,visibility TEXT,hash TEXT UNIQUE,created TEXT);
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,title TEXT,kind TEXT,body TEXT,revision INTEGER,updated TEXT);
        CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,artifact_id TEXT,revision INTEGER,body TEXT,reason TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT,role TEXT,text TEXT,job_id TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,conversation_id TEXT,artifact_id TEXT,status TEXT,payload TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS reading_page_subscriptions(page_id TEXT PRIMARY KEY,subscription_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_categories(id TEXT PRIMARY KEY,name TEXT UNIQUE,revision INTEGER);
        CREATE TABLE IF NOT EXISTS asset_categories_map(asset_id TEXT PRIMARY KEY,category_id TEXT);
        CREATE TABLE IF NOT EXISTS asset_origins(asset_id TEXT PRIMARY KEY,origin TEXT,reference TEXT);
        """)
        self.db.commit()
        for table in ('sources','artifacts','conversations'):
            if 'archived' not in {r['name'] for r in self.db.execute('PRAGMA table_info('+table+')')}:
                self.db.execute('ALTER TABLE '+table+' ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
        self.db.commit()
        with self.lock:
            for row in self.db.execute("SELECT id,payload FROM jobs WHERE status IN ('queued','running')").fetchall():
                p = json.loads(row['payload'])
                p['error'] = '服务已重启；任务未自动重放，请重新提交。'
                self.db.execute("UPDATE jobs SET status='interrupted',payload=?,updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now(), row['id']))
            self.db.commit()
        # Older conversations used the latest prompt as their label. Recover the
        # first successful draft's real title without another model request.
        for c in self.conversations():
            first=self.db.execute("SELECT job_id FROM messages WHERE conversation_id=? AND role='user' ORDER BY rowid LIMIT 1",(c['id'],)).fetchone()
            if first and first['job_id']:
                row=self.db.execute("SELECT payload FROM jobs WHERE id=? AND status IN ('review','approved')",(first['job_id'],)).fetchone()
                if row:
                    proposal=json.loads(row['payload']).get('proposal',{})
                    title=proposal.get('title') or proposal.get('page',{}).get('title')
                    if title:self.summarize_title(c['id'],title,first['job_id'])
        self.seed()

    def seed(self):
        if self.artifacts():
            return
        modules = [
            ('input','输入与调度','用户提出任务，系统接收输入。','排队、插入和中断应明确区分；中断不等于撤回已执行操作。','先明确目标、使用哪些材料，以及是否允许修改成果。'),
            ('context','构建本次上下文','组合当前任务、角色与规则、相关材料和必要历史。','知识库是外部资料，当前上下文是本次模型实际看到的内容。','经营分析需注入指标口径；不能把全部品牌资料无差别拼接。'),
            ('model','调用模型并判断','模型决定直接回答，还是请求工具或委派子任务。','角色、模型选择、推理强度是三个不同的设置。','根据任务评测质量、时延与成本，不能仅看模型参数量。'),
            ('tools','执行工具与子任务','执行工具，收集真实返回结果。','工具定义先进入上下文；调用时再按名称和参数执行。','读取数据、生成草稿与发布商品必须有不同权限。'),
            ('continue','结果回传与继续','工具结果回到会话，模型判断是否需要下一步。','上下文压缩帮助长任务继续；它不等于自动长期记忆。','搜索和试错细节可留在子会话，主任务保留结论与证据。'),
            ('delivery','审核与交付','核验结果，用户确认后保存可复用成果。','执行成功、内容符合、业务目标达成要分开验收。','分析有无依据、口径是否正确、行动是否可执行分别检查。'),
        ]
        body = {'modules':[{'id':i,'title':t,'summary':s,'points':[p],'commerce':c,'citations':[]} for i,t,s,p,c in modules]}
        self.db.execute("INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)", ('map-agent','Agent 执行知识地图','map',json.dumps(body,ensure_ascii=False),1,now()))
        self.db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?)",(uid('ver'),'map-agent',1,json.dumps(body,ensure_ascii=False),'MVP 结构底稿；详细历史地图在原图页保留',now()))
        self.db.commit()

    def sources(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM sources ORDER BY created DESC')]

    def source(self, sid):
        with self.lock:
            r = self.db.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
            if not r: raise ValueError('资料不存在')
            return dict(r)

    def add_source(self, title, content, url='', visibility='private'):
        title, content = str(title).strip(), str(content).strip()
        if not title or not content: raise ValueError('标题和正文不能为空')
        if len(title)>200 or len(content)>120000: raise ValueError('标题最多200字；正文最多120000字')
        if visibility not in ('private','public'): raise ValueError('无效的隐私范围')
        digest=hashlib.sha256(content.encode()).hexdigest()
        with self.lock:
            existing=self.db.execute('SELECT id FROM sources WHERE hash=?',(digest,)).fetchone()
            if existing: return {'source':self.source(existing['id']),'duplicate':True}
            sid=uid('src')
            self.db.execute('INSERT INTO sources(id,title,content,url,visibility,hash,created) VALUES(?,?,?,?,?,?,?)',(sid,title,content,url,visibility,digest,now()))
            self.db.commit()
            return {'source':self.source(sid),'duplicate':False}

    def artifacts(self):
        with self.lock:
            result=[]
            for r in self.db.execute('SELECT * FROM artifacts ORDER BY updated DESC'):
                item=dict(r);item['body']=json.loads(item['body']);result.append(item)
            return result

    def artifact(self, aid):
        items=[a for a in self.artifacts() if a['id']==aid]
        if not items: raise ValueError('成果不存在')
        return items[0]

    def conversations(self):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM conversations ORDER BY created DESC')]

    def conversation(self, cid=None):
        with self.lock:
            if cid:
                if not self.db.execute('SELECT id FROM conversations WHERE id=?',(cid,)).fetchone():raise ValueError('会话不存在')
                return cid
            cid=uid('conv');self.db.execute('INSERT INTO conversations(id,title,created) VALUES(?,?,?)',(cid,'新的知识整理',now()));self.db.commit();return cid

    def message(self,cid,role,text,job_id=''):
        with self.lock:
            first = role == 'user' and not self.db.execute('SELECT id FROM messages WHERE conversation_id=? AND role=?', (cid, 'user')).fetchone()
            self.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',(uid('msg'),cid,role,text,job_id,now()))
            if first:
                topic = re.sub(r'\s+', ' ', text).strip()
                topic = re.sub(r'^(请|帮我|我想|能不能|可以|根据|基于|对照)+', '', topic).strip()
                self.db.execute('UPDATE conversations SET title=? WHERE id=?', (topic[:48] or '新对话', cid))
            self.db.commit()

    def summarize_title(self, cid, title, job_id):
        """Only the first task sets the model title; follow-ups retain the topic."""
        title = re.sub(r'\s+', ' ', str(title or '')).strip().strip('#"')[:80]
        if not title: return
        with self.lock:
            first = self.db.execute('SELECT job_id FROM messages WHERE conversation_id=? AND role=? ORDER BY rowid LIMIT 1', (cid, 'user')).fetchone()
            if first and first['job_id'] == job_id:
                self.db.execute('UPDATE conversations SET title=? WHERE id=?', (title, cid))
                self.db.commit()

    def messages(self,cid):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid',(cid,))]

    def create_job(self,cid,aid,payload):
        with self.lock:
            if self.db.execute("SELECT id FROM jobs WHERE conversation_id=? AND status IN ('queued','running')",(cid,)).fetchone():
                raise Conflict('本会话已有任务在运行；请等待或先中断')
            jid=uid('job');self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',(jid,cid,aid,'queued',json.dumps(payload,ensure_ascii=False),now(),now()))
            self.db.commit();return self.job(jid)

    def job(self,jid):
        with self.lock:
            r=self.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not r:raise ValueError('任务不存在')
            item=dict(r);item['payload']=json.loads(item['payload']);return item

    def jobs(self,cid=None):
        with self.lock:
            sql='SELECT id FROM jobs';args=()
            if cid:sql+=' WHERE conversation_id=?';args=(cid,)
            return [self.job(r['id']) for r in self.db.execute(sql+' ORDER BY rowid DESC',args).fetchall()]

    def update_job(self,jid,status=None,**fields):
        with self.lock:
            item=self.job(jid)
            # A late model response must never resurrect an interrupted task.
            if item['status']=='interrupted':return item
            item['payload'].update(fields)
            self.db.execute('UPDATE jobs SET status=?,payload=?,updated=? WHERE id=?',(status or item['status'],json.dumps(item['payload'],ensure_ascii=False),now(),jid));self.db.commit()
            return self.job(jid)

    def validate_changes(self, changes, artifact, allowed_sources):
        if not isinstance(changes,list) or not 1<=len(changes)<=6:raise ValueError('每次需提交1至6个模块修改')
        module_ids={m['id'] for m in artifact['body']['modules']};seen=set();validated=[]
        for c in changes:
            if not isinstance(c,dict) or c.get('module_id') not in module_ids:raise ValueError('修改必须对应已有模块')
            if c['module_id'] in seen:raise ValueError('同一模块只能提交一份修改')
            seen.add(c['module_id'])
            summary=str(c.get('summary','')).strip();points=c.get('points');citations=c.get('citations')
            if not summary or len(summary)>1200:raise ValueError('模块说明不能为空或过长')
            if not isinstance(points,list) or not 1<=len(points)<=5 or any(not isinstance(p,str) or not p.strip() or len(p)>1000 for p in points):raise ValueError('需提交1至5条有效要点')
            if not isinstance(citations,list) or not 1<=len(citations)<=8:raise ValueError('每个修改必须有原文引用')
            checked=[]
            for cite in citations:
                if not isinstance(cite,dict) or cite.get('source_id') not in allowed_sources:raise ValueError('引用了未选择的来源')
                quote=str(cite.get('quote','')).strip()
                if len(quote)<8 or len(quote)>1200 or quote not in allowed_sources[cite['source_id']]['content']:raise ValueError('引用必须能在选定资料中逐字找到')
                checked.append({'source_id':cite['source_id'],'quote':quote})
            commerce=str(c.get('commerce','')).strip()
            if len(commerce)>1200:raise ValueError('行业启发过长')
            validated.append({'module_id':c['module_id'],'summary':summary,'points':[p.strip() for p in points],'commerce':commerce,'citations':checked})
        return validated

    def approve(self,jid,edits=None):
        # The revision guard and write live in one transaction, not a UI-only check.
        with self.lock:
            job=self.job(jid)
            if job['status']=='approved':return self.artifact(job['payload'].get('published_id',job['artifact_id']))
            if job['status']!='review':raise Conflict('任务没有可审核的草稿')
            # User edits are drafts until this explicit asset-save operation succeeds.
            draft=job['payload'].get('user_draft')
            if draft:
                p=job['payload'];kind=p.get('kind')
                if kind in ('wiki','document') or p.get('chat_output'):
                    key='document' if kind=='document' else 'page'
                    p['proposal'][key].update(title=draft['title'],content=draft['content'])
                elif kind in ('experience','tailor'):
                    p['proposal'].update(title=draft['title'])
                    edits={**(edits or {}),('general' if kind=='experience' else 'tailored'):draft['content']}
            from library import validate_destination
            validate_destination(self, edits or {})
            for selected in job['payload'].get('board_snapshot',[]):
                current=self.artifact(selected['id'])
                if current['archived'] or current['revision']!=selected['revision']:
                    raise Conflict('引用的画板已变化，请基于最新版本重新生成；草稿仍保留')
            for ref in job['payload'].get('document_snapshot',[]):
                current=self.artifact(ref['id'])
                if current['archived'] or current['revision']!=ref['revision']:raise Conflict('引用文稿已变化，请重新生成；草稿仍保留')
            if job['payload'].get('output_board'):
                p=job['payload'];allowed={sid:self.source(sid) for sid in p['source_ids']}
                if any(s['archived'] for s in allowed.values()):raise Conflict('来源已归档，请重新生成')
                page=self.validate_wiki(p['proposal']['page'],allowed,require_citations=not p.get('chat_output') or bool(allowed))
                import boards
                # Save board and mark its originating proposal in the same transaction.
                result=boards.save(self,{'title':page['title'],'scene':p.get('board_draft_scene') or boards.page_scene(page),'category_id':(edits or {}).get('category_id','')},job_id=jid)
                return result
            if job['payload'].get('kind')=='document':
                from library import approve_document
                return approve_document(self,job,edits or {})
            if job['payload'].get('kind') in ('experience','tailor'):
                from career import approve
                return approve(self,job,edits or {})
            if job['payload'].get('kind')=='wiki' or job['payload'].get('chat_output'):return self.approve_wiki(job, edits or {})
            p=job['payload'];artifact=self.artifact(job['artifact_id'])
            if artifact['revision']!=p['base_revision']:raise Conflict('成果已更新；请基于最新版本重新生成')
            sources={sid:self.source(sid) for sid in p['source_ids']}
            if any(s['archived'] for s in sources.values()):raise Conflict('来源已归档，请重新选择资料')
            changes=self.validate_changes(p['proposal']['changes'],artifact,sources)
            body=artifact['body']
            for c in changes:
                m=next(m for m in body['modules'] if m['id']==c['module_id'])
                for key in ('summary','points','citations'):m[key]=c[key]
                if c['commerce']:m['commerce']=c['commerce']
            revision=artifact['revision']+1;encoded=json.dumps(body,ensure_ascii=False)
            try:
                self.db.execute('UPDATE artifacts SET body=?,revision=?,updated=? WHERE id=? AND revision=?',(encoded,revision,now(),artifact['id'],artifact['revision']))
                self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),artifact['id'],revision,encoded,p['prompt'][:200],now()))
                p['approved_revision']=revision
                self.db.execute("UPDATE jobs SET status='approved',payload=?,updated=? WHERE id=?",(json.dumps(p,ensure_ascii=False),now(),jid))
                self.db.commit()
            except Exception:
                self.db.rollback();raise
            return self.artifact(artifact['id'])

    def versions(self,aid):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT id,revision,reason,created FROM versions WHERE artifact_id=? ORDER BY revision DESC',(aid,))]

    def restore(self,aid,version_id,revision):
        with self.lock:
            a=self.artifact(aid)
            if a['revision']!=revision:raise Conflict('成果版本已变化，请刷新后重试')
            v=self.db.execute('SELECT * FROM versions WHERE id=? AND artifact_id=?',(version_id,aid)).fetchone()
            if not v:raise ValueError('版本不存在')
            new=a['revision']+1
            try:
                title=json.loads(v['body']).get('title',a['title'])
                self.db.execute('UPDATE artifacts SET title=?,body=?,revision=?,updated=? WHERE id=?',(title,v['body'],new,now(),aid))
                self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),aid,new,v['body'],'恢复版本 '+str(v['revision']),now()))
                self.db.commit()
            except Exception:self.db.rollback();raise
            return self.artifact(aid)

    def archive(self, kind, item_id, archived=True):
        table={'source':'sources','conversation':'conversations','artifact':'artifacts'}.get(kind)
        if not table:raise ValueError('无效归档类型')
        with self.lock:
            if kind=='conversation' and any(j['status'] in ('queued','running') for j in self.jobs(item_id)):raise Conflict('请先中断任务再归档')
            cursor=self.db.execute('UPDATE '+table+' SET archived=? WHERE id=?',(int(archived),item_id))
            if not cursor.rowcount:raise ValueError('内容不存在')
            self.db.commit()

    def validate_wiki(self, page, allowed_sources, require_citations=True):
        if not isinstance(page,dict):raise ValueError('Wiki 草稿必须是对象')
        title=str(page.get('title','')).strip();summary=str(page.get('summary','')).strip();content=str(page.get('content','')).strip()
        if not 1<=len(title)<=100 or not 1<=len(summary)<=400 or not 1<=len(content)<=18000:raise ValueError('请提供有效标题、摘要和正文')
        tags=page.get('tags',[])
        if not isinstance(tags,list) or len(tags)>8 or any(not isinstance(t,str) or not 1<=len(t)<=30 for t in tags):raise ValueError('标签最多8个，每个最多30字')
        citations=page.get('citations',[])
        if not isinstance(citations,list):raise ValueError('citations 必须是引用列表')
        if len(citations)>12:raise ValueError('citations 最多12条，请只保留支持核心结论的引用')
        if require_citations and not citations:raise ValueError('AI 知识页需要至少一条原文引用')
        checked=[]
        for cite in citations:
            if not isinstance(cite,dict) or cite.get('source_id') not in allowed_sources:raise ValueError('引用了未选择或已归档的来源')
            quote=str(cite.get('quote','')).strip()
            if not 8<=len(quote)<=1200 or quote not in allowed_sources[cite['source_id']]['content']:raise ValueError('Wiki 引用必须逐字匹配原文')
            checked.append({'source_id':cite['source_id'],'quote':quote})
        ids={a['id'] for a in self.artifacts() if a['kind']=='wiki' and not a['archived']}
        provided=page.get('links',[])
        if not isinstance(provided,list) or any(not isinstance(v,str) for v in provided):raise ValueError('关联页面必须是列表')
        links=list(dict.fromkeys(provided+re.findall(r'\[\[(wiki_[a-z0-9]+)\]\]',content)))
        if len(links)>15 or any(link not in ids for link in links):raise ValueError('关联页面必须是已存在的 Wiki 页面')
        diagram=page.get('diagram',[])
        if not isinstance(diagram,list) or len(diagram)>10 or any(not isinstance(n,str) or not 1<=len(n.strip())<=60 for n in diagram):
            raise ValueError('流程图最多10个步骤，每个步骤1至60字')
        body={'title':title,'summary':summary,'content':content,'tags':tags,'links':links,'citations':checked,'diagram':[n.strip() for n in diagram]}
        if page.get('graph') is not None:
            from boards import validate_graph
            body['graph']=validate_graph(page['graph'])
        return body

    def save_wiki(self, page, target=None, expected_revision=0, reason='手动确认知识页', destination=None, origin=None, reference=''):
        with self.lock:
            allowed={s['id']:s for s in self.sources() if not s['archived']}
            body=self.validate_wiki(page,allowed,require_citations=False)
            if target and 'diagram' not in page:body['diagram']=self.artifact(target)['body'].get('diagram',[])
            if target and 'graph' not in page and self.artifact(target)['body'].get('graph'):
                body['graph']=self.artifact(target)['body']['graph']
            return self._write_wiki(body,target,expected_revision,reason,destination,origin,reference)

    def _write_wiki(self, body, target, expected, reason, destination=None, origin=None, reference=''):
        existing=self.artifact(target) if target else None
        if existing and (existing['kind']!='wiki' or existing['archived'] or existing['revision']!=expected):raise Conflict('知识页已经变更，请刷新后再保存')
        if not target and expected!=0:raise Conflict('新页面版本必须为0')
        aid=target or uid('wiki');revision=expected+1;encoded=json.dumps(body,ensure_ascii=False)
        try:
            if existing:self.db.execute('UPDATE artifacts SET title=?,body=?,revision=?,updated=? WHERE id=?',(body['title'],encoded,revision,now(),aid))
            else:self.db.execute('INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)',(aid,body['title'],'wiki',encoded,revision,now()))
            self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),aid,revision,encoded,reason[:200],now()))
            from library import record_destination
            record_destination(self, aid, destination or {}, origin, reference)
            self.db.commit()
        except Exception:self.db.rollback();raise
        return self.artifact(aid)

    def approve_wiki(self, job, edits=None):
        p=job['payload'];allowed={sid:self.source(sid) for sid in p['source_ids']}
        if any(s['archived'] for s in allowed.values()):raise Conflict('来源已经归档，请重新选择')
        body=self.validate_wiki(p['proposal']['page'],allowed,require_citations=not p.get('chat_output') or bool(allowed))
        # _write_wiki and job approval share this transaction.
        target=p.get('wiki_target_id');expected=p.get('wiki_base_revision',0)
        existing=self.artifact(target) if target else None
        if existing and (existing['kind']!='wiki' or existing['revision']!=expected or existing['archived']):raise Conflict('知识页已经变更，请重新生成')
        if existing:
            body['diagram']=existing['body'].get('diagram',[])
            if not body.get('graph') and existing['body'].get('graph'):body['graph']=existing['body']['graph']
        aid=target or uid('wiki');revision=expected+1;encoded=json.dumps(body,ensure_ascii=False)
        try:
            if existing:self.db.execute('UPDATE artifacts SET title=?,body=?,revision=?,updated=? WHERE id=?',(body['title'],encoded,revision,now(),aid))
            else:self.db.execute('INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)',(aid,body['title'],'wiki',encoded,revision,now()))
            self.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),aid,revision,encoded,p['prompt'][:200],now()))
            p['approved_revision']=revision;p['published_id']=aid
            from library import record_destination
            record_destination(self, aid, edits or {}, 'ai', job['id'])
            if p.get('weekly_run_id'):
                self.db.execute('INSERT OR REPLACE INTO reading_page_subscriptions VALUES(?,?)', (aid,p.get('subscription_id','sub_legacy')))
            self.db.execute("UPDATE jobs SET status='approved',payload=?,updated=? WHERE id=?",(json.dumps(p,ensure_ascii=False),now(),job['id']))
            self.db.commit()
        except Exception:self.db.rollback();raise
        return self.artifact(aid)
