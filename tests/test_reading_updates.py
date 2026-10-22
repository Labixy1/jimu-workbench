import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import reading_room
import test_api
from domain import Conflict
from reading_updates import ReadingUpdates
from server import App
from weekly import next_time


class ReadingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.tmp.name), None)
        self.app.weekly.validator = lambda url: url
        self.app.news.validator = lambda url: url
        self.updates = self.app.reading_updates
        self.sub = self.app.weekly.save({'title': 'Explicit fixture feed', 'urls': ['https://example.com/rss']})
        self.instant = datetime(2026, 10, 21, 2, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.updates.stop.set()
        if self.updates.thread:
            self.updates.thread.join(timeout=1)
        self.app.store.db.close()
        self.tmp.cleanup()

    def save(self, **fields):
        return self.updates.save({**self.updates.config(), **fields}, self.instant)

    def fixture(self, index=0):
        return {'title': 'Explicit fixture article ' + str(index),
                'url': 'https://example.com/article/' + str(index),
                'feed_url': 'https://example.com/rss',
                'published_at': datetime.now(timezone.utc).isoformat(),
                'excerpt': 'Explicit fixture RSS summary, not a real public update.'}

    def execute(self):
        with patch.object(self.updates, '_launch') as launch:
            self.updates.manual({'allow_remote': True})
        self.updates._execute(*launch.call_args.args)
        return self.updates.state()['last_run']

    def test_disabled_default_and_no_paid_model_requirement(self):
        self.assertFalse(self.updates.config()['enabled'])
        self.assertIsNone(self.updates.tick(self.instant))
        with patch('weekly.model_key', side_effect=AssertionError('No model key lookup')):
            config = self.save(enabled=True, frequency='daily', time='09:30')
        self.assertEqual(config['next_run'], '2026-10-22T01:30:00+00:00')
        self.assertFalse(self.app.weekly.config()['enabled'], 'The legacy model workflow remains off')
        self.assertEqual(self.app.store.jobs(), [])

    def test_schedule_validation_and_revision_guard(self):
        for fields in ({'enabled': 1}, {'frequency': 'hourly'}, {'time': '25:00'}, {'time': None},
                       {'time': '9:30'}, {'weekday': 7}, {'weekday': True}, {'revision': True}):
            with self.subTest(fields=fields), self.assertRaises((ValueError, Conflict)):
                self.save(**fields)
        original = self.updates.config()
        self.save(time='11:00')
        with self.assertRaises(Conflict):
            self.updates.save(original)

    def test_next_daily_weekly_and_exact_due_time_in_shanghai(self):
        daily = {'frequency': 'daily', 'weekday': 0, 'time': '09:00'}
        weekly = {**daily, 'frequency': 'weekly', 'weekday': 4}
        self.assertEqual(next_time(daily, self.instant), '2026-10-22T01:00:00+00:00')
        self.assertEqual(next_time(weekly, self.instant), '2026-10-23T01:00:00+00:00')
        self.assertEqual(next_time(weekly, datetime(2026, 10, 23, 1, tzinfo=timezone.utc)),
                         '2026-10-30T01:00:00+00:00')

    def test_configuration_survives_restart_and_pause_clears_next_run(self):
        config = self.save(enabled=True)
        restarted = ReadingUpdates(self.app)
        self.assertEqual(restarted.config(), config)
        self.assertFalse(self.save(enabled=False)['enabled'])
        self.assertIsNone(self.updates.config()['next_run'])

    def test_missing_sources_and_demo_cannot_enable_schedule(self):
        self.app.weekly.remove(self.sub['id'], self.sub['revision'])
        with self.assertRaisesRegex(ValueError, '来源管理'):
            self.save(enabled=True)
        self.app.credential_root = self.app.root / 'other'
        with self.assertRaisesRegex(ValueError, '我的空间'):
            self.save(enabled=True)
        self.assertFalse(self.save(enabled=False)['enabled'])

    def test_due_claim_is_durable_and_missed_periods_coalesce(self):
        config = self.save(enabled=True, frequency='daily')
        due = datetime.fromisoformat(config['next_run'])
        with patch.object(self.updates, '_launch') as launch:
            self.assertIsNone(self.updates.tick(self.instant))
            first = self.updates.tick(due)
            self.assertEqual(first['trigger'], 'scheduled')
            self.assertIsNone(self.updates.tick(due))
            launch.assert_called_once()
        self.assertNotEqual(self.updates.config()['next_run'], config['next_run'])
        restarted = ReadingUpdates(self.app)
        self.assertEqual(restarted.state()['last_run']['status'], 'interrupted')
        with patch.object(restarted, '_launch') as launch:
            self.assertIsNone(restarted.tick(due))
            later = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
            restarted.tick(later)
            restarted.tick(later)
            launch.assert_called_once()
        self.assertGreater(datetime.fromisoformat(restarted.config()['next_run']), later)

    def test_manual_overlap_keeps_due_schedule_pending(self):
        config = self.save(enabled=True)
        due = datetime.fromisoformat(config['next_run'])
        with patch.object(self.updates, '_launch') as launch:
            self.updates.manual({'allow_remote': True})
            with self.assertRaises(Conflict):
                self.updates.manual({'allow_remote': True})
            self.assertIsNone(self.updates.tick(due))
            launch.assert_called_once()
        self.assertEqual(self.updates.config()['next_run'], config['next_run'])

    def test_manual_permission_and_repeated_clicks(self):
        for body in ({}, {'allow_remote': False}):
            with self.assertRaises(ValueError):
                self.updates.manual(body)
        self.assertIsNone(self.updates.state()['last_run'])

    def test_cached_failed_body_is_still_reported_without_silent_retry(self):
        with patch('news.fetch_feed',return_value=[self.fixture()]), \
                patch('news.fetch_article',side_effect=ValueError('Explicit fixture body restriction')) as fetch:
            first=self.execute()
            second=self.execute()
        self.assertEqual(first['status'],'partial')
        self.assertEqual(second['status'],'partial')
        self.assertTrue(second['read_warnings'][0]['previous_attempt'])
        self.assertEqual(fetch.call_count,1)

    def test_manual_runs_feed_body_snapshot_without_model(self):
        with patch('news.fetch_feed', return_value=[self.fixture()]), \
                patch('news.fetch_article', return_value={'content': 'Explicit full article fixture. ' * 10,
                                                         'content_status': 'article'}) as fetch, \
                patch('weekly.deepseek_web_request', side_effect=AssertionError('No paid requests')), \
                patch.object(self.app.runner, 'submit', side_effect=AssertionError('No AI jobs')):
            run = self.execute()
            second = self.execute()
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['added'], 1)
        self.assertEqual(second['added'], 0)
        self.assertEqual(fetch.call_count, 1)
        issue = reading_room.state(self.app.store)['issues'][0]
        self.assertEqual(issue['body']['news'][0]['content_status'], 'article')
        self.assertEqual(self.app.store.jobs(), [])

    def test_feed_partial_failure_and_body_failure_still_snapshot(self):
        self.app.weekly.save({'new': True, 'title': 'Explicit broken fixture', 'urls': ['https://example.org/rss']})
        with patch('news.fetch_feed', side_effect=[[self.fixture()], ValueError('Fixture feed failure')]), \
                patch('news.fetch_article', side_effect=ValueError('Fixture body failure')):
            run = self.execute()
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(len(run['warnings']), 1)
        self.assertEqual(len(run['read_warnings']), 1)
        self.assertEqual(len(reading_room.state(self.app.store)['issues']), 1)
        self.assertFalse(self.app.news.items()[0].get('content'))

    def test_scheduled_tick_uses_same_pipeline_with_current_sources(self):
        config = self.save(enabled=True, frequency='daily')
        due = datetime.fromisoformat(config['next_run'])
        with patch.object(self.updates, '_launch') as launch:
            self.updates.tick(due)
        with patch('news.fetch_feed', return_value=[self.fixture()]), \
                patch('news.fetch_article', return_value={'content': 'Explicit scheduled fixture body. ' * 10,
                                                         'content_status': 'article'}), \
                patch.object(self.app.runner, 'submit', side_effect=AssertionError('No AI jobs')):
            self.updates._execute(*launch.call_args.args)
        run = self.updates.state()['last_run']
        self.assertEqual(run['trigger'], 'scheduled')
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['added'], 1)
        self.assertEqual(len(reading_room.state(self.app.store)['issues']), 1)

    def test_all_sources_failed_preserves_previous_issue(self):
        self.app.news.store_item(self.fixture())
        reading_room.snapshot(self.app.store, self.app.news.items())
        before = reading_room.state(self.app.store)['issues']
        with patch('news.fetch_feed', side_effect=ValueError('Explicit fixture failure')):
            run = self.execute()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(reading_room.state(self.app.store)['issues'], before)
        self.assertIsNone(self.updates.state()['current'])

    def test_body_collection_is_bounded_and_old_failures_not_retried(self):
        failed, _ = self.app.news.store_item(self.fixture(0))
        self.app.news.update_item(failed['id'], {'read_at': '2026-10-20', 'read_error': 'Previous fixture failure'})
        with patch('news.fetch_feed', return_value=[self.fixture(i) for i in range(20)]), \
                patch('news.fetch_article', side_effect=ValueError('Explicit fixture failure')) as fetch:
            self.execute()
        self.assertEqual(fetch.call_count, 12)
        self.assertNotIn(failed['url'], [c.args[0] for c in fetch.call_args_list])

    def test_feed_lock_prevents_other_refresh_during_pipeline(self):
        locked, release = threading.Event(), threading.Event()
        def hold():
            with self.app.news.collect_lock:
                locked.set()
                release.wait(3)
        worker = threading.Thread(target=hold)
        worker.start()
        try:
            self.assertTrue(locked.wait(1))
            with patch('news.fetch_feed') as fetch:
                run = self.execute()
            self.assertEqual(run['status'], 'failed')
            fetch.assert_not_called()
        finally:
            release.set()
            worker.join()

    def test_scheduler_start_is_idempotent_and_disabled_does_no_work(self):
        with patch.object(self.updates, '_launch') as launch:
            self.updates.start()
            thread = self.updates.thread
            self.updates.start()
            self.assertIs(self.updates.thread, thread)
            self.assertIsNone(self.updates.tick(self.instant))
            launch.assert_not_called()


