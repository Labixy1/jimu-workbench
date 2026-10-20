"""Manual, bounded public-feed collection; AI publication remains a separate approval."""
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

DEFAULT_FEEDS = ['https://openai.com/news/rss.xml', 'https://github.com/openai/codex/releases.atom',
                 'https://github.com/anomalyco/opencode/releases.atom']
ATOM = '{http://www.w3.org/2005/Atom}'


def plain(text):
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text or '', flags=re.S|re.I)
    text = re.sub(r'</(?:p|div|li|h[1-6])>', '\n', text, flags=re.I)
    return unescape(re.sub(r'<[^>]+>', '', text)).strip()


def parse_feed(raw, feed_url, instant=None):
    if len(raw) > 1500000: raise ValueError('订阅源超过1.5MB')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('不支持带实体声明的订阅源')
    root = ET.fromstring(raw); instant = instant or datetime.now(timezone.utc)
    entries = root.findall('./channel/item') or root.findall(ATOM+'entry')
    if not entries: raise ValueError('没有读取到RSS/Atom条目，请填订阅源地址，普通网页可用联网采集')
    result = []
    for entry in entries[:80]:
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
        text = plain(entry.findtext('description') or entry.findtext(ATOM+'content') or entry.findtext(ATOM+'summary'))[:6000]
        result.append({'title':title,'url':url,'published_at':date,'excerpt':text or '订阅源未提供摘要，请阅读原文。','feed_url':feed_url})
    result.sort(key=lambda n:n['published_at'] or '', reverse=True)
    return result[:8]


def fetch_feed(url, validator):
    validator(url)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validator(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    opener = urllib.request.build_opener(Redirect())
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'JimuPersonalLearning/1.0','Accept':'application/rss+xml, application/atom+xml, application/xml'}),timeout=20) as response:
        raw=response.read(1500001)
    return parse_feed(raw,url)


class News:
    def __init__(self, app, validator):
        self.app=app; self.store=app.store; self.validator=validator; self.collect_lock=threading.Lock()
        with self.store.lock:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS reading_news(id TEXT PRIMARY KEY,url TEXT UNIQUE,body TEXT,source_id TEXT,fetched_at TEXT)')
            self.store.db.commit()

    def items(self):
        with self.store.lock:
            return [{**json.loads(r['body']),'id':r['id'],'source_id':r['source_id'],'fetched_at':r['fetched_at']} for r in self.store.db.execute('SELECT * FROM reading_news ORDER BY json_extract(body,\'$.published_at\') DESC LIMIT 80')]

    def refresh(self, data):
        if data.get('allow_remote') is not True: raise ValueError('请授权本次公开订阅源采集')
        config=self.app.weekly.config(data.get('id'))
        urls=config['urls'] or DEFAULT_FEEDS
        if not self.collect_lock.acquire(blocking=False): raise Conflict('资讯正在刷新，请稍候')
        try:
            added=0; warnings=[]
            for url in urls:
                try:
                    for item in fetch_feed(url,self.validator):
                        item['subscription_id']=config.get('id','');item['column']=config.get('title') or 'AI学习周刊'
                        content=f"标题：{item['title']}\n来源：{item['url']}\n发布日期：{item['published_at'] or '未提供'}\n\n订阅源摘要（非全文）：\n{item['excerpt']}"
                        with self.store.lock:
                            old=self.store.db.execute('SELECT id FROM reading_news WHERE url=?',(item['url'],)).fetchone()
                            source=self.store.add_source(item['title'], content, item['url'],'public')['source']
                            import library
                            assigned=self.store.db.execute('SELECT asset_id FROM asset_categories_map WHERE asset_id=?',(source['id'],)).fetchone()
                            if not assigned:
                                library.record_destination(self.store,source['id'],{'category_id':'learning'} if any(c['id']=='learning' for c in library.categories(self.store)) else {})
                            ident=old['id'] if old else 'news_'+hashlib.sha256(item['url'].encode()).hexdigest()[:16]
                            self.store.db.execute('INSERT OR REPLACE INTO reading_news VALUES(?,?,?,?,?)',(ident,item['url'],json.dumps(item,ensure_ascii=False),source['id'],now()))
                            self.store.db.commit()
                            if not old:added+=1
                except Exception as error: warnings.append({'url':url,'error':str(error)[:200]})
            return {'added':added,'items':self.items(),'warnings':warnings,'checked_at':now()}
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
