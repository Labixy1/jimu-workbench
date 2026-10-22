"""Fixed official MCP adapters; secrets stay in OpenCode's private runtime."""
import json
import shutil
import sys
from pathlib import Path

SERVERS = {
    'github': {'type': 'remote', 'url': 'https://api.githubcopilot.com/mcp/', 'headers': {'X-MCP-Readonly': 'true'}, 'enabled': True, 'timeout': 30000},
    'browser_use': {'type': 'local', 'command': [str(Path(__file__).resolve().parent / '.runtime/browser-use-env/bin/browser-use'), '--mcp'], 'environment': {'ANONYMIZED_TELEMETRY': 'false'}, 'enabled': True, 'timeout': 60000},
}


def config(engine):
    path = Path(engine.directory) / 'mcp-connections.json'
    return json.loads(path.read_text()) if path.exists() else {}


def connect(engine, name):
    if not engine: raise ValueError('Agent 引擎未启动，请重启积木')
    if name not in SERVERS: raise ValueError('未知连接器')
    current = config(engine)
    current[name] = dict(SERVERS[name])
    if name=='github':
        secret=Path(engine.directory)/'github-mcp-token'
        if secret.exists():current[name].update(headers={**current[name].get('headers',{}),'Authorization':'Bearer '+secret.read_text().strip()},oauth=False)
    path = Path(engine.directory) / 'mcp-connections.json'
    path.write_text(json.dumps(current)); path.chmod(0o600)
    project=Path(engine.directory)/'opencode.json'
    if project.exists():
        saved=json.loads(project.read_text());saved['mcp']=current
        project.write_text(json.dumps(saved));project.chmod(0o600)
    return engine.call('/mcp', {'name': name, 'config': current[name]}, timeout=90)


def connect_github_login(engine):
    if not engine: raise ValueError('Agent 引擎未启动，请重启积木')
    import connections
    if not connections.github_cli(): raise ValueError('请先在本机运行 gh auth login 完成 GitHub 登录')
    entry = {'type': 'local', 'command': [sys.executable, str(Path(__file__).with_name('github_mcp_bridge.py'))],
             'enabled': True, 'timeout': 45000}
    current = config(engine)
    current['github'] = entry
    path = Path(engine.directory) / 'mcp-connections.json'
    path.write_text(json.dumps(current)); path.chmod(0o600)
    project = Path(engine.directory) / 'opencode.json'
    if project.exists():
        saved = json.loads(project.read_text()); saved['mcp'] = current
        project.write_text(json.dumps(saved)); project.chmod(0o600)
    return engine.call('/mcp', {'name': 'github', 'config': entry}, timeout=90)


def status(engine):
    if not engine: return {}
    try: return engine.call('/mcp', timeout=10)
    except Exception: return {'github': {'status': 'failed', 'error': '引擎暂不可用，请重试'},
                              'browser_use': {'status': 'failed', 'error': '引擎暂不可用，请重试'}}


def save_github_token(engine, token):
    if not engine: raise ValueError('Agent 引擎未启动，请重启积木')
    if not isinstance(token,str) or not 10<=len(token.strip())<=500 or any(c.isspace() for c in token.strip()):
        raise ValueError('请填写有效 GitHub Token')
    path=Path(engine.directory)/'github-mcp-token'
    path.write_text(token.strip());path.chmod(0o600)
    return connect(engine,'github')


def test_github(data, engine=None):
    if data.get('allow_remote') is not True: raise ValueError('请允许读取公开仓库进行连接测试')
    from mcp_runtime import StdioMCP
    command=[sys.executable,str(Path(__file__).with_name('github_mcp_bridge.py'))]
    if engine and config(engine).get('github',{}).get('type')=='remote':
        secret=Path(engine.directory)/'github-mcp-token'
        if not secret.is_file():raise ValueError('请先完成 GitHub 授权再测试读取')
        command.extend(['--token-file',str(secret)])
    client = StdioMCP(command)
    try:
        text = client.call('get_file_contents', {'owner': 'browser-use', 'repo': 'browser-use', 'path': 'README.md'}, timeout=45)
        if not text.strip(): raise ValueError('GitHub MCP 返回为空')
        return {'ok': True, 'repository': 'browser-use/browser-use', 'tool': 'get_file_contents', 'characters': len(text)}
    finally:
        client.close()
