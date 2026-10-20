"""Evidence-backed career drafts. Model proposals require explicit user approval."""
import json
import re
from domain import Conflict, now, uid


def quote_anchors(payload):
    if payload.get('kind') != 'tailor': return []
    content = payload['career_snapshot']['body']['general']
    parts = re.findall(r'[^。！？\n]+[。！？]?|\n', content)
    quotes = [part.strip() for part in parts if part.strip()]
    quotes = [quote[i:i+600] for quote in quotes for i in range(0, len(quote), 600)]
    return [{'id': 'quote_' + str(i+1), 'quote': quote} for i, quote in enumerate(quotes)]


def text(value, label, limit=1500):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(label + '不能为空或超过长度限制')
    return value.strip()


def evidence(items, sources):
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError('每项需提供1至5条证据')
    checked = []
    for ref in items:
        if not isinstance(ref, dict) or ref.get('source_id') not in sources:
            raise ValueError('证据引用了未选择的资料')
        if ref.get('quote_id'):
            choices={q['quote_id']:q['quote'] for q in source_quote_anchors([sources[ref['source_id']]])}
            if not isinstance(ref['quote_id'],str) or ref['quote_id'] not in choices: raise ValueError('不存在的证据原句编号')
            quote=choices[ref['quote_id']]
            if ref.get('quote') and ref['quote']!=quote: raise ValueError('证据编号与原句不一致')
        else: quote = text(ref.get('quote'), '引用', 1200)
        if len(quote) < 8 or quote not in sources[ref['source_id']]['content']:
            raise ValueError('证据必须在所选原文中逐字找到，至少8字')
        checked.append({'source_id': ref['source_id'], 'quote': quote})
    return checked


def source_quote_anchors(sources):
    result=[]
    for source in sources:
        lines=[line.strip() for line in source['content'].splitlines() if len(line.strip())>=8]
        for i,line in enumerate(lines):
            for j in range(0,len(line),600):
                quote=line[j:j+600]
                if len(quote)>=8: result.append({'source_id':source['id'],'quote_id':'line_'+str(i+1)+'_'+str(j),'quote':quote})
    return result


def validate_proposal(proposal, payload, sources):
    if not isinstance(proposal, dict): raise ValueError('经历草稿必须是对象')
    if payload['kind'] == 'experience':
        facts = proposal.get('facts')
        if not isinstance(facts, list) or not 1 <= len(facts) <= 8:
            raise ValueError('请提供1至8项经历事实')
        checked = []
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict): raise ValueError('无效事实')
            checked.append({'id': 'fact_' + str(i+1), 'text': text(fact.get('text'), '事实', 800),
                'ownership': text(fact.get('ownership'), '本人职责', 200),
                'evidence': evidence(fact.get('evidence'), sources)})
        questions = proposal.get('questions', [])
        if not isinstance(questions, list) or len(questions) > 8 or any(not isinstance(q, str) or not 1 <= len(q) <= 300 for q in questions):
            raise ValueError('待确认问题最多8个，每个300字')
        return {'title': text(proposal.get('title'), '经历标题', 100), 'facts': checked,
                'general': text(proposal.get('general'), '通用版表达', 3000), 'questions': questions,
                'output_format':payload.get('output_format','experience')}
    base = payload['career_snapshot']
    diagnostics = proposal.get('diagnostics')
    if not isinstance(diagnostics, list) or not 1 <= len(diagnostics) <= 8:
        raise ValueError('请提供1至8条诊断')
    checked = []
    anchors = {q['id']: q['quote'] for q in quote_anchors(payload)}
    for d in diagnostics:
        if not isinstance(d, dict): raise ValueError('无效诊断')
        category = d.get('category')
        if category not in ('expression', 'evidence', 'gap'): raise ValueError('诊断类别无效')
        # Resolve a stable original-text anchor instead of asking the model to retype it.
        if d.get('quote_id'):
            if not isinstance(d['quote_id'], str) or d['quote_id'] not in anchors: raise ValueError('批注选择了不存在的原句编号')
            quote = anchors[d['quote_id']]
            if d.get('quote') and d['quote'] != quote: raise ValueError('原句编号与批注原句不一致')
        else: quote = text(d.get('quote'), '标记原句', 600)
        if quote not in base['body']['general']: raise ValueError('批注原句必须逐字匹配当前通用版')
        # A missing statement never proves a missing ability.
        declared_quote = d.get('declared_gap_quote','')
        if category == 'gap' and (not isinstance(declared_quote,str) or not declared_quote.strip()
                                  or declared_quote not in payload.get('declared_gaps','')):
            category = 'evidence'
        refs = evidence(d.get('jd_evidence'), sources)
        if any(r['source_id'] not in payload['jd_source_ids'] for r in refs):
            raise ValueError('岗位要求必须引用本次 JD')
        checked.append({'quote': quote, 'category': category, 'problem': text(d.get('problem'), '问题', 500),
                        'suggestion': text(d.get('suggestion'), '建议', 800), 'jd_evidence': refs})
    return {'title': text(proposal.get('title'), '岗位标题', 100), 'diagnostics': checked,
            'tailored': text(proposal.get('tailored'), '定向改写', 3000),
            'output_format':base['body'].get('output_format','experience')}


