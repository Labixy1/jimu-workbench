"""Local Excalidraw scenes, bounded JSON and version guards."""
import json
import math
from domain import Conflict, now, uid


def scene(data):
    if not isinstance(data, dict): raise ValueError('无效画板')
    if len(json.dumps(data).encode()) > 1500000: raise ValueError('画板超过1.5MB')
    if data.get('files'): raise ValueError('当前画板不导入附件')
    elements = data.get('elements', [])
    if not isinstance(elements, list) or len(elements) > 400: raise ValueError('最多400个图形')
    ids = set()
    for e in elements:
        if not isinstance(e, dict) or e.get('type') not in ('rectangle','ellipse','diamond','text','arrow','line','freedraw'):
            raise ValueError('当前画板只支持文字、图形、箭头和手绘；不导入图片或外链')
        if not isinstance(e.get('id'), str) or len(e['id']) > 100 or e['id'] in ids: raise ValueError('图形ID无效')
        ids.add(e['id'])
        for key in ('x','y','width','height','angle'):
            value = e.get(key, 0)
            if type(value) not in (int,float) or not math.isfinite(value) or abs(value) > 1000000: raise ValueError('图形坐标无效')
        if len(str(e.get('text',''))) > 10000 or e.get('link'): raise ValueError('图形文字过长或包含外链')
    state = data.get('appState', {})
    if not isinstance(state, dict): raise ValueError('无效画板状态')
    return {'elements': elements, 'appState': {'viewBackgroundColor': str(state.get('viewBackgroundColor','#ffffff'))[:30]}, 'files': {}}


def save(store, data, job_id=None):
    title = str(data.get('title','')).strip()
    if not 1 <= len(title) <= 100: raise ValueError('画板标题1至100字')
    body = {'title':title,'scene':scene(data.get('scene',{})), 'linked_id':data.get('linked_id')}
    with store.lock:
        if job_id:
            page=store.job(job_id)['payload']['proposal']['page']
            body['citations']=page.get('citations',[])
            body['notes']=page.get('content','')
        if body['linked_id']:
            linked=store.artifact(body['linked_id'])
            if linked['archived'] or linked['kind']=='board':raise ValueError('无效关联资产')
        existing=store.artifact(data['id']) if data.get('id') else None
        if existing:
            for key in ('citations','notes'):
                if key in existing['body']:body[key]=existing['body'][key]
        expected=data.get('revision',0)
        if existing and (existing['kind']!='board' or existing['archived'] or existing['revision']!=expected):raise Conflict('画板已变更，请重新打开；当前画布未丢弃')
        if not existing and expected!=0:raise Conflict('新画板版本必须为0')
        aid=existing['id'] if existing else uid('board');revision=expected+1;encoded=json.dumps(body,ensure_ascii=False)
        try:
            if existing:store.db.execute('UPDATE artifacts SET title=?,body=?,revision=?,updated=? WHERE id=?',(title,encoded,revision,now(),aid))
            else:store.db.execute('INSERT INTO artifacts(id,title,kind,body,revision,updated) VALUES(?,?,?,?,?,?)',(aid,title,'board',encoded,revision,now()))
            store.db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(uid('ver'),aid,revision,encoded,'保存画板',now()))
            from library import record_destination
            origin=None;reference='';destination=data
            if job_id:origin='ai';reference=job_id
            if not existing and body['linked_id']:
                linked_origin=store.db.execute('SELECT origin FROM asset_origins WHERE asset_id=?',(body['linked_id'],)).fetchone()
                if linked_origin and linked_origin['origin']=='ai':origin='ai';reference=body['linked_id']
                category=store.db.execute('SELECT category_id FROM asset_categories_map WHERE asset_id=?',(body['linked_id'],)).fetchone()
                if category and 'category_id' not in data:destination={**data,'category_id':category['category_id']}
            record_destination(store,aid,destination,origin,reference)
            if job_id:
                job=store.job(job_id);payload=job['payload'];payload.update(published_id=aid,approved_revision=revision)
                store.db.execute("UPDATE jobs SET status='approved',payload=?,updated=? WHERE id=?",(json.dumps(payload,ensure_ascii=False),now(),job['id']))
            store.db.commit()
        except Exception:store.db.rollback();raise
        return store.artifact(aid)


