"""Explicit task routing, not autonomous OpenCode skill discovery."""
import hashlib
import json
from pathlib import Path
from domain import Conflict, uid

ROOT = Path(__file__).resolve().parent / 'skills'
TASKS = {'experience': 'experience-writing', 'tailor': 'jd-review', 'wiki': 'knowledge-compilation', 'weekly': 'weekly-reading'}
PREVIOUS_DEFAULTS = {'knowledge-compilation': '77ee419ce1707058e8dea02ad09982ab17a142ce1e53cbadb668833e88b95d92', 'experience-writing': 'b5fcf889443648e6e28e161b626b4f6dc7d5c59645e15994e9020205dd01fece', 'jd-review': 'c9649fc920218c565496853fdeee9815dc807ad1cc8397c22735b281873c8320', 'weekly-reading': ['5a529093164b9e1ea0ab4a11f1999266c79e067cd9ab085b8c6fe3b4f1c4d675', 'c4de01b1ab7c16fda81ca94dbf3ded5bd9dff7bc70deb8154e5303c4e2fcae27']}
LABELS = {'experience-writing': ('梳理经历', '从本人说明和附件提取事实，整理经历或简历。'),
          'board-generation': ('生成画板', '把材料整理为流程图，预览编辑后保存为画板资产。'),
          'jd-review': ('对照岗位', '基于已确认经历，诊断JD差距并改写。'),
          'knowledge-compilation': ('整理材料', '将选定材料整理成有来源的Markdown文稿。'),
          'weekly-reading': ('阅读周报', '按指定网站与主题整理阅读周报，由周刊页面手动触发。')}


def task_method(kind, store=None):
    name = TASKS.get(kind)
    if not name:
        return None
    if store is not None:
        return next((s for s in all_skills(store) if s['id'] == name), None)
    text = (ROOT / name / 'SKILL.md').read_text()
    return {'name': name, 'instructions': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def init(store):
    with store.lock:
        store.db.execute('CREATE TABLE IF NOT EXISTS managed_skills(id TEXT PRIMARY KEY,body TEXT,revision INTEGER)')
        if 'archived' not in {r['name'] for r in store.db.execute('PRAGMA table_info(managed_skills)')}:
            store.db.execute('ALTER TABLE managed_skills ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
        for name, (title, description) in LABELS.items():
            text = (ROOT / name / 'SKILL.md').read_text()
            body = {'id': name, 'name': name, 'title': title, 'description': description, 'instructions': text, 'builtin': True}
            existing=store.db.execute('SELECT body,revision FROM managed_skills WHERE id=?',(name,)).fetchone()
            if existing:
                previous=json.loads(existing['body'])
                hashes=PREVIOUS_DEFAULTS.get(name, [])
                if isinstance(hashes, str): hashes=[hashes]
                if hashlib.sha256(previous['instructions'].encode()).hexdigest() in hashes:
                    store.db.execute('UPDATE managed_skills SET body=?,revision=? WHERE id=?',(json.dumps(body,ensure_ascii=False),existing['revision']+1,name))
            else:
                store.db.execute('INSERT INTO managed_skills(id,body,revision) VALUES(?,?,1)', (name, json.dumps(body, ensure_ascii=False)))
        store.db.commit()


def all_skills(store):
    with store.lock:
        return [{**json.loads(r['body']), 'revision': r['revision'],
                 'sha256': hashlib.sha256(json.loads(r['body'])['instructions'].encode()).hexdigest()}
                for r in store.db.execute('SELECT * FROM managed_skills WHERE archived=0 ORDER BY rowid')]


def get(store, ident):
    skill = next((s for s in all_skills(store) if s['id'] == ident), None)
    if not skill: raise ValueError('技能不存在')
    return skill


def save(store, data):
    for key, limit in [('title', 60), ('description', 300), ('instructions', 6000)]:
        if not isinstance(data.get(key), str) or not 1 <= len(data[key].strip()) <= limit:
            raise ValueError('技能标题、用途和规则不能为空或过长')
    with store.lock:
        ident = data.get('id'); old = get(store, ident) if ident else None
        if old and old['revision'] != data.get('revision'): raise Conflict('技能已变化，请重新打开编辑')
        ident = ident or uid('skill'); revision = old['revision'] + 1 if old else 1
        body = {k: data[k].strip() for k in ('title', 'description', 'instructions')}
        body.update(id=ident, name=ident, builtin=old['builtin'] if old else False)
        store.db.execute('INSERT OR REPLACE INTO managed_skills(id,body,revision) VALUES(?,?,?)', (ident, json.dumps(body, ensure_ascii=False), revision))
        store.db.commit()
        return get(store, ident)


def remove(store, data):
    with store.lock:
        skill = get(store, data.get('id'))
        if skill['revision'] != data.get('revision'):
            raise Conflict('技能已变化，请刷新后重试')
        store.db.execute('UPDATE managed_skills SET archived=1,revision=revision+1 WHERE id=?', (skill['id'],))
        store.db.commit()
        return {'removed': True}


def selected(store, refs):
    if not isinstance(refs, list): raise ValueError('无效技能引用')
    result, seen = [], set()
    for ref in refs:
        if not isinstance(ref, dict): raise ValueError('无效技能引用')
        skill = get(store, ref.get('id'))
        if skill['revision'] != ref.get('revision'): raise Conflict('技能已变化，请刷新后重新选择')
        if skill['id'] not in seen: result.append(skill); seen.add(skill['id'])
    return result
