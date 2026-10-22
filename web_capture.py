"""Product-owned webpage previews. No source is saved until the user chooses Save."""
import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from article_reader import ArticleHTML, blocked_page, cover_url, fetch_article, fetch_image, featured_image, content_blocks
from domain import Conflict, now, uid
from mcp_runtime import StdioMCP
from news import source_body
import library
import reading_room


def canonical_url(url):
    if not isinstance(url, str) or len(url) > 4000:
        raise ValueError('网址无效或过长')
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('需要不含账号密码的 HTTP(S) 地址')
    # Keep article identifiers; strip account tokens and tracking parameters.
    keys = {'id', 'p', 'v', 'article', 'article_id', 'post', 'page', 'story'}
    if parsed.hostname == 'mp.weixin.qq.com':
        keys |= {'__biz', 'mid', 'idx', 'sn'}
        query = urllib.parse.parse_qs(parsed.query)
        if not query.get('mid') and query.get('signature'):
            # Search share signatures identify a public article, not an account session.
            keys |= {'src', 'timestamp', 'ver', 'signature', 'new'}
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if k in keys])
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ''))


def validate_article(article, validator, method):
    if not isinstance(article, dict): raise ValueError('采集内容格式无效')
    title, text = article.get('title', ''), article.get('content', '')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ValueError('标题需要1至200字')
    if not isinstance(text, str) or not 20 <= len(text.strip()) <= 119000:
        raise ValueError('正文需要20至119000字；过长时请选择需要的部分')
    if blocked_page(title, text): raise ValueError('网页是登录、验证或拦截页面，没有保存为文章')
    url = canonical_url(article.get('url', '')); validator(url)
    date = article.get('published_at') or None
    if date:
        try:
            parsed = datetime.fromisoformat(date.replace('Z', '+00:00'))
            if not parsed.tzinfo or parsed > datetime.now(timezone.utc): raise ValueError()
            date = parsed.isoformat()
        except (TypeError, ValueError, AttributeError):
            raise ValueError('发布日期无效；没有准确日期请留空') from None
    image = cover_url(article.get('cover_url', ''))
    if image: validator(image)
    result = {key: article[key].strip()[:200] for key in ('author', 'source_name', 'source_kind', 'published_label')
              if isinstance(article.get(key), str)}
    author_url = article.get('author_url', '')
    if author_url:
        result['author_url'] = canonical_url(author_url); validator(result['author_url'])
    host = urllib.parse.urlsplit(url).hostname
    result.setdefault('source_kind', '公众号' if host == 'mp.weixin.qq.com' else
                      '小红书' if host.endswith('xiaohongshu.com') else '网页')
    result.setdefault('source_name', result.get('author') or host)
    result.update(title=title.strip(), content=text.strip(), url=url, cover_url=image, published_at=date,
                  excerpt=text.strip()[:300], content_status='article' if method == 'public_html' else 'browser',
                  collection_method=method, read_at=now(), read_error='')
    blocks=content_blocks(article.get('content_blocks'),text,url)
    if blocks is not None:result['content_blocks']=blocks
    return result


