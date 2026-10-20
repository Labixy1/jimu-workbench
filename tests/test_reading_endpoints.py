import test_api
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
