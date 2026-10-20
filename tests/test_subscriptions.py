import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

from domain import Conflict
from weekly import Weekly
import test_workflow
import test_api


class SubscriptionTests(unittest.TestCase):
    setUp = test_workflow.WeeklyTests.setUp
    tearDown = test_workflow.WeeklyTests.tearDown

    def create(self, title='订阅测试', **extra):
        return self.weekly.save({**self.cfg, 'title': title, 'new': True, **extra})

    def test_three_limit_update_and_stale_guard(self):
        items = [self.create(str(i)) for i in range(3)]
        self.assertEqual(len(self.weekly.subscriptions()), 3)
        with self.assertRaises(ValueError): self.create('第四个')
        saved = self.weekly.save({**items[1], 'title':'改名'})
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(self.weekly.config(items[0]['id'])['title'], '0')
        self.assertEqual(self.weekly.config()['id'],items[0]['id'])
        with self.assertRaises(Conflict): self.weekly.save(items[1])
        with self.assertRaises(Conflict): self.weekly.toggle(items[0]['id'],True,False)
        with self.assertRaises(Conflict): self.weekly.remove(items[0]['id'],True)

    def test_atomic_limit_with_concurrent_create(self):
        barrier = threading.Barrier(5)
        def save(i):
            barrier.wait()
            try: return self.create(str(i))
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=5) as pool: results = list(pool.map(save, range(5)))
        self.assertEqual(sum(r is not None for r in results), 3)

    def test_legacy_migrates_once_and_preserves_schedule(self):
        db = self.app.store.db
        db.execute('DROP TABLE reading_subscriptions')
        old = {**self.cfg, 'enabled':True, 'allow_remote':True, 'next_run':'2026-10-22T02:00:00+00:00'}
        db.execute('INSERT INTO weekly_config VALUES(1,?)', (json.dumps(old),)); db.commit()
        migrated = Weekly(self.app, lambda url:url)
        self.assertIsNone(migrated.config()['next_run'])
        self.assertFalse(migrated.config()['enabled'])
        self.assertEqual(migrated.config()['urls'], old['urls'])
        sid = migrated.config()['id']; migrated.remove(sid, migrated.config()['revision'])
        self.assertEqual(Weekly(self.app, lambda url:url).subscriptions(), [])

    def test_legacy_slot_claim_is_not_replayed_after_migration(self):
        self.app.store.db.execute('INSERT INTO weekly_runs(id,slot,status,body,created,subscription_id) VALUES(?,?,?,?,?,?)',
            ('issue_old','scheduled:old','no_updates',json.dumps({'config':self.cfg,'warnings':[]}), '2026-10-19', 'sub_legacy'))
        self.app.store.db.commit()
        restarted=Weekly(self.app,lambda url:url)
        self.assertIsNone(restarted.claim(self.cfg,'scheduled:old'))

    def test_pause_one_remove_retains_history_and_reuses_capacity(self):
        self.weekly.manual_only=False  # Exercise retained scheduler internals, not the MVP API.
        one, two = self.create('一'), self.create('二')
        with patch('weekly.model_key', return_value='test-key'):
            one = self.weekly.toggle(one['id'],1,True,True)
            two = self.weekly.toggle(two['id'],1,True,True)
        self.weekly.toggle(one['id'],one['revision'],False)
        self.assertTrue(self.weekly.config(two['id'])['enabled'])
        rid = self.weekly.claim(one, 'test'); self.weekly.update(rid,'no_updates')
        current=self.weekly.config(one['id']); self.weekly.remove(one['id'],current['revision'])
        self.assertEqual(self.weekly.runs()[0]['subscription_id'],one['id'])
        with self.assertRaises(ValueError): self.weekly.claim(current, 'removed')
        self.create('三'); self.create('四'); self.assertEqual(len(self.weekly.subscriptions()),3)

    def test_simultaneous_schedule_waits_without_losing_second(self):
        self.weekly.manual_only=False
        with patch('weekly.model_key', return_value='test-key'):
            one, two = self.create('一',enabled=True,allow_remote=True), self.create('二',enabled=True,allow_remote=True)
        for c in (one,two):
            c['next_run']='2026-10-02T11:00:00+00:00'
            self.app.store.db.execute('UPDATE reading_subscriptions SET body=? WHERE id=?',(json.dumps(c),c['id']))
        self.app.store.db.commit(); instant=datetime(2026,10,18,10,tzinfo=timezone.utc)
        with patch('weekly.threading.Thread'):
            self.weekly.tick(instant); self.weekly.tick(instant)
            self.assertEqual(len(self.weekly.runs()),1)
            self.assertEqual(self.weekly.config(two['id'])['next_run'],two['next_run'])
            self.weekly.update(self.weekly.runs()[0]['id'],'no_updates')
            self.weekly.tick(instant)
            self.assertEqual(len(self.weekly.runs()),2)
            self.assertEqual({r['subscription_id'] for r in self.weekly.runs()},{one['id'],two['id']})

    def test_dedup_is_scoped_to_subscription_and_remove_busy_rejected(self):
        one, two = self.create('一'), self.create('二')
        page={'title':'公共测试','content':'公开正文应有来源与引用，测试不代表真实推理。'*30}
        with patch('weekly.model_key',return_value='test-key'),patch('weekly.deepseek_web_request',return_value=page):
            rid=self.weekly.claim(one,'first'); self.weekly.collect(rid,one)
            with self.assertRaises(Conflict):self.weekly.remove(one['id'],1)
            job=self.weekly.runs()[0]['job_id']; self.app.store.update_job(job,'review')
            rid2=self.weekly.claim(two,'second');self.weekly.collect(rid2,two)
        self.assertEqual(self.weekly.runs()[0]['status'],'queued')
        self.assertEqual(self.app.store.job(self.weekly.runs()[0]['job_id'])['payload']['subscription_id'],two['id'])
        self.assertEqual(len(self.app.store.sources()),1)

    def test_page_association_survives_rename_and_remove(self):
        sub=self.create('原名称')
        source=self.app.store.add_source('公共测试','这是一段明确标注的测试原文，用于检查引用与审批。')['source']
        cid=self.app.store.conversation()
        job=self.app.store.create_job(cid,'map-agent',{'kind':'wiki','source_ids':[source['id']],
            'weekly_run_id':'issue_test','subscription_id':sub['id'],'prompt':'测试审批'})
        self.app.store.update_job(job['id'],'review',proposal={'page':{'title':'一期测试','summary':'测试',
            'content':'已核验测试原文。','tags':['周刊','原名称'],'citations':[{'source_id':source['id'],'quote':source['content']}]}})
        page=self.app.store.approve(job['id'])
        sub=self.weekly.save({**sub,'title':'新名称'})
        self.assertEqual(self.weekly.page_subscriptions()[page['id']],sub['id'])
        self.weekly.remove(sub['id'],sub['revision'])
        self.assertEqual(self.weekly.page_subscriptions()[page['id']],sub['id'])
        self.assertEqual(self.app.store.artifact(page['id'])['kind'],'wiki')


class SubscriptionApiTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def test_create_three_state_and_remove(self):
        cfg={'title':'测试','urls':[],'query':'','weekday':4,'time':'19:00','enabled':False,'new':True}
        items=[self.request('/api/weekly/config',{**cfg,'title':str(i)})[1] for i in range(3)]
        self.assertEqual(self.request('/api/weekly/config',cfg)[0],400)
        self.assertEqual(len(self.request('/api/state')[1]['weekly']['subscriptions']),3)
        self.assertEqual(self.request('/api/weekly/toggle',{'id':items[0]['id'],'revision':1,'enabled':False})[0],200)
        self.assertEqual(self.request('/api/weekly/remove',{'id':items[0]['id'],'revision':1})[0],409)
        self.assertEqual(self.request('/api/weekly/remove',{'id':items[0]['id'],'revision':2})[0],200)
        self.assertEqual(self.request('/api/weekly/config',cfg)[0],200)
