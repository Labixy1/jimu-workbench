"""Bounded public-feed collection; AI publication remains a separate approval."""
import hashlib
import json
import re
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from domain import Conflict, now
from article_reader import ArticleHTML, blocked_page, fetch_article, fetch_image, cover_url, content_blocks

DEFAULT_FEEDS = ['https://openai.com/news/rss.xml', 'https://github.com/openai/codex/releases.atom',
                 'https://github.com/anomalyco/opencode/releases.atom']
ATOM = '{http://www.w3.org/2005/Atom}'


def plain(text):
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text or '', flags=re.S|re.I)
    text = re.sub(r'</(?:p|div|li|h[1-6])>', '\n', text, flags=re.I)
    return unescape(re.sub(r'<[^>]+>', '', text)).strip()


def useful_entry(item):
    """Release labels without a changelog are not useful reading material."""
    text=item.get('excerpt','').strip()
    if not text or text=='订阅源未提供摘要，请阅读原文。':return False
    if re.fullmatch(r'(?:release[: ]+)?v?\d[\w.\-]*',text,re.I):return False
    if text.lower().startswith('co-authored-by:') and len(text.splitlines())<=2:return False
    return True


def source_body(source):
    """Remove only Jimu's known source header when comparing immutable captures."""
    text=source['content']
    prefix=f"标题：{source['title']}\n来源：{source['url']}"
    if text.startswith(prefix+'\n\n'):
        return text[len(prefix)+2:]
    if text.startswith(prefix+'\n发布日期：'):
        _,separator,body=text[len(prefix):].partition('\n\n')
        for label in ('已读取正文：\n','订阅源摘要（非全文）：\n'):
            if separator and body.startswith(label):return body[len(label):]
    return text


def parse_feed(raw, feed_url, instant=None, limit=8):
    if len(raw) > 1500000: raise ValueError('订阅源超过1.5MB')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('不支持带实体声明的订阅源')
    root = ET.fromstring(raw); instant = instant or datetime.now(timezone.utc)
    entries = root.findall('./channel/item') or root.findall(ATOM+'entry')
    if not entries: raise ValueError('没有读取到RSS/Atom条目，请填订阅源地址，普通网页可用联网采集')
    result = []
    for entry in entries[:200]:
        title = plain(entry.findtext('title') or entry.findtext(ATOM+'title'))[:200]
        link = entry.findtext('link')
        if not link:
            node = next((n for n in entry.findall(ATOM+'link') if n.get('rel', 'alternate')=='alternate'), None)
            link = node.get('href') if node is not None else ''
        url = urllib.parse.urljoin(feed_url, link or '')
        parsed = urllib.parse.urlsplit(url)
        if not title or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password: continue
        date = entry.findtext('pubDate') or entry.findtext(ATOM+'published') or entry.findtext(ATOM+'updated')
        try:
            published = parsedate_to_datetime(date) if ',' in (date or '') else datetime.fromisoformat(date.replace('Z','+00:00'))
            if published.tzinfo is None: published=published.replace(tzinfo=timezone.utc)
            if published > instant: continue
            date = published.isoformat()
        except (TypeError, ValueError, AttributeError): date = None
        html = entry.findtext('description') or entry.findtext(ATOM+'content') or entry.findtext(ATOM+'summary') or ''
        text = plain(html)[:6000]
        media = entry.find('{http://search.yahoo.com/mrss/}content')
        if media is None: media = entry.find('{http://search.yahoo.com/mrss/}thumbnail')
        image = media.get('url', '') if media is not None else ''
        if not image:
            enclosure = entry.find('enclosure')
            if enclosure is not None and enclosure.get('type', '').startswith('image/'):
                image = enclosure.get('url', '')
        image=cover_url(unescape(image),url)
        if not image:
            image=next((candidate for match in re.finditer(r'<img\b[^>]+(?:src|data-src)=["\']([^"\']+)', html, re.I)
                        if (candidate:=cover_url(unescape(match.group(1)),url))), '')
        item={'title':title,'url':url,'published_at':date,'excerpt':text or '订阅源未提供摘要，请阅读原文。',
              'feed_url':feed_url, 'cover_url':image, 'content_status':'summary', 'collection_method':'rss'}
        if blocked_page(title, text):continue
        if useful_entry(item):result.append(item)
    result.sort(key=lambda n:n['published_at'] or '', reverse=True)
    return result[:max(1,min(limit,120))]


