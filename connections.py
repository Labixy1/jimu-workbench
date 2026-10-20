"""Read-only GitHub import and personal website shortcuts, not autonomous tools."""
import base64
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from domain import Conflict, uid

GROUPS = ('设计', 'Vibe Coding', 'MCP与连接器', '技能与Skill Hub', '产品研究', '模型与评测', 'AI官网', '其他')
DEFAULT_LINKS = [
    ('stitch', 'Stitch', 'https://stitch.withgoogle.com/', '设计', '用自然语言探索界面设计'),
    ('mobbin', 'Mobbin', 'https://mobbin.com/', '设计', '查看真实产品的界面与交互参考'),
    ('pageflows', 'Page Flows', 'https://pageflows.com/', '产品研究', '参考登录、引导、订阅等用户流程'),
    ('doubao', '豆包', 'https://www.doubao.com/', 'AI官网', '体验豆包，观察对话与任务交互'),
    ('deepseek', 'DeepSeek', 'https://www.deepseek.com/', 'AI官网', '访问 DeepSeek 官方产品与信息'),
    ('openai', 'OpenAI', 'https://openai.com/', 'AI官网', '了解官方产品与更新'),
    ('anthropic', 'Claude / Anthropic', 'https://www.anthropic.com/', 'AI官网', '了解 Claude 产品与官方动态'),
    ('36kr', '36氪', 'https://36kr.com/', '产品研究', '浏览行业报道与产品资讯'),
]


CURATED_LINKS = [('v0', 'v0', 'https://v0.app/', 'Vibe Coding', '通过对话生成界面和前端代码，适合快速做原型'), ('lovable', 'Lovable', 'https://lovable.dev/', 'Vibe Coding', '通过自然语言搭建网站与应用原型'), ('bolt', 'Bolt', 'https://bolt.new/', 'Vibe Coding', '在浏览器里生成、运行和迭代应用'), ('replit', 'Replit', 'https://replit.com/', 'Vibe Coding', '在线开发、运行与部署应用'), ('cursor', 'Cursor', 'https://cursor.com/', 'Vibe Coding', 'AI 编程编辑器，参考代码协作和 Agent 交互'), ('opencode', 'OpenCode', 'https://opencode.ai/', 'Vibe Coding', '开源编程 Agent，查看框架、文档与实现'), ('mcp-registry', 'MCP Registry', 'https://registry.modelcontextprotocol.io/', 'MCP与连接器', '官方 MCP 注册目录，查找服务器与接入信息'), ('mcp-servers', 'MCP Servers', 'https://github.com/modelcontextprotocol/servers', 'MCP与连接器', '官方参考服务器与社区集成清单'), ('smithery', 'Smithery', 'https://smithery.ai/', 'MCP与连接器', '发现 MCP 服务器并查看工具接入方式'), ('glama', 'Glama MCP', 'https://glama.ai/mcp/servers', 'MCP与连接器', '浏览 MCP 目录、分类和服务器信息'), ('browseruse', 'Browser Use', 'https://browser-use.com/', 'MCP与连接器', '浏览器 Agent 项目，了解网页操作与自动化'), ('skills-sh', 'skills.sh', 'https://skills.sh/', '技能与Skill Hub', '查找可复用的 Agent Skills 与安装说明'), ('anthropic-skills', 'Anthropic Skills', 'https://github.com/anthropics/skills', '技能与Skill Hub', '官方技能示例，参考 SKILL.md 与能力封装'), ('agentskills', 'Agent Skills', 'https://agentskills.io/', '技能与Skill Hub', '查看 Agent Skills 开放格式与集成规范'), ('skillsmp', 'SkillsMP', 'https://skillsmp.com/', '技能与Skill Hub', '按任务搜索社区技能，使用前检查来源和权限'), ('shadcn', 'shadcn/ui', 'https://ui.shadcn.com/', '设计', '可复用界面组件，适合构建简洁产品界面'), ('radix', 'Radix UI', 'https://www.radix-ui.com/', '设计', '无障碍交互组件，参考弹窗、菜单和选择器'), ('awwwards', 'Awwwards', 'https://www.awwwards.com/', '设计', '网站设计作品，参考视觉、布局与动效'), ('godly', 'Godly', 'https://godly.website/', '设计', '精选网站设计，寻找首页与界面灵感'), ('figma-community', 'Figma Community', 'https://www.figma.com/community', '设计', '查找设计资源、组件和社区模板'), ('producthunt', 'Product Hunt', 'https://www.producthunt.com/', '产品研究', '发现新产品，观察定位、卖点与用户反馈'), ('huggingface', 'Hugging Face', 'https://huggingface.co/', '模型与评测', '了解开源模型、数据集与演示应用'), ('openrouter', 'OpenRouter', 'https://openrouter.ai/', '模型与评测', '比较模型接入信息、价格与使用方式'), ('artificialanalysis', 'Artificial Analysis', 'https://artificialanalysis.ai/', '模型与评测', '参考模型质量、速度与成本评测'), ('lmarena', 'Arena', 'https://arena.ai/', '模型与评测', '参考用户偏好驱动的模型对比与榜单')]