class WebCapture:
    def __init__(self, app, validator):
        self.app, self.validator = app, validator
        self.lock = threading.RLock()
        self.browser_lock = threading.Lock()
        self.previews = {}
        self.client = None
        self.browser_url = ''
        self.browser_error = ''
        self.trace = []

    def state(self):
        return {'installed': self.executable().is_file(), 'opened': bool(self.browser_url),
                'url': canonical_url(self.browser_url) if self.browser_url else '',
                'busy': self.browser_lock.locked(), 'error': self.browser_error,
                'tools': ['browser_navigate', 'browser_get_state', 'browser_get_html'],
                'trace': list(self.trace)}

    def executable(self):
        return Path(__file__).parent / '.runtime/browser-use-env/bin/browser-use'

    def _browser(self):
        if not self.executable().is_file():
            raise ValueError('Browser Use 未安装，请按扩展说明安装到积木项目内')
        if self.client is None:
            root = self.app.root / '.runtime/reading-browser'
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            config = root / 'config.json'
            config.write_text(json.dumps({'browser_profile': {'jimu': {
                'id': 'jimu', 'default': True, 'headless': False, 'disable_security': False,
                'user_data_dir': str(root / 'profile'), 'downloads_path': str(root / 'downloads'),
                'keep_alive': False, 'enable_default_extensions': False}}, 'llm': {}, 'agent': {}}))
            config.chmod(0o600)
            self.client = StdioMCP([str(self.executable()), '--mcp'], {
                'ANONYMIZED_TELEMETRY': 'false', 'BROWSER_USE_CLOUD_SYNC': 'false',
                'BROWSER_USE_VERSION_CHECK': 'false', 'BROWSER_USE_CONFIG_PATH': str(config),
                'BROWSER_USE_CONFIG_DIR': str(root), 'XDG_CONFIG_HOME': str(root)})
        return self.client

    def _call(self, name, args=None):
        step = {'tool': name, 'status': 'running', 'at': now()}
        self.trace.append(step); self.trace = self.trace[-8:]
        try:
            value = self._browser().call(name, args, timeout=75)
            step['status'] = 'completed'
            return value
        except Exception:
            step['status'] = 'failed'
            raise

    def open_browser(self, data):
        if data.get('allow_remote') is not True: raise ValueError('请允许打开所选网页')
        url = data.get('url', '')
        canonical_url(url); self.validator(url)
        if not self.browser_lock.acquire(blocking=False): raise Conflict('浏览器正在工作，请稍候')
        try:
            self.trace = []
            self._call('browser_navigate', {'url': url, 'new_tab': not bool(self.browser_url)})
            self.browser_url, self.browser_error = url, ''
            return self.state()
        except Exception as error:
            self.browser_error = str(error)[:240]
            raise
        finally:
            self.browser_lock.release()

    def read_browser(self, data):
        if data.get('allow_remote') is not True: raise ValueError('请允许读取当前页面')
        if not self.browser_url: raise ValueError('请先在积木打开需要采集的网页')
        if not self.browser_lock.acquire(blocking=False): raise Conflict('浏览器正在工作，请稍候')
        try:
            state = json.loads(self._call('browser_get_state', {'include_screenshot': False}))
            url = state.get('url', '')
            self.validator(url)
            html = self._call('browser_get_html')
            if len(html.encode()) > 2_000_000: raise ValueError('网页过大，请使用插件选取正文')
            parser = ArticleHTML(url); parser.feed(html)
            article = {**parser.result(), 'url': url}
            if not article.get('cover_url') and parser.article_json:
                try: article['cover_url'] = featured_image(parser.article_json, self.validator)
                except Exception: pass
            if not article.get('title'): article['title'] = state.get('title', '')
            self.browser_error = ''
            return self.stage(article, 'browser_use_mcp')
        except Exception as error:
            self.browser_error = str(error)[:240]
            raise
        finally:
            self.browser_lock.release()

    def close_browser(self):
        if not self.browser_lock.acquire(blocking=False): raise Conflict('正在读取，请完成后关闭')
        try:
            if self.client:
                try: self.client.call('browser_close_all', timeout=15)
                finally: self.client.close()
        finally:
            self.client = None; self.browser_url = ''; self.browser_error = ''
            self.browser_lock.release()
        return self.state()

    def public_preview(self, data):
        if data.get('allow_remote') is not True: raise ValueError('请允许读取所选网页')
        url = data.get('url', ''); canonical_url(url); self.validator(url)
        article = fetch_article(url, self.validator)
        article.update(url=url)
        if not article.get('title'): article['title'] = urllib.parse.urlsplit(url).hostname
        return self.stage(article, 'public_html')

    def stage(self, article, method='browser_extension'):
        entry = validate_article(article, self.validator, method)
        with self.lock:
            self.previews = {k: v for k, v in self.previews.items() if time.monotonic() - v['at'] < 1800}
            if len(self.previews) >= 8: self.previews.pop(next(iter(self.previews)))
            ident = uid('capture')
            self.previews[ident] = {'at': time.monotonic(), 'article': entry}
            return {'id': ident, 'article': entry, 'trace': list(self.trace) if method == 'browser_use_mcp' else []}

    def preview(self, ident):
        with self.lock:
            preview = self.previews.get(ident)
            if not preview or time.monotonic() - preview['at'] > 1800:
                raise ValueError('预览已过期，请重新读取；未保存的内容没有进入资产')
            return preview

    def image(self, ident):
        preview = self.preview(ident)
        url = preview['article'].get('cover_url')
        if not url: raise ValueError('原文没有封面')
        if 'image' not in preview: preview['image'] = fetch_image(url, self.validator)
        return preview['image']

    def save(self, data):
        with self.lock, self.app.store.lock:
            preview = self.preview(data.get('id'))
            if preview.get('saved'): return {**preview['saved'], 'duplicate': True}
            entry = dict(preview['article'])
            for key in ('title', 'content'):
                if key in data: entry[key] = data[key]
            entry = validate_article(entry, self.validator, entry['collection_method'])
            library.validate_destination(self.app.store, data)
            if data.get('favorite') is True and data.get('favorite_category') not in (None, '', 'all'):
                if data['favorite_category'] not in reading_room.state(self.app.store)['groups']:
                    raise Conflict('收藏分类已删除，请重新选择')
            if data.get('reading') is True and len(entry['content']) < 80:
                raise ValueError('加入阅览室需要至少80字正文；短摘录可只存入资产')
            old = self.app.store.db.execute('SELECT source_id FROM reading_news WHERE url=?', (entry['url'],)).fetchone()
            original = self.app.store.source(old['source_id']) if old else None
            if data.get('reading') is True:
                old_source = old['source_id'] if old else None
                item, added = self.app.news.store_item(entry, {'capture_snapshot': True,
                    'visibility': 'public' if entry['collection_method'] == 'public_html' else 'private',
                    'category_id': data.get('category_id', '')})
                ident = item['source_id']
                added = added or (old_source is not None and old_source != ident)
            elif original and entry['content'] == source_body(original) and entry['title'] == original['title']:
                ident, added, item = old['source_id'], False, None
            else:
                text = f"标题：{entry['title']}\n来源：{entry['url']}\n\n{entry['content']}"
                source = self.app.store.add_source(entry['title'], text, entry['url'], 'private')
                ident, added = source['source']['id'], not source['duplicate']
                item = None
            # Explicitly saving an archived capture restores it, without replacing its text.
            if self.app.store.source(ident)['archived']:
                self.app.store.db.execute('UPDATE sources SET archived=0 WHERE id=?', (ident,))
            library.record_destination(self.app.store, ident, data)
            self.app.store.db.commit()
            if data.get('favorite') is True:
                previous = self.app.store.db.execute('''SELECT f.* FROM reading_favorites f
                    JOIN sources s ON s.id=f.asset_id WHERE s.url=? ORDER BY f.position,f.created LIMIT 1''',
                    (entry['url'],)).fetchone()
                category = data.get('favorite_category', '')
                if category == 'all': category = ''
                # Favorites point to the latest capture; cited older sources remain intact.
                self.app.store.db.execute('''DELETE FROM reading_favorites WHERE asset_id IN
                    (SELECT id FROM sources WHERE url=?)''', (entry['url'],))
                self.app.store.db.execute('INSERT INTO reading_favorites(asset_id,created,category,position) VALUES(?,?,?,?)',
                    (ident,previous['created'] if previous else now(),category,previous['position'] if previous else 0))
                self.app.store.db.commit()
            if item: reading_room.snapshot(self.app.store, self.app.news.items(), 3)
            result = {'source_id': ident, 'news_id': item['id'] if item else None, 'duplicate': not added}
            preview['saved'] = result
            return result
