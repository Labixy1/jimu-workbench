import base64
import json
import unittest
from unittest.mock import patch
import test_api
import connections


class ConnectionTests(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_default_websites_are_preferences_not_model_tools(self):
        code, result = self.request('/api/connections')
        self.assertEqual(code, 200)
        self.assertIn('Stitch', [l['name'] for l in result['links']])
        self.assertIn('豆包', [l['name'] for l in result['links']])
        self.assertFalse(result['browser_use']['connected'])
        self.assertNotIn('token', json.dumps(result))

    def test_create_edit_delete_and_revision_guard(self):
        payload = {'name': '设计参考', 'url': 'https://example.com/', 'group': '设计', 'description': '我的个人参考'}
        code, link = self.request('/api/tool-links', payload)
        self.assertEqual(code, 200)
        self.assertEqual(self.request('/api/tool-links', {**payload, 'id': link['id'], 'revision': 0})[0], 409)
        _, edited = self.request('/api/tool-links', {**payload, 'id': link['id'], 'revision': 1, 'name': '改名'})
        self.assertEqual(edited['revision'], 2)
        self.assertEqual(self.request('/api/tool-links/remove', {'id': link['id'], 'revision': 1})[0], 409)
        self.assertEqual(self.request('/api/tool-links/remove', {'id': link['id'], 'revision': 2})[0], 200)
        self.assertFalse(any(l['id'] == link['id'] for l in connections.links(self.app.store)))
        self.assertEqual(self.request('/api/export')[1]['tool_links'], connections.links(self.app.store))

    def test_bookmark_rejects_script_credentials_and_invalid_group(self):
        payload = {'name': 'test', 'url': 'https://example.com', 'group': '其他'}
        for invalid in ({'url': 'javascript:alert(1)'}, {'url': 'file:///private'}, {'url': 'https://user:secret@example.com'}, {'group': 'invalid'}, {'name': ' '}):
            self.assertEqual(self.request('/api/tool-links', {**payload, **invalid})[0], 400)

    def test_deleted_defaults_do_not_reappear_on_restart(self):
        self.request('/api/tool-links/remove', {'id': 'stitch', 'revision': 1})
        connections.init(self.app.store)
        self.assertNotIn('stitch', [l['id'] for l in connections.links(self.app.store)])

    def test_github_repo_validation(self):
        self.assertEqual(connections.github_repo('https://github.com/anomalyco/opencode/'), ('anomalyco', 'opencode'))
        self.assertEqual(connections.github_repo('owner/repo.git'), ('owner', 'repo'))
        for value in ('https://github.com.evil.com/a/b', 'https://github.com/a/b?token=x', 'https://github.com/a/b/tree/main', 'a/b/../../secret', 'a/..', '; rm -rf /', 'https://user:pass@github.com/a/b'):
            with self.assertRaises(ValueError): connections.github_repo(value)

    def test_github_is_readonly_preview_and_requires_explicit_read(self):
        text = '# Fixture project\nOnly labelled local test content.'
        responses = [{'private': False}, {'encoding': 'base64', 'path': 'README.md', 'sha': 'fixture-sha', 'size': len(text), 'content': base64.b64encode(text.encode()).decode()}]
        with patch('connections.github_cli', return_value=None), patch('connections.github_json', side_effect=responses) as call:
            self.assertEqual(self.request('/api/github/preview', {'repo': 'owner/repo'})[0], 400)
            self.assertEqual(call.call_count, 0)
            code, result = self.request('/api/github/preview', {'repo': 'owner/repo', 'allow_remote': True})
            self.assertEqual(code, 200)
            self.assertIn(text, result['content'])
            self.assertIn('fixture-sha', result['content'])
            self.assertEqual(result['visibility'], 'public')
            self.assertEqual(call.call_count, 2)
        self.assertEqual(self.app.store.sources(), [])
        self.assertEqual(self.app.store.jobs(), [])

    def test_private_github_requires_separate_consent_before_readme(self):
        with patch('connections.github_cli', return_value='/fixture/gh'), patch('connections.github_json', return_value={'private': True}) as call:
            self.assertEqual(self.request('/api/github/preview', {'repo': 'owner/repo', 'allow_remote': True})[0], 400)
            self.assertEqual(call.call_count, 1)
        text = 'Private fixture data, not from a real repository.'
        responses = [{'private': True}, {'encoding': 'base64', 'content': base64.b64encode(text.encode()).decode(), 'size': len(text)}]
        with patch('connections.github_cli', return_value='/fixture/gh'), patch('connections.github_json', side_effect=responses):
            _, result = self.request('/api/github/preview', {'repo': 'owner/repo', 'allow_remote': True, 'allow_private': True})
            self.assertEqual(result['visibility'], 'private')
            self.assertTrue(result['private'])
            self.assertEqual(result['auth'], 'local_gh')

    def test_github_rejects_oversized_or_invalid_readme(self):
        for info in ({'encoding': 'base64', 'content': '', 'size': 120001}, {'encoding': 'none', 'content': ''}, {'encoding': 'base64', 'content': base64.b64encode(b'\xff').decode()}):
            with patch('connections.github_cli', return_value=None), patch('connections.github_json', side_effect=[{'private': False}, info]):
                self.assertEqual(self.request('/api/github/preview', {'repo': 'owner/repo', 'allow_remote': True})[0], 400)
        self.assertEqual(self.app.store.sources(), [])
