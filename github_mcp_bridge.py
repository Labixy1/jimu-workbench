"""Forward MCP to GitHub using the existing gh login, without copying credentials."""
import json
import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = 'https://api.githubcopilot.com/mcp/'


class GitHubBridge:
    def __init__(self, token_file=None):
        self.session = None
        self.token = None
        self.token_file = token_file

    def login(self):
        if self.token_file:
            try: token = Path(self.token_file).read_text().strip()
            except OSError: raise ValueError('本机 GitHub Token 不可用，请在扩展中重新配置') from None
            if not 10 <= len(token) <= 500 or any(c.isspace() for c in token):
                raise ValueError('本机 GitHub Token 格式无效，请重新配置')
            self.token = token
            return
        cli = shutil.which('gh')
        if not cli:
            raise ValueError('未安装 GitHub CLI，请先安装 gh 并运行 gh auth login')
        result = subprocess.run([cli, 'auth', 'token', '--hostname', 'github.com'], capture_output=True,
                                timeout=10, env={**os.environ, 'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1'})
        if result.returncode or not result.stdout.strip():
            raise ValueError('本机 GitHub 尚未登录，请运行 gh auth login 后重试')
        self.token = result.stdout.decode().strip()

    def request(self, message):
        if not self.token:
            self.login()
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream', 'X-MCP-Readonly': 'true',
                   'X-MCP-Toolsets': 'repos,issues,pull_requests', 'User-Agent': 'Jimu-MCP/1.0'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        request = urllib.request.Request(ENDPOINT, data=json.dumps(message).encode(), headers=headers)
        # Never forward Authorization through a redirect to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                self.session = response.headers.get('Mcp-Session-Id', self.session)
                raw = response.read(3_000_001)
                mime = response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            body = error.read(4000).decode('utf-8', errors='replace')
            if error.code == 403 and any(word in body for word in ('安全策略', '域名拦截', 'network policy', 'blocked by policy')):
                raise ValueError('官方 GitHub MCP 域名被当前网络安全策略拦截；请由你按公司流程申请放行。README 导入是独立能力。') from None
            if error.code in (401, 403):
                self.token = None
                raise ValueError('GitHub 未授权此 MCP 请求，请重新登录或使用有权限的 Token') from None
            raise ValueError('GitHub MCP 返回 HTTP ' + str(error.code)) from None
        except (OSError, TimeoutError):
            raise ValueError('GitHub MCP 暂时无法连接，请检查网络后重试') from None
        if len(raw) > 3_000_000:
            raise ValueError('GitHub 返回内容过大，请缩小读取范围')
        if 'id' not in message or not raw:
            return None
        if mime == 'text/event-stream':
            for line in raw.decode().splitlines():
                if line.startswith('data:'):
                    result = json.loads(line[5:].strip())
                    if result.get('id') == message['id']:
                        return result
            raise ValueError('GitHub MCP 未返回本次请求的结果')
        return json.loads(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--token-file')
    args = parser.parse_args()
    bridge = GitHubBridge(args.token_file)
    for line in sys.stdin:
        message = None
        try:
            if len(line) > 500_000:
                raise ValueError('MCP 请求过大')
            message = json.loads(line)
            result = bridge.request(message)
        except Exception as error:
            # Authentication details and subprocess output never enter protocol errors.
            detail = str(error) if isinstance(error, ValueError) else 'GitHub MCP 请求未完成'
            result = {'jsonrpc': '2.0', 'id': (message or {}).get('id'),
                      'error': {'code': -32000, 'message': detail[:240]}}
        if result is not None and isinstance(message, dict) and 'id' in message:
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
