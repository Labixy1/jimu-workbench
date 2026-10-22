"""Scripted local fixtures for repair isolation; no model-quality claim."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

from domain import Store
from engine import Runner
from test_board_graph import fixture_graph


class FixtureEngine:
    def __init__(self, directory, replies):
        self.directory=directory
        self.replies=iter(replies)
        self.sessions=[]
        self.prompts=[]
        self.last_tools=[]

    def configure(self, *args):
        return {'providerID':'fixture','modelID':'fixture'}

    def create(self, agent, model, parent=None, read_file=None):
        sid='fixture_'+str(len(self.sessions)+1)
        self.sessions.append({'id':sid,'agent':agent,'parent':parent})
        return sid

    def prompt(self, sid, text, agent, model):
        self.prompts.append({'id':sid,'text':text,'agent':agent})
        return next(self.replies)


class RunnerRepairTests(unittest.TestCase):
    def run_fixture(self, first_draft, verdicts=None):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=Store(root/'db')
            quote='Only selected material is read; users decide when to save.'
            source=store.add_source('Fixture source',quote)['source']
            research={'findings':[{'source_id':source['id'],'quote':quote,'insight':'Fixture evidence'}],'uncertainties':[]}
            page={'title':'Fixture graph','summary':'Fixture','content':'Read, verify, then save.',
                  'tags':[],'links':[],'diagram':[],'graph':fixture_graph(),
                  'citations':[{'source_id':source['id'],'quote_id':'evidence_1'}]}
            proposal=json.dumps({'page':page})
            passed={'passed':True,'issues':[],'summary':'Fixture verification'}
            replies=[json.dumps(research),first_draft,proposal,json.dumps(passed)]
            if verdicts:
                replies=[json.dumps(research),proposal,json.dumps(verdicts),proposal,json.dumps(passed)]
            engine=FixtureEngine(root,replies)
            job=store.create_job(store.conversation(),'map-agent',{'kind':'wiki','prompt':'Fixture graph',
                'source_ids':[source['id']],'output_board':True,'preferences_snapshot':{},'history_snapshot':[]})
            Runner(store,engine,{'mode':'model','model':'fixture','base_url':'http://127.0.0.1:1'}).run(job['id'],threading.Event())
            result=store.job(job['id']);store.db.close()
            return result,engine

    def test_unparseable_draft_has_one_isolated_repair(self):
        result,engine=self.run_fixture('Not JSON: fixture failure')
        self.assertEqual(result['status'],'review',result['payload'].get('error'))
        self.assertNotEqual(engine.prompts[1]['id'],engine.prompts[2]['id'])
        root=engine.sessions[0]['id']
        repair=next(s for s in engine.sessions if s['id']==engine.prompts[2]['id'])
        self.assertEqual(repair['parent'],root)
        self.assertIn('unparsed_text',engine.prompts[2]['text'])
        self.assertEqual(result['payload']['proposal']['page']['citations'][0]['quote'],
                         'Only selected material is read; users decide when to save.')

    def test_invalid_schema_is_not_silently_accepted(self):
        result,engine=self.run_fixture(json.dumps({'page':{'title':'Missing evidence'}}))
        self.assertEqual(result['status'],'review',result['payload'].get('error'))
        self.assertEqual(len(engine.prompts),4)
        self.assertNotEqual(engine.prompts[1]['id'],engine.prompts[2]['id'])

    def test_reviewer_feedback_uses_new_writer_session(self):
        feedback={'passed':False,'issues':['Fixture unsupported claim'],'summary':'Fix it'}
        result,engine=self.run_fixture('',feedback)
        self.assertEqual(result['status'],'review',result['payload'].get('error'))
        self.assertNotEqual(engine.prompts[1]['id'],engine.prompts[3]['id'])
        self.assertIn('Fixture unsupported claim',engine.prompts[3]['text'])


if __name__=='__main__':
    unittest.main()
