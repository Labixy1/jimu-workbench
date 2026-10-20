"""Bounded local retrieval; only user-selected excerpts reach the model."""
import math
import re
from collections import Counter


def terms(text):
    words = re.findall(r'[a-z0-9_-]{2,}|[\u4e00-\u9fff]+', text.lower())
    return [token for word in words for token in
            ([word] if not re.search(r'[\u4e00-\u9fff]', word) else
             [word[i:i+2] for i in range(len(word)-1)] + ([word] if len(word) <= 6 else []))]


def chunks(text):
    return [text[i:i+1200] for i in range(0, len(text), 1000)]


def retrieve(store, query):
    query = str(query).strip()
    if not 1 <= len(query) <= 200:
        raise ValueError('检索词需为1至200字')
    tokens = set(terms(query))
    records = []
    for s in store.sources():
        if not s['archived']:
            records.append(('source', s['id'], s['title'], s['content'], s['hash']))
    for a in store.artifacts():
        if a['kind'] == 'wiki' and not a['archived']:
            records.append(('wiki', a['id'], a['title'], a['body']['content'], a['revision']))
    documents = []
    for kind, item_id, title, text, revision in records:
        for index, excerpt in enumerate(chunks(text)):
            documents.append({'kind': kind, 'id': item_id, 'title': title,
                              'chunk_index': index, 'revision': revision, 'excerpt': excerpt})
    frequency = Counter(t for d in documents for t in set(terms(d['excerpt'])))
    ranked = []
    for d in documents:
        counts = Counter(terms(d['excerpt']))
        score = sum((1 + math.log(1 + counts[t])) * math.log(2 + len(documents)/(1+frequency[t]))
                    for t in tokens if counts[t])
        score += 5 * len(tokens & set(terms(d['title'])))
        if score:
            ranked.append({**d, 'score': round(score, 2)})
    ranked.sort(key=lambda d: -d['score'])
    # Spread the limited context across pages, not six hits from one long file.
    counts = Counter()
    result = []
    for d in ranked:
        key = (d['kind'], d['id'])
        if counts[key] < 2:
            result.append(d); counts[key] += 1
        if len(result) == 6:
            break
    return result


def selected_context(store, items):
    if not isinstance(items, list) or len(items) > 6:
        raise ValueError('最多选择6段检索内容')
    sources, pages = {}, {}
    for item in items:
        if not isinstance(item, dict): raise ValueError('无效检索内容')
        kind, item_id = item.get('kind'), item.get('id')
        if kind == 'source':
            record = store.source(item_id); text = record['content']; revision = record['hash']
        elif kind == 'wiki':
            record = store.artifact(item_id)
            if record['kind'] != 'wiki': raise ValueError('不是知识页')
            text = record['body']['content']; revision = record['revision']
        else: raise ValueError('无效检索内容类型')
        if record['archived'] or item.get('revision') != revision:
            raise ValueError('检索内容已变更或归档，请重新检索')
        index = item.get('chunk_index')
        excerpts = chunks(text)
        if type(index) is not int or not 0 <= index < len(excerpts):
            raise ValueError('无效片段位置')
        target = sources if kind == 'source' else pages
        if item_id not in target:
            target[item_id] = {**record, 'content': ''} if kind == 'source' else {**record, 'body': {**record['body'], 'content': ''}}
        if kind == 'source': target[item_id]['content'] += excerpts[index] + '\n\n'
        else: target[item_id]['body']['content'] += excerpts[index] + '\n\n'
    return sources, pages
