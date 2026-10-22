import unittest
from unittest.mock import patch
import test_api
from task_skills import task_method
from context import stage_context


class SimpleLoopTests(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_send_button_is_authorization_without_second_confirmation(self):
        self.app.settings.update(mode='model', base_url='https://provider.example/v1')
        status, job = self.request('/api/jobs', {'kind':'chat','prompt':'Hello', 'send_to_model':True})
        self.assertEqual(status,202)
        self.assertEqual(job['payload']['source_ids'],[])
        self.assertEqual(job['status'],'queued')
        self.assertFalse(any(a['kind']=='wiki' for a in self.app.store.artifacts()))

    def test_no_authorization_creates_no_empty_conversation(self):
        self.app.settings.update(mode='model',base_url='https://provider.example/v1')
        self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'Hello'})[0],400)
        self.assertEqual(self.app.store.conversations(),[])

    def test_title_is_stable_and_reuses_existing_result(self):
        cid=self.app.store.conversation()
        self.app.store.message(cid,'user','请帮我整理商品图项目经历','first')
        self.app.store.summarize_title(cid,'商品图项目经历','first')
        self.app.store.message(cid,'user','再短一点','second')
        self.app.store.summarize_title(cid,'再短一点','second')
        self.assertEqual(self.app.store.conversations()[0]['title'],'商品图项目经历')

    def test_generated_title_is_not_cut_mid_model_or_version_name(self):
        cid=self.app.store.conversation()
        self.app.store.message(cid,'user','整理所选源码','first')
        title='OpenCode Agent Loop（22e771f 源码摘录）'
        self.app.store.summarize_title(cid,title,'first')
        self.assertEqual(self.app.store.conversations()[0]['title'],title)
        self.app.store.summarize_title(cid,'x'*200,'first')
        self.assertEqual(len(self.app.store.conversations()[0]['title']),80)

    def test_skill_is_task_specific_and_frozen(self):
        source=self.app.store.add_source('公开材料','这是公开材料的原始内容，需要有准确的原文依据。')['source']
        _,job=self.request('/api/jobs',{'kind':'wiki','prompt':'整理知识','source_ids':[source['id']]})
        self.assertEqual(job['payload']['task_method']['name'],'knowledge-compilation')
        self.assertEqual(job['payload']['task_method']['sha256'],task_method('wiki')['sha256'])
        self.assertIsNone(task_method('chat'))
        for kind in ('wiki','experience','tailor'):
            self.assertIn('name:',task_method(kind)['instructions'])

    def board(self):
        return self.request('/api/boards',{'title':'测试画板','scene':{'elements':[
            {'id':'label','type':'text','text':'提出任务 → 核对事实','x':0,'y':0,'width':100,'height':20},
            {'id':'deleted','type':'text','text':'已删除的秘密','isDeleted':True}
        ]}})[1]

    def test_board_reference_is_bounded_text_and_frozen_revision(self):
        b=self.board()
        status,job=self.request('/api/jobs',{'kind':'chat','prompt':'解释这个画板','board_refs':[{'id':b['id'],'revision':1}]})
        self.assertEqual(status,202)
        snapshot=job['payload']['board_snapshot'][0]
        self.assertEqual(snapshot['content'],'提出任务 → 核对事实')
        self.assertNotIn('scene',snapshot)
        self.assertEqual(job['payload']['context_meta']['board_count'],1)
        self.request('/api/boards',{'id':b['id'],'revision':1,'title':'新版画板','scene':{'elements':[]}})
        self.assertEqual(job['payload']['board_snapshot'][0]['revision'],1)
        self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'test','board_refs':[{'id':b['id'],'revision':1}]})[0],409)

    def test_board_archived_empty_or_overlimit_is_not_sent(self):
        b=self.board()
        refs=[{'id':b['id'],'revision':1}]*4
        self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'test','board_refs':refs})[0],400)
        self.app.store.archive('artifact',b['id'])
        self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'test','board_refs':refs[:1]})[0],400)
        self.assertEqual(self.app.store.conversations(),[])

    def test_changed_board_prevents_formal_save(self):
        b=self.board()
        _,job=self.request('/api/jobs',{'kind':'chat','prompt':'test','board_refs':[{'id':b['id'],'revision':1}]})
        self.app.store.update_job(job['id'],'review')
        self.request('/api/boards',{'id':b['id'],'revision':1,'title':'changed','scene':{'elements':[]}})
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{})[0],409)
        self.assertEqual(self.app.store.job(job['id'])['status'],'review')

    def test_child_context_does_not_get_whole_history_or_board_scene(self):
        packet={'prompt':'test','sources':[],'task_method':task_method('wiki'),
                'boards':[{'content':'labels'}],'recent_history':['private'],'preferences':{}}
        for child in ('research','review'):
            context=stage_context(packet,child)
            self.assertNotIn('recent_history',context)
            self.assertNotIn('boards',context)
            self.assertIn('task_method',context)
        self.assertIn('boards',stage_context(packet,'draft'))

    def test_scheduler_is_disabled_even_if_called(self):
        config=self.app.weekly.save({'title':'手动主题','urls':[],'query':'','new':True})
        self.assertFalse(config['enabled'])
        with patch('weekly.threading.Thread') as thread:
            self.app.weekly.start();self.app.weekly.tick()
            thread.assert_not_called()
        with self.assertRaisesRegex(ValueError,'手动更新'):
            self.app.weekly.toggle(config['id'],config['revision'],True,True)


    def test_more_than_three_skills_and_invalid_references(self):
        import task_skills
        refs=[{'id':s['id'],'revision':s['revision']} for s in task_skills.all_skills(self.app.store)]
        self.assertGreater(len(refs),3)
        status,job=self.request('/api/jobs',{'kind':'chat','prompt':'按所选技能回答','skill_refs':refs})
        self.assertEqual(status,202)
        self.assertEqual(len(job['payload']['skill_snapshot']),len(refs))
        self.assertEqual(self.request('/api/jobs',{'kind':'chat','prompt':'test','skill_refs':{}})[0],400)

    def test_draft_edit_revision_and_manual_save(self):
        source=self.app.store.add_source('公开测试原文','这是公开测试原文，必须保留原始证据和引用。')['source']
        _,j=self.request('/api/jobs',{'kind':'wiki','prompt':'test','source_ids':[source['id']]})
        j=self.app.store.update_job(j['id'],'review',proposal={'page':{'title':'test','summary':'test','content':'# test','tags':[],'links':[],'citations':[{'source_id':source['id'],'quote':source['content']}]}})
        before=len(self.app.store.artifacts())
        self.assertEqual(self.request('/api/jobs/'+j['id']+'/draft',{'title':'edited','content':'# edited','expected_updated':'stale'})[0],409)
        status,edited=self.request('/api/jobs/'+j['id']+'/draft',{'title':'edited','content':'# edited','expected_updated':j['updated']})
        self.assertEqual(status,200);self.assertEqual(len(self.app.store.artifacts()),before)
        status,asset=self.request('/api/jobs/'+j['id']+'/approve',{})
        self.assertEqual(status,200);self.assertEqual(asset['body']['content'],'# edited')
        self.assertEqual(self.request('/api/jobs/'+j['id']+'/draft',{'title':'late','content':'late','expected_updated':edited['updated']})[0],409)
