"""Bounded public article extraction. Login and challenge pages are not articles."""
import re
import json
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser


MAX_HTML = 2_000_000
MAX_IMAGE = 5_000_000
MAX_ARTICLE_IMAGES = 80
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
SKIP = {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'iframe', 'form', 'button'}
BLOCK = re.compile(r'^(?:access denied|forbidden|just a moment[.!…]*|security verification|'
                   r'vercel security checkpoint|请完成安全验证|访问过于频繁|环境异常|验证中心|'
                   r'登录后查看|页面不存在|内容已删除|该内容无法展示|访问受限|无法访问|'
                   r'(?:401|403)\b)', re.I)


def safe_url(value, base=''):
    if not isinstance(value,str) or not value.strip():
        return ''
    url = urllib.parse.urljoin(base, (value or '').strip())
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password:
            return url
    except ValueError:
        pass
    return ''


def cover_url(value, base=''):
    url=safe_url(value,base)
    return '' if re.search(r'logo|avatar|qrcode|qr_code|(?:^|[/_.-])icon(?:[/_.-]|$)|/head\.',url,re.I) else url


def blocked_page(title, content):
    if BLOCK.search((title or '').strip()):
        return True
    short = re.sub(r'\s+', ' ', content or '').strip()
    return len(short) < 1000 and bool(re.search(
        r'verify you are human|checking your browser|captcha|请完成验证|访问过于频繁|'
        r'当前环境异常|访问被拒绝|请在微信客户端打开|登录后查看搜索结果|暂时无法访问|'
        r'内容因违规无法查看|请先登录后查看|该内容暂时无法浏览', short, re.I))


def clean_text(parts):
    text = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parts))
    return re.sub(r'\n\s*\n+', '\n\n', text).strip()


def content_blocks(value, content, base=''):
    """Keep only text and raster-image references that belong to the same text snapshot."""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ARTICLE_IMAGES * 2 + 1:
        return None
    result = []
    images = 0
    for block in value:
        if not isinstance(block, dict): return None
        if block.get('type') == 'text' and isinstance(block.get('text'), str):
            if len(block['text']) > 120000: return None
            result.append({'type': 'text', 'text': block['text']})
        elif block.get('type') == 'image' and images < MAX_ARTICLE_IMAGES:
            url = safe_url(block.get('url'), base)
            if not url or len(url) > 4000: continue
            alt = block.get('alt') if isinstance(block.get('alt'), str) else ''
            result.append({'type': 'image', 'url': url, 'alt': alt[:300],
                           'id': hashlib.sha256(url.encode()).hexdigest()[:24]})
            images += 1
    text = ''.join(block['text'] for block in result if block['type'] == 'text')
    if re.sub(r'\s+', '', text) != re.sub(r'\s+', '', content): return None
    return result


def article_image(attrs, base):
    for key in ('data-src', 'data-original', 'data-lazy-src', 'data-actualsrc', 'src'):
        image = cover_url(attrs.get(key), base)
        if image: return image
    candidates = []
    for part in (attrs.get('data-srcset') or attrs.get('srcset') or '').split(','):
        bits = part.strip().split()
        if not bits: continue
        image = cover_url(bits[0], base)
        if image:
            size = re.match(r'([\d.]+)[wx]$', bits[-1])
            candidates.append((float(size[1]) if size else 0, image))
    return max(candidates, default=(0, ''))[1]


