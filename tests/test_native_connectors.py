import json
import sys
import tempfile
import unittest
import io
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

import mcp_connections
from mcp_runtime import StdioMCP
from github_mcp_bridge import GitHubBridge


class NativeConnectorTests(unittest.TestCase):
    def test_github_cli_config_never_contains_token(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = SimpleNamespace(directory=folder, call=Mock(return_value={'github': {'status': 'connected'}}))
            Path(folder, 'opencode.json').write_text('{}')
            with patch('connections.github_cli', return_value='/fixture/gh'):
                result = mcp_connections.connect_github_login(engine)
            self.assertEqual(result['github']['status'], 'connected')
            data = Path(folder, 'mcp-connections.json').read_text()
            self.assertNotIn('Authorization', data)
            self.assertNotIn('token', data)
            self.assertIn('github_mcp_bridge.py', data)

    def test_bridge_requests_only_official_endpoint_readonly(self):
        bridge = GitHubBridge(); bridge.token = 'fixture-secret'
        response = Mock(); response.read.return_value = b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
        response.headers = Mock(); response.headers.get.return_value = None
        response.headers.get_content_type.return_value = 'application/json'
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        opener = Mock(); opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            bridge.request({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.githubcopilot.com/mcp/')
        self.assertEqual(request.get_header('X-mcp-readonly'), 'true')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-secret')

    def test_status_failure_is_not_connected(self):
        engine = SimpleNamespace(call=Mock(side_effect=RuntimeError('sensitive detail')))
        result = mcp_connections.status(engine)
        self.assertEqual(result['github']['status'], 'failed')
        self.assertNotIn('sensitive', json.dumps(result))

    def test_bridge_uses_explicit_token_file_without_switching_accounts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'github-token';path.write_text('fixture-token-for-test')
            bridge=GitHubBridge(path)
            with patch('github_mcp_bridge.subprocess.run',side_effect=AssertionError('Do not use gh for token mode')):
                bridge.login()
            self.assertEqual(bridge.token,'fixture-token-for-test')

    def test_read_test_respects_configured_token_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'mcp-connections.json').write_text(json.dumps({'github':{'type':'remote'}}))
            secret=Path(folder,'github-mcp-token');secret.write_text('fixture-token-for-test')
            with patch('mcp_runtime.StdioMCP') as client:
                client.return_value.call.return_value='Explicit fixture MCP content'
                mcp_connections.test_github({'allow_remote':True},SimpleNamespace(directory=folder))
                command=client.call_args.args[0]
                self.assertEqual(command[-2:],['--token-file',str(secret)])
                self.assertNotIn('fixture-token-for-test',json.dumps(command))

    def test_network_policy_error_is_not_reported_as_an_auth_failure(self):
        bridge = GitHubBridge(); bridge.token = 'fixture-secret'
        error = urllib.error.HTTPError('https://api.githubcopilot.com/mcp/', 403, 'Forbidden', {},
                                      io.BytesIO('域名拦截：安全策略限制'.encode()))
        opener = Mock(); opener.open.side_effect = error
        with patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, '网络安全策略'):
                bridge.request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        self.assertEqual(bridge.token, 'fixture-secret')

    def test_real_stdio_transport_with_explicit_fixture(self):
        program = '''import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 result={'protocolVersion':'2024-11-05','capabilities':{}} if r['method']=='initialize' else {'tools':[{'name':'fixture_read'}]} if r['method']=='tools/list' else {'content':[{'type':'text','text':'Explicit local fixture, not a website.'}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
'''
        client = StdioMCP([sys.executable, '-u', '-c', program])
        try:
            self.assertEqual(client.call('fixture_read'), 'Explicit local fixture, not a website.')
            with self.assertRaises(ValueError): client.call('missing_tool')
        finally:
            client.close()
