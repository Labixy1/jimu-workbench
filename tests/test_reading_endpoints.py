import test_api
from unittest.mock import patch
import urllib.request
from article_reader import content_blocks
class ReadingEndpointTests(test_api.ApiTests):
 def test_favorite_and_snapshot_endpoints(self):
  status,doc=self.request('/api/documents/create',{'title':'Fixture','content':'# Fixture'})
  self.assertEqual(status,200)
  self.assertEqual(self.request('/api/reading/favorite',{'id':doc['id']})[0],200)
  self.assertIn(doc['id'],self.request('/api/state')[1]['reading']['favorites'])
  self.assertEqual(self.request('/api/reading/favorite',{'id':doc['id'],'remove':True})[0],200)
  self.assertEqual(self.request('/api/reading/snapshot',{})[1],None)
 def test_focus_validation(self):
  self.assertEqual(self.request('/api/reading/focus',{'name':'Fixture','kind':'bad','url':'https://example.com'})[0],400)
  self.assertEqual(self.request('/api/reading/focus',{'name':'Fixture','kind':'官网','url':'http://127.0.0.1'})[0],400)

 def test_focus_description_and_site_icon_are_bound_to_saved_website(self):
  with patch('server.validate_url',side_effect=lambda url:url):
   status,focus=self.request('/api/reading/focus',{'name':'Fixture','kind':'官网','url':'https://example.com/news','description':'Official updates'})
  self.assertEqual(status,200)
  self.assertEqual(self.request('/api/state')[1]['reading']['focus'][0]['description'],'Official updates')
  raw=b'\x89PNG\r\n\x1a\nfixture'
  with patch('server.validate_url') as validate,patch('server.urllib.request.build_opener') as opener:
   response=opener.return_value.open.return_value.__enter__.return_value
   response.read.return_value=raw;response.headers.get.return_value='image/png'
   with urllib.request.urlopen(self.url+'/api/site-icon?id='+focus['id']) as result:
    self.assertEqual(result.read(),raw)
    self.assertEqual(result.headers['X-Content-Type-Options'],'nosniff')
   self.assertEqual(opener.return_value.open.call_args.args[0].full_url,'https://example.com/favicon.ico')
   validate.assert_called_with('https://example.com/favicon.ico')
   opener.reset_mock()
   self.assertEqual(self.request('/api/site-icon?id=missing')[0],400)
   opener.assert_not_called()
  with patch('server.validate_url',side_effect=lambda url:url):
   self.request('/api/reading/focus',{**focus,'name':'Fixture account','kind':'公众号','url':'https://example.com/news'})
  with patch('server.urllib.request.build_opener') as opener:
   self.assertEqual(self.request('/api/site-icon?id='+focus['id'])[0],400)
   opener.assert_not_called()

 def test_bundled_focus_icons_are_served_with_image_mime(self):
  for filename,mime in [('deepseek.svg','image/svg+xml'),('doubao.png','image/png'),('openai.png','image/png'),('anthropic.png','image/png')]:
   with urllib.request.urlopen(self.url+'/brand/'+filename) as response:
    self.assertEqual(response.headers.get_content_type(),mime)
    self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
    self.assertGreater(len(response.read()),100)

 def news_fixture(self):
  return self.app.news.store_item({'title':'Fixture article','url':'https://example.com/post','excerpt':'Original fixture RSS summary.','content_status':'summary'})[0]

 def test_article_enrich_preserves_source_and_failed_read_is_not_content(self):
  n=self.news_fixture();source=self.app.store.source(n['source_id'])
  self.assertEqual(self.request('/api/news/enrich',{'ids':[n['id']]})[0],400)
  with patch('news.fetch_article',side_effect=ValueError('Fixture login challenge')):
   status,result=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})
  self.assertEqual(status,200);self.assertFalse(result['results'][0]['ok'])
  self.assertFalse(result['items'][0].get('content'))
  with patch('news.fetch_article',return_value={'content':'Fixture full body. '*15,'content_status':'article','cover_url':'https://example.com/c.jpg'}):
   status,result=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})
  self.assertEqual(result['items'][0]['content_status'],'article')
  self.assertFalse(result['items'][0]['read_error'])
  self.assertEqual(self.app.store.source(n['source_id'])['content'],source['content'])

 def test_cover_is_cached_raster_and_missing_is_404(self):
  n=self.news_fixture()
  self.assertEqual(self.request('/api/news/'+n['id']+'/cover')[0],404)
  self.app.news.update_item(n['id'],{'cover_url':'https://example.com/cover.png'})
  raw=b'\x89PNG\r\n\x1a\nfixture'
  with patch('news.fetch_image',return_value=(raw,'image/png')) as fetch:
   for _ in range(2):
    with urllib.request.urlopen(self.url+'/api/news/'+n['id']+'/cover') as response:
     self.assertEqual(response.headers['Content-Type'],'image/png')
     self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
     self.assertEqual(response.read(),raw)
   self.assertEqual(fetch.call_count,1)

 def test_inline_image_endpoint_is_bound_cached_and_preserves_source(self):
  n=self.news_fixture();original=self.app.store.source(n['source_id'])['content']
  text='Explicit full article with a chart. '*10
  blocks=content_blocks([{'type':'text','text':text},{'type':'image','url':'https://example.com/chart.png','alt':'Fixture chart'}],text)
  with patch('news.fetch_article',return_value={'content':text,'content_status':'article','content_blocks':blocks}) as read:
   first=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})[1]
   second=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})[1]
   self.assertEqual(read.call_count,1)
   self.assertTrue(second['results'][0]['cached'])
  self.assertEqual(first['items'][0]['content_blocks'],blocks)
  route='/api/news/'+n['id']+'/images/'+blocks[1]['id']
  raw=b'\x89PNG\r\n\x1a\nfixture'
  with patch('news.fetch_image',return_value=(raw,'image/png')) as fetch:
   for _ in range(2):
    with urllib.request.urlopen(self.url+route) as response:
     self.assertEqual(response.read(),raw)
     self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
   self.assertEqual(fetch.call_count,1)
   self.assertEqual(fetch.call_args.kwargs['referer'],n['url'])
   self.assertEqual(self.request('/api/news/'+n['id']+'/images/'+'0'*24)[0],404)
   self.assertEqual(fetch.call_count,1,'unknown IDs must not fetch any URL')
  self.assertEqual(self.app.store.source(n['source_id'])['content'],original)

 def test_browser_enrichment_preserves_capture_and_drops_stale_blocks(self):
  n=self.news_fixture();text='Browser-only fixture article. '*10
  self.app.news.update_item(n['id'],{'content':text,'content_status':'browser','collection_method':'browser_use_mcp'})
  different='Different public page. '*10
  with patch('news.fetch_article',return_value={'content':different,'content_status':'article','content_blocks':[{'type':'text','text':different}]}):
   result=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})[1]
  self.assertFalse(result['results'][0]['ok'])
  self.assertEqual(result['items'][0]['content'],text)
  self.assertEqual(result['items'][0]['collection_method'],'browser_use_mcp')
  blocks=content_blocks([{'type':'text','text':text},{'type':'image','url':'https://example.com/c.png'}],text)
  with patch('news.fetch_article',return_value={'content':text,'content_status':'article','content_blocks':blocks}):
   result=self.request('/api/news/enrich',{'ids':[n['id']],'allow_remote':True})[1]
  self.assertTrue(result['results'][0]['ok'])
  self.assertEqual(result['items'][0]['content_status'],'browser')
  self.assertEqual(result['items'][0]['content_blocks'],blocks)
  updated=self.app.news.update_item(n['id'],{'content':different})
  self.assertNotIn('content_blocks',updated)

 def test_body_image_internal_url_is_not_fetched(self):
  n=self.news_fixture();text='Explicit fixture body.'
  blocks=content_blocks([{'type':'text','text':text},{'type':'image','url':'http://127.0.0.1/private.png'}],text)
  self.app.news.update_item(n['id'],{'content':text,'content_blocks':blocks})
  with patch('article_reader.urllib.request.build_opener') as opener:
   self.assertEqual(self.request('/api/news/'+n['id']+'/images/'+blocks[1]['id'])[0],404)
   opener.assert_not_called()

 def test_news_notes_validate_against_full_body_without_rewriting_source(self):
  n=self.news_fixture();source=self.app.store.source(n['source_id'])
  self.app.news.update_item(n['id'],{'content':'Fixture full article quote, not in original summary.','content_status':'article'})
  status,note=self.request('/api/notes',{'kind':'news','id':n['id'],'quote':'full article quote','text':'Explicit fixture note.'})
  self.assertEqual(status,200)
  self.assertEqual(self.request('/api/notes?kind=news&id='+n['id'])[1][0]['id'],note['id'])
  self.assertEqual(self.request('/api/notes',{'kind':'news','id':n['id'],'quote':'invented quotation','text':'Fixture'})[0],400)
  self.assertEqual(self.app.store.source(n['source_id'])['content'],source['content'])

 def test_reference_uses_full_article_preserves_cited_summary_and_is_idempotent(self):
  n=self.news_fixture();source=self.app.store.source(n['source_id'])
  self.request('/api/reading/favorite',{'id':source['id'],'category':'Harness'})
  text='Explicit fixture article full body, not just its RSS summary. '*10
  self.app.news.update_item(n['id'],{'content':text,'content_status':'article'})
  status,result=self.request('/api/news/reference',{'id':n['id']})
  self.assertEqual(status,200,result)
  self.assertTrue(result['updated'])
  self.assertIn(text.strip(),self.app.store.source(result['source_id'])['content'])
  self.assertEqual(self.app.store.source(source['id'])['content'],source['content'])
  self.assertEqual(self.request('/api/state')[1]['reading']['favorites'],[result['source_id']])
  repeated=self.request('/api/news/reference',{'id':n['id']})[1]
  self.assertFalse(repeated['updated'])
  self.assertEqual(result['source_id'],repeated['source_id'])
  self.assertEqual(self.app.store.jobs(),[])

 def test_capture_rejects_challenge_future_date_and_invalid_origin(self):
  capture={'title':'Fixture browser article','url':'https://example.com/browser','content':'Actual fixture visible body. '*10,'published_at':None}
  self.app.news.validator=lambda _:None
  status,result=self.request('/api/news/capture',{'article':capture})
  self.assertEqual(status,200);self.assertEqual(result['item']['collection_method'],'visible_browser')
  self.assertIsNone(result['item']['published_at'])
  self.assertEqual(self.request('/api/news/capture',{'article':{**capture,'title':'Access denied'}})[0],400)
  self.assertEqual(self.request('/api/news/capture',{'article':{**capture,'published_at':'2099-01-01T00:00:00Z'}})[0],400)
  self.assertEqual(self.request('/api/news/capture',{'article':capture},{'Origin':'https://attacker.example'})[0],403)

 def test_url_asset_rejects_challenge_without_creating_source(self):
  before=len(self.app.store.sources())
  html=b'<title>Just a moment...</title><main>'+b'Checking your browser. '*20+b'</main>'
  with patch('article_reader.fetch_bytes',return_value=(html,'text/html','utf-8','https://example.com/blocked')):
   self.assertEqual(self.request('/api/sources',{'url':'https://example.com/blocked'})[0],400)
  self.assertEqual(len(self.app.store.sources()),before)