def init(store):
    with store.lock:
        store.db.execute('CREATE TABLE IF NOT EXISTS tool_links(id TEXT PRIMARY KEY,body TEXT,revision INTEGER)')
        store.db.execute('CREATE TABLE IF NOT EXISTS connections_meta(key TEXT PRIMARY KEY,value TEXT)')
        if not store.db.execute("SELECT value FROM connections_meta WHERE key='links_seeded'").fetchone():
            for ident, name, url, group, description in DEFAULT_LINKS:
                body = dict(id=ident, name=name, url=url, group=group, description=description)
                store.db.execute('INSERT OR IGNORE INTO tool_links VALUES(?,?,1)', (ident, json.dumps(body, ensure_ascii=False)))
            store.db.execute("INSERT INTO connections_meta VALUES('links_seeded','1')")
        if not store.db.execute("SELECT value FROM connections_meta WHERE key='curated_links_v1'").fetchone():
            existing={json.loads(r['body'])['url'] for r in store.db.execute('SELECT body FROM tool_links')}
            for ident,name,url,group,description in CURATED_LINKS:
                if url in existing:continue
                body=dict(id=ident,name=name,url=url,group=group,description=description)
                store.db.execute('INSERT OR IGNORE INTO tool_links VALUES(?,?,1)',(ident,json.dumps(body,ensure_ascii=False)))
            store.db.execute("INSERT INTO connections_meta VALUES('curated_links_v1','1')")
        store.db.commit()


def links(store):
    with store.lock:
        return [{**json.loads(r['body']), 'revision': r['revision']} for r in store.db.execute('SELECT * FROM tool_links ORDER BY rowid')]


def safe_link(url):
    if not isinstance(url, str) or len(url) > 2000: raise ValueError('网址无效或过长')
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请填写不含账户凭证的 HTTP(S) 网址')
    return parsed.geturl()