def approve(store, job, edits):
    p = job['payload']; sources = {sid: store.source(sid) for sid in p['source_ids']}
    if any(s['archived'] for s in sources.values()): raise Conflict('资料已归档，请重新生成')
    proposed = validate_proposal(p['proposal'], p, sources)
    if p['kind'] == 'experience':
        # User confirms attribution and facts, not merely an attractive paragraph.
        ids = edits.get('confirmed_fact_ids', [])
        if not isinstance(ids, list) or set(ids) != {f['id'] for f in proposed['facts']}:
            raise ValueError('请逐项确认本人职责和事实；有误请先补充材料重新生成')
        body = {**proposed, 'general': text(edits.get('general', proposed['general']), '通用版表达', 3000),
                'source_ids': p['source_ids'], 'confirmed': True, 'created_from_job': job['id']}
        kind, aid, revision = 'career', uid('career'), 1
    else:
        base = store.artifact(p['career_id'])
        if base['archived'] or base['revision'] != p['career_revision']:
            raise Conflict('经历通用版已变化，请基于最新版本重新诊断')
        if edits.get('confirm_no_new_claims') is not True:
            raise ValueError('请确认改写没有新增未经证实的贡献和数据')
        body = {**proposed, 'tailored': text(edits.get('tailored', proposed['tailored']), '定向改写', 3000),
                'career_id': base['id'], 'career_revision': base['revision'], 'original': base['body']['general'],
                'jd_source_ids': p['jd_source_ids'], 'created_from_job': job['id']}
        kind, aid, revision = 'career_review', uid('review'), 1
    encoded = json.dumps(body, ensure_ascii=False)
    try:
        store.db.execute('INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)',
                         (aid, body['title'], kind, encoded, revision, now()))
        store.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)', (uid('ver'), aid, revision, encoded, '用户确认经历资产', now()))
        p['published_id'] = aid
        from library import record_destination
        record_destination(store, aid, edits, 'ai', job['id'])
        store.db.execute("UPDATE jobs SET status='approved',payload=?,updated=? WHERE id=?", (json.dumps(p, ensure_ascii=False), now(), job['id']))
        store.db.commit()
    except Exception: store.db.rollback(); raise
    return store.artifact(aid)


