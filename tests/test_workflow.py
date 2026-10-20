# coding: utf-8
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from domain import Store, Conflict
from retrieval import retrieve, selected_context
from server import App
from weekly import next_time, same_site
import test_api


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()
    def test_bounded_retrieval_and_exact_excerpt(self):
        s=self.store.add_source('品牌经营','品牌经营需要一致的指标口径。'*900)['source']
        self.store.add_source('无关文章','小猫喜欢吃鱼。')
        hits=retrieve(self.store,'品牌经营指标口径')
        self.assertEqual(len(hits),2)
        self.assertTrue(all(h['id']==s['id'] and len(h['excerpt'])<=1200 for h in hits))
        sources,pages=selected_context(self.store,hits[:1])
        self.assertEqual(sources[s['id']]['content'].strip(),hits[0]['excerpt'])
        self.assertLess(len(sources[s['id']]['content']),len(s['content']))
        self.assertEqual(pages,{})
    def test_archive_and_stale_selection(self):
        s=self.store.add_source('Harness','Harness 管理工具权限与执行状态。')['source']
        hit=retrieve(self.store,'Harness')[0]
        self.store.archive('source',s['id'])
        self.assertEqual(retrieve(self.store,'Harness'),[])
        with self.assertRaises(ValueError):selected_context(self.store,[hit])
    def test_wiki_revision_guard(self):
        page=self.store.save_wiki({'title':'品牌记忆','summary':'规则','content':'品牌记忆包括视觉规则和用户偏好。'})
        hit=retrieve(self.store,'品牌记忆')[0]
        self.store.save_wiki(page['body'],page['id'],1)
        with self.assertRaises(ValueError):selected_context(self.store,[hit])
    def test_empty_and_invalid_input(self):
        self.assertEqual(retrieve(self.store,'完全无关'),[])
        with self.assertRaises(ValueError):retrieve(self.store,'')
        with self.assertRaises(ValueError):selected_context(self.store,[{'kind':'code'}])


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App(Path(self.tmp.name),None)
        self.app.settings.update(mode='deepseek',model='deepseek-flash')
        self.app.runner.submit=lambda job:None
        self.weekly=self.app.weekly;self.weekly.validator=lambda url: url
        self.cfg={'title':'Harness 周刊','query':'','urls':['https://example.com/news'],'weekday':4,'time':'19:00','enabled':False,'allow_remote':False}
    def tearDown(self):
        self.app.store.db.close();self.tmp.cleanup()
    def test_disabled_by_default_and_consent(self):
        self.assertFalse(self.weekly.config()['enabled'])
        self.weekly.save(self.cfg)
        with self.assertRaises(ValueError):self.weekly.save({**self.cfg,'enabled':True})
        with self.assertRaises(ValueError):self.weekly.manual(False)
    def test_validation(self):
        for bad in ({'time':'99:00'},{'weekday':7},{'urls':['https://example.com?token=secret']},{'urls':['https://example.com']*9}):
            with self.assertRaises(ValueError):self.weekly.save({**self.cfg,**bad})
    def test_time_in_shanghai(self):
        instant=datetime(2026,10,16,10,59,tzinfo=timezone.utc)
        self.assertEqual(next_time(self.cfg,instant),'2026-10-16T11:00:00+00:00')
        self.assertEqual(next_time(self.cfg,instant.replace(hour=11,minute=0)),'2026-10-23T11:00:00+00:00')
    def test_daily_schedule_and_old_weekly_compatibility(self):
        instant=datetime(2026,10,16,11,0,tzinfo=timezone.utc)
        self.assertEqual(next_time({**self.cfg,'frequency':'daily'},instant),'2026-10-17T11:00:00+00:00')
        saved=self.weekly.save({**self.cfg,'frequency':'daily'})
        self.assertEqual(saved['frequency'],'daily')
        self.assertEqual(self.weekly.save(self.cfg)['frequency'],'weekly')
        with self.assertRaises(ValueError):self.weekly.save({**self.cfg,'frequency':'bad'})
    def test_claim_is_durable_and_deduplicated(self):
        rid=self.weekly.claim(self.cfg,'slot')
        with self.assertRaises(Conflict):self.weekly.claim(self.cfg,'slot2')
        self.weekly.update(rid,'no_updates')
        self.assertIsNone(self.weekly.claim(self.cfg,'slot'))
    def test_only_allowlisted_sites(self):
        self.assertTrue(same_site('https://example.com/news/a','https://example.com/news'))
        self.assertFalse(same_site('https://example.com.evil/news/a','https://example.com/news'))
        self.assertFalse(same_site('https://other.com/news/a','https://example.com/news'))
        self.assertFalse(same_site('javascript:alert(1)','https://example.com'))
    def collect(self,cfg=None,content=None):
        cfg=cfg or self.cfg;rid=self.weekly.claim(cfg,'test-'+str(len(self.weekly.runs())))
        page={'title':'Public guide','content':content or 'Agent 工具执行必须有真实结果与可核验的引用。'*60}
        with patch('weekly.model_key',return_value='test-key'),patch('weekly.deepseek_web_request',return_value=page):self.weekly.collect(rid,cfg)
        return self.weekly.runs()[0]
    def test_real_job_created_but_not_published(self):
        run=self.collect()
        self.assertEqual(run['status'],'queued')
        job=self.app.store.job(run['job_id'])
        self.assertEqual(job['payload']['kind'],'wiki')
        self.assertEqual(job['payload']['history_snapshot'],[])
        self.assertFalse(any(a['kind']=='wiki' for a in self.app.store.artifacts()))
    def test_failed_draft_can_retry_same_source(self):
        first=self.collect();self.app.store.update_job(first['job_id'],'failed',error='test failure')
        second=self.collect();self.assertEqual(second['status'],'queued')
        self.assertEqual(len(self.app.store.sources()),1)
    def test_pending_draft_not_generated_twice(self):
        first=self.collect();self.app.store.update_job(first['job_id'],'review')
        second=self.collect();self.assertEqual(second['status'],'no_updates')
    def test_failure_not_success(self):
        rid=self.weekly.claim(self.cfg,'fail')
        with patch('weekly.model_key',return_value='x'),patch('weekly.deepseek_web_request',side_effect=ValueError('unavailable')):self.weekly.collect(rid,self.cfg)
        run=self.weekly.runs()[0];self.assertEqual(run['status'],'failed');self.assertTrue(run['warnings'])
        self.assertEqual(self.app.store.sources(),[])
    def test_search_respects_scope(self):
        rid=self.weekly.claim(self.cfg,'search')
        results={'results':[{'url':'https://evil.com/a'},{'url':'https://example.com/news/a'}]}
        cfg={**self.cfg,'query':'Harness'}
        def remote(root,operation,body):
            if operation=='search':return results
            self.assertEqual(body['url'],'https://example.com/news/a')
            return {'title':'Article','content':'这是文章里的原文证据，工具结果需要核验。'*30}
        with patch('weekly.model_key',return_value='x'),patch('weekly.deepseek_web_request',side_effect=remote):self.weekly.collect(rid,cfg)
        self.assertEqual(len(self.app.store.sources()),1)


class WorkflowApiTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request
    def test_retrieval_job_frozen_and_bounded(self):
        s=self.app.store.add_source('Harness','Harness 工具执行需要核验结果。'*900)['source']
        _,result=self.request('/api/retrieve',{'query':'Harness'})
        selected=result['results'][:1]
        status,job=self.request('/api/jobs',{'prompt':'解释 Harness','kind':'chat','retrieval':selected})
        self.assertEqual(status,202)
        self.assertLess(len(job['payload']['source_snapshot'][s['id']]['content']),1300)
    def test_diagram_version_and_restore(self):
        _,page=self.request('/api/wiki',{'page':{'title':'流程','summary':'测试','content':'正文'}})
        status,saved=self.request('/api/diagram',{'id':page['id'],'revision':1,'nodes':['收集','整理','确认']})
        self.assertEqual(status,200);self.assertEqual(saved['revision'],2)
        self.assertEqual(saved['body']['diagram'],['收集','整理','确认'])
        self.assertEqual(self.request('/api/diagram',{'id':page['id'],'revision':1,'nodes':['覆盖']})[0],409)
        self.assertEqual(self.request('/api/diagram',{'id':page['id'],'revision':2,'nodes':['x']*11})[0],400)
        versions=self.app.store.versions(page['id'])
        restored=self.app.store.restore(page['id'],versions[-1]['id'],2)
        self.assertEqual(restored['body']['diagram'],[])
    def test_weekly_config_is_disabled(self):
        _,state=self.request('/api/state');self.assertFalse(state['weekly']['config']['enabled'])
        self.assertEqual(self.request('/api/weekly/run',{'allow_remote':False})[0],400)

class SchedulerTickTests(unittest.TestCase):
    setUp=WeeklyTests.setUp
    tearDown=WeeklyTests.tearDown
    collect=WeeklyTests.collect
    def test_due_tick_claim_once_and_skip_backlog(self):
        self.weekly.manual_only=False  # Scheduler is dormant in the shipped application.
        cfg={**self.cfg,'enabled':True,'allow_remote':True}
        with patch('weekly.model_key',return_value='x'):self.weekly.save(cfg)
        with self.app.store.lock:
            cfg=self.weekly.config();cfg['next_run']='2026-10-02T11:00:00+00:00'
            self.app.store.db.execute('UPDATE reading_subscriptions SET body=? WHERE id=?',(json.dumps(cfg),cfg['id']));self.app.store.db.commit()
        instant=datetime(2026,10,18,10,tzinfo=timezone.utc)
        with patch('weekly.threading.Thread') as thread:
            self.weekly.tick(instant);self.weekly.tick(instant)
            self.assertEqual(thread.call_count,1)
        self.assertEqual(len(self.weekly.runs()),1)
        self.assertEqual(self.weekly.config()['next_run'],'2026-10-23T11:00:00+00:00')
    def test_source_is_complete_context_is_bounded(self):
        run=self.collect(content='完整原文需要保留，给模型选取有界片段。'*600)
        s=self.app.store.sources()[0];job=self.app.store.job(run['job_id'])
        self.assertGreater(len(s['content']),5000)
        self.assertEqual(len(job['payload']['source_snapshot'][s['id']]['content']),5000)
