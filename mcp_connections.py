"""Fixed official MCP adapters; secrets stay in OpenCode's private runtime."""
import json
import shutil
from pathlib import Path

SERVERS = {
    'github': {'type': 'remote', 'url': 'https://api.githubcopilot.com/mcp/', 'enabled': True, 'timeout': 30000},
    'browser_use': {'type': 'local', 'command': [str(Path(__file__).resolve().parent / '.runtime/browser-use-env/bin/browser-use'), '--mcp'], 'environment': {'ANONYMIZED_TELEMETRY': 'false'}, 'enabled': True, 'timeout': 60000},
}


def config(engine):
    path = Path(engine.directory) / 'mcp-connections.json'
    return json.loads(path.read_text()) if path.exists() else {}


def connect(engine, name):
    if name not in SERVERS: raise ValueError('未知连接器')
    current = config(engine)
    current[name] = dict(SERVERS[name])
    if name=='github':
        secret=Path(engine.directory)/'github-mcp-token'
        if secret.exists():current[name].update(headers={'Authorization':'Bearer '+secret.read_text().strip()},oauth=False)
    path = Path(engine.directory) / 'mcp-connections.json'
    path.write_text(json.dumps(current)); path.chmod(0o600)
    project=Path(engine.directory)/'opencode.json'
    if project.exists():
        saved=json.loads(project.read_text());saved['mcp']=current
        project.write_text(json.dumps(saved));project.chmod(0o600)
    return engine.call('/mcp', {'name': name, 'config': current[name]}, timeout=90)


def status(engine):
    return engine.call('/mcp', timeout=10) if engine else {}


def save_github_token(engine, token):
    if not isinstance(token,str) or not 10<=len(token.strip())<=500 or any(c.isspace() for c in token.strip()):
        raise ValueError('请填写有效 GitHub Token')
    path=Path(engine.directory)/'github-mcp-token'
    path.write_text(token.strip());path.chmod(0o600)
    return connect(engine,'github')
