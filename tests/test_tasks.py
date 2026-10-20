import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_api
from career import instruction


class TaskTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def test_resume_format_frozen_in_job(self):
        status,job=self.request('/api/jobs',{'kind':'experience','output_format':'resume','prompt':'write resume','narrative':'本人负责整理反馈和建议清单，没有上线效果数据，需要保留职责边界。'})
        self.assertEqual(status,202)
        self.assertEqual(job['payload']['output_format'],'resume')

    def test_unknown_format_rejected_before_evidence_write(self):
        status,_=self.request('/api/jobs',{'kind':'experience','output_format':'invalid','prompt':'write resume','narrative':'本人负责整理反馈和建议清单，没有上线效果数据，需要保留职责边界。'})
        self.assertEqual(status,400)
        self.assertEqual(self.app.store.sources(),[])

    def test_resume_prompt_is_not_short_experience_prompt(self):
        self.assertIn('完整简历',instruction('experience','resume'))
        self.assertIn('300至700字',instruction('tailor','resume'))
        self.assertIn('120至250字',instruction('experience'))

    def page(self):
        return self.request('/api/wiki',{'page':{'title':'测试流程','summary':'测试','content':'自己的学习笔记','tags':[],'links':[],'citations':[],'diagram':['读材料','核对事实','保存知识']}})[1]

    def test_approved_flow_builds_independent_linked_board(self):
        page=self.page()
        status,board=self.request('/api/boards/from-wiki',{'id':page['id'],'revision':page['revision']})
        self.assertEqual(status,200)
        self.assertEqual(board['body']['linked_id'],page['id'])
        self.assertEqual(len(board['body']['scene']['elements']),8)
        self.assertEqual(self.app.store.artifact(page['id'])['revision'],page['revision'])

    def test_stale_wiki_cannot_generate_board(self):
        page=self.page()
        self.assertEqual(self.request('/api/boards/from-wiki',{'id':page['id'],'revision':0})[0],409)
        self.assertFalse(any(a['kind']=='board' for a in self.app.store.artifacts()))

    def test_empty_flow_rejected(self):
        page=self.page()
        page=self.request('/api/wiki',{'id':page['id'],'revision':1,'page':{**page['body'],'diagram':[]}})[1]
        self.assertEqual(self.request('/api/boards/from-wiki',{'id':page['id'],'revision':2})[0],400)


if __name__=='__main__':unittest.main()
