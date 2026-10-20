import unittest
import test_api
from career import validate_proposal


class CoreTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def experience(self):
        narrative='我负责整理测试记录和用户反馈，发现图片主体不一致的问题，并给出三条改进建议。暂时没有上线后的结果数据。'
        status,job=self.request('/api/jobs',{'kind':'experience','prompt':'整理我的经历','narrative':narrative})
        self.assertEqual(status,202)
        sid=job['payload']['source_ids'][0]
        proposal={'title':'测试经历','facts':[{'text':'整理测试记录与反馈','ownership':'本人负责整理，不代表独立负责整个产品','evidence':[{'source_id':sid,'quote':'我负责整理测试记录和用户反馈'}]}],'general':'我负责整理测试记录和用户反馈，发现图片主体不一致的问题，并给出三条改进建议。','questions':['建议是否上线仍需确认']}
        self.app.store.update_job(job['id'],'review',proposal=proposal)
        return job,proposal

    def test_experience_requires_narrative(self):
        self.assertEqual(self.request('/api/jobs',{'kind':'experience','prompt':'整理'})[0],400)

    def test_facts_need_explicit_confirmation(self):
        job,p=self.experience()
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{})[0],400)
        status,page=self.request('/api/jobs/'+job['id']+'/approve',{'confirmed_fact_ids':['fact_1'],'general':p['general']})
        self.assertEqual(status,200);self.assertEqual(page['kind'],'career')
        self.assertTrue(page['body']['confirmed'])
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{})[1]['id'],page['id'])
        return page

    def test_fabricated_quote_blocked(self):
        job,p=self.experience();p['facts'][0]['evidence'][0]['quote']='我独立负责整个系统并提升业绩50%'
        with self.assertRaises(ValueError):validate_proposal(p,job['payload'],{s['id']:s for s in self.app.store.sources()})

    def tailor(self):
        page=self.test_facts_need_explicit_confirmation()
        jd=self.app.store.add_source('招聘JD','岗位要求：设计Agent评测维度，分析用户反馈，推动产品迭代。')['source']
        status,job=self.request('/api/jobs',{'kind':'tailor','prompt':'按JD诊断','source_ids':[jd['id']],'jd_source_ids':[jd['id']],'career_id':page['id'],'career_revision':1})
        self.assertEqual(status,202)
        proposal={'title':'Agent岗位诊断','diagnostics':[{'quote':'我负责整理测试记录和用户反馈','category':'gap','problem':'未展示评测维度设计经历','suggestion':'先确认是否参与设计维度，不应编造','jd_evidence':[{'source_id':jd['id'],'quote':'设计Agent评测维度，分析用户反馈'}]}],'tailored':'整理测试记录与用户反馈，发现图片主体不一致问题，提出三条改进建议。'}
        return page,job,proposal

    def test_tailor_quote_and_ability_guard(self):
        page,job,p=self.tailor();checked=validate_proposal(p,job['payload'],{s['id']:s for s in self.app.store.sources()})
        self.assertEqual(checked['diagnostics'][0]['category'],'evidence')
        p['diagnostics'][0]['quote']='这句话不存在'
        with self.assertRaises(ValueError):validate_proposal(p,job['payload'],{s['id']:s for s in self.app.store.sources()})

    def test_tailor_anchor_resolves_exact_original(self):
        from career import quote_anchors
        page,job,p=self.tailor();d=p['diagnostics'][0];d.pop('quote');d['quote_id']='quote_1'
        sources={s['id']:s for s in self.app.store.sources()}
        checked=validate_proposal(p,job['payload'],sources)
        self.assertEqual(checked['diagnostics'][0]['quote'],quote_anchors(job['payload'])[0]['quote'])
        d['quote_id']='quote_99'
        with self.assertRaises(ValueError):validate_proposal(p,job['payload'],sources)
        d['quote_id']='quote_1';d['quote']='不存在的句子'
        with self.assertRaises(ValueError):validate_proposal(p,job['payload'],sources)

    def test_jd_evidence_anchor_is_exact_and_cannot_override_text(self):
        from career import evidence, source_quote_anchors
        source={'id':'src_demo','content':'岗位要求：分析商家反馈，设计质量评测维度。'}
        anchor=source_quote_anchors([source])[0]
        refs=[{'source_id':source['id'],'quote_id':anchor['quote_id']}]
        self.assertEqual(evidence(refs,{source['id']:source})[0]['quote'],source['content'])
        refs[0]['quote']='伪造的JD原句'
        with self.assertRaises(ValueError):evidence(refs,{source['id']:source})

    def test_tailor_preserves_general_and_saves_separately(self):
        page,job,p=self.tailor();self.app.store.update_job(job['id'],'review',proposal=p)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{})[0],400)
        status,result=self.request('/api/jobs/'+job['id']+'/approve',{'confirm_no_new_claims':True,'tailored':p['tailored']})
        self.assertEqual(status,200);self.assertEqual(result['kind'],'career_review')
        self.assertEqual(self.app.store.artifact(page['id'])['body']['general'],page['body']['general'])
        self.assertEqual(result['body']['career_id'],page['id'])

    def test_tailor_stale_base_blocked(self):
        page,job,p=self.tailor();self.app.store.update_job(job['id'],'review',proposal=p)
        self.app.store.db.execute('UPDATE artifacts SET revision=2 WHERE id=?',(page['id'],));self.app.store.db.commit()
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{'confirm_no_new_claims':True})[0],409)

    def test_board_roundtrip_and_revision(self):
        scene={'elements':[{'type':'rectangle','id':'x','x':1,'y':2,'width':120,'height':80}],'appState':{'viewBackgroundColor':'#fff'},'files':{}}
        status,p=self.request('/api/boards',{'title':'流程画板','scene':scene})
        self.assertEqual(status,200);self.assertEqual(p['body']['scene']['elements'],scene['elements'])
        self.assertEqual(self.request('/api/boards',{'id':p['id'],'revision':0,'title':'覆盖','scene':scene})[0],409)
        status,new=self.request('/api/boards',{'id':p['id'],'revision':1,'title':'第二版','scene':scene})
        self.assertEqual(status,200);self.assertEqual(new['revision'],2)
        versions=self.app.store.versions(p['id']);restored=self.app.store.restore(p['id'],versions[-1]['id'],2)
        self.assertEqual(restored['title'],'流程画板');self.assertEqual(restored['revision'],3)

    def test_board_rejects_external_files_and_links(self):
        for element in ({'type':'image','id':'x'},{'type':'rectangle','id':'x','link':'https://evil.test'}):
            self.assertEqual(self.request('/api/boards',{'title':'unsafe','scene':{'elements':[element]}})[0],400)
        self.assertEqual(self.request('/api/boards',{'title':'unsafe','scene':{'files':{'x':{'dataURL':'https://evil.test'}}}})[0],400)

    def test_site_presets_do_not_start_schedule(self):
        status,sites=self.request('/api/sites');self.assertEqual(status,200);self.assertEqual(len(sites),5)
        self.assertFalse(self.request('/api/state')[1]['weekly']['config']['enabled'])

    def test_local_board_assets_and_traversal(self):
        self.assertEqual(self.request('/../../server.py')[0],404)

    def test_edit_experience_invalidates_pending_tailor(self):
        page,job,p=self.tailor();self.app.store.update_job(job['id'],'review',proposal=p)
        status,edited=self.request('/api/career/edit',{'id':page['id'],'revision':1,'content':'新的用户确认表达，不增加事实。','confirmed':True})
        self.assertEqual(status,200);self.assertEqual(edited['revision'],2)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/approve',{'confirm_no_new_claims':True})[0],409)
        self.assertEqual(self.request('/api/career/edit',{'id':page['id'],'revision':1,'content':'旧版覆盖','confirmed':True})[0],409)

    def test_selected_search_sites_filter_results(self):
        from unittest.mock import patch
        response={'results':[{'title':'official','url':'https://api-docs.deepseek.com/test','snippet':'test'},{'title':'other','url':'https://evil.test/article'}]}
        with patch('server.deepseek_web_request',return_value=response) as call:
            status,result=self.request('/api/web/search',{'query':'Agent','site_ids':['deepseek'],'allow_remote':True})
        self.assertEqual(status,200);self.assertEqual(len(result['results']),1)
        self.assertIn('site:api-docs.deepseek.com',call.call_args[0][2]['query'])
        self.assertEqual(self.request('/api/web/search',{'query':'test','site_ids':['unknown'],'allow_remote':True})[0],400)
