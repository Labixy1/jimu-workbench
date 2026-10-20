"""One asset catalog; keep immutable sources and versioned documents distinct."""
import json
from domain import Conflict, now, uid

DOCUMENT_FIELDS = {'wiki': 'content', 'career': 'general', 'career_review': 'tailored'}


def init(store):
    with store.lock:
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS asset_categories(id TEXT PRIMARY KEY,name TEXT UNIQUE,revision INTEGER);
        CREATE TABLE IF NOT EXISTS asset_categories_map(asset_id TEXT PRIMARY KEY,category_id TEXT);
        CREATE TABLE IF NOT EXISTS asset_origins(asset_id TEXT PRIMARY KEY,origin TEXT,reference TEXT);
        ''')
        columns = {r['name'] for r in store.db.execute('PRAGMA table_info(asset_categories)')}
        if 'scope' not in columns:
            store.db.executescript("""
            ALTER TABLE asset_categories RENAME TO asset_categories_old;
            CREATE TABLE asset_categories(id TEXT PRIMARY KEY,name TEXT,revision INTEGER,scope TEXT NOT NULL DEFAULT 'materials',parent_id TEXT NOT NULL DEFAULT '');
            INSERT INTO asset_categories(id,name,revision) SELECT id,name,revision FROM asset_categories_old;
            DROP TABLE asset_categories_old;
            """)
        if 'position' not in {r['name'] for r in store.db.execute('PRAGMA table_info(asset_categories)')}:
            store.db.execute('ALTER TABLE asset_categories ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
        for ident, name in [('career', '简历与JD'), ('internship', '实习记录'), ('learning', '学习资料')]:
            store.db.execute('INSERT OR IGNORE INTO asset_categories(id,name,revision) VALUES(?,?,1)', (ident, name))
        for job in store.jobs():
            ident = job['payload'].get('published_id')
            if job['status'] == 'approved' and ident:
                store.db.execute('INSERT OR IGNORE INTO asset_origins VALUES(?,?,?)', (ident, 'ai', job['id']))
        store.db.commit()


def categories(store):
    with store.lock:
        return [dict(r) for r in store.db.execute('SELECT * FROM asset_categories ORDER BY position,rowid')]


def category_save(store, data):
    name = data.get('name', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError('分类名称需要1至40字')
    name = name.strip()
    with store.lock:
        ident = data.get('id')
        old = store.db.execute('SELECT * FROM asset_categories WHERE id=?', (ident,)).fetchone() if ident else None
        if ident and (not old or old['revision'] != data.get('revision')):
            raise Conflict('分类已经变化，请刷新后重试')
        scope = data.get('scope', old['scope'] if old else 'materials')
        parent = data.get('parent_id', old['parent_id'] if old else '')
        if scope not in ('materials', 'creations') or not isinstance(parent, str):
            raise ValueError('无效文件夹位置')
        ancestor, seen = parent, {ident} if ident else set()
        while ancestor:
            if ancestor in seen: raise ValueError('不能将文件夹放入自己的子目录')
            seen.add(ancestor)
            row = store.db.execute('SELECT * FROM asset_categories WHERE id=?', (ancestor,)).fetchone()
            if not row or row['scope'] != scope: raise ValueError('父文件夹不存在或不属于当前资料区')
            ancestor = row['parent_id']
        if len(seen)-(1 if ident else 0)>=3:raise ValueError('文件夹最多支持三级')
        if old and parent!=old['parent_id']:
            def height(folder):
                children=store.db.execute('SELECT id FROM asset_categories WHERE parent_id=?',(folder,)).fetchall()
                return 1+max((height(c['id']) for c in children),default=0)
            if len(seen)-1+height(ident)>3:raise ValueError('移动后文件夹超过三级')
        duplicate = store.db.execute('SELECT id FROM asset_categories WHERE name=? AND scope=? AND parent_id=?', (name, scope, parent)).fetchone()
        if duplicate and duplicate['id'] != ident: raise ValueError('同一目录中已存在这个文件夹')
        ident = ident or uid('cat')
        revision = old['revision'] + 1 if old else 1
        store.db.execute('INSERT OR REPLACE INTO asset_categories(id,name,revision,scope,parent_id,position) VALUES(?,?,?,?,?,?)', (ident, name, revision, scope, parent,old['position'] if old else 0))
        store.db.commit()
        return {'id': ident, 'name': name, 'revision': revision, 'scope': scope, 'parent_id': parent}


def category_remove(store, data):
    with store.lock:
        row = store.db.execute('SELECT * FROM asset_categories WHERE id=?', (data.get('id'),)).fetchone()
        if not row or row['revision'] != data.get('revision'):
            raise Conflict('分类已经变化，请刷新后重试')
        store.db.execute('UPDATE asset_categories SET parent_id=?,revision=revision+1 WHERE parent_id=?', (row['parent_id'], row['id']))
        store.db.execute('DELETE FROM asset_categories_map WHERE category_id=?', (row['id'],))
        store.db.execute('DELETE FROM asset_categories WHERE id=?', (row['id'],))
        store.db.commit()
        return {'removed': True}


def asset(store, ident):
    obj = store.source(ident) if isinstance(ident, str) and ident.startswith('src_') else store.artifact(ident)
    if obj['archived'] or obj.get('kind') == 'map':
        raise ValueError('资产不可用')
    return obj


def assign(store, data):
    with store.lock:
        asset(store, data.get('id'))
        category = data.get('category_id')
        if 'expected_category_id' in data:
            current=store.db.execute('SELECT category_id FROM asset_categories_map WHERE asset_id=?',(data['id'],)).fetchone()
            if (current['category_id'] if current else '') != data['expected_category_id']:
                raise Conflict('文件位置已变化，请刷新后重试')
        if category and not store.db.execute('SELECT id FROM asset_categories WHERE id=?', (category,)).fetchone():
            raise ValueError('分类不存在')
        store.db.execute('INSERT OR REPLACE INTO asset_categories_map VALUES(?,?)', (data['id'], category or ''))
        store.db.commit()
        return {'id': data['id'], 'category_id': category or ''}


def catalog(store):
    with store.lock:
        mapping = {r['asset_id']: r['category_id'] for r in store.db.execute('SELECT * FROM asset_categories_map')}
        origins = {r['asset_id']: r['origin'] for r in store.db.execute('SELECT * FROM asset_origins')}
        return [dict(id=a['id'], title=a['title'], type='original' if 'content' in a else 'board' if a['kind']=='board' else 'document',
                     category_id=mapping.get(a['id'], ''), origin=origins.get(a['id'], 'imported' if 'content' in a else 'manual'), revision=a.get('revision', 0))
                for a in store.sources()+store.artifacts() if not a['archived'] and a.get('kind') != 'map']


def validate_destination(store, data):
    if 'category_id' not in data: return
    category = data['category_id']
    if not isinstance(category, str): raise ValueError('请选择资产分类')
    if category and not store.db.execute('SELECT id FROM asset_categories WHERE id=?', (category,)).fetchone():
        raise Conflict('分类已删除，请重新选择保存位置；草稿仍保留')


def record_destination(store, ident, data, origin=None, reference=''):
    """Called before the artifact transaction commits; never a second save."""
    validate_destination(store, data)
    if 'category_id' in data:
        store.db.execute('INSERT OR REPLACE INTO asset_categories_map VALUES(?,?)', (ident, data['category_id']))
    if origin:
        store.db.execute('INSERT OR REPLACE INTO asset_origins VALUES(?,?,?)', (ident, origin, reference))


def document(store, ident):
    a = asset(store, ident)
    if a.get('kind') not in DOCUMENT_FIELDS:
        raise ValueError('只有整理文稿可以编辑；原件保留不变')
    return {'id': a['id'], 'title': a['title'], 'kind': a['kind'], 'revision': a['revision'],
            'content': a['body'][DOCUMENT_FIELDS[a['kind']]], 'citations': a['body'].get('citations', [])}


def selected_documents(store, refs):
    if not isinstance(refs, list) or len(refs) > 5:
        raise ValueError('最多引用5份文稿')
    result, seen = [], set()
    with store.lock:
        for ref in refs:
            if not isinstance(ref, dict): raise ValueError('无效文稿引用')
            doc = document(store, ref.get('id'))
            if doc['revision'] != ref.get('revision'): raise Conflict('引用文稿已变化，请刷新后重新选择')
            if doc['id'] not in seen:
                result.append(doc); seen.add(doc['id'])
    return result


def validate_document(data):
    if not isinstance(data, dict): raise ValueError('文稿必须是对象')
    title, content = data.get('title'), data.get('content')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100: raise ValueError('标题需要1至100字')
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 18000: raise ValueError('正文需要1至18000字')
    return {'title': title.strip(), 'content': content.strip()}


def _write(store, data, reason):
    a = asset(store, data.get('id')); doc = validate_document(data)
    if a.get('kind') not in DOCUMENT_FIELDS: raise ValueError('原始文件不能覆盖修改')
    if data.get('revision') != a['revision']: raise Conflict('文稿已更新，未保存内容仍保留；请重新打开最新版本')
    if a['kind'] in ('career', 'career_review') and data.get('confirmed') is not True:
        raise ValueError('请确认没有新增未经证实的经历事实')
    body = {**a['body'], DOCUMENT_FIELDS[a['kind']]: doc['content']}
    if a['kind'] == 'wiki': body['title'] = doc['title']
    revision = a['revision'] + 1; encoded = json.dumps(body, ensure_ascii=False)
    store.db.execute('UPDATE artifacts SET title=?,body=?,revision=?,updated=? WHERE id=?', (doc['title'], encoded, revision, now(), a['id']))
    store.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)', (uid('ver'), a['id'], revision, encoded, reason, now()))
    return a['id']


def save_document(store, data):
    with store.lock:
        try:
            ident = _write(store, data, '用户编辑文稿')
            store.db.commit()
        except Exception:
            store.db.rollback(); raise
        return store.artifact(ident)


def create_document(store, data):
    """Create a manual Markdown asset, optionally as an editable source copy."""
    with store.lock:
        try:
            validate_destination(store, data)
            title = data.get('title', '未命名文稿')
            content = data.get('content', '# 未命名文稿')
            doc = validate_document({'title': title, 'content': content})
            source_id = data.get('source_id')
            if source_id:
                source = next((s for s in store.sources() if s['id'] == source_id and not s['archived']), None)
                if not source:
                    raise Conflict('原文件已不可用，请刷新后重试')
                if source['content'] != data.get('source_content'):
                    raise Conflict('原文件内容已经变化，请重新打开')
            ident = uid('wiki')
            body = {'title': doc['title'], 'content': doc['content'], 'summary': doc['content'][:180],
                    'tags': [], 'links': [], 'citations': [], 'diagram': []}
            if source_id:
                body['source_id'] = source_id
            encoded = json.dumps(body, ensure_ascii=False)
            store.db.execute('INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)',
                             (ident, doc['title'], 'wiki', encoded, 1, now()))
            store.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',
                             (uid('ver'), ident, 1, encoded, '用户创建文稿', now()))
            record_destination(store, ident, data, 'manual', source_id or '')
            store.db.commit()
            return store.artifact(ident)
        except Exception:
            store.db.rollback()
            raise


def approve_document(store, job, edits):
    p = job['payload']; target = p['document_target']
    try:
        ident = _write(store, {**p['proposal']['document'], 'id': target['id'], 'revision': target['revision'],
                              'confirmed': edits.get('confirmed')}, '确认AI修改建议')
        p.update(published_id=ident, approved_revision=target['revision']+1)
        record_destination(store, ident, edits, 'ai', job['id'])
        store.db.execute("UPDATE jobs SET status='approved',payload=?,updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now(), job['id']))
        store.db.commit()
    except Exception:
        store.db.rollback(); raise
    return store.artifact(ident)


def category_order(store,data):
    with store.lock:
        ids=data.get('ids')
        if not isinstance(ids,list) or len(ids)!=len(set(ids)):raise ValueError('无效目录顺序')
        rows=[store.db.execute('SELECT * FROM asset_categories WHERE id=?',(i,)).fetchone() for i in ids]
        if not rows or any(not r for r in rows):raise ValueError('文件夹不存在')
        if any((r['scope'],r['parent_id'])!=(rows[0]['scope'],rows[0]['parent_id']) for r in rows):raise ValueError('只能调整同级文件夹顺序')
        for index,ident in enumerate(ids):store.db.execute('UPDATE asset_categories SET position=? WHERE id=?',(index,ident))
        store.db.commit()
        return {'ok':True}
