"""Local file parsing and bounded previews. Never execute imported HTML or macros."""
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
from domain import Conflict, now

MAX_FILE = 64 * 1024 * 1024
CATEGORIES = ('article', 'record', 'jd', 'reference')


def init(store):
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS source_meta(source_id TEXT PRIMARY KEY,category TEXT,favorite INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS source_files(source_id TEXT PRIMARY KEY,name TEXT,extension TEXT,digest TEXT,size INTEGER);
    CREATE TABLE IF NOT EXISTS reading_notes(id TEXT PRIMARY KEY,target_kind TEXT,target_id TEXT,quote TEXT,text TEXT,created TEXT);
    ''')
    store.db.commit()


def runtime(name):
    configured = os.environ.get('JIMU_' + name.upper())
    if configured: return configured
    bundle = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
    candidate = bundle/('python/bin/python3' if name == 'python' else 'bin/override/'+name)
    return str(candidate) if candidate.is_file() else (sys.executable if name == 'python' else shutil.which(name))


class Reader(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skipped=0
    def handle_starttag(self, tag, attrs):
        if tag in ('head','script','style','iframe','object','svg','template'): self.skipped+=1
        if not self.skipped and tag in ('p','div','h1','h2','h3','li','br','tr'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('head','script','style','iframe','object','svg','template') and self.skipped: self.skipped-=1
        if not self.skipped and tag in ('p','div','h1','h2','h3','li','tr'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skipped: self.parts.append(data)


def parse(raw, ext):
    if ext in ('.txt','.md','.markdown','.html','.htm'):
        try: content=raw.decode('utf-8-sig')
        except UnicodeDecodeError: raise ValueError('文字文件请使用UTF-8编码')
        if ext in ('.html','.htm'):
            reader=Reader(); reader.feed(content); content=''.join(reader.parts)
    elif ext == '.docx':
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist())>2000 or sum(i.file_size for i in z.infolist())>32*1024*1024: raise ValueError('DOCX解压内容过大')
            xml=z.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml: raise ValueError('不支持含实体声明的文档')
            root=ET.fromstring(xml); ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            lines=[]
            for p in root.findall('.//w:p',ns):
                words=''.join(n.text or '' for n in p.findall('.//w:t',ns))
                style=p.find('w:pPr/w:pStyle',ns)
                name=style.get('{'+ns['w']+'}val','') if style is not None else ''
                lines.append(('## ' if name in ('Title','Heading1','Heading2') else '')+words)
            content='\n\n'.join(lines)
    elif ext == '.pdf':
        if not raw.startswith(b'%PDF-'): raise ValueError('不是有效PDF')
        code='''import sys,json,io
from pypdf import PdfReader
r=PdfReader(io.BytesIO(sys.stdin.buffer.read()))
if r.is_encrypted: raise ValueError('不支持加密PDF')
if len(r.pages)>40: raise ValueError('PDF最多40页')
print(json.dumps({'content':'\\n\\n'.join(p.extract_text() or '' for p in r.pages)},ensure_ascii=False))'''
        try:
            p=subprocess.run([runtime('python'),'-c',code],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
            if p.returncode: raise ValueError('PDF读取失败：需安装pypdf；加密、扫描件或超过40页暂不支持')
            content=json.loads(p.stdout)['content']
        except subprocess.TimeoutExpired: raise ValueError('PDF读取超时，请拆分文件')
    else: raise ValueError('支持DOCX、PDF、TXT、Markdown和HTML')
    content=content.strip()
    if not content: raise ValueError('没有可读取文字；扫描PDF请先OCR')
    if len(content)>120000: raise ValueError('文件正文超过12万字，请拆分文件')
    return content


def import_file(app, data):
    name=Path(str(data.get('name',''))).name
    ext=Path(name).suffix.lower()
    if not name or len(name)>200: raise ValueError('文件名无效')
    encoded=data.get('base64','')
    if not isinstance(encoded,str) or len(encoded)>MAX_FILE*4//3+8: raise ValueError('文件最多64MB')
    try: raw=base64.b64decode(encoded,validate=True)
    except Exception: raise ValueError('文件编码无效')
    if not raw or len(raw)>MAX_FILE: raise ValueError('文件为空或超过64MB')
    if ext in ('.excalidraw','.board'):
        import boards
        try: board=json.loads(raw.decode('utf-8-sig'))
        except Exception: raise ValueError('画板文件必须是有效JSON')
        result=boards.save(app.store,{'title':data.get('title') or Path(name).stem,'scene':board.get('scene',board),'category_id':data.get('category_id','')})
        return {'artifact':result}
    text_types=('.txt','.md','.markdown','.html','.htm','.docx','.pdf')
    if ext in text_types:
        content=parse(raw,ext)
    else:
        digest=hashlib.sha256(raw).hexdigest()
        content='附件：'+name+'\n类型：'+(ext or '无扩展名')+'\n大小：'+str(len(raw))+' 字节\n文件摘要：'+digest+'\n附件仅保存原件，未提取正文。'
        if ext=='.zip':
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    content+='\n\n压缩包目录（不解压）：\n'+'\n'.join(i.filename for i in archive.infolist()[:200])
            except zipfile.BadZipFile:raise ValueError('ZIP文件无效')
    category=data.get('category','reference')
    if category not in CATEGORIES: raise ValueError('资产分类无效')
    digest=hashlib.sha256(raw).hexdigest()
    folder=app.root/'data/asset-files'; folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(digest+ext)
    if not path.exists(): path.write_bytes(raw); path.chmod(0o600)
    result=app.store.add_source(data.get('title') or Path(name).stem,content,visibility=data.get('visibility','private'))
    sid=result['source']['id']
    if result['source'].get('archived'):
        app.store.archive('source',sid,False)
        result['source']=app.store.source(sid)
    with app.store.lock:
        if not app.store.db.execute('SELECT 1 FROM source_files WHERE source_id=?',(sid,)).fetchone():
            app.store.db.execute('INSERT INTO source_files VALUES(?,?,?,?,?)',(sid,name,ext,digest,len(raw)))
        app.store.db.execute('INSERT OR IGNORE INTO source_meta VALUES(?,?,0)',(sid,category));app.store.db.commit()
    return result


def metadata(store):
    with store.lock:
        meta={r['source_id']:dict(r) for r in store.db.execute('SELECT * FROM source_meta')}
        for row in store.db.execute('SELECT * FROM source_files'):
            item=dict(row); item.pop('digest');meta.setdefault(row['source_id'],{}).update(item)
        return meta


def set_meta(store,data):
    sid=data.get('id');s=store.source(sid)
    if s['archived']: raise Conflict('资产已归档')
    category=data.get('category','reference')
    if category not in CATEGORIES: raise ValueError('资产分类无效')
    with store.lock:
        store.db.execute('INSERT OR REPLACE INTO source_meta VALUES(?,?,?)',(sid,category,int(data.get('favorite') is True)));store.db.commit()
    return metadata(store).get(sid)


def file_path(app,sid):
    source=app.store.source(sid)
    if source['archived']: raise ValueError('资产已归档')
    row=app.store.db.execute('SELECT * FROM source_files WHERE source_id=?',(sid,)).fetchone()
    if not row: raise ValueError('此资产没有原始附件')
    path=app.root/'data/asset-files'/(row['digest']+row['extension'])
    if not path.is_file(): raise ValueError('附件文件缺失')
    return path,dict(row)


def pdf_page(app,sid,page):
    if not 1<=page<=40: raise ValueError('页码无效')
    path,info=file_path(app,sid)
    if info['extension']!='.pdf': raise ValueError('不是PDF附件')
    cache=app.root/'.runtime/previews'/info['digest'];cache.mkdir(parents=True,exist_ok=True)
    png=cache/(str(page)+'.png')
    if not png.exists():
        with tempfile.TemporaryDirectory(dir=cache) as folder:
            target=Path(folder)/'page.png'
            code="""import sys
import pypdfium2 as pdfium
pdf=pdfium.PdfDocument(sys.argv[1])
index=int(sys.argv[2])-1
if index<0 or index>=len(pdf): raise ValueError('Invalid PDF page')
page=pdf[index]
scale=1400/max(page.get_size())
bitmap=page.render(scale=scale)
bitmap.to_pil().save(sys.argv[3])
bitmap.close();page.close();pdf.close()
"""
            p=subprocess.run([runtime('python'),'-c',code,str(path),str(page),str(target)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
            if p.returncode or not target.is_file(): raise ValueError('此PDF页不可预览')
            target.replace(png)
    return png


def pdf_info(app,sid):
    path,info=file_path(app,sid)
    if info['extension']!='.pdf': raise ValueError('不是PDF附件')
    code='import sys; from pypdf import PdfReader; print(len(PdfReader(sys.argv[1]).pages))'
    try:
        p=subprocess.run([runtime('python'),'-c',code,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        if p.returncode: raise ValueError('无法读取PDF页数；可先查看提取文字')
        return {'pages':int(p.stdout)}
    except subprocess.TimeoutExpired:
        raise ValueError('读取PDF页数超时；可先查看提取文字')


def add_note(store,data):
    from domain import uid
    kind,target=data.get('kind'),data.get('id')
    if kind=='source':
        source=store.source(target)
        if source['archived']: raise ValueError('资产已归档')
        content=source['content']
    elif kind=='wiki':
        a=store.artifact(target)
        if a['kind']!='wiki' or a['archived']: raise ValueError('无效知识页')
        content=a['body']['content']
    elif kind=='news':
        with store.lock:
            row=store.db.execute('SELECT body,source_id FROM reading_news WHERE id=?',(target,)).fetchone()
        if not row or store.source(row['source_id'])['archived']:raise ValueError('文章不可用')
        article=json.loads(row['body'])
        content=article.get('content') or article.get('excerpt','')
    else: raise ValueError('笔记目标无效')
    quote=str(data.get('quote','')).strip();text=str(data.get('text','')).strip()
    if not 1<=len(text)<=2000 or len(quote)>1200: raise ValueError('笔记最多2000字，引文最多1200字')
    if quote and quote not in content: raise ValueError('摘录需逐字来自当前正文')
    note={'id':uid('note'),'target_kind':kind,'target_id':target,'quote':quote,'text':text,'created':now()}
    with store.lock:
        store.db.execute('INSERT INTO reading_notes VALUES(?,?,?,?,?,?)',tuple(note.values()));store.db.commit()
    return note


def notes(store,kind,target):
    with store.lock: return [dict(r) for r in store.db.execute('SELECT * FROM reading_notes WHERE target_kind=? AND target_id=? ORDER BY rowid DESC',(kind,target))]
