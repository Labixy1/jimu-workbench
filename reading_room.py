"""Persistent reading references and immutable, manually updated issue snapshots."""
import json
from domain import now, uid, Conflict
import library


def init(store):
    with store.lock:
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS reading_favorites(asset_id TEXT PRIMARY KEY,created TEXT);
        CREATE TABLE IF NOT EXISTS reading_focus(id TEXT PRIMARY KEY,name TEXT,kind TEXT,url TEXT);
        CREATE TABLE IF NOT EXISTS favorite_groups(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS reading_issues(id TEXT PRIMARY KEY,title TEXT,created TEXT,body TEXT);
        ''')
        if 'category' not in {r['name'] for r in store.db.execute('PRAGMA table_info(reading_favorites)')}:
            store.db.execute("ALTER TABLE reading_favorites ADD COLUMN category TEXT DEFAULT 'Personal Agent'")
        if 'position' not in {r['name'] for r in store.db.execute('PRAGMA table_info(reading_favorites)')}:
            store.db.execute('ALTER TABLE reading_favorites ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
        store.db.execute("CREATE TABLE IF NOT EXISTS reading_meta(key TEXT PRIMARY KEY)")
        if not store.db.execute("SELECT 1 FROM reading_meta WHERE key='groups_seeded'").fetchone():
            for name in ('Personal Agent','Harness'):
                store.db.execute('INSERT OR IGNORE INTO favorite_groups VALUES(?)',(name,))
            store.db.execute("INSERT INTO reading_meta VALUES('groups_seeded')")
        store.db.commit()


def state(store):
    with store.lock:
        visible={a['id'] for a in library.catalog(store)}
        favorites=[r['asset_id'] for r in store.db.execute('SELECT * FROM reading_favorites ORDER BY position,created DESC') if r['asset_id'] in visible]
        return {'groups':[r['name'] for r in store.db.execute('SELECT name FROM favorite_groups ORDER BY rowid')],'favorites':favorites,'favorite_categories':{r['asset_id']:r['category'] for r in store.db.execute('SELECT * FROM reading_favorites')},'focus':[dict(r) for r in store.db.execute('SELECT * FROM reading_focus ORDER BY rowid')],
                'issues':[{**dict(r),'body':json.loads(r['body'])} for r in store.db.execute('SELECT * FROM reading_issues ORDER BY created DESC')]}


def favorite(store,data):
    with store.lock:
        asset=library.asset(store,data.get('id'))
        if data.get('remove') is True:
            store.db.execute('DELETE FROM reading_favorites WHERE asset_id=?',(asset['id'],))
        else:
            category=data.get('category','')
            if category=='all':category=''
            if category and not store.db.execute('SELECT 1 FROM favorite_groups WHERE name=?',(category,)).fetchone():raise Conflict('收藏分类已删除，请重新选择')
            store.db.execute('INSERT OR REPLACE INTO reading_favorites(asset_id,created,category) VALUES(?,?,?)',(asset['id'],now(),category))
        store.db.commit()
        return {'ok':True}


def focus_save(store,data,validator):
    name=data.get('name','').strip();kind=data.get('kind');url=data.get('url','').strip()
    if not 1<=len(name)<=60 or kind not in ('官网','公众号','小红书账号'):
        raise ValueError('请填写名称和来源类型')
    validator(url)
    with store.lock:
        ident=data.get('id') or uid('focus')
        if data.get('id') and not store.db.execute('SELECT 1 FROM reading_focus WHERE id=?',(ident,)).fetchone():
            raise Conflict('关注来源不存在')
        store.db.execute('INSERT OR REPLACE INTO reading_focus VALUES(?,?,?,?)',(ident,name,kind,url))
        store.db.commit()
        return {'id':ident}


def focus_remove(store,data):
    with store.lock:
        store.db.execute('DELETE FROM reading_focus WHERE id=?',(data.get('id'),));store.db.commit()
    return {'ok':True}


def snapshot(store,items):
    """Archive fetched metadata only; this is not an AI-authored publication."""
    if not items:return None
    from datetime import datetime
    from zoneinfo import ZoneInfo
    date=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    with store.lock:
        ident='reading_'+date.replace('-','')
        body={'news':items[:80], 'date':date}
        store.db.execute('INSERT OR REPLACE INTO reading_issues VALUES(?,?,?,?)',
                         (ident,'阅读周刊 · '+date,now(),json.dumps(body,ensure_ascii=False)))
        store.db.commit()
    return {'id':ident}


def favorite_order(store,data):
    ids=data.get('ids')
    if not isinstance(ids,list) or len(ids)>500 or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):raise ValueError('无效收藏顺序')
    with store.lock:
        for ident in ids:
            library.asset(store,ident)
            if not store.db.execute('SELECT 1 FROM reading_favorites WHERE asset_id=?',(ident,)).fetchone():raise Conflict('收藏已变化，请刷新')
        for index,ident in enumerate(ids):store.db.execute('UPDATE reading_favorites SET position=? WHERE asset_id=?',(index,ident))
        store.db.commit()
    return {'ok':True}


def favorite_group(store,data):
    name=data.get('name','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=40 or name.strip() in ('全部','all'):raise ValueError('分类名称需要1至40字，不能使用全部')
    name=name.strip()
    with store.lock:
        if data.get('remove') is True:
            store.db.execute('UPDATE reading_favorites SET category=? WHERE category=?',('',name))
            store.db.execute('DELETE FROM favorite_groups WHERE name=?',(name,))
        else:
            if store.db.execute('SELECT 1 FROM favorite_groups WHERE name=?',(name,)).fetchone():raise ValueError('分类名称已存在')
            store.db.execute('INSERT INTO favorite_groups VALUES(?)',(name,))
        store.db.commit()
    return {'ok':True}
