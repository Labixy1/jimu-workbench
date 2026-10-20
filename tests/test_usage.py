import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from models import deepseek_balance, deepseek_request
from usage import TrackedResponse, UsageLedger
import test_api


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = UsageLedger(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_unknown_usage_is_not_zero(self):
        rid=self.ledger.begin('chat','test-model');self.ledger.finish(rid,'ok',1)
        s=self.ledger.summary()
        self.assertIsNone(s['input_tokens']);self.assertEqual(s['missing_usage_calls'],1)

    def test_split_stream_usage_forwarded_without_mutation(self):
        rid=self.ledger.begin('chat','test-model')
        raw=b'data: {"choices":[{"delta":{"content":"private output"}}]}\n\ndata: {"usage":{"prompt_tokens":12,"completion_tokens":4}}\n\ndata: [DONE]\n\n'
        tracked=TrackedResponse(io.BytesIO(raw),self.ledger,rid,time.monotonic(),True)
        with tracked:
            chunks=[]
            while True:
                chunk=tracked.read(7)
                if not chunk:break
                chunks.append(chunk)
        self.assertEqual(b''.join(chunks),raw)
        s=self.ledger.summary();self.assertEqual(s['input_tokens'],12);self.assertEqual(s['output_tokens'],4)
        self.assertNotIn('private output',json.dumps(s))

    def test_nonstream_and_incomplete_stream(self):
        rid=self.ledger.begin('chat');raw=b'{"choices":[{}],"usage":{"prompt_tokens":3,"completion_tokens":2}}'
        with TrackedResponse(io.BytesIO(raw),self.ledger,rid,time.monotonic(),False) as r:json.load(r)
        rid=self.ledger.begin('chat')
        with TrackedResponse(io.BytesIO(b'data: {"choices":[]}\n'),self.ledger,rid,time.monotonic(),True) as r:r.read()
        self.assertEqual(self.ledger.summary()['recent'][0]['status'],'incomplete')
        self.assertEqual(self.ledger.summary()['token_calls'],1)

    def test_fixed_balance_endpoint_and_whitelist(self):
        response={'is_available':True,'secret':'never return','balance_infos':[{'currency':'CNY','total_balance':'1.20','granted_balance':'0','topped_up_balance':'1.20','key':'never return'}]}
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-test-only'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result=deepseek_balance(self.root)
        self.assertEqual(call.call_args[0][0].full_url,'https://api.deepseek.com/user/balance')
        self.assertNotIn('never return',json.dumps(result));self.assertEqual(result['balance_infos'][0]['total_balance'],'1.20')

    def test_nan_balance_rejected(self):
        response={'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'NaN','granted_balance':'0','topped_up_balance':'0'}]}
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-test-only'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(RuntimeError):deepseek_balance(self.root)

    def test_stream_requests_include_actual_usage(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-test-only'}),patch('urllib.request.urlopen',return_value=io.BytesIO(b'data: [DONE]\n')) as call:
            with deepseek_request(self.root,{'model':'deepseek-flash','messages':[],'stream':True}) as response:response.read()
        self.assertTrue(json.loads(call.call_args[0][0].data)['stream_options']['include_usage'])


class UsageApiTests(unittest.TestCase):
    setUp=test_api.ApiTests.setUp
    tearDown=test_api.ApiTests.tearDown
    request=test_api.ApiTests.request

    def test_balance_requires_consent_and_usage_is_local(self):
        with patch('server.deepseek_balance') as remote:
            self.assertEqual(self.request('/api/model/balance',{})[0],400)
            remote.assert_not_called()
        self.assertEqual(self.request('/api/usage')[1]['calls'],0)

    def test_balance_returns_only_sanitized_transport(self):
        value={'is_available':True,'balance_infos':[]}
        with patch('server.deepseek_balance',return_value=value):
            self.assertEqual(self.request('/api/model/balance',{'allow_remote':True})[1],value)
