"""Server-only DeepSeek credentials and fixed official API transport."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from usage import UsageLedger, TrackedResponse

DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
DEEPSEEK_MODELS = ('deepseek-flash', 'deepseek-v4-pro')


def deepseek_web_request(root, operation, body):
    if operation not in ('search', 'fetch'):
        raise ValueError('无效联网操作')
    key = model_key(root)
    if not key:
        raise ValueError('请先配置 DeepSeek API Key')
    request = urllib.request.Request(
        'https://api.deepseek.com/v1/tools/' + operation,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    ledger = UsageLedger(root); rid = ledger.begin(operation); started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(2000001)
            if len(raw) > 2000000:
                raise ValueError('联网返回内容过大，请缩小范围')
            result = json.loads(raw)
            ledger.finish(rid, 'ok', time.monotonic()-started)
            return result
    except urllib.error.HTTPError as error:
        ledger.finish(rid, 'failed', time.monotonic()-started, error='HTTP '+str(error.code))
        messages = {401: '密钥无效', 402: '账户余额不足', 403: '目标被安全策略拒绝',
                    404: '未能获取可用正文', 429: '请求限流', 504: '目标网页超时'}
        raise RuntimeError('DeepSeek 联网 HTTP ' + str(error.code) + '：' +
                           messages.get(error.code, '调用失败')) from None
    except urllib.error.URLError:
        ledger.finish(rid, 'failed', time.monotonic()-started, error='network unavailable')
        raise RuntimeError('无法连接 DeepSeek 联网服务') from None
    except Exception:
        ledger.finish(rid, 'failed', time.monotonic()-started, error='invalid response')
        raise RuntimeError('DeepSeek 联网返回格式异常') from None


def model_key(root):
    if os.environ.get('DEEPSEEK_API_KEY'):
        return os.environ['DEEPSEEK_API_KEY']
    path = Path(root) / '.runtime/secrets/deepseek-key'
    return path.read_text().strip() if path.exists() else ''


def save_key(root, key):
    if not isinstance(key, str) or not 10 <= len(key.strip()) <= 300 or any(c.isspace() for c in key.strip()):
        raise ValueError('请输入有效的 DeepSeek API Key')
    path = Path(root) / '.runtime/secrets/deepseek-key'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(key.strip())
    path.chmod(0o600)


def deepseek_request(root, body):
    key = model_key(root)
    if not key:
        raise ValueError('尚未配置 DeepSeek API Key，请在模型设置中填写')
    if body.get('model') not in DEEPSEEK_MODELS:
        raise ValueError('不支持的 DeepSeek 模型')
    # Non-thinking tool mode avoids losing reasoning_content in the pinned
    # OpenAI-compatible adapter. Do not silently claim deep reasoning support.
    body = {k:v for k,v in body.items() if k in ('model','messages','tools','tool_choice','stream','stream_options','max_tokens','temperature','top_p','response_format','stop','parallel_tool_calls')}
    body = {**body, 'thinking': {'type': 'disabled'}, 'max_tokens': min(int(body.get('max_tokens', 6000)), 6000)}
    body.pop('reasoning_effort', None)
    if body.get('stream'): body['stream_options'] = {**(body.get('stream_options') or {}), 'include_usage': True}
    request = urllib.request.Request(DEEPSEEK_URL, data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    ledger = UsageLedger(root); rid = ledger.begin('chat', body['model']); started = time.monotonic()
    try:
        return TrackedResponse(urllib.request.urlopen(request, timeout=100), ledger, rid, started, bool(body.get('stream')))
    except urllib.error.HTTPError as error:
        ledger.finish(rid, 'failed', time.monotonic()-started, error='HTTP '+str(error.code))
        messages = {401: '密钥无效', 402: '账户余额不足', 429: '请求限流', 400: '请求参数不兼容', 503: '服务暂不可用'}
        raise RuntimeError('DeepSeek HTTP ' + str(error.code) + '：' + messages.get(error.code, '调用失败')) from None
    except urllib.error.URLError:
        ledger.finish(rid, 'failed', time.monotonic()-started, error='network unavailable')
        raise RuntimeError('无法连接 DeepSeek，请检查网络') from None


def deepseek_balance(root):
    key = model_key(root)
    if not key: raise ValueError('请先配置 DeepSeek API Key')
    request = urllib.request.Request('https://api.deepseek.com/user/balance',
                                     headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read(100000))
        from decimal import Decimal, InvalidOperation
        balances = []
        if type(result.get('is_available')) is not bool or not isinstance(result.get('balance_infos'), list):
            raise ValueError('invalid balance response')
        for item in result['balance_infos']:
            if item.get('currency') not in ('CNY', 'USD'): continue
            clean = {'currency': item['currency']}
            for name in ('total_balance', 'granted_balance', 'topped_up_balance'):
                number = Decimal(str(item.get(name)))
                if not number.is_finite(): raise InvalidOperation()
                clean[name] = str(number)
            balances.append(clean)
        if not balances: raise ValueError('empty balance response')
        from domain import now
        return {'is_available': result['is_available'], 'balance_infos': balances, 'checked_at': now()}
    except urllib.error.HTTPError as error:
        raise RuntimeError('DeepSeek 余额查询 HTTP '+str(error.code)+'，请检查密钥或稍后再试') from None
    except urllib.error.URLError:
        raise RuntimeError('无法连接 DeepSeek 余额接口') from None
    except Exception:
        raise RuntimeError('DeepSeek 余额返回格式异常') from None
