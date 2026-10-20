"""Local request metadata only; never persist prompts, output or credentials."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')


class UsageLedger:
    def __init__(self, root):
        self.path = Path(root) / 'data/usage.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS requests(
                id TEXT PRIMARY KEY, created TEXT, operation TEXT, model TEXT,
                status TEXT, input_tokens INTEGER, output_tokens INTEGER,
                elapsed_ms INTEGER, error TEXT)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def begin(self, operation, model=''):
        rid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO requests(id,created,operation,model,status) VALUES(?,?,?,?,?)',
                       (rid, datetime.now(timezone.utc).isoformat(), operation, model, 'running'))
        return rid

    def finish(self, rid, status, elapsed, usage=None, error=''):
        usage = usage if isinstance(usage, dict) else {}
        def number(key):
            value = usage.get(key)
            return value if type(value) is int and value >= 0 else None
        with self.connect() as db:
            db.execute('UPDATE requests SET status=?,input_tokens=?,output_tokens=?,elapsed_ms=?,error=? WHERE id=?',
                       (status, number('prompt_tokens'), number('completion_tokens'),
                        round(elapsed * 1000), error[:160], rid))

    def summary(self):
        start = (datetime.now(TZ).date() - timedelta(days=6)).isoformat()
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM requests ORDER BY created DESC')]
        dated = [(r, datetime.fromisoformat(r['created']).astimezone(TZ).date().isoformat()) for r in rows]
        recent = [r for r, day in dated if day >= start]
        known = [r for r in recent if r['input_tokens'] is not None and r['output_tokens'] is not None]
        days = []
        for offset in range(7):
            day = (datetime.now(TZ).date() - timedelta(days=6-offset)).isoformat()
            items = [r for r, d in dated if d == day]
            tokens = [r for r in items if r['input_tokens'] is not None and r['output_tokens'] is not None]
            days.append({'date': day, 'calls': len(items), 'tokens':
                         sum(r['input_tokens'] + r['output_tokens'] for r in tokens) if tokens else None})
        return {'since': min((r['created'] for r in rows), default=None),
                'calls': len(recent), 'failed': sum(r['status'] == 'failed' for r in recent),
                'token_calls': len(known), 'missing_usage_calls': sum(r['operation'] == 'chat' and r not in known for r in recent),
                'input_tokens': sum(r['input_tokens'] for r in known) if known else None,
                'output_tokens': sum(r['output_tokens'] for r in known) if known else None,
                'days': days, 'recent': recent[:8], 'scope': 'local_since_enabled'}


class TrackedResponse:
    """Observe the final usage record while forwarding streaming bytes unchanged."""
    def __init__(self, response, ledger, rid, started, streaming):
        self.response, self.ledger, self.rid = response, ledger, rid
        self.started, self.streaming = started, streaming
        self.pending = b''
        self.usage = None
        self.complete = False

    def __getattr__(self, name):
        return getattr(self.response, name)

    def observe(self, chunk):
        self.pending += chunk
        if self.streaming:
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                if line.startswith(b'data:'):
                    payload = line[5:].strip()
                    if payload == b'[DONE]':
                        self.complete = True
                    else:
                        try:
                            value = json.loads(payload)
                            if isinstance(value.get('usage'), dict): self.usage = value['usage']
                        except (ValueError, AttributeError): pass
            # An unexpectedly huge line must not retain an unbounded model output.
            if len(self.pending) > 2000000: self.pending = b''
        elif len(self.pending) > 2000000:
            self.pending = b''
        return chunk

    def read(self, *args):
        return self.observe(self.response.read(*args))

    def read1(self, *args):
        return self.observe(self.response.read1(*args))

    def __enter__(self):
        self.response.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        if not self.streaming:
            try:
                result = json.loads(self.pending)
                self.usage = result.get('usage')
                self.complete = bool(result.get('choices'))
            except (ValueError, AttributeError): pass
        status = 'failed' if kind else 'ok' if self.complete else 'incomplete'
        self.ledger.finish(self.rid, status, time.monotonic()-self.started, self.usage,
                           'response interrupted' if kind else '')
        return self.response.__exit__(kind, value, traceback)
