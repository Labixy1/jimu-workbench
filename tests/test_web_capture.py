import json
import unittest
from unittest.mock import patch, Mock

import test_api
import web_capture
from article_reader import ArticleHTML
from web_capture import canonical_url


class CaptureTests(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def article(self, **changes):
        return {'title': 'Explicit test article', 'content': 'Labelled fixture: this is a product-owned capture test. ' * 8,
                'url': 'https://example.com/article?id=3&access_token=private#anchor',
                'published_at': None, 'cover_url': '', **changes}

    def stage(self, **changes):
        self.app.capture.validator = lambda _: None
        status, preview = self.request('/api/capture/stage', {'article': self.article(**changes)})
        self.assertEqual(status, 200, preview)
        return preview

    def test_preview_does_not_save_or_call_model(self):
        with patch('web_capture.fetch_article', return_value=self.article()):
            self.assertEqual(self.request('/api/capture/preview', {'url': 'https://example.com'})[0], 400)
            self.app.capture.validator = lambda _: None
            code, p = self.request('/api/capture/preview', {'url': 'https://example.com', 'allow_remote': True})
        self.assertEqual(code, 200, p)
        self.assertEqual(self.app.store.sources(), [])
        self.assertEqual(self.app.store.jobs(), [])
        self.assertEqual(p['article']['collection_method'], 'public_html')

    def test_native_capture_keeps_inline_images_and_text_edits_clear_old_layout(self):
        article=self.article()
        blocks=[{'type':'text','text':article['content']},
                {'type':'image','url':'https://example.com/diagram.png','alt':'Fixture diagram'}]
        preview=self.stage(content_blocks=blocks)
        self.assertEqual(preview['article']['content_blocks'][1]['type'],'image')
        code,result=self.request('/api/capture/save',{'id':preview['id'],'reading':True})
        self.assertEqual(code,200,result)
        self.assertEqual(self.app.news.item(result['news_id'])['content_blocks'][1]['url'],'https://example.com/diagram.png')
        preview=self.stage(content_blocks=blocks)
        code,result=self.request('/api/capture/save',{'id':preview['id'],'reading':True,'content':'Edited fixture body. '*10})
        self.assertEqual(code,200,result)
        self.assertNotIn('content_blocks',self.app.news.item(result['news_id']))

    def test_save_to_folder_favorite_and_reading_then_dedupe(self):
        p = self.stage()
        data = {'id': p['id'], 'category_id': 'learning', 'reading': True, 'favorite': True,
                'favorite_category': 'Harness'}
        code, result = self.request('/api/capture/save', data)
        self.assertEqual(code, 200, result)
        state = self.request('/api/state')[1]
        self.assertEqual(state['library'][0]['category_id'], 'learning')
        self.assertIn(result['source_id'], state['reading']['favorites'])
        self.assertEqual(state['reading']['favorite_categories'][result['source_id']], 'Harness')
        self.assertEqual(state['weekly']['news'][0]['content'], p['article']['content'])
        self.assertEqual(len(state['reading']['issues']), 1)
        self.assertTrue(self.request('/api/capture/save', data)[1]['duplicate'])
        self.assertEqual(len(self.app.store.sources()), 1)
        self.assertEqual(self.app.store.jobs(), [])

    def test_bad_destination_writes_nothing_and_preview_survives(self):
        p = self.stage()
        code, _ = self.request('/api/capture/save', {'id': p['id'], 'category_id': 'missing', 'reading': True})
        self.assertEqual(code, 409)
        self.assertEqual(self.app.store.sources(), [])
        code, _ = self.request('/api/capture/save', {'id': p['id'], 'favorite': True, 'favorite_category': 'missing'})
        self.assertEqual(code, 409)
        self.assertEqual(self.app.store.sources(), [])
        self.assertEqual(self.request('/api/capture/save', {'id': p['id'], 'reading': False})[0], 200)

    def test_login_bad_date_and_credentials_rejected(self):
        self.app.capture.validator = lambda _: None
        for change in ({'title': 'Access denied'}, {'published_at': '2099-01-01T00:00:00Z'},
                       {'url': 'https://user:password@example.com'}, {'content': 'short'}):
            self.assertEqual(self.request('/api/capture/stage', {'article': self.article(**change)})[0], 400)
        self.assertEqual(self.app.store.sources(), [])
        self.assertEqual(self.request('/api/capture/stage', {'article': self.article()}, {'Origin': 'https://attacker.example'})[0], 403)

    def test_public_url_validation_and_expired_preview(self):
        self.assertEqual(self.request('/api/capture/preview', {'url': 'http://127.0.0.1/private', 'allow_remote': True})[0], 400)
        p = self.stage()
        self.app.capture.previews[p['id']]['at'] -= 1801
        self.assertEqual(self.request('/api/capture/save', {'id': p['id']})[0], 400)
        self.assertEqual(self.app.store.sources(), [])

    def test_capture_new_snapshot_preserves_existing_source(self):
        old, _ = self.app.news.store_item(self.article(url='https://example.com/article', content='Original fixture body. '*10))
        original = self.app.store.source(old['source_id'])['content']
        p = self.stage(url='https://example.com/article')
        code, result = self.request('/api/capture/save', {'id': p['id'], 'reading': True, 'category_id': 'learning'})
        self.assertEqual(code, 200, result)
        self.assertNotEqual(result['source_id'], old['source_id'])
        self.assertEqual(self.app.store.source(old['source_id'])['content'], original)
        self.assertIn(p['article']['content'], self.app.store.source(result['source_id'])['content'])

    def test_metadata_only_refresh_reuses_source_and_favorite(self):
        p = self.stage()
        first = self.request('/api/capture/save', {'id': p['id'], 'reading': True, 'favorite': True})[1]
        p = self.stage(published_at='2026-10-21T00:00:00+08:00')
        second = self.request('/api/capture/save', {'id': p['id'], 'reading': True, 'favorite': True,
                                                  'category_id': 'learning'})[1]
        self.assertEqual(first['source_id'], second['source_id'])
        self.assertEqual(len(self.app.store.sources()), 1)
        self.assertEqual(len(self.request('/api/state')[1]['reading']['favorites']), 1)

    def test_unchecked_reading_does_not_publish_news(self):
        p = self.stage()
        result = self.request('/api/capture/save', {'id': p['id'], 'favorite': True, 'reading': False})[1]
        self.assertIsNone(result['news_id'])
        self.assertEqual(self.app.news.items(), [])
        self.assertEqual(len(self.request('/api/state')[1]['reading']['favorites']), 1)

    def test_shortened_capture_and_renamed_title_are_saved(self):
        p = self.stage()
        first = self.request('/api/capture/save', {'id': p['id'], 'reading': True, 'favorite': True})[1]
        original = self.app.store.source(first['source_id'])['content']
        p = self.stage(content=self.article()['content'][:160], title='Reviewed fixture title')
        code, second = self.request('/api/capture/save', {'id': p['id'], 'reading': True, 'favorite': True})
        self.assertEqual(code, 200, second)
        self.assertNotEqual(first['source_id'], second['source_id'])
        self.assertEqual(self.app.store.source(second['source_id'])['title'], 'Reviewed fixture title')
        self.assertEqual(self.app.store.source(first['source_id'])['content'], original)
        self.assertEqual(self.request('/api/state')[1]['reading']['favorites'], [second['source_id']])

    def test_same_text_at_different_urls_keeps_source_identity(self):
        p = self.stage(url='https://example.com/a')
        first = self.request('/api/capture/save', {'id': p['id'], 'reading': False})[1]
        p = self.stage(url='https://example.com/b')
        second = self.request('/api/capture/save', {'id': p['id'], 'reading': False})[1]
        self.assertNotEqual(first['source_id'], second['source_id'])
        self.assertEqual(self.app.store.source(second['source_id'])['url'], 'https://example.com/b')

    def test_explicit_resave_restores_archived_source(self):
        p = self.stage()
        first = self.request('/api/capture/save', {'id': p['id'], 'reading': True})[1]
        self.app.store.archive('source', first['source_id'])
        p = self.stage()
        second = self.request('/api/capture/save', {'id': p['id'], 'reading': True})[1]
        self.assertEqual(first['source_id'], second['source_id'])
        self.assertFalse(self.app.store.source(second['source_id'])['archived'])

    def test_browser_open_read_uses_only_deterministic_mcp_tools(self):
        self.app.capture.validator = lambda _: None
        client = Mock()
        self.app.capture.client = client
        client.call.side_effect = ['Navigated', json.dumps({'url': 'https://example.com/article', 'title': 'Test'}),
                                  '<title>Fixture article</title><article>'+'Visible fixture article body. '*20+'</article>']
        self.assertEqual(self.request('/api/capture/browser/open', {'url': 'https://example.com/article'})[0], 400)
        with patch.object(self.app.capture, '_browser', return_value=client):
            self.assertEqual(self.request('/api/capture/browser/open', {'url': 'https://example.com/article', 'allow_remote': True})[0], 200)
            code, p = self.request('/api/capture/browser/read', {'allow_remote': True})
        self.assertEqual(code, 200, p)
        self.assertEqual(p['article']['collection_method'], 'browser_use_mcp')
        self.assertEqual([call.args[0] for call in client.call.call_args_list],
                         ['browser_navigate', 'browser_get_state', 'browser_get_html'])
        self.assertEqual(self.app.store.sources(), [])
        self.assertEqual([t['status'] for t in p['trace']], ['completed']*3)

    def test_browser_failure_is_reported_not_saved(self):
        self.app.capture.validator = lambda _: None
        self.app.capture.browser_url = 'https://example.com'
        client = Mock()
        client.call.side_effect = [json.dumps({'url': 'https://example.com'}),
                                  '<title>Just a moment...</title><main>Checking your browser</main>']
        with patch.object(self.app.capture, '_browser', return_value=client):
            code, result = self.request('/api/capture/browser/read', {'allow_remote': True})
        self.assertEqual(code, 400)
        self.assertTrue(result['error'])
        self.assertEqual(self.app.store.sources(), [])

    def test_browser_cleanup_clears_stale_state_after_failed_close(self):
        self.app.capture.browser_url = 'https://example.com'
        client = Mock()
        client.call.side_effect = RuntimeError('Explicit fixture close error')
        self.app.capture.client = client
        self.assertEqual(self.request('/api/capture/browser/close', {})[0], 400)
        self.assertFalse(self.app.capture.state()['opened'])
        self.assertIsNone(self.app.capture.client)
        client.close.assert_called_once()

    def test_appearance_persists_only_known_tokens(self):
        self.assertEqual(self.request('/api/appearance')[1]['theme'], 'classic')
        self.assertEqual(self.request('/api/appearance', {'theme': 'sage'})[0], 200)
        self.assertEqual(self.request('/api/appearance')[1]['theme'], 'sage')
        self.assertEqual(self.request('/api/appearance', {'theme': 'url(https://evil.example)'})[0], 400)
        self.assertEqual(self.app.settings['mode'], 'fixture')


class CanonicalTests(unittest.TestCase):
    def test_wechat_identity_preserved_not_login_token(self):
        url = canonical_url('https://mp.weixin.qq.com/s?__biz=test&mid=2&idx=1&sn=abc&key=private&uin=person#wechat_redirect')
        self.assertEqual(url, 'https://mp.weixin.qq.com/s?__biz=test&mid=2&idx=1&sn=abc')

    def test_xhs_signed_identity_and_tracking_not_saved(self):
        self.assertEqual(canonical_url('https://www.xiaohongshu.com/explore/abc?xsec_token=private&xsec_source=pc'),
                         'https://www.xiaohongshu.com/explore/abc')

    def test_distinct_wechat_share_links_do_not_collapse(self):
        one = canonical_url('https://mp.weixin.qq.com/s?src=11&signature=public-article-a&timestamp=100&key=private')
        two = canonical_url('https://mp.weixin.qq.com/s?src=11&signature=public-article-b&timestamp=100&key=private')
        self.assertNotEqual(one, two)
        self.assertNotIn('key=', one)

    def test_qbitai_visible_date_uses_shanghai_time(self):
        p = ArticleHTML('https://www.qbitai.com/2026/10/fixture.html')
        p.feed('<title>Fixture</title><article><span class="date">2026-10-21</span><span class="time">10:37:39</span>'+'Visible fixture. '*20+'</article>')
        self.assertEqual(p.result()['published_at'], '2026-10-21T10:37:39+08:00')

    def test_social_dom_extraction_is_visible_data_not_script_state(self):
        p = ArticleHTML('https://mp.weixin.qq.com/s/fixture')
        p.feed('<title>Fallback</title><h1 id="activity-name">Fixture title</h1><span id="js_name">Fixture author</span>'
               '<script>const login_secret="DO NOT READ"</script><div id="js_content">'+'Fixture visible article. '*12+'</div>')
        a = p.result()
        self.assertEqual(a['title'], 'Fixture title')
        self.assertEqual(a['author'], 'Fixture author')
        self.assertNotIn('DO NOT READ', a['content'])