class ArticleHTML(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.stack = []
        self.meta = {}
        self.regions = []
        self.title = []
        self.feed_urls = []
        self.article_json = ''
        self.author = []
        self.visible_title = []
        self.published = ''
        self.date_text = []
        self.time_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        key = (a.get('property') or a.get('name') or '').lower()
        if tag == 'meta' and key and a.get('content'):
            self.meta.setdefault(key, a['content'])
        if tag == 'link' and a.get('type') in ('application/rss+xml', 'application/atom+xml'):
            self.feed_urls.append(safe_url(a.get('href'), self.url))
        if tag == 'link' and a.get('type')=='application/json' and a.get('rel')=='alternate':
            candidate=safe_url(a.get('href'),self.url)
            if urllib.parse.urlsplit(candidate).hostname==urllib.parse.urlsplit(self.url).hostname:
                self.article_json=candidate
        hidden = ('hidden' in a or a.get('aria-hidden', '').lower() == 'true' or
                  bool(re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b',
                                 a.get('style', ''), re.I)))
        skipped = hidden or tag in SKIP or any(s['skip'] for s in self.stack)
        classes = set(a.get('class', '').split())
        ident = a.get('id', '')
        if not skipped and tag == 'time' and a.get('datetime') and not self.published:
            self.published = a['datetime']
        score = (100 if ident in ('js_content', 'article-body', 'post-content', 'detail-desc') else
                 90 if classes & {'entry-content', 'article-content', 'post-content', 'article-body', 'note-content', 'markdown-body', 'note-scroller'} else
                 80 if tag == 'article' or 'article' in classes else
                 40 if tag == 'main' or a.get('role') == 'main' else 0)
        if score and not skipped:
            region = {'score': score, 'depth': len(self.stack), 'parts': [], 'images': [], 'flow': []}
            self.regions.append(region)
        if not skipped:
            if tag in ('p', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'li', 'br', 'tr', 'blockquote'):
                self._append('\n')
            if tag == 'img':
                image = article_image(a, self.url)
                decorative=re.search(r'avatar|logo|qrcode|qr-code|icon',a.get('class','')+' '+ident,re.I)
                tiny = any(re.fullmatch(r'[012](?:px)?', a.get(key, '').strip()) for key in ('width', 'height'))
                if image and not decorative and not tiny:
                    for region in self.regions:
                        if region['depth'] < len(self.stack) and not region.get('closed') and len(region['images']) < MAX_ARTICLE_IMAGES:
                            region['images'].append(image)
                            region['flow'].append({'type': 'image', 'url': image, 'alt': a.get('alt') or a.get('title') or ''})
        if tag not in VOID:
            self.stack.append({'tag': tag, 'skip': skipped,
                               'author': ident == 'js_name' or 'author-name' in classes,
                               'title': ident == 'activity-name' or ident == 'detail-title',
                               'date': ident == 'publish_time' or 'date' in classes,
                               'time': 'time' in classes})

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack)-1, -1, -1) if self.stack[i]['tag'] == tag), None)
        if index is None:
            return
        if not any(s['skip'] for s in self.stack) and tag in ('p', 'div', 'section', 'li', 'h1', 'h2', 'h3'):
            self._append('\n')
        self.stack = self.stack[:index]
        for region in self.regions:
            if region['depth'] >= len(self.stack):
                region['closed'] = True

    def _append(self, data):
        for region in self.regions:
            if not region.get('closed'):
                region['parts'].append(data)
                region['flow'].append(data)

    def handle_data(self, data):
        if any(s['tag'] == 'title' for s in self.stack):
            self.title.append(data)
        if not any(s['skip'] for s in self.stack):
            self._append(data)
            if any(s.get('author') for s in self.stack): self.author.append(data)
            if any(s.get('title') for s in self.stack): self.visible_title.append(data)
            if any(s.get('date') for s in self.stack): self.date_text.append(data)
            if any(s.get('time') for s in self.stack): self.time_text.append(data)

    def result(self):
        title = (''.join(self.visible_title) or self.meta.get('og:title') or ''.join(self.title)).strip()
        candidates = [(r, clean_text(r['parts'])) for r in self.regions]
        candidates = [(r, text) for r, text in candidates if text]
        region, content = max(candidates, key=lambda item: (item[0]['score'], len(item[1])), default=({}, ''))
        if urllib.parse.urlsplit(self.url).hostname=='github.com' and '/releases/' in self.url and region.get('score',0)<90:
            raise ValueError('发布页未提供独立正文，保留订阅源摘要')
        if blocked_page(title, content):
            raise ValueError('来源返回登录或验证页面，未保存为文章')
        if len(content)<80:
            raise ValueError('未读取到文章正文；没有把导航、登录页或搜索摘要当正文')
        if len(content) > 120000:
            raise ValueError('文章正文超过12万字，请选择需要的部分')
        blocks, text = [], []
        for part in region.get('flow', []):
            if isinstance(part, str):
                text.append(part)
            else:
                if clean_text(text): blocks.append({'type': 'text', 'text': clean_text(text)})
                text = []
                blocks.append(part)
        if clean_text(text): blocks.append({'type': 'text', 'text': clean_text(text)})
        cover = cover_url(self.meta.get('og:image') or self.meta.get('twitter:image'), self.url)
        if urllib.parse.urlsplit(self.url).hostname=='github.com' and 'repository-images.githubusercontent.com' in cover:
            cover=''
        date = self.meta.get('article:published_time') or self.meta.get('datepublished') or self.meta.get('publishdate') or self.published
        try:
            parsed = datetime.fromisoformat((date or '').replace('Z', '+00:00'))
            date = parsed.isoformat() if parsed.tzinfo else None
        except ValueError:
            date = None
        label = ''.join(self.date_text).strip()
        host = urllib.parse.urlsplit(self.url).hostname or ''
        if not date and host in ('www.qbitai.com', 'qbitai.com', 'mp.weixin.qq.com'):
            match = re.match(r'^(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})(?:日)?(?:\s|$)', label)
            if match:
                clock = re.search(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?', label+' '+''.join(self.time_text))
                try:
                    parts = [int(v or '0') for v in clock.groups()] if clock else [0, 0, 0]
                    parsed = datetime(*map(int, match.groups()), *parts, tzinfo=timezone(timedelta(hours=8)))
                    if parsed <= datetime.now(timezone.utc): date = parsed.isoformat()
                except ValueError:
                    pass
        return {'title': title[:200], 'content': content, 'cover_url': cover,
                'content_blocks': content_blocks(blocks, content, self.url),
                'excerpt': self.meta.get('description') or self.meta.get('og:description') or content[:260],
                'author': (''.join(self.author).strip() or self.meta.get('author', ''))[:100], 'published_at': date,
                'published_label': label[:100],
                'content_status': 'article', 'collection_method': 'public_html'}


def fetch_bytes(url, validator, *, limit=MAX_HTML, accept='text/html', timeout=15, referer=''):
    validator(url)

    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validator(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    headers = {'User-Agent': 'JimuPersonalLearning/1.0', 'Accept': accept}
    if safe_url(referer):
        parsed = urllib.parse.urlsplit(referer)
        headers['Referer'] = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '/', '', ''))
    request = urllib.request.Request(urllib.parse.quote(url,safe=":/?&=#%+;,@!$'()*[]"), headers=headers)
    with urllib.request.build_opener(Redirect()).open(request, timeout=timeout) as response:
        raw = response.read(limit+1)
        if len(raw) > limit:
            raise ValueError('来源超过读取大小限制')
        return raw, response.headers.get_content_type(), response.headers.get_content_charset() or 'utf-8', response.geturl()