class ReadingUpdateEndpointTests(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    request = test_api.ApiTests.request

    def test_update_endpoints_validate_and_expose_pending_job(self):
        self.app.weekly.validator = lambda url: url
        self.app.weekly.save({'title': 'Explicit API fixture', 'urls': ['https://example.com/rss']})
        updates = self.request('/api/reading/updates')[1]
        self.assertFalse(updates['schedule']['enabled'])
        self.assertEqual(self.request('/api/reading/update', {})[0], 400)
        with patch.object(self.app.reading_updates, '_launch'):
            status, run = self.request('/api/reading/update', {'allow_remote': True})
            self.assertEqual(status, 202)
            self.assertEqual(self.request('/api/reading/update', {'allow_remote': True})[0], 409)
        self.assertEqual(self.request('/api/reading/updates')[1]['current']['id'], run['id'])
        self.assertEqual(self.request('/api/state')[1]['reading']['updates']['current']['id'], run['id'])

    def test_schedule_save_revision_origin_guard_and_no_remote_call(self):
        data = self.request('/api/reading/updates')[1]['schedule']
        with patch('news.fetch_feed') as fetch:
            self.assertEqual(self.request('/api/reading/schedule', {**data, 'time': '18:00'})[0], 200)
            self.assertEqual(self.request('/api/reading/schedule', data)[0], 409)
            self.assertEqual(self.request('/api/reading/schedule', data, {'Origin': 'https://example.org'})[0], 403)
            fetch.assert_not_called()
