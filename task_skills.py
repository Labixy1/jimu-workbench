"""Versioned Skill packages, with legacy task adapters kept for saved workflows."""
import hashlib
import json
import base64
from pathlib import Path
from domain import Conflict, uid
import skill_packages

ROOT = Path(__file__).resolve().parent / 'skills'
TASKS = {'experience': 'experience-writing', 'tailor': 'jd-review', 'wiki': 'knowledge-compilation', 'weekly': 'weekly-reading'}
PREVIOUS_DEFAULTS = {'knowledge-compilation': '77ee419ce1707058e8dea02ad09982ab17a142ce1e53cbadb668833e88b95d92', 'experience-writing': 'b5fcf889443648e6e28e161b626b4f6dc7d5c59645e15994e9020205dd01fece', 'jd-review': 'c9649fc920218c565496853fdeee9815dc807ad1cc8397c22735b281873c8320', 'weekly-reading': ['5a529093164b9e1ea0ab4a11f1999266c79e067cd9ab085b8c6fe3b4f1c4d675', 'c4de01b1ab7c16fda81ca94dbf3ded5bd9dff7bc70deb8154e5303c4e2fcae27']}
PREVIOUS_DEFAULTS['knowledge-compilation'] = [PREVIOUS_DEFAULTS['knowledge-compilation'], '09df0281adecea1520d45816df5c7c3afe42ae26bdb09f0970fb1cbc2d02dd7b']
PREVIOUS_DEFAULTS['board-generation'] = '91add3a8490aa7ccb4e941fb8a65c824397fd1adf683137d19abd3c1540fee63'
for _name, _hash in {
    'board-generation':'0efe78e405086cea508581af4306293e888d097622f8b04019e1f89224bbad7c',
    'experience-writing':'b01ce44d4fd5585b8627fafcb8a068f1a2046671f0bf40186c2896993fca605c',
    'jd-review':'a9587347a5f08ebc832d4415e7b89b2013df2b7adcca0db9a83139efb80eeb9b',
    'knowledge-compilation':'388f439e653a882b2000f78ed221efeeea32c81657dd23e44efc170e44a4c9c4',
    'weekly-reading':'ec8884b9bfc40d443739880c0254ee728d217d63bad5935fa5f2a3ade09bf059',
}.items():
    _previous=PREVIOUS_DEFAULTS.get(_name,[])
    PREVIOUS_DEFAULTS[_name]=([_previous] if isinstance(_previous,str) else _previous)+[_hash]
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
            files=[{'path':str(path.relative_to(ROOT/name)),'content':base64.b64encode(path.read_bytes()).decode()}
                   for path in (ROOT/name).rglob('*') if path.is_file() and path.name!='SKILL.md']
            body = {'id': name, 'name': name, 'title': title, 'description': description, 'instructions': text, 'builtin': True,
                    'resources':skill_packages.resources(files)}
            existing=store.db.execute('SELECT body,revision FROM managed_skills WHERE id=?',(name,)).fetchone()
            if existing:
                previous=json.loads(existing['body'])
                hashes=PREVIOUS_DEFAULTS.get(name, [])
                if isinstance(hashes, str): hashes=[hashes]
                candidates={hashlib.sha256(value.encode()).hexdigest() for value in
                            (previous['instructions'],previous['instructions'].rstrip(),previous['instructions'].rstrip()+'\n')}
                if candidates.intersection(hashes):
                    store.db.execute('UPDATE managed_skills SET body=?,revision=? WHERE id=?',(json.dumps(body,ensure_ascii=False),existing['revision']+1,name))
            else:
                store.db.execute('INSERT INTO managed_skills(id,body,revision) VALUES(?,?,1)', (name, json.dumps(body, ensure_ascii=False)))
        store.db.commit()


def all_skills(store):
    with store.lock:
        result = []
        for row in store.db.execute('SELECT * FROM managed_skills WHERE archived=0 ORDER BY rowid'):
            body = json.loads(row['body'])
            text = skill_packages.document(body['instructions'], body['name'], body['description'])
            parsed = skill_packages.parse(text)
            result.append({**body, 'name': parsed['name'], 'description': parsed['description'],
                           'skill_md': text, 'resources': body.get('resources', []), 'revision': row['revision'],
                           'sha256': hashlib.sha256(text.encode()).hexdigest()})
        return result


def catalog(store):
    return [{'id': s['id'], 'name': s['name'], 'title': s['title'], 'description': s['description'],
             'revision': s['revision'], 'files': ['SKILL.md'] + [r['path'] for r in s['resources']]}
            for s in all_skills(store)]


def get(store, ident):
    skill = next((s for s in all_skills(store) if s['id'] == ident), None)
    if not skill: raise ValueError('技能不存在')
    return skill


def save(store, data):
    instructions = data.get('instructions', data.get('skill_md'))
    if not isinstance(instructions, str) or not 1 <= len(instructions.strip()) <= skill_packages.MAX_INSTRUCTIONS:
        raise ValueError('请填写 SKILL.md，最多24000字')
    with store.lock:
        ident = data.get('id'); old = get(store, ident) if ident else None
        if old and old['revision'] != data.get('revision'): raise Conflict('技能已变化，请重新打开编辑')
        ident = ident or uid('skill'); revision = old['revision'] + 1 if old else 1
        text = skill_packages.document(instructions, data.get('name') or (old or {}).get('name') or ident,
                                       data.get('description') or (old or {}).get('description') or '')
        parsed = skill_packages.parse(text)
        title = data.get('title', parsed['title'])
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
            raise ValueError('技能名称需要在1至60字之间')
        if any(s['name'] == parsed['name'] and s['id'] != ident for s in all_skills(store)):
            raise Conflict('已安装同名 Skill，请编辑已有技能，或修改 name 后再导入')
        files = skill_packages.resources(data.get('resources', (old or {}).get('resources', [])))
        body = {'title': title.strip(), 'description': parsed['description'], 'instructions': instructions,
                'resources': files, 'id': ident, 'name': parsed['name'], 'builtin': old['builtin'] if old else False}
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
        if skill['id'] not in seen:
            # Only an explicitly referenced Skill's instructions enter the initial prompt.
            result.append({**skill, 'instructions': skill['skill_md']})
            seen.add(skill['id'])
    return result


def prompt_skills(skills):
    return [{k: s[k] for k in ('id', 'name', 'title', 'description', 'instructions', 'revision') if k in s}
            for s in skills]