def fetch_article(url, validator):
    raw, mime, charset, final_url = fetch_bytes(url, validator)
    if mime not in ('text/html', 'application/xhtml+xml', 'text/plain', 'text/markdown', 'text/x-markdown', 'application/json'):
        raise ValueError('来源不是文章网页')
    text = raw.decode(charset, errors='replace')
    if mime not in ('text/html','application/xhtml+xml'):
        if blocked_page('', text) or len(text.strip()) < 80:
            raise ValueError('未读取到文章正文')
        if len(text)>120000:raise ValueError('文章正文超过12万字，请选择需要的部分')
        return {'content': text, 'cover_url': '', 'content_status': 'article', 'collection_method': 'public_text',
                'content_blocks': [{'type': 'text', 'text': text}]}
    parser = ArticleHTML(final_url)
    parser.feed(text)
    article=parser.result()
    if not article['cover_url'] and parser.article_json:
        try:article['cover_url']=featured_image(parser.article_json,validator)
        except Exception:pass
    return article


def featured_image(url, validator):
    """Use a site's advertised article metadata, never substitute an arbitrary body image."""
    def read_json(address):
        raw,mime,_,_=fetch_bytes(address,validator,limit=1000000,accept='application/json',timeout=8)
        if mime!='application/json':raise ValueError('不是文章元数据')
        return json.loads(raw)
    article=read_json(url)
    media_links=article.get('_links',{}).get('wp:featuredmedia',[])
    if not article.get('featured_media') or not media_links:return ''
    media_url=safe_url(media_links[0].get('href'))
    if urllib.parse.urlsplit(media_url).hostname!=urllib.parse.urlsplit(url).hostname:return ''
    media=read_json(media_url)
    sizes=media.get('media_details',{}).get('sizes',{})
    image=(sizes.get('medium_large') or sizes.get('large') or {}).get('source_url') or media.get('source_url','')
    return cover_url(image)


def fetch_image(url, validator, *, referer=''):
    raw, mime, _, _ = fetch_bytes(url, validator, limit=MAX_IMAGE, accept='image/*', timeout=12, referer=referer)
    signatures = {'image/jpeg': raw.startswith(b'\xff\xd8\xff'), 'image/png': raw.startswith(b'\x89PNG\r\n\x1a\n'),
                  'image/webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP',
                  'image/gif': raw.startswith((b'GIF87a', b'GIF89a')),
                  'image/avif': raw[4:8] == b'ftyp' and raw[8:12] in (b'avif', b'avis')}
    if not signatures.get(mime):
        raise ValueError('来源不是可预览图片')
    return raw, mime
