"""Small, bounded stdio MCP client for product-owned connector actions."""
import json
import os
import queue
import subprocess
import threading
import time


class StdioMCP:
    def __init__(self, command, environment=None):
        self.command, self.environment = command, environment or {}
        self.process = None
        self.sequence = 0
        self.lock = threading.RLock()
        self.messages = queue.Queue(maxsize=100)
        self.tools = []

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                return
            # Browser readers do not receive model keys or unrelated shell secrets.
            allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'DISPLAY', 'SYSTEMROOT')
            env = {k: os.environ[k] for k in allowed if k in os.environ}
            env.update(self.environment)
            self.messages = queue.Queue(maxsize=100)
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, env=env)
            process, messages = self.process, self.messages

            def read():
                try:
                    while True:
                        line = process.stdout.readline(4_000_001)
                        if not line:
                            break
                        if len(line) > 4_000_000:
                            raise ValueError('连接器返回超过大小限制')
                        try:
                            value = json.loads(line)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(value, dict):
                            messages.put(value, timeout=1)
                except Exception:
                    pass
                finally:
                    try:
                        messages.put(None, timeout=1)
                    except queue.Full:
                        pass

            threading.Thread(target=read, daemon=True, name='jimu-mcp-reader').start()
            try:
                self._request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                                            'clientInfo': {'name': 'jimu', 'version': '1.0'}}, 45)
                self._write({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                self.tools = self._request('tools/list', {}, 30).get('tools', [])
            except Exception:
                self.close()
                raise

    def _write(self, data):
        self.process.stdin.write((json.dumps(data, ensure_ascii=False) + '\n').encode())
        self.process.stdin.flush()

    def _request(self, method, params, timeout):
        self.sequence += 1
        ident = self.sequence
        self._write({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = self.messages.get(timeout=max(.01, deadline-time.monotonic()))
            except queue.Empty:
                break
            if response is None:
                raise RuntimeError('连接器已停止，请重新连接')
            if response.get('id') != ident:
                continue
            if response.get('error'):
                raise RuntimeError(str(response['error'].get('message', '连接器请求失败'))[:240])
            return response.get('result') or {}
        self.close()
        raise TimeoutError('连接器响应超时，请重试；没有自动重复调用')

    def call(self, name, arguments=None, timeout=60):
        with self.lock:
            self.start()
            if name not in {tool['name'] for tool in self.tools}:
                raise ValueError('连接器没有提供所需工具：' + name)
            result = self._request('tools/call', {'name': name, 'arguments': arguments or {}}, timeout)
            text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
            if result.get('isError') or result.get('is_error') or text.startswith('Error:'):
                raise RuntimeError(text[:240] or '连接器未完成操作')
            return text

    def close(self):
        with self.lock:
            process, self.process = self.process, None
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                for stream in (process.stdin, process.stdout):
                    if stream:
                        stream.close()