def save_link(store, data):
    name, description = data.get('name'), data.get('description', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60: raise ValueError('网站名称需要1至60字')
    if not isinstance(description, str) or len(description) > 200: raise ValueError('说明最多200字')
    group = data.get('group', '其他')
    if group not in GROUPS: raise ValueError('无效网站分组')
    url = safe_link(data.get('url'))
    with store.lock:
        old = next((v for v in links(store) if v['id'] == data.get('id')), None)
        if data.get('id') and (not old or old['revision'] != data.get('revision')): raise Conflict('网站已变化，请重新打开编辑')
        if not old and len(links(store)) >= 40: raise ValueError('最多保存40个常用网站')
        ident = old['id'] if old else uid('link')
        body = dict(id=ident, name=name.strip(), url=url, group=group, description=description.strip())
        revision = old['revision']+1 if old else 1
        store.db.execute('INSERT OR REPLACE INTO tool_links VALUES(?,?,?)', (ident, json.dumps(body, ensure_ascii=False), revision))
        store.db.commit()
        return {**body, 'revision': revision}


def remove_link(store, data):
    with store.lock:
        row = store.db.execute('SELECT revision FROM tool_links WHERE id=?', (data.get('id'),)).fetchone()
        if not row or row['revision'] != data.get('revision'): raise Conflict('网站已变化，请刷新后重试')
        store.db.execute('DELETE FROM tool_links WHERE id=?', (data['id'],)); store.db.commit()
        return {'removed': True}


def github_repo(value):
    if not isinstance(value, str): raise ValueError('请填写 GitHub 仓库地址或 owner/repo')
    value = value.strip()
    if value.startswith('https://'):
        p = urllib.parse.urlsplit(value)
        if p.netloc != 'github.com' or p.query or p.fragment or p.username or p.password:
            raise ValueError('仅支持 github.com 仓库根地址，不接收访问令牌或查询参数')
        value = p.path.strip('/')
    if value.endswith('.git'): value = value[:-4]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('请输入 owner/repo 或 https://github.com/owner/repo')
    owner, repo = value.split('/')
    if repo in ('.', '..'): raise ValueError('仓库名称无效')
    return owner, repo


def github_cli():
    """Use the existing local login without reading or copying its token."""
    cli = shutil.which('gh')
    if not cli: return None
    try:
        env = {**os.environ, 'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1'}
        result = subprocess.run([cli, 'auth', 'status', '--hostname', 'github.com'], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return cli if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired): return None


def github_json(path, cli=None):
    if cli:
        try:
            result = subprocess.run([cli, 'api', '--hostname', 'github.com', '--method', 'GET', path],
                                    env={**os.environ, 'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1'},
                                    capture_output=True, timeout=25)
            if result.returncode != 0: raise ValueError('GitHub 读取失败，请检查仓库权限或本机 gh 登录状态')
            raw = result.stdout
        except subprocess.TimeoutExpired: raise ValueError('GitHub 读取超时，请稍后重试') from None
    else:
        req = urllib.request.Request('https://api.github.com/'+path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Jimu-Workbench'})
        try:
            with urllib.request.urlopen(req, timeout=25) as response: raw = response.read(1500001)
        except urllib.error.HTTPError as e:
            message = '仓库或 README 不存在，或这是未授权的私有仓库' if e.code == 404 else 'GitHub 限流或权限不足' if e.code in (403,429) else 'GitHub 读取失败'
            raise ValueError(message) from None
        except (urllib.error.URLError, TimeoutError): raise ValueError('无法连接 GitHub，请检查网络') from None
    if len(raw) > 1500000: raise ValueError('GitHub 返回过大，请选择更小的文档')
    return json.loads(raw)


def github_preview(data):
    if data.get('allow_remote') is not True: raise ValueError('请确认向 GitHub 读取所选仓库')
    owner, repo = github_repo(data.get('repo')); base = 'repos/'+owner+'/'+repo
    cli = github_cli()
    try:
        metadata = github_json(base, cli)
    except ValueError as error:
        # Public raw files do not require the rate-limited GitHub REST API.
        if cli or str(error) != 'GitHub 限流或权限不足': raise
        for branch in ('main', 'master'):
            url='https://raw.githubusercontent.com/'+owner+'/'+repo+'/'+branch+'/README.md'
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Jimu-Workbench'})
                with urllib.request.urlopen(req,timeout=20) as response:
                    raw=response.read(120001)
                if len(raw)>120000:raise ValueError('README 超过12万字节，请选择片段')
                content=raw.decode('utf-8')
                if not content.strip():continue
                return {'title':f'{owner}/{repo} · README','content':'公开文件：'+url+'\n\n'+content,
                        'url':'https://github.com/'+owner+'/'+repo,'visibility':'public','private':False,
                        'auth':'public_raw','file_path':'README.md','sha':None}
            except (urllib.error.URLError, UnicodeError):continue
        raise ValueError('GitHub API受限，公开README备用入口也未读取到；请授权后重试') from None
    private = metadata.get('private') is True
    if private and data.get('allow_private') is not True:
        raise ValueError('这是私有仓库。请明确勾选允许读取私有 README 后重试；尚未读取正文')
    info = github_json(base+'/readme', cli)
    if info.get('encoding') != 'base64' or not isinstance(info.get('content'), str): raise ValueError('README 不是可读取的文本')
    if info.get('size', 0) > 120000: raise ValueError('README 超过12万字节，请手动选择片段')
    try:
        raw = base64.b64decode(''.join(info['content'].split()), validate=True)
        if len(raw) > 120000: raise ValueError('README 过长')
        content = raw.decode('utf-8')
    except (ValueError, UnicodeError): raise ValueError('README 编码不可读取，请手动导入文本') from None
    if not content.strip(): raise ValueError('README 为空，不会创建空资产')
    canonical = 'https://github.com/'+owner+'/'+repo
    header = f"仓库：{canonical}\n文件：{info.get('path','README')}\n文件版本（Git blob）：{info.get('sha','未返回')}\n\n"
    return {'title': f'{owner}/{repo} · README'[:200], 'content': header+content, 'url': canonical,
            'visibility': 'private' if private else 'public', 'private': private,
            'auth': 'local_gh' if cli else 'public', 'file_path': info.get('path'), 'sha': info.get('sha')}
