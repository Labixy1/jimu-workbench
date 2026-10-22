"""Portable Skill packages. Importing a package never runs its scripts."""
import base64
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import PurePosixPath

MAX_BYTES = 2 * 1024 * 1024
MAX_FILES = 64
MAX_INSTRUCTIONS = 24000
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def _scalar(value):
    value = value.strip()
    if value.startswith('"'):
        try:
            result = json.loads(value)
            if isinstance(result, str):
                return result
        except ValueError:
            pass
        raise ValueError('SKILL.md 的双引号字段需要使用有效的字符串')
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise ValueError('SKILL.md 的引号未闭合')
        return value[1:-1].replace("''", "'")
    value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
    if not value or value[0] in '[{&*!>|' or re.search(r':\s', value) or value.lower() in ('true','false','null','~') or re.fullmatch(r'[-+]?\d+(?:\.\d+)?',value):
        raise ValueError('name 和 description 必须是文本；含冒号时请用双引号包住')
    return value


def parse(text):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_INSTRUCTIONS:
        raise ValueError('SKILL.md 不能为空，最多24000字')
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    match = re.match(r'\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)', text, re.S)
    if not match:
        raise ValueError('SKILL.md 顶部需要 --- 包围的 name 和 description')
    lines = match[1].splitlines()
    values = {}
    for index, line in enumerate(lines):
        field = re.match(r'^(name|description):[ \t]*(.*)$', line)
        if not field:
            continue
        key, value = field.groups()
        if key in values:
            raise ValueError('SKILL.md 的 ' + key + ' 不能重复')
        if value.strip() in ('|', '|-', '|+', '>', '>-', '>+'):
            block = []
            for following in lines[index + 1:]:
                if following.strip() and not following.startswith((' ', '\t')):
                    break
                block.append(following.strip())
            values[key] = (' ' if value.strip().startswith('>') else '\n').join(block).strip()
        else:
            values[key] = _scalar(value)
    name = values.get('name', '')
    if not 1 <= len(name) <= 64 or not NAME.fullmatch(name):
        raise ValueError('name 请使用小写英文、数字和连字符，最多64个字符')
    if not 1 <= len(values.get('description', '')) <= 1024:
        raise ValueError('description 需要说明技能何时使用，最多1024字')
    body = text[match.end():].strip()
    if not body:
        raise ValueError('请在 SKILL.md 正文写入执行方法')
    heading = re.search(r'^#\s+(.+)$', body, re.M)
    return {**values, 'title': heading[1].strip()[:60] if heading else name,
            'skill_md': text, 'body': body}


def document(instructions, name, description):
    if instructions.lstrip('\ufeff').startswith('---'):
        return parse(instructions)['skill_md']
    # Legacy user-authored rules stay unchanged in storage; export them as a Skill.
    text = ('---\nname: ' + name.replace('_', '-') + '\ndescription: ' +
            json.dumps(description, ensure_ascii=False) + '\n---\n\n' + instructions)
    return parse(text)['skill_md']


def safe_path(name):
    if not isinstance(name, str) or not name or len(name) > 240 or '\\' in name or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('技能包包含无效路径')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') or p.startswith('.') or ':' in p for p in name.split('/')):
        raise ValueError('技能包不能包含隐藏文件、绝对路径或上级路径')
    if path.name.lower() == 'skill.md':
        raise ValueError('一个技能包只允许根目录的一份 SKILL.md')
    return name


def resources(items):
    if not isinstance(items, list) or len(items) >= MAX_FILES:
        raise ValueError('一个技能包最多64个文件')
    result, seen, total = [], set(), 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('无效技能资源')
        path = safe_path(item.get('path'))
        if path.casefold() in seen:
            raise ValueError('技能包包含重复路径：' + path)
        try:
            raw = base64.b64decode(item.get('content', ''), validate=True)
        except (TypeError, ValueError):
            raise ValueError('技能资源内容无效') from None
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError('技能包解压后不能超过2MB')
        result.append({'path': path, 'content': base64.b64encode(raw).decode(), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest()})
        seen.add(path.casefold())
    if any(str(parent).casefold() in seen for item in result for parent in PurePosixPath(item['path']).parents if str(parent)!='.'):
        raise ValueError('技能包的文件与文件夹路径不能冲突')
    return sorted(result, key=lambda i: i['path'])


def preview(filename, encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError):
        raise ValueError('技能文件无法读取') from None
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('技能文件大小需要在2MB以内')
    files = []
    if filename.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = [e for e in archive.infolist() if not e.is_dir() and
                           not e.filename.startswith('__MACOSX/') and PurePosixPath(e.filename).name != '.DS_Store']
                if len(entries) > MAX_FILES or sum(e.file_size for e in entries) > MAX_BYTES:
                    raise ValueError('技能包最多64个文件，解压后不超过2MB')
                mains = [e for e in entries if PurePosixPath(e.filename).name == 'SKILL.md']
                if len(mains) != 1:
                    raise ValueError('请选择只包含一个 Skill 的 ZIP，需有一份 SKILL.md')
                main = mains[0]
                prefix = main.filename[:-len('SKILL.md')]
                # Check the archive prefix too; it is not trusted just because it is stripped.
                if prefix:
                    safe_path(prefix.rstrip('/') + '/placeholder')
                text = None
                for entry in entries:
                    if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                        raise ValueError('技能包不支持符号链接或加密文件')
                    if not entry.filename.startswith(prefix):
                        raise ValueError('所有资源需要放在同一个技能文件夹内')
                    name = entry.filename[len(prefix):]
                    value = archive.read(entry)
                    if entry == main:
                        text = value.decode('utf-8-sig')
                    else:
                        files.append({'path': safe_path(name), 'content': base64.b64encode(value).decode()})
        except (zipfile.BadZipFile, UnicodeError):
            raise ValueError('无法读取技能包，请使用有效 ZIP 和 UTF-8 编码的 SKILL.md') from None
    elif filename.lower().endswith('.md'):
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError:
            raise ValueError('SKILL.md 请使用 UTF-8 编码') from None
    else:
        raise ValueError('请选择 SKILL.md 或包含技能文件夹的 ZIP')
    parsed = parse(text)
    return {k: parsed[k] for k in ('name', 'title', 'description', 'skill_md')} | {'resources': resources(files)}


def export(skill):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        prefix = skill['name'] + '/'
        archive.writestr(prefix + 'SKILL.md', skill['skill_md'])
        for file in resources(skill.get('resources', [])):
            archive.writestr(prefix + file['path'], base64.b64decode(file['content']))
    return output.getvalue()


def materialize(directory, skills):
    """Write only immutable, validated job snapshots, never uploaded config/plugins."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = []
    for skill in skills:
        parsed = parse(skill['skill_md'])
        folder = directory / parsed['name']
        folder.mkdir(exist_ok=True, mode=0o700)
        files = [('SKILL.md', parsed['skill_md'].encode())]
        files += [(r['path'], base64.b64decode(r['content'])) for r in resources(skill.get('resources', []))]
        for name, data in files:
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(data)
            path.chmod(0o600)
            paths.append(str(path.resolve()))
    return paths
