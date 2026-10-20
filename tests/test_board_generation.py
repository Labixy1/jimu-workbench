import unittest
import test_api
import boards
import library
class BoardGenerationTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request
    def test_skill_to_board_manual_save_and_favorite(self):
        s=self.app.store.add_source('测试流程','先上传资料，再核对依据，最后保存结果。')['source']
        skill=next(s for s in self.app.state()['skills'] if s['id']=='board-generation')
        status,j=self.request('/api/jobs',{'kind':'wiki','prompt':'生成测试流程图','source_ids':[s['id']],'skill_refs':[{'id':skill['id'],'revision':skill['revision']}]})
        self.assertEqual(status,202);self.assertTrue(j['payload']['output_board'])
        page={'title':'测试流程图','summary':'测试','content':'上传→核对→保存','tags':[],'links':[],'diagram':['上传资料','核对依据','保存结果'],'citations':[{'source_id':s['id'],'quote':s['content']}]}
        j=self.app.store.update_job(j['id'],'review',proposal={'page':page},board_draft_scene=boards.flow_scene(page['diagram']))
        self.assertFalse(any(a['kind']=='board' for a in self.app.store.artifacts()))
        status,j=self.request('/api/jobs/'+j['id']+'/draft',{'scene':boards.flow_scene(['上传资料','阅读材料','核对依据','保存结果']),'title':'编辑后流程图','expected_updated':j['updated']})
        self.assertEqual(status,200)
        status,a=self.request('/api/jobs/'+j['id']+'/approve',{})
        self.assertEqual(status,200);self.assertEqual(a['kind'],'board');self.assertEqual(a['title'],'编辑后流程图')
        self.assertEqual(len([e for e in a['body']['scene']['elements'] if e['type']=='text']),4)
        self.assertEqual(next(x for x in library.catalog(self.app.store) if x['id']==a['id'])['origin'],'ai')
        self.assertEqual(self.request('/api/jobs/'+j['id']+'/approve',{})[1]['id'],a['id'])
        self.assertEqual(self.request('/api/reading/favorite',{'id':a['id'],'category':'Harness'})[0],200)
        self.assertIn(a['id'],self.app.state()['reading']['favorites'])
    def test_invalid_flow_and_scene(self):
        with self.assertRaises(ValueError):boards.flow_scene([])
        with self.assertRaises(ValueError):boards.scene({'elements':[{'id':'bad','type':'image'}]})
