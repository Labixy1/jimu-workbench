"""Explicit, bounded task context; this is selection, not semantic memory."""
import json

MAX_CONTEXT_CHARS = 36000
HISTORY_MESSAGES = 8
HISTORY_MESSAGE_CHARS = 1200


def recent_history(messages):
    selected = messages[-HISTORY_MESSAGES:]
    history = [{'role': m['role'], 'text': m['text'][:HISTORY_MESSAGE_CHARS]}
               for m in selected]
    return history, {'messages_included': len(selected),
                     'messages_omitted': max(0, len(messages) - len(selected)),
                     'messages_shortened': sum(len(m['text']) > HISTORY_MESSAGE_CHARS for m in selected),
                     'policy': 'recent_8_messages_1200_chars_each'}


def check_context(prompt, sources, pages, preferences, history, target=None, career=None, boards=None, method=None, skills=None, documents=None):
    body = {'prompt': prompt, 'sources': sources, 'wiki_pages': pages,
            'preferences': preferences, 'recent_history': history,
            'wiki_target': target, 'career_snapshot': career, 'boards': boards or [], 'task_method': method, 'skills': skills or [], 'documents': documents or []}
    size = len(json.dumps(body, ensure_ascii=False))
    if size > MAX_CONTEXT_CHARS:
        raise ValueError('本次上下文超过36000字符，请减少整份材料，或自行选取相关片段；不会静默截断所选材料')
    return {'characters': size, 'limit_characters': MAX_CONTEXT_CHARS,
            'source_count': len(sources), 'knowledge_count': len(pages), 'board_count': len(boards or []),
            'policy': 'selected_materials_and_bounded_history'}


def stage_context(packet, stage):
    base = {k: packet[k] for k in ('prompt', 'kind', 'sources', 'task_method', 'skills', 'source_quote_anchors', 'validation_note') if k in packet}
    base['stage'] = stage
    # Children do not inherit the whole conversation or the writer's preferences.
    keys = {
        'chat': ('preferences', 'recent_history', 'wiki_pages', 'boards', 'documents'),
        'research': ('jd_source_ids', 'career_snapshot'),
        'draft': ('preferences', 'recent_history', 'wiki_pages', 'wiki_target',
                  'career_snapshot', 'declared_gaps', 'jd_source_ids', 'research',
                  'general_quote_anchors', 'source_quote_anchors', 'invalid_proposal', 'artifact', 'boards', 'documents', 'document_target'),
        'review': ('proposal', 'career_snapshot', 'declared_gaps', 'jd_source_ids'),
    }
    for key in keys[stage]:
        if packet.get(key) is not None:
            base[key] = packet[key]
    return base
