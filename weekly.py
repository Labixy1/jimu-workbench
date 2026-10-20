"""Local, review-only weekly collection with durable claims and bounded scope."""
import json
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from domain import Conflict, now, uid
from models import deepseek_web_request, model_key

TZ = ZoneInfo('Asia/Shanghai')


def next_time(config, after=None):
    local = (after or datetime.now(timezone.utc)).astimezone(TZ)
    hour, minute = map(int, config['time'].split(':'))
    date = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    daily = config.get('frequency', 'weekly') == 'daily'
    if not daily: date += timedelta(days=(config['weekday'] - local.weekday()) % 7)
    if date <= local: date += timedelta(days=1 if daily else 7)
    return date.astimezone(timezone.utc).isoformat(timespec='seconds')


def same_site(url, base):
    parsed, site = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
    return (parsed.scheme in ('https', 'http') and not parsed.username and not parsed.password
            and parsed.hostname == site.hostname
            and (site.path in ('', '/') or parsed.path == site.path.rstrip('/')
                 or parsed.path.startswith(site.path.rstrip('/') + '/')))


class Weekly:
    def __init__(self, app, validator):
        self.app, self.store, self.validator = app, app.store, validator
        self.manual_only = True
        with self.store.lock:
            migrated = self.store.db.execute("SELECT name FROM sqlite_master WHERE name='reading_subscriptions'").fetchone()
            self.store.db.executescript('''
            CREATE TABLE IF NOT EXISTS weekly_config(id INTEGER PRIMARY KEY,body TEXT);
            CREATE TABLE IF NOT EXISTS weekly_runs(id TEXT PRIMARY KEY,slot TEXT UNIQUE,status TEXT,body TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS reading_subscriptions(id TEXT PRIMARY KEY,body TEXT,revision INTEGER NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
            ''')
            if not migrated:
                legacy = self.store.db.execute('SELECT body FROM weekly_config WHERE id=1').fetchone()
                if legacy:
                    config = json.loads(legacy['body'])
                    config.update(id='sub_legacy', revision=1)
                    config.setdefault('frequency', 'weekly')
                    self.store.db.execute('INSERT INTO reading_subscriptions VALUES(?,?,1,0)', ('sub_legacy', json.dumps(config, ensure_ascii=False)))
            if 'subscription_id' not in {r['name'] for r in self.store.db.execute('PRAGMA table_info(weekly_runs)')}:
                self.store.db.execute("ALTER TABLE weekly_runs ADD COLUMN subscription_id TEXT NOT NULL DEFAULT 'sub_legacy'")
            self.store.db.execute("UPDATE weekly_runs SET slot='sub_legacy:'||slot WHERE subscription_id='sub_legacy' AND slot NOT LIKE 'sub_legacy:%'")
            for job in self.store.jobs():
                payload = job['payload']
                if payload.get('weekly_run_id') and payload.get('published_id'):
                    self.store.db.execute('INSERT OR IGNORE INTO reading_page_subscriptions VALUES(?,?)',
                        (payload['published_id'], payload.get('subscription_id', 'sub_legacy')))
            self.store.db.execute("UPDATE weekly_runs SET status='failed' WHERE status='collecting'")
            for row in self.store.db.execute('SELECT id,body,revision FROM reading_subscriptions').fetchall():
                config=json.loads(row['body'])
                if config.get('enabled') or config.get('next_run'):
                    config.update(enabled=False,allow_remote=False,next_run=None,revision=row['revision']+1)
                    self.store.db.execute('UPDATE reading_subscriptions SET body=?,revision=? WHERE id=?',
                        (json.dumps(config,ensure_ascii=False),config['revision'],row['id']))
            self.store.db.commit()
        self.stop = threading.Event()

    def subscriptions(self):
        with self.store.lock:
            rows = self.store.db.execute('SELECT body FROM reading_subscriptions WHERE archived=0 ORDER BY rowid').fetchall()
            return [json.loads(row['body']) for row in rows]

    def config(self, subscription_id=None):
        with self.store.lock:
            if subscription_id:
                row = self.store.db.execute('SELECT body FROM reading_subscriptions WHERE id=? AND archived=0', (subscription_id,)).fetchone()
                if not row: raise ValueError('订阅不存在或已移除')
                return json.loads(row['body'])
            items = self.subscriptions()
            return items[0] if items else {'title': '', 'urls': [], 'query': '', 'frequency': 'weekly',
                'weekday': 4, 'time': '19:00', 'enabled': False, 'allow_remote': False, 'next_run': None}

    def save(self, data):
        title, query = str(data.get('title', '')).strip(), str(data.get('query', '')).strip()
        urls = data.get('urls', [])
        weekday, clock = data.get('weekday',4), data.get('time', '19:00')
        frequency = data.get('frequency', 'weekly')
        if frequency not in ('daily', 'weekly'): raise ValueError('请选择每天或每周更新')
        if not 1 <= len(title) <= 60 or len(query) > 80: raise ValueError('栏目标题1至60字，关键词最多80字')
        if not isinstance(urls, list) or len(urls) > 8: raise ValueError('每个栏目最多8个网站或文章链接')
        import re
        if type(weekday) is not int or not 0 <= weekday <= 6 or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', clock):
            raise ValueError('请选择有效的星期和时间')
        checked = []
        for url in urls:
            if not isinstance(url, str) or len(url) > 2000: raise ValueError('无效网站地址')
            self.validator(url)
            if urllib.parse.urlsplit(url).query or urllib.parse.urlsplit(url).fragment:
                raise ValueError('周刊链接不能含查询参数或访问令牌，请使用公开页面地址')
            if url not in checked: checked.append(url)
        enabled = data.get('enabled') is True
        if enabled and self.manual_only: raise ValueError('当前版本只支持手动更新，不启用定时任务')
        consent = data.get('allow_remote') is True
        if enabled and (not checked or not consent): raise ValueError('启用前请填写网站并确认周期性 API 调用')
        if enabled and (self.app.settings.get('mode') != 'deepseek' or not model_key(self.app.credential_root)):
            raise ValueError('启用前请先连接 DeepSeek')
        config = {'title': title, 'query': query, 'urls': checked, 'weekday': weekday, 'time': clock, 'frequency': frequency,
                  'enabled': enabled, 'allow_remote': consent, 'updated': now()}
        titles=data.get('source_titles',{})
        if not isinstance(titles,dict) or any(not isinstance(v,str) or len(v)>60 for v in titles.values()):raise ValueError('来源标题无效')
        config['source_titles']={u:titles.get(u,'') for u in checked}
        config['next_run'] = next_time(config) if enabled else None
        with self.store.lock:
            sid = data.get('id')
            if sid is not None and (not isinstance(sid, str) or not sid): raise ValueError('无效订阅ID')
            if not sid and data.get('new') is not True:
                sid = self.config().get('id')
            existing = self.config(sid) if sid else None
            expected = data.get('revision', existing['revision'] if existing and not data.get('id') else None)
            if existing and (type(expected) is not int or expected != existing['revision']):
                raise Conflict('订阅已经修改，请重新打开设置')
            if not existing and len(self.subscriptions()) >= 3: raise ValueError('最多创建3个订阅，请先移除一个订阅')
            config.update(id=sid or uid('sub'), revision=existing['revision'] + 1 if existing else 1)
            if existing:
                self.store.db.execute('UPDATE reading_subscriptions SET body=?,revision=? WHERE id=?',
                    (json.dumps(config, ensure_ascii=False), config['revision'], config['id']))
            else:
                self.store.db.execute('INSERT INTO reading_subscriptions(id,body,revision,archived) VALUES(?,?,?,0)',
                    (config['id'], json.dumps(config, ensure_ascii=False), config['revision']))
            self.store.db.commit()
        return config

    def toggle(self, sid, revision, enabled, allow_remote=False):
        with self.store.lock:
            if not isinstance(sid, str) or not sid: raise ValueError('请选择订阅')
            config = self.config(sid)
            if type(revision) is not int or config['revision'] != revision: raise Conflict('订阅已经修改，请刷新后重试')
            if type(enabled) is not bool: raise ValueError('请选择启用或暂停')
            if enabled:
                return self.save({**config, 'enabled': True, 'allow_remote': allow_remote})
            config.update(enabled=False, allow_remote=False, next_run=None, revision=revision+1, updated=now())
            self.store.db.execute('UPDATE reading_subscriptions SET body=?,revision=? WHERE id=?', (json.dumps(config, ensure_ascii=False), config['revision'], sid))
            self.store.db.commit()
            return config

    def remove(self, sid, revision):
        with self.store.lock:
            if not isinstance(sid, str) or not sid: raise ValueError('请选择订阅')
            config = self.config(sid)
            if type(revision) is not int or config['revision'] != revision: raise Conflict('订阅已经修改，请刷新后重试')
            if any(r['subscription_id'] == sid and r['status'] in ('collecting', 'queued', 'running') for r in self.runs()):
                raise Conflict('这个订阅正在更新，请完成后再移除；可以先暂停定时')
            self.store.db.execute('UPDATE reading_subscriptions SET archived=1 WHERE id=?', (sid,))
            self.store.db.commit()
            return {'id': sid, 'removed': True}

    def page_subscriptions(self):
        with self.store.lock:
            return {r['page_id']:r['subscription_id'] for r in self.store.db.execute('SELECT * FROM reading_page_subscriptions')}

    def runs(self):
        with self.store.lock:
            rows = self.store.db.execute('SELECT * FROM weekly_runs ORDER BY rowid DESC LIMIT 90').fetchall()
        result = []
        for row in rows:
            run = {**dict(row), **json.loads(row['body'])}; run.pop('body')
            if run.get('job_id'):
                job = self.store.job(run['job_id']); run['status'] = job['status']
                run['published_id'] = job['payload'].get('published_id')
                run['error'] = job['payload'].get('error')
            elif run['status'] == 'failed' and not run.get('error'):
                run['error'] = '服务重启，采集已停止；可手动重新运行。'
            result.append(run)
        return result

    def update(self, rid, status, **fields):
        with self.store.lock:
            row = self.store.db.execute('SELECT body FROM weekly_runs WHERE id=?', (rid,)).fetchone()
            body = json.loads(row['body']); body.update(fields)
            self.store.db.execute('UPDATE weekly_runs SET status=?,body=? WHERE id=?', (status, json.dumps(body, ensure_ascii=False), rid))
            self.store.db.commit()

    def claim(self, config, slot):
        sid = config.get('id', 'sub_legacy')
        slot = sid + ':' + slot
        with self.store.lock:
            if config.get('id'):
                self.config(sid)  # A removed subscription cannot start from a stale dialog.
            if any(r['status'] in ('collecting', 'queued', 'running') for r in self.runs()):
                raise Conflict('已有订阅正在采集或生成，请等待完成后再更新')
            existing = self.store.db.execute('SELECT id FROM weekly_runs WHERE slot=?', (slot,)).fetchone()
            if existing: return None
            rid = uid('issue')
            self.store.db.execute('INSERT INTO weekly_runs(id,slot,status,body,created,subscription_id) VALUES(?,?,?,?,?,?)',
                (rid, slot, 'collecting', json.dumps({'config': config, 'warnings': []}, ensure_ascii=False), now(), sid))
            self.store.db.commit()
            return rid

    def manual(self, allow_remote, subscription_id=None):
        config = self.config(subscription_id)
        if not config['urls'] or allow_remote is not True: raise ValueError('请先配置网站并确认本次 API 调用')
        if self.app.settings.get('mode') != 'deepseek' or not model_key(self.app.credential_root): raise ValueError('请先连接 DeepSeek')
        from task_skills import task_method
        config={**config,'skill_snapshot':task_method('weekly',self.store)}
        rid = self.claim(config, uid('manual'))
        threading.Thread(target=self.collect, args=(rid, config), daemon=True).start()
        return {'id': rid, 'subscription_id': config.get('id', 'sub_legacy')}

    def tick(self, instant=None):
        if self.manual_only: return
        instant = instant or datetime.now(timezone.utc)
        with self.store.lock:
            due = sorted((c for c in self.subscriptions() if c['enabled'] and c.get('next_run')
                          and datetime.fromisoformat(c['next_run']) <= instant), key=lambda c:c['next_run'])
            for config in due:
                try: rid = self.claim(config, 'scheduled:' + config['next_run'])
                except Conflict: return  # Leave other due subscriptions pending, without losing their slot.
                config['next_run'] = next_time(config, instant)
                self.store.db.execute('UPDATE reading_subscriptions SET body=? WHERE id=?', (json.dumps(config, ensure_ascii=False), config['id']))
                self.store.db.commit()
                if rid:
                    threading.Thread(target=self.collect, args=(rid, config), daemon=True).start()
                    return

    def start(self):
        if self.manual_only: return
        def loop():
            while not self.stop.wait(30):
                try: self.tick()
                except Exception: pass  # A busy collector is retried, never duplicated.
        threading.Thread(target=loop, daemon=True).start()

    def collect(self, rid, config):
        warnings, sources, selected_urls, snapshots, read_count = [], [], [], {}, 0
        try:
            if self.app.settings.get('mode') != 'deepseek' or not model_key(self.app.credential_root):
                raise ValueError('DeepSeek 未连接，未执行采集')
            for base in config['urls']:
                try:
                    self.validator(base)
                    if config['query']:
                        host = urllib.parse.urlsplit(base).hostname
                        result = deepseek_web_request(self.app.credential_root, 'search', {'query': f"site:{host} {config['query']}"[:128], 'count': 5, 'need_content': False})
                        urls = [r['url'] for r in result.get('results', []) if same_site(r.get('url', ''), base)][:2]
                        if not urls: warnings.append(base + '：没有范围内的搜索结果')
                    else: urls = [base]
                    for url in urls:
                        if url not in selected_urls: selected_urls.append(url)
                except Exception as e: warnings.append(base + '：' + str(e)[:150])
            for url in selected_urls[:6]:
                try:
                    self.validator(url)
                    page = deepseek_web_request(self.app.credential_root, 'fetch', {'url': url})
                    content = page.get('content')
                    if not isinstance(content, str) or not 50 <= len(content.strip()) <= 120000:
                        raise ValueError('正文为空、过短或超过长度限制')
                    read_count += 1
                    # Bound each weekly source explicitly rather than silently sending an entire site.
                    excerpt = content[:5000]
                    if len(content) > 5000: warnings.append(url + '：仅选取前5000字，非全文')
                    imported = self.store.add_source(str(page.get('title') or url)[:200], content, url, 'public')
                    if imported['duplicate']:
                        # Failed drafts can reuse evidence; accepted/pending issues must not duplicate it.
                        used = any(imported['source']['id'] in j['payload'].get('source_ids', [])
                                   and j['payload'].get('weekly_run_id') and j['status'] in ('review', 'approved')
                                   and j['payload'].get('subscription_id', 'sub_legacy') == config.get('id', 'sub_legacy')
                                   for j in self.store.jobs())
                        if used: continue
                        if imported['source']['archived']: continue
                    if imported['source']['id'] not in snapshots:
                        sources.append(imported['source'])
                        snapshots[imported['source']['id']]={**imported['source'],'content':excerpt}
                except Exception as e: warnings.append(url + '：' + str(e)[:150])
            if not sources:
                failed = read_count == 0 and bool(warnings)
                self.update(rid, 'failed' if failed else 'no_updates', warnings=warnings,
                            error='采集未完成，请查看采集说明或调整网站。' if failed else '没有读取到新的正文；相同内容不重复生成周刊。')
                return
            self.enqueue(rid, config, sources, snapshots, warnings)
        except Exception as e:
            self.update(rid, 'failed', error=str(e)[:400], warnings=warnings)

    def enqueue(self, rid, config, sources, snapshots, warnings):
        cid = self.store.conversation(); artifact = self.store.artifact('map-agent')
        date = datetime.now(TZ).date().isoformat()
        edition = '阅读简报' if config.get('frequency') == 'daily' else '阅读周刊'
        prompt = f"整理栏目「{config['title']}」的 {date} {edition}草稿，标题含日期。按照阅读周报技能中的结构与方法执行。只依据本次采集正文，明确采集日期不等于文章发布日期。采集限制：" + '；'.join(warnings)[:1500]
        from task_skills import task_method
        from context import check_context
        method=config.get('skill_snapshot') or task_method('weekly',self.store)
        context_meta=check_context(prompt,list(snapshots.values()),[],{'instructions':''},[],method=method)
        job = self.store.create_job(cid, 'map-agent', {'prompt': prompt, 'kind': 'wiki', 'source_ids': [s['id'] for s in sources],
            'base_revision': artifact['revision'], 'artifact_snapshot': artifact, 'stages': [], 'weekly_run_id': rid,'subscription_id':config.get('id','sub_legacy'),'weekly_column':config['title'],'source_snapshot':snapshots,
            'preferences_snapshot': {'instructions': ''}, 'history_snapshot': [], 'wiki_snapshot': [],
            'wiki_target_id': None, 'wiki_base_revision': 0, 'execution_settings': dict(self.app.settings),
            'task_method':method,'context_meta':{**context_meta,'history':{'messages_included':0,'messages_omitted':0,'messages_shortened':0}}})
        self.store.message(cid, 'user', prompt, job['id'])
        self.update(rid, 'queued', job_id=job['id'], conversation_id=cid, warnings=warnings, source_ids=[s['id'] for s in sources])
        self.app.runner.submit(job)
