import unittest
import test_api
from context import check_context, recent_history, research_quote_anchors, stage_context


class ContextTests(unittest.TestCase):
    def test_history_is_explicitly_bounded_and_original_unchanged(self):
        messages=[{'role':'user','text':'x'*2000} for _ in range(12)]
        selected,meta=recent_history(messages)
        self.assertEqual(len(selected),8)
        self.assertEqual(meta['messages_omitted'],4)
        self.assertEqual(meta['messages_shortened'],8)
        self.assertEqual(len(messages[0]['text']),2000)

    def test_research_and_review_do_not_inherit_chat_or_preferences(self):
        p={'prompt':'test','kind':'wiki','sources':[{'id':'s'}],
           'recent_history':['private chat'],'preferences':{'instructions':'tone'},
           'research':{'findings':[]},'invalid_proposal':{},'proposal':{'page':{}},
           'career_snapshot':{'confirmed':True}}
        research=stage_context(p,'research');review=stage_context(p,'review')
        for child in (research,review):
            self.assertNotIn('recent_history',child)
            self.assertNotIn('preferences',child)
            self.assertNotIn('invalid_proposal',child)
        self.assertIn('proposal',review)
        self.assertNotIn('research',review)
        self.assertIn('research',stage_context(p,'draft'))

    def test_combined_budget_rejects_without_truncating(self):
        source={'content':'x'*34000}
        with self.assertRaises(ValueError):check_context('test',[source],[{'body':{'content':'y'*4000}}],{},[])
        self.assertEqual(len(source['content']),34000)

    def test_revision_receives_actual_reviewer_feedback(self):
        packet={'prompt':'fixture','review_feedback':{'passed':False,'issues':['Unsupported claim']},
                'proposal':{'page':{'title':'Current draft'}}}
        self.assertEqual(stage_context(packet,'draft')['review_feedback'],packet['review_feedback'])
        self.assertEqual(stage_context(packet,'draft')['proposal'],packet['proposal'])
        self.assertNotIn('review_feedback',stage_context(packet,'research'))

    def test_quote_anchors_reuse_selected_evidence_without_copying_full_sources(self):
        quote='Only selected evidence may support the result.'
        original=quote+'\n'+'unrelated text '*2000
        source={'id':'s','content':original}
        research={'findings':[{'source_id':'s','quote':quote},
                              {'source_id':'s','quote':quote},
                              {'source_id':'other','quote':quote},
                              {'source_id':'s','quote':'invented quotation'},
                              {'source_id':{},'quote':quote}]}
        anchors=research_quote_anchors([source],research)
        self.assertEqual(anchors,[{'source_id':'s','quote_id':'evidence_1','quote':quote}])
        self.assertLess(len(str(anchors)),200)
        self.assertEqual(source['content'],original)


class ContextApiTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def test_source_snapshot_and_budget_frozen(self):
        source=self.app.store.add_source('test source','evidence and findings')['source']
        _,job=self.request('/api/jobs',{'kind':'chat','prompt':'test','source_ids':[source['id']]})
        self.assertEqual(job['payload']['source_snapshot'][source['id']]['content'],source['content'])
        self.assertEqual(job['payload']['context_meta']['source_count'],1)

    def test_rejected_wiki_input_does_not_save_narrative(self):
        status,_=self.request('/api/jobs',{'kind':'experience','prompt':'test',
            'narrative':'User supplied narrative with enough characters.', 'wiki_ids':['missing']})
        self.assertEqual(status,400)
        self.assertEqual(self.app.store.sources(),[])

    def test_clear_preferences_only_clears_preferences(self):
        source=self.app.store.add_source('fixture','unchanged original')['source']
        self.request('/api/memory',{'instructions':'concise'})
        self.assertEqual(self.request('/api/memory',{'instructions':{'not':'text'}})[0],400)
        self.assertEqual(self.request('/api/memory',{'instructions':''})[0],200)
        self.assertEqual(self.app.store.source(source['id'])['content'],'unchanged original')
        self.assertEqual(self.app.memory()['instructions'],'')
