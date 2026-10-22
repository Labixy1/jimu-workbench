"""Persistent reading references and versioned snapshots of collected articles."""
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
        if 'description' not in {r['name'] for r in store.db.execute('PRAGMA table_info(reading_focus)')}:
            store.db.execute("ALTER TABLE reading_focus ADD COLUMN description TEXT NOT NULL DEFAULT ''")
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
    name=data.get('name','');kind=data.get('kind');url=data.get('url','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=60 or kind not in ('官网','公众号','小红书账号'):
        raise ValueError('请填写名称和来源类型')
    if not isinstance(url,str):raise ValueError('请填写来源地址')
    name=name.strip();url=url.strip()
    validator(url)
    with store.lock:
        ident=data.get('id') or uid('focus')
        old=store.db.execute('SELECT description FROM reading_focus WHERE id=?',(ident,)).fetchone()
        if data.get('id') and not old:
            raise Conflict('关注来源不存在')
        description=data.get('description',old['description'] if old else '')
        if not isinstance(description,str) or len(description)>160:raise ValueError('简介最多160字')
        store.db.execute('''INSERT INTO reading_focus(id,name,kind,url,description) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,kind=excluded.kind,url=excluded.url,description=excluded.description''',
            (ident,name,kind,url,description.strip()))
        store.db.commit()
        return {'id':ident}


def focus_remove(store,data):
    with store.lock:
        store.db.execute('DELETE FROM reading_focus WHERE id=?',(data.get('id'),));store.db.commit()
    return {'ok':True}


def period_start(value):
    try:
        instant=datetime.fromisoformat(value.replace('Z','+00:00'))
        date=instant.astimezone(ZoneInfo('Asia/Shanghai')).date()
        return date-timedelta(days=date.weekday())
    except (TypeError,ValueError,AttributeError):
        return None


def snapshot(store,items,weeks=1):
    """Group real articles by publication week; keep collection time truthful."""
    if type(weeks) is not int or not 1<=weeks<=3:raise ValueError('每次最多更新三期周刊')
    if not items:return None
    current=period_start(datetime.now(timezone.utc).isoformat())
    result=[]
    with store.lock:
        store.db.execute('CREATE TABLE IF NOT EXISTS reading_issue_versions(issue_id TEXT,created TEXT,body TEXT)')
        for offset in range(weeks):
            start=current-timedelta(weeks=offset);end=start+timedelta(days=6)
            candidates=[n for n in items if period_start(n.get('published_at') or n.get('fetched_at') or now())==start]
            if not candidates:continue
            # Readable articles come first; do not let a busy release feed monopolize the issue.
            def learning_priority(item):
                text=item.get('title','')+' '+item.get('excerpt','')
                return bool(item.get('topic') or re.search(r'agent|harness|模型|工作流|记忆|产品经理|设计|面经',text,re.I))
            candidates.sort(key=lambda n:(bool(n.get('content')),learning_priority(n),not 'github.com' in n.get('feed_url',''),n.get('published_at') or ''),reverse=True)
            selected=[];per_source={};seen_titles=set()
            for item in candidates:
                source=item.get('feed_url') or item.get('source_name') or item.get('url','')
                title=re.sub(r'\s+','',item.get('title','')).casefold()
                if title in seen_titles or per_source.get(source,0)>=8:continue
                selected.append(item);per_source[source]=per_source.get(source,0)+1
                seen_titles.add(title)
                if len(selected)>=24:break
            ident='reading_week_'+start.strftime('%Y%m%d')
            previous=store.db.execute('SELECT body FROM reading_issues WHERE id=?',(ident,)).fetchone()
            if previous:store.db.execute('INSERT INTO reading_issue_versions VALUES(?,?,?)',(ident,now(),previous['body']))
            body={'news':selected,'date':start.isoformat(),'period_start':start.isoformat(),'period_end':end.isoformat(),
                  'collected_at':now(),'date_rule':'按发布日期分期；没有准确发布日期的内容按本次采集周收录并保留原始时间说明。'}
            store.db.execute('INSERT OR REPLACE INTO reading_issues VALUES(?,?,?,?)',
                (ident,'阅读周刊 · '+start.strftime('%m.%d')+' — '+end.strftime('%m.%d'),now(),json.dumps(body,ensure_ascii=False)))
            result.append({'id':ident,'period_start':start.isoformat(),'period_end':end.isoformat(),'count':len(selected)})
        store.db.commit()
    return {'id':result[0]['id'],'issues':result} if result else None


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