def selected_text(store, selections):
    """Send saved board text, never the whole scene or an inferred graph."""
    if not isinstance(selections, list) or len(selections) > 3:
        raise ValueError('每次最多引用3个画板')
    result, ids = [], set()
    for selected in selections:
        if not isinstance(selected, dict): raise ValueError('无效画板引用')
        board = store.artifact(selected.get('id'))
        if board['kind'] != 'board' or board['archived']: raise ValueError('无效画板引用')
        if type(selected.get('revision')) is not int or selected['revision'] != board['revision']:
            raise Conflict('画板已修改，请重新选择后发送')
        if board['id'] in ids: continue
        ids.add(board['id'])
        labels = [e.get('text', '') for e in board['body']['scene']['elements']
                  if e.get('type') == 'text' and not e.get('isDeleted')]
        text = '\n'.join(labels)
        if not text.strip(): raise ValueError('画板没有可引用文字；暂不支持图像理解')
        if len(text) > 10000: raise ValueError('画板文字超过10000字，请缩小范围')
        result.append({'id': board['id'], 'title': board['title'], 'revision': board['revision'],
                       'content': text, 'representation': 'text_labels_only_not_visual_relationships'})
    return result


def from_wiki(store, data):
    """Render an approved sequence, never execute model-authored drawing code."""
    with store.lock:
        page=store.artifact(data.get('id'))
        if page['kind']!='wiki' or page['archived']:raise ValueError('请选择已保存知识页')
        if page['revision']!=data.get('revision'):raise Conflict('知识页已变化，请刷新再生成画板')
        nodes=page['body'].get('diagram',[])
        if not nodes:raise ValueError('本页没有已保存的流程步骤')
        generated=flow_scene(nodes)
        return save(store,{'title':page['title'][:94]+' · 画板','scene':generated,'linked_id':page['id'],'revision':0})


def flow_scene(nodes):
    if not isinstance(nodes,list) or not 1<=len(nodes)<=10 or any(not isinstance(n,str) or not 1<=len(n)<=60 for n in nodes):raise ValueError('流程步骤无效')
    elements=[]
    for i,label in enumerate(nodes):
        y=i*140
        base={'angle':0,'strokeColor':'#4b5563','backgroundColor':'#f8fafc','fillStyle':'solid','strokeWidth':1,'strokeStyle':'solid','roughness':0,'opacity':100,'seed':100+i,'version':1,'versionNonce':100+i,'isDeleted':False,'groupIds':[],'frameId':None,'index':None,'updated':0,'link':None,'locked':False}
        rect_id=uid('rect');text_id=uid('text')
        elements.append({**base,'id':rect_id,'type':'rectangle','x':100,'y':y,'width':380,'height':80,'roundness':{'type':3},'boundElements':[{'id':text_id,'type':'text'}]})
        lines=[label[j:j+20] for j in range(0,len(label),20)]
        elements.append({**base,'id':text_id,'type':'text','x':110,'y':y+40-len(lines)*11.25,'width':360,'height':len(lines)*22.5,'text':'\n'.join(lines),'originalText':label,'fontSize':18,'fontFamily':3,'textAlign':'center','verticalAlign':'middle','containerId':rect_id,'autoResize':True,'lineHeight':1.25,'backgroundColor':'transparent','boundElements':None})
        if i<len(nodes)-1:
            elements.append({**base,'id':uid('arrow'),'type':'arrow','x':290,'y':y+85,'width':0,'height':45,'points':[[0,0],[0,45]],'startBinding':None,'endBinding':None,'startArrowhead':None,'endArrowhead':'arrow','elbowed':False,'roundness':None,'backgroundColor':'transparent','boundElements':None})
    return scene({'elements':elements,'appState':{'viewBackgroundColor':'#ffffff'},'files':{}})
