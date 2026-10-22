"""One public-reading refresh pipeline, triggered manually or by a local schedule."""
import json
import logging
import re
import threading
from datetime import datetime, timezone

import reading_room
from domain import Conflict, now, uid
from weekly import next_time


class ReadingUpdates:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.stop = threading.Event()
        self.thread = None
        with self.store.lock:
            self.store.db.executescript('''
                CREATE TABLE IF NOT EXISTS reading_refresh_config(id INTEGER PRIMARY KEY,body TEXT);
                CREATE TABLE IF NOT EXISTS reading_refresh_runs(id TEXT PRIMARY KEY,slot TEXT UNIQUE,body TEXT);
            ''')
            default = {'enabled': False, 'frequency': 'weekly', 'weekday': 0, 'time': '09:00',
                       'timezone': 'Asia/Shanghai', 'next_run': None, 'revision': 0}
            self.store.db.execute('INSERT OR IGNORE INTO reading_refresh_config VALUES(1,?)',
                                  (json.dumps(default),))
            for row in self.store.db.execute('SELECT id,body FROM reading_refresh_runs').fetchall():
                run = json.loads(row['body'])
                if run['status'] == 'running':
                    run.update(status='interrupted', finished=now(), error='服务已重启，本次更新已中断。')
                    self._write_run(run)
            self.store.db.commit()

    def config(self):
        with self.store.lock:
            return json.loads(self.store.db.execute('SELECT body FROM reading_refresh_config WHERE id=1').fetchone()['body'])

    def state(self):
        with self.store.lock:
            row = self.store.db.execute('SELECT body FROM reading_refresh_runs ORDER BY rowid DESC LIMIT 1').fetchone()
            last = json.loads(row['body']) if row else None
            return {'schedule': self.config(), 'current': last if last and last['status'] == 'running' else None,
                    'last_run': last}

    def save(self, data, instant=None):
        enabled, frequency, weekday, clock = (data.get(k) for k in ('enabled', 'frequency', 'weekday', 'time'))
        if type(enabled) is not bool or frequency not in ('daily', 'weekly'):
            raise ValueError('请选择更新频率和开关状态')
        if type(weekday) is not int or not 0 <= weekday <= 6:
            raise ValueError('请选择有效的星期')
        if not isinstance(clock, str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', clock):
            raise ValueError('请选择有效的更新时间')
        if enabled and self.app.root != self.app.credential_root:
            raise ValueError('请在我的空间设置定时更新')
        with self.store.lock:
            current = self.config()
            if type(data.get('revision')) is not int or data['revision'] != current['revision']:
                raise Conflict('计划已修改，请关闭后重新打开')
            if enabled and not self._sources():
                raise ValueError('请先在来源管理中添加订阅地址')
            config = {**current, 'enabled': enabled, 'frequency': frequency, 'weekday': weekday,
                      'time': clock, 'revision': current['revision'] + 1, 'updated': now()}
            config['next_run'] = next_time(config, instant) if enabled else None
            self._write_config(config)
            self.store.db.commit()
            return config

    def _sources(self):
        return [c for c in self.app.weekly.subscriptions() if c.get('urls')]

    def _write_config(self, config):
        self.store.db.execute('UPDATE reading_refresh_config SET body=? WHERE id=1',
                              (json.dumps(config, ensure_ascii=False),))

    def _write_run(self, run):
        self.store.db.execute('UPDATE reading_refresh_runs SET body=? WHERE id=?',
                              (json.dumps(run, ensure_ascii=False), run['id']))

    def _claim(self, trigger, slot):
        if self.store.db.execute('SELECT 1 FROM reading_refresh_runs WHERE slot=?', (slot,)).fetchone():
            return None
        if self.state()['current']:
            raise Conflict('阅览室正在更新，请等待本次完成')
        run = {'id': uid('reading_update'), 'slot': slot, 'trigger': trigger, 'status': 'running',
               'started': now(), 'finished': None, 'added': 0, 'collected_count': 0,
               'warnings': [], 'read_warnings': [], 'error': ''}
        self.store.db.execute('INSERT INTO reading_refresh_runs VALUES(?,?,?)',
                              (run['id'], slot, json.dumps(run, ensure_ascii=False)))
        return run

    def manual(self, data):
        if data.get('allow_remote') is not True:
            raise ValueError('请授权本次公开来源更新')
        with self.store.lock:
            configs = self._sources()
            if not configs:
                raise ValueError('请先在来源管理中添加订阅地址')
            run = self._claim('manual', uid('manual'))
            self.store.db.commit()
            response = dict(run)
        self._launch(run, configs)
        return response

    def tick(self, instant=None):
        instant = instant or datetime.now(timezone.utc)
        with self.store.lock:
            config = self.config()
            if (not config['enabled'] or self.app.root != self.app.credential_root or not config['next_run']
                    or datetime.fromisoformat(config['next_run']) > instant):
                return None
            try:
                run = self._claim('scheduled', 'scheduled:' + config['next_run'])
            except Conflict:
                return None
            configs = self._sources()
            # Claim and advance together. Missed periods coalesce into one current update.
            config['next_run'] = next_time(config, instant)
            self._write_config(config)
            self.store.db.commit()
        if run:
            self._launch(run, configs)
        return run

    def _launch(self, run, configs):
        try:
            threading.Thread(target=self._execute, args=(run, configs), daemon=True,
                             name='reading-refresh').start()
        except Exception as error:
            run.update(status='failed', error=str(error)[:240], finished=now())
            with self.store.lock:
                self._write_run(run)
                self.store.db.commit()
            raise

    def _execute(self, run, configs):
        locked = False
        try:
            if not configs:
                raise ValueError('没有可更新的来源，请在来源管理中添加订阅地址')
            locked = self.app.news.collect_lock.acquire(blocking=False)
            if not locked:
                raise Conflict('来源正在采集，本次未重复更新')
            collected = set()
            for config in configs:
                try:
                    result = self.app.news.refresh({'id': config['id'], 'allow_remote': True})
                    run['added'] += result['added']
                    collected.update(result.get('collected_ids', []))
                    run['warnings'].extend(result.get('warnings', []))
                except Exception as error:
                    run['warnings'].append({'url': config['title'], 'error': str(error)[:240]})
            run['collected_count'] = len(collected)
            if collected:
                recent = [n for n in self.app.news.items() if n['id'] in collected
                          and not n.get('read_at') and not n.get('content')][:12]
                if recent:
                    try:
                        result = self.app.news.enrich({'ids': [n['id'] for n in recent], 'allow_remote': True})
                        run['read_warnings'] = [r for r in result['results'] if not r['ok']]
                    except Exception as error:
                        run['read_warnings'] = [{'error': str(error)[:240]}]
                seen={warning.get('id') for warning in run['read_warnings']}
                for item in self.app.news.items():
                    if item['id'] in collected and item['id'] not in seen and item.get('read_error') and not item.get('content'):
                        run['read_warnings'].append({'id':item['id'],'ok':False,'status':'summary',
                                                    'error':item['read_error'],'previous_attempt':True})
                run['snapshot'] = reading_room.snapshot(self.store, self.app.news.items())
            run['status'] = ('partial' if run['warnings'] or run['read_warnings'] else 'completed')
            if not collected and run['warnings']:
                run.update(status='failed', error='来源暂未读取成功，保留上次内容。')
        except Exception as error:
            run.update(status='failed', error=str(error)[:240])
        finally:
            if locked:
                self.app.news.collect_lock.release()
            run['finished'] = now()
            with self.store.lock:
                self._write_run(run)
                self.store.db.commit()

    def start(self):
        if self.thread and self.thread.is_alive():
            return

        def loop():
            while not self.stop.wait(15):
                try:
                    self.tick()
                except Exception:
                    logging.exception('Reading schedule check failed')

        self.thread = threading.Thread(target=loop, daemon=True, name='reading-schedule')
        self.thread.start()
