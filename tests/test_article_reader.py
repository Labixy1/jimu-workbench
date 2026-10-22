import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import library
import reading_room
from article_reader import ArticleHTML, blocked_page, fetch_image, fetch_article, featured_image, content_blocks
from domain import Store
from news import News, parse_feed, fetch_feed


class ArticleReaderTests(unittest.TestCase):
    def test_inline_images_keep_original_order_and_lazy_sources(self):
        parser=ArticleHTML('https://example.com/post')
        before='Evidence before image. '*5
        after='Evidence after image. '*5
        parser.feed('<article><p>'+before+'</p><img data-src="/chart.png" src="data:image/gif;base64,placeholder" alt="Chart &amp; evidence">'
                    '<p>'+after+'</p><img srcset="/small.png 300w, /large.png 900w">'
                    '<img src="/tracking.gif" width="1"><img src="/avatar.jpg">'
                    '<span hidden><img src="/hidden.png"></span><img src="javascript:alert(1)"></article>')
        article=parser.result();blocks=article['content_blocks']
        self.assertEqual([b['type'] for b in blocks],['text','image','text','image'])
        self.assertEqual(blocks[1]['url'],'https://example.com/chart.png')
        self.assertEqual(blocks[1]['alt'],'Chart & evidence')
        self.assertEqual(blocks[3]['url'],'https://example.com/large.png')
        self.assertEqual(len(blocks[1]['id']),24)
        self.assertIn(before.strip(),blocks[0]['text'])
        self.assertIn(after.strip(),blocks[2]['text'])
        self.assertEqual(article['cover_url'],'','inline images do not become a made-up cover')

    def test_image_blocks_are_bounded_and_never_replace_mismatched_text(self):
        text='Explicit fixture evidence.'
        blocks=[{'type':'text','text':text},{'type':'image','url':'javascript:alert(1)'},
                {'type':'image','url':'https://example.com/diagram.png','id':'untrusted'}]
        safe=content_blocks(blocks,text)
        self.assertEqual(len(safe),2)
        self.assertNotEqual(safe[-1]['id'],'untrusted')
        self.assertIsNone(content_blocks(blocks,'A different edited article.'))
        self.assertIsNone(content_blocks([{'type':'image','url':'https://example.com/a.png'}]*162,text))

    def test_extract_article_without_mistaking_logo_or_body_image_for_cover(self):
        parser=ArticleHTML('https://example.com/post')
        parser.feed('<title>Fixture article</title><meta property="og:image" content="/logo.png">'
                    '<nav>Navigation must not become article</nav><article><h1>Fixture article</h1>'
                    '<img src="/200.jpg" class="avatar photo"><p>'+('Article evidence. '*12)+'</p><img src="/cover.jpg">'
                    '<script>do_not_execute()</script></article><footer>Footer</footer>')
        article=parser.result()
        self.assertEqual(article['cover_url'],'')
        self.assertNotIn('Navigation',article['content'])
        self.assertNotIn('do_not_execute',article['content'])
        self.assertNotIn('Footer',article['content'])

    def test_challenge_is_not_readable_article(self):
        self.assertTrue(blocked_page('Just a moment...','Checking your browser'))
        self.assertTrue(blocked_page('','当前环境异常，请完成验证'))
        parser=ArticleHTML('https://example.com')
        parser.feed('<title>Access denied</title><main>'+('Please verify you are human '*20)+'</main>')
        with self.assertRaises(ValueError):parser.result()

    def test_nested_specific_body_and_missing_image(self):
        parser=ArticleHTML('https://example.com')
        parser.feed('<main>Navigation<article><div id="js_content"><p>'+('Actual body '*20)+'</p></div><p>Related articles</p></article></main>')
        article=parser.result()
        self.assertNotIn('Related articles',article['content'])
        self.assertEqual(article['cover_url'],'')

    def test_hidden_content_does_not_enter_the_capture(self):
        parser=ArticleHTML('https://example.com/post')
        parser.feed('<title>Fixture article</title><article>'+('Visible fixture text. '*10)+
                    '<div hidden>PRIVATE HIDDEN ONE</div><span aria-hidden="true">PRIVATE HIDDEN TWO</span>'+
                    '<div style="color:red; display: none">PRIVATE HIDDEN THREE</div></article>')
        self.assertNotIn('PRIVATE HIDDEN',parser.result()['content'])

    def response(self, text, mime, url):
        response=Mock()
        response.read.return_value=text.encode()
        response.headers.get_content_type.return_value=mime
        response.headers.get_content_charset.return_value='utf-8'
        response.geturl.return_value=url
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        return response

    def test_html_discovers_public_rss_and_validates_both_urls(self):
        root='https://example.com/news'
        html='<title>Fixture site</title><link type="application/rss+xml" href="/feed">'
        rss='<rss><channel><item><title>Fixture post</title><link>https://example.com/p</link><description>Explicit fixture summary.</description></item></channel></rss>'
        opener=Mock()
        opener.open.side_effect=[self.response(html,'text/html',root),self.response(rss,'application/rss+xml','https://example.com/feed')]
        validator=Mock()
        with patch('news.urllib.request.build_opener',return_value=opener):result=fetch_feed(root,validator)
        self.assertEqual(result[0]['title'],'Fixture post')
        self.assertEqual([call.args[0] for call in validator.call_args_list],[root,'https://example.com/feed'])
        self.assertEqual(opener.open.call_count,2)

    def test_html_article_can_be_a_source_without_a_feed(self):
        url='https://example.com/p'
        html='<title>Fixture article</title><article>'+('Explicit article evidence. '*12)+'</article>'
        opener=Mock();opener.open.return_value=self.response(html,'text/html',url)
        with patch('news.urllib.request.build_opener',return_value=opener):result=fetch_feed(url,lambda _:None)
        self.assertEqual(result[0]['content_status'],'article')
        self.assertEqual(result[0]['url'],url)
        self.assertIn('Explicit article evidence.',result[0]['content'])

    def test_html_challenge_is_not_followed_or_added_to_feed(self):
        html='<title>Access denied</title><link type="application/rss+xml" href="/private"><main>Verify you are human</main>'
        opener=Mock();opener.open.return_value=self.response(html,'text/html','https://example.com')
        with patch('news.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):fetch_feed('https://example.com',lambda _:None)
        self.assertEqual(opener.open.call_count,1)

    def test_image_must_be_raster_not_error_or_svg(self):
        with patch('article_reader.fetch_bytes',return_value=(b'<html>captcha</html>','image/jpeg','utf-8','https://example.com/cover')):
            with self.assertRaises(ValueError):fetch_image('https://example.com/cover',lambda _:None)
        with patch('article_reader.fetch_bytes',return_value=(b'\x89PNG\r\n\x1a\n' + b'fixture','image/png','utf-8','https://example.com/cover')):
            self.assertEqual(fetch_image('https://example.com/cover',lambda _:None)[1],'image/png')

    def test_rss_thumbnail_and_explicit_large_history_limit(self):
        items=''.join('<item><title>Fixture '+str(i)+'</title><link>https://example.com/'+str(i)+'</link>'
                      '<description>Fixture body content</description><media:thumbnail url="https://example.com/cover.png"/></item>' for i in range(20))
        raw=('<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>'+items+'</channel></rss>').encode()
        self.assertEqual(len(parse_feed(raw,'https://example.com/feed')),8)
        self.assertEqual(len(parse_feed(raw,'https://example.com/feed',limit=80)),20)
        self.assertEqual(parse_feed(raw,'https://example.com/feed')[0]['cover_url'],'https://example.com/cover.png')

    def test_rss_contributor_avatar_is_not_article_cover(self):
        raw=b'''<rss><channel><item><title>Fixture release</title><link>https://example.com/release</link>
            <description>&lt;p&gt;A fixture changelog.&lt;/p&gt;&lt;img src="https://avatars.githubusercontent.com/u/1"&gt;</description>
            </item></channel></rss>'''
        self.assertEqual(parse_feed(raw,'https://example.com/feed')[0]['cover_url'],'')

    def test_plain_text_is_not_silently_truncated(self):
        with patch('article_reader.fetch_bytes',return_value=(b'A'*120001,'text/plain','utf-8','https://example.com/a')):
            with self.assertRaises(ValueError):fetch_article('https://example.com/a',lambda _:None)

    def test_release_body_excludes_navigation_and_load_errors(self):
        parser=ArticleHTML('https://github.com/example/project/releases/tag/v1')
        parser.feed('<title>Release v1</title><main>Repository navigation. Sorry, something went wrong.'
                    '<div class="markdown-body"><h2>Improvements</h2><p>'+('Actual fixture release details. '*5)+
                    '</p></div><div>Assets Loading Uh oh! Please reload this page.</div></main>')
        content=parser.result()['content']
        self.assertIn('Actual fixture release details.',content)
        self.assertNotIn('Repository navigation',content)
        self.assertNotIn('Loading',content)

    def test_short_specific_body_does_not_fall_back_to_navigation(self):
        parser=ArticleHTML('https://example.com/post')
        parser.feed('<main>'+('Navigation control. '*25)+'<div class="markdown-body">Release v1</div></main>')
        with self.assertRaises(ValueError):parser.result()

    def test_missing_release_body_does_not_capture_whole_github_page(self):
        parser=ArticleHTML('https://github.com/example/project/releases/tag/v1')
        parser.feed('<main>'+('Repository navigation. Loading. '*20)+'</main>')
        with self.assertRaises(ValueError):parser.result()

    def test_advertised_featured_media_is_used_instead_of_logo(self):
        import json
        article={'featured_media':7,'_links':{'wp:featuredmedia':[{'href':'https://example.com/wp-json/wp/v2/media/7'}]}}
        media={'source_url':'https://example.com/original-cover.jpg','media_details':{'sizes':{'medium_large':{'source_url':'https://example.com/cover-768.jpg'}}}}
        results=[(json.dumps(data).encode(),'application/json','utf-8','https://example.com') for data in (article,media)]
        with patch('article_reader.fetch_bytes',side_effect=results):
            self.assertEqual(featured_image('https://example.com/wp-json/wp/v2/posts/1',lambda _:None),'https://example.com/cover-768.jpg')

    def test_refresh_keeps_original_source_and_enriched_body(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'db.sqlite3');library.init(store);reading_room.init(store)
            news=News(SimpleNamespace(root=root,store=store),lambda _:None)
            original={'title':'Fixture','url':'https://example.com/post','excerpt':'Feed excerpt for fixture','content_status':'summary'}
            first,_=news.store_item(original)
            source=store.source(first['source_id'])
            news.update_item(first['id'],{'content':'Read article content '*20,'content_status':'article','cover_url':'https://example.com/cover.png'})
            second,_=news.store_item(original)
            self.assertEqual(first['source_id'],second['source_id'])
            self.assertEqual(store.source(second['source_id'])['content'],source['content'])
            self.assertEqual(second['content_status'],'article')
            self.assertEqual(second['cover_url'],'https://example.com/cover.png')
            self.assertTrue(second['content'])
            with self.assertRaises(ValueError):news.import_capture({'article':{'title':'Access denied','url':'https://example.com/blocked','content':'Verify you are human '*10}})
            store.db.close()


if __name__=='__main__':unittest.main()