def fetch_feed(url, validator, limit=8, discover=True):
    validator(url)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validator(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener = urllib.request.build_opener(Redirect())
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'JimuPersonalLearning/1.0','Accept':'application/rss+xml, application/atom+xml, application/xml, text/html'}),timeout=20) as response:
        raw=response.read(1500001)
        mime=response.headers.get_content_type()
        charset=response.headers.get_content_charset() or 'utf-8'
        final_url=response.geturl()
    if len(raw)>1500000:raise ValueError('来源超过1.5MB')
    if mime in ('text/html','application/xhtml+xml'):
        parser=ArticleHTML(final_url);parser.feed(raw.decode(charset,errors='replace'))
        if blocked_page(''.join(parser.title),plain(raw.decode(charset,errors='replace'))[:900]):
            raise ValueError('来源需要登录或验证，请使用网页采集')
        if discover and parser.feed_urls:
            feed=next((f for f in parser.feed_urls if f and f!=url),None)
            if feed:return fetch_feed(feed,validator,limit,False)
        article=parser.result()
        if not article.get('title'):raise ValueError('页面未提供文章标题，请选择具体文章或订阅源')
        return [{**article,'url':final_url,'feed_url':url}]
    return parse_feed(raw,url,limit=limit)


class News:
    def __init__(self, app, validator):
        self.app=app; self.store=app.store; self.validator=validator; self.collect_lock=threading.RLock()
        self.image_lock=threading.Lock()
        with self.store.lock:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS reading_news(id TEXT PRIMARY KEY,url TEXT UNIQUE,body TEXT,source_id TEXT,fetched_at TEXT)')
            self.store.db.commit()

    def items(self):
        with self.store.lock:
            return [{**json.loads(r['body']),'id':r['id'],'source_id':r['source_id'],'fetched_at':r['fetched_at']} for r in self.store.db.execute('SELECT * FROM reading_news ORDER BY json_extract(body,\'$.published_at\') DESC LIMIT 240')]

    def item(self, ident):
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM reading_news WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('文章不存在')
            return {**json.loads(row['body']), 'id':row['id'], 'source_id':row['source_id'], 'fetched_at':row['fetched_at']}

    def store_item(self, item, config=None):
        """Keep cited source snapshots immutable; previews may be enriched independently."""
        import library
        item=dict(item);config=config or {}
        if blocked_page(item.get('title',''),item.get('content') or item.get('excerpt','')):
            raise ValueError('登录、验证或拦截页面不能保存为文章')
        item.setdefault('subscription_id',config.get('id',''))
        item.setdefault('column',config.get('title') or '学习阅读')
        item.setdefault('feed_url',item['url'])
        item.setdefault('content_status','summary')
        def source_text(value):
            content=(value.get('content') or value.get('excerpt','')).strip()
            label='已读取正文' if value['content_status']!='summary' else '订阅源摘要（非全文）'
            return f"标题：{value['title']}\n来源：{value['url']}\n发布日期：{value.get('published_at') or '未提供'}\n\n{label}：\n{content}"
        with self.store.lock:
            old=self.store.db.execute('SELECT * FROM reading_news WHERE url=?',(item['url'],)).fetchone()
            if old:
                previous=json.loads(old['body'])
                source_id=old['source_id']
                incoming_content=item.get('content')
                item={**previous,**item}
                for key in ('published_at','published_label','author','author_url','source_name'):
                    if previous.get(key) and not item.get(key):item[key]=previous[key]
                if previous.get('content') and not incoming_content:
                    item['content']=previous['content'];item['content_status']=previous.get('content_status','article')
                    item['collection_method']=previous.get('collection_method','public_html')
                if previous.get('cover_url') and not item.get('cover_url'):item['cover_url']=previous['cover_url']
                ident=old['id']
                content=(item.get('content') or item.get('excerpt','')).strip()
                original=self.store.source(source_id)
                if config.get('capture_snapshot') and (content!=source_body(original) or item['title']!=original['title']):
                    source_id=self.store.add_source(item['title'],source_text(item),item['url'],config.get('visibility','private'))['source']['id']
                    library.record_destination(self.store,source_id,config)
            else:
                source_id=self.store.add_source(item['title'],source_text(item),item['url'],config.get('visibility','public'))['source']['id']
                destination=config if 'category_id' in config else ({'category_id':'learning'} if any(c['id']=='learning' for c in library.categories(self.store)) else {})
                library.record_destination(self.store,source_id,destination)
                ident='news_'+hashlib.sha256(item['url'].encode()).hexdigest()[:16]
            blocks=content_blocks(item.get('content_blocks'),item.get('content',''),item['url'])
            if blocks is None:item.pop('content_blocks',None)
            else:item['content_blocks']=blocks
            self.store.db.execute('INSERT OR REPLACE INTO reading_news VALUES(?,?,?,?,?)',
                (ident,item['url'],json.dumps(item,ensure_ascii=False),source_id,now()))
            self.store.db.commit()
        return self.item(ident),not bool(old)

    def reference(self, data):
        """Reference the displayed article, not a stale RSS-only source snapshot."""
        import library
        with self.store.lock:
            item=self.item(data.get('id'))
            original=library.asset(self.store,item['source_id'])
            content=(item.get('content') or item.get('excerpt','')).strip()
            if not content or (content==source_body(original) and item['title']==original['title']):
                return {'source_id':original['id'],'updated':False}
            mapping=self.store.db.execute('SELECT category_id FROM asset_categories_map WHERE asset_id=?',
                                          (original['id'],)).fetchone()
            saved,_=self.store_item(item,{'capture_snapshot':True,'visibility':original['visibility'],
                                         'category_id':mapping['category_id'] if mapping else ''})
            ident=saved['source_id']
            self.store.db.execute('UPDATE OR IGNORE reading_favorites SET asset_id=? WHERE asset_id=?',
                                  (ident,original['id']))
            self.store.db.commit()
            return {'source_id':ident,'updated':True}

    def update_item(self, ident, fields):
        with self.store.lock:
            item=self.item(ident)
            body={k:v for k,v in {**item,**fields}.items() if k not in ('id','source_id','fetched_at')}
            blocks=content_blocks(body.get('content_blocks'),body.get('content',''),body['url'])
            if blocks is None:body.pop('content_blocks',None)
            else:body['content_blocks']=blocks
            self.store.db.execute('UPDATE reading_news SET body=? WHERE id=?',(json.dumps(body,ensure_ascii=False),ident))
            self.store.db.commit()
            return self.item(ident)

    def enrich(self, data):
        if data.get('allow_remote') is not True:raise ValueError('请授权读取原文与封面')
        ids=data.get('ids',[])
        if not isinstance(ids,list) or not 1<=len(ids)<=36 or any(not isinstance(i,str) for i in ids):raise ValueError('每次读取1至36篇文章')
        items=[self.item(i) for i in dict.fromkeys(ids)]
        def read(item):
            if item.get('content_status') in ('article','browser') and item.get('content') and isinstance(item.get('content_blocks'),list):
                return {'id':item['id'],'ok':True,'status':item['content_status'],'cached':True}
            try:
                page=fetch_article(item['url'],self.validator)
                fields={k:v for k,v in page.items() if v and k not in ('title','published_at','excerpt')}
                if item.get('content_status')=='browser' and item.get('content'):
                    blocks=content_blocks(page.get('content_blocks'),item['content'],item['url'])
                    if blocks is None:
                        raise ValueError('原文与浏览器采集的正文不同，已保留原内容；请从原页面重新采集图文')
                    fields={'content_blocks':blocks}
                if item.get('cover_url'):fields.pop('cover_url',None)
                fields.update(read_at=now(),read_error='')
                self.update_item(item['id'],fields)
                return {'id':item['id'],'ok':True,'status':'article'}
            except Exception as error:
                self.update_item(item['id'],{'read_error':str(error)[:240],'read_at':now()})
                return {'id':item['id'],'ok':False,'status':item.get('content_status','summary'),'error':str(error)[:240]}
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(read,items))
        return {'results':results,'items':[self.item(item['id']) for item in items]}

    def import_capture(self, data):
        """Accept only explicit visible-page captures, never scrape browser credentials."""
        item=data.get('article',{})
        if not isinstance(item,dict):raise ValueError('文章格式无效')
        url=item.get('url','');self.validator(url)
        title=item.get('title','');content=item.get('content','')
        if not isinstance(title,str) or not 1<=len(title)<=200 or not isinstance(content,str) or not 80<=len(content)<=120000:
            raise ValueError('标题1至200字，正文80至12万字；请先读取完整正文')
        if blocked_page(title,content):raise ValueError('没有读取到正文，不能导入登录或验证页面')
        date=item.get('published_at')
        if date:
            try:
                parsed=datetime.fromisoformat(date.replace('Z','+00:00'))
                if parsed.tzinfo is None or parsed>datetime.now(timezone.utc):raise ValueError()
            except (ValueError,TypeError,AttributeError):raise ValueError('发布日期无效；未提供准确日期时请留空')
        cover=cover_url(item.get('cover_url',''))
        if cover:self.validator(cover)
        entry={k:item[k] for k in ('author','author_url','source_name','source_kind','published_label','date_basis','topic','feed_url') if isinstance(item.get(k),str)}
        for key in ('feed_url','author_url'):
            if entry.get(key):self.validator(entry[key])
        entry.update(title=title,url=url,content=content,excerpt=content[:300],published_at=date,
                     cover_url=cover,content_status='browser',collection_method='visible_browser',read_at=now(),read_error='')
        blocks=content_blocks(item.get('content_blocks'),content,url)
        if blocks is not None:entry['content_blocks']=blocks
        saved,added=self.store_item(entry)
        return {'item':saved,'added':added}

    def cover(self, ident):
        item=self.item(ident);url=item.get('cover_url','')
        if not url:raise ValueError('原文没有封面')
        folder=self.app.root/'data/news-covers';folder.mkdir(parents=True,exist_ok=True)
        digest=hashlib.sha256(url.encode()).hexdigest()
        file=folder/digest;meta=folder/(digest+'.json')
        if file.exists() and meta.exists():return file.read_bytes(),json.loads(meta.read_text())['mime']
        raw,mime=fetch_image(url,self.validator)
        file.write_bytes(raw);meta.write_text(json.dumps({'mime':mime,'url':url}))
        return raw,mime

    def image(self, ident, image_id):
        item=self.item(ident)
        blocks=content_blocks(item.get('content_blocks'),item.get('content',''),item['url']) or []
        image=next((block for block in blocks if block['type']=='image' and block['id']==image_id),None)
        if not image:raise ValueError('正文中没有这张图片')
        folder=self.app.root/'data/news-images';folder.mkdir(parents=True,exist_ok=True)
        digest=hashlib.sha256(image['url'].encode()).hexdigest()
        file=folder/digest;meta=folder/(digest+'.json')
        with self.image_lock:
            if file.exists() and meta.exists():return file.read_bytes(),json.loads(meta.read_text())['mime']
            raw,mime=fetch_image(image['url'],self.validator,referer=item['url'])
            temporary=file.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(file)
            temporary=meta.with_suffix('.tmp');temporary.write_text(json.dumps({'mime':mime,'url':image['url']}));temporary.replace(meta)
            return raw,mime

    def refresh(self, data):
        if data.get('allow_remote') is not True: raise ValueError('请授权本次公开订阅源采集')
        config=self.app.weekly.config(data.get('id'))
        urls=config['urls'] or DEFAULT_FEEDS
        if not self.collect_lock.acquire(blocking=False): raise Conflict('资讯正在刷新，请稍候')
        try:
            added=0; warnings=[];collected=[]
            weeks=data.get('weeks',1)
            if type(weeks) is not int or not 1<=weeks<=3:raise ValueError('每次最多更新三期')
            for url in urls:
                try:
                    rows=fetch_feed(url,self.validator,limit=80) if weeks>1 else fetch_feed(url,self.validator)
                    for item in rows:
                        if not useful_entry(item):continue
                        if weeks>1:
                            from reading_room import period_start
                            from datetime import timedelta
                            cutoff=period_start(datetime.now(timezone.utc).isoformat())-timedelta(weeks=weeks-1)
                            published=period_start(item.get('published_at'))
                            if published is None or published<cutoff:continue
                        saved,is_new=self.store_item(item,config);added+=int(is_new);collected.append(saved['id'])
                except Exception as error: warnings.append({'url':url,'error':str(error)[:200]})
            return {'added':added,'items':self.items(),'collected_ids':list(dict.fromkeys(collected)),'warnings':warnings,'checked_at':now()}
        finally:self.collect_lock.release()

    def test_sources(self, data):
        if data.get('allow_remote') is not True:
            raise ValueError('请授权测试公开来源')
        configs = self.app.weekly.subscriptions()
        urls = list(dict.fromkeys(url for config in configs for url in config.get('urls', [])))[:9]
        def test(url):
            try:
                items = fetch_feed(url, self.validator)
                return {'url': url, 'ok': bool(items), 'count': len(items),
                        'title': items[0]['title'] if items else '', 'error': '' if items else '未读取到条目'}
            except Exception as error:
                return {'url': url, 'ok': False, 'count': 0, 'error': str(error)[:240]}
        with ThreadPoolExecutor(max_workers=3) as pool:
            return {'results': list(pool.map(test, urls))}

    def generate(self, data):
        if data.get('allow_remote') is not True:raise ValueError('请授权本次模型整理')
        from models import model_key
        if self.app.settings.get('mode')!='deepseek' or not model_key(self.app.credential_root):raise ValueError('请先连接DeepSeek')
        config=self.app.weekly.config(data.get('id'))
        selected=data.get('news_ids')
        if not isinstance(selected,list) or not 1<=len(selected)<=5:raise ValueError('请选择1至5篇资讯整理')
        items={n['id']:n for n in self.items()};sources=[]
        for ident in dict.fromkeys(selected):
            if ident not in items:raise ValueError('资讯不存在，请刷新')
            n=items[ident]
            if n['subscription_id']!=config.get('id',''):raise ValueError('请选择当前订阅的资讯')
            s=self.store.source(n['source_id'])
            if s['archived']:raise Conflict('资讯原文已归档，请重新刷新')
            sources.append(s)
        from task_skills import task_method
        config={**config,'skill_snapshot':task_method('weekly',self.store)}
        from domain import uid
        with self.store.lock:
            ids={s['id'] for s in sources}
            for job in self.store.jobs():
                p=job['payload']
                if p.get('weekly_run_id') and p.get('subscription_id')==config.get('id') and job['status'] in ('queued','running','review','approved') and set(p.get('source_ids',[]))==ids:
                    raise Conflict('这些资讯已有周刊草稿或已保存周刊，请查看已有内容，不重复调用模型')
            rid=self.app.weekly.claim(config,uid('manual'))
        try:self.app.weekly.enqueue(rid,config,sources,{s['id']:s for s in sources},['本期依据RSS/Atom摘要，而非文章全文；发布日期由订阅源提供。'])
        except Exception as error:
            self.app.weekly.update(rid,'failed',error=str(error)[:400]);raise
        return {'id':rid,'subscription_id':config.get('id','')}
