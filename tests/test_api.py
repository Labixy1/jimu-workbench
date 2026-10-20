import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import io
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import App, Handler, ThreadingHTTPServer


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.tmp.name), None)
        self.app.settings.update(mode='fixture')
        self.app.runner.submit = lambda job: None
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.app = self.app
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.store.db.close()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        request = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_origin_host_guard(self):
        for headers in ({'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}):
            self.assertEqual(self.request('/api/state', headers=headers)[0], 403)
            self.assertEqual(self.request('/api/memory', {'instructions': 'test'}, headers)[0], 403)

    def test_remote_requires_confirmation(self):
        self.app.settings.update(mode='model', base_url='https://provider.example/v1')
        self.assertEqual(self.request('/api/jobs', {'prompt': 'test', 'kind': 'chat'})[0], 400)
        self.assertEqual(self.app.store.jobs(), [])

    def test_context_snapshot_frozen_at_submission(self):
        status, job = self.request('/api/jobs', {'prompt': 'test', 'kind': 'chat'})
        self.assertEqual(status, 202)
        self.request('/api/memory', {'instructions': 'later preference'})
        payload = self.app.store.job(job['id'])['payload']
        self.assertEqual(payload['preferences_snapshot']['instructions'], '')
        self.assertEqual(payload['artifact_snapshot']['revision'], payload['base_revision'])
        self.assertEqual(payload['execution_settings']['mode'], 'fixture')

    def test_busy_and_settings_guard(self):
        _, job = self.request('/api/jobs', {'prompt': 'test', 'kind': 'chat'})
        self.assertEqual(self.request('/api/jobs', {'prompt': 'second', 'kind': 'chat', 'conversation_id': job['conversation_id']})[0], 409)
        self.assertEqual(self.request('/api/settings', {'mode': 'unconfigured'})[0], 409)

    def test_export_has_messages_not_settings(self):
        cid = self.app.store.conversation()
        self.app.store.message(cid, 'user', 'export evidence')
        _, exported = self.request('/api/export')
        self.assertNotIn('settings', exported)
        self.assertEqual(exported['messages'][cid][0]['text'], 'export evidence')

    def test_source_import_failure_not_fabricated(self):
        with patch('server.fetch_source', side_effect=ValueError('unavailable')):
            self.assertEqual(self.request('/api/sources', {'url': 'https://example.com'})[0], 400)
        self.assertEqual(self.app.store.sources(), [])

    def test_path_traversal(self):
        self.assertEqual(self.request('/../server.py')[0], 404)

    def test_wiki_save_and_archive(self):
        status,page=self.request('/api/wiki',{'page':{'title':'我的笔记','summary':'手动笔记','content':'## 测试\n正文','tags':[],'links':[],'citations':[]}})
        self.assertEqual(status,200)
        self.request('/api/archive',{'kind':'artifact','id':page['id']})
        self.assertNotIn(page['id'],[a['id'] for a in self.request('/api/state')[1]['artifacts']])
        self.assertIn(page['id'],[a['id'] for a in self.request('/api/archived')[1]['artifacts']])

    def test_key_never_returned(self):
        secret='not-a-real-test-secret'
        self.assertEqual(self.request('/api/model/key',{'key':secret})[0],200)
        self.assertNotIn(secret,json.dumps(self.request('/api/state')[1]))
        self.assertNotIn(secret,json.dumps(self.request('/api/export')[1]))

    def test_deepseek_gateway_unauthorized(self):
        self.app.settings.update(mode='deepseek',model='deepseek-flash')
        self.assertEqual(self.request('/model/v1/chat/completions',{'model':'deepseek-flash'})[0],403)

    def test_deepseek_requires_key(self):
        self.app.settings.update(mode='deepseek',model='deepseek-flash')
        with patch('server.model_key',return_value=''):
            self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'hello','allow_private':True})[0],400)

    def test_connection_probe_reports_real_response(self):
        self.app.settings.update(mode='deepseek',model='deepseek-flash')
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'OK'}}],'usage':{'total_tokens':2}}).encode())
        with patch('server.deepseek_request',return_value=response):
            self.assertTrue(self.request('/api/model/test',{})[1]['passed'])

    def test_web_requires_confirmation(self):
        for path in ('/api/web/search','/api/web/fetch'):
            with patch('server.deepseek_web_request') as call:
                self.assertEqual(self.request(path,{'query':'test','url':'https://example.com'})[0],400)
                call.assert_not_called()

    def test_search_keeps_results_ephemeral(self):
        result={'results':[{'title':'Example','url':'https://example.com','snippet':'evidence'},
                           {'title':'unsafe','url':'javascript:alert(1)'}]}
        with patch('server.deepseek_web_request',return_value=result) as call:
            status,response=self.request('/api/web/search',{'query':'example','allow_remote':True})
        self.assertEqual(status,200)
        self.assertEqual(len(response['results']),1)
        self.assertEqual(self.app.store.sources(),[])
        self.assertEqual(call.call_args[0][2]['need_content'],False)

    def test_fetch_preview_does_not_save(self):
        with patch('server.validate_url'),patch('server.deepseek_web_request',return_value={'title':'Page','content':'# Original'}):
            status,page=self.request('/api/web/fetch',{'url':'https://example.com','allow_remote':True})
        self.assertEqual(status,200)
        self.assertEqual(page['content'],'# Original')
        self.assertEqual(self.app.store.sources(),[])

    def test_fetch_rejects_local_and_empty(self):
        with patch('server.deepseek_web_request') as call:
            self.assertEqual(self.request('/api/web/fetch',{'url':'http://127.0.0.1/private','allow_remote':True})[0],400)
            call.assert_not_called()
        with patch('server.validate_url'),patch('server.deepseek_web_request',return_value={'content':''}):
            self.assertEqual(self.request('/api/web/fetch',{'url':'https://example.com','allow_remote':True})[0],400)


if __name__ == '__main__':
    unittest.main()