def instruction(kind, output_format='experience'):
    if output_format=='resume':
        if kind=='experience':
            return '''仅依据sources与本人说明，整理完整简历。返回JSON {title:string,facts:[{text,ownership,evidence:[{source_id,quote}]}],general:string,questions:[string]}。general是可直接阅读的完整中文Markdown简历，300至700字，不为达到字数重复内容；包含资料明确给出的个人简介、教育背景、实习或项目经历、技能；不知道姓名、日期、联系方式时直接省略，绝不编造；不要把目标岗位能力写成本人能力。facts 1至8项覆盖简历中的核心事实与职责，每项1至2条逐字原文证据，引用至少8字。团队产出不能写本人独立负责；未上线、待验证、本人职责边界集中简明保留一次，避免每段反复免责声明。学校、日期、联系人和未证实能力等缺失信息只写questions，general不要“说明”“材料未提供”等冗长尾注。明确虚构材料时，标题与正文开头均保留“虚构示例”，不冒充真实简历。'''
        return '''对照career_snapshot里的完整简历与已确认facts，按第一个目标JD改写完整中文Markdown简历，保留其他有效章节。返回JSON {title:string,diagnostics:[{quote_id,category:expression|evidence|gap,declared_gap_quote,problem,suggestion,jd_evidence:[{source_id,quote_id}]}],tailored:string}。tailored为300至700字完整简历，不只给一段经历；仅调整信息顺序与表达，不新增能力、职责、日期、业绩。诊断1至4条，只选重要且实际存在的问题：必须结合完整简历判断，不能因某句没有写就忽略相邻句/其他章节已写的内容。已有职责边界不能诊断为没有写；可以指出信息位置或表达重点，但不能虚构缺失。quote_id使用general_quote_anchors，jd_evidence使用source_quote_anchors里的真实source_id与quote_id，不输出引用原文。没有写不等于没有能力，默认evidence；只有declared_gaps明确确认时才gap。待补信息、缺失能力、岗位要求放diagnostics，tailored不堆“材料未提供”说明，不添加“信息待补”或类似章节；不知道就省略，补充清单只放diagnostics。没有材料证明做过某事，也不能写成明确没做过；禁止把证据不足改为“不涉及某工作”这种否定事实。贡献边界简明保留一次。虚构标识必须保留。'''
    if kind == 'experience':
        return '''仅依据 sources 及本人说明，整理经历；团队文件不是本人贡献证明。每项写清本人职责，未明确的写待确认，结果未核验不能写已达成。返回 JSON {title:string,facts:[{text:string,ownership:string,evidence:[{source_id,quote}]}],general:string,questions:[string]}。facts 1至6项，每项1至2条逐字引用，quote 从sources.content逐字复制至少8字，不加引号、不改标点、不用省略号。通用版是可直接用于简历的2至3条短句，总共120至250字，突出真实行动、方法与已证实产出；没有效果就写产出，不必大段解释不能证明什么。所有未知项目名、日期、待确认结果放questions，general不要堆砌免责声明或待确认列表。若材料明确虚构，general开头保留虚构标识。无JD不生成虚构岗位。'''
    return '''根据 career_snapshot.body.general 与已确认 facts，分别对照本次各JD，不把不同岗位混为一套要求。返回 JSON {title:string,diagnostics:[{quote_id:string,category:expression|evidence|gap,declared_gap_quote:string,problem:string,suggestion:string,jd_evidence:[{source_id,quote}]}],tailored:string}。diagnostics 1至6条。quote_id 必须选择 general_quote_anchors 中提供的真实原句编号（例如quote_1），不要输出诊断quote字段，也不要对虚构验收标识单独诊断。jd_evidence 从JD原文逐字复制至少8字，不改标点。没有写不等于没有能力，默认evidence，只有用户declared_gaps明确确认的才gap，且declared_gap_quote必须逐字引用本人缺失说明。tailored只针对jd_source_ids第一个目标JD，其余JD只在diagnostics分别比较。改写为可直接用于简历的2至3条短句，总共120至250字；只使用已确认事实，不把JD技能改成本人经历，不编造数字、上线结果、独立负责。不把大段诊断、JD复述、待确认事项写进tailored，建议留diagnostics。若明确虚构保留标识。'''


def edit(store, data):
    with store.lock:
        a=store.artifact(data.get('id'))
        if a['kind'] not in ('career','career_review') or a['archived']:raise ValueError('无效经历资产')
        if data.get('revision')!=a['revision']:raise Conflict('经历版本已变化，请重新打开编辑')
        field='general' if a['kind']=='career' else 'tailored'
        body={**a['body'],field:text(data.get('content'),'经历表达',3000)}
        if data.get('confirmed') is not True:raise ValueError('请确认改动没有新增未证实事实')
        revision=a['revision']+1;encoded=json.dumps(body,ensure_ascii=False)
        try:
            store.db.execute('UPDATE artifacts SET body=?,revision=?,updated=? WHERE id=?',(encoded,revision,now(),a['id']))
            store.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),a['id'],revision,encoded,'用户修订经历表达',now()));store.db.commit()
        except Exception:store.db.rollback();raise
        return store.artifact(a['id'])
