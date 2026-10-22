"""Local Excalidraw scenes, bounded JSON and version guards."""
import json
import math
import heapq
import re
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
            if page.get('graph'):body['generated_graph']=validate_graph(page['graph'])
        if body['linked_id']:
            linked=store.artifact(body['linked_id'])
            if linked['archived'] or linked['kind']=='board':raise ValueError('无效关联资产')
            if not data.get('id'):
                body.setdefault('citations',linked['body'].get('citations',[]))
                body.setdefault('notes',linked['body'].get('content',''))
                if linked['body'].get('graph'):body.setdefault('generated_graph',linked['body']['graph'])
        existing=store.artifact(data['id']) if data.get('id') else None
        if existing:
            for key in ('citations','notes','generated_graph','edited_graph'):
                if key in existing['body']:body[key]=existing['body'][key]
        if 'graph' in data:
            body['edited_graph']=validate_graph(data['graph'])
        if 'notes' in data:
            if not isinstance(data['notes'],str) or len(data['notes'])>18000:raise ValueError('画板说明需要是文本，最多18000字')
            body['notes']=data['notes']
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
        if not page['body'].get('graph') and not page['body'].get('diagram'):raise ValueError('本页没有已保存的流程或关系')
        generated=page_scene(page['body'])
        return save(store,{'title':page['title'][:94]+' · 画板','scene':generated,'linked_id':page['id'],'revision':0})


def validate_graph(data):
    """A small declarative graph, not drawing code or an inferred knowledge graph."""
    if not isinstance(data,dict):raise ValueError('画板graph必须是对象')
    groups,nodes,edges=data.get('groups'),data.get('nodes'),data.get('edges')
    if not isinstance(groups,list) or not 1<=len(groups)<=5:raise ValueError('画板需要1至5个分组')
    if not isinstance(nodes,list) or not 2<=len(nodes)<=32:raise ValueError('画板需要2至32个节点')
    if not isinstance(edges,list) or not 1<=len(edges)<=60:raise ValueError('画板需要1至60条关系')
    def ident(value):
        if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,39}',value):raise ValueError('画板标识只能包含字母、数字、横杠和下划线')
        return value
    def text(value,limit,empty=False):
        if not isinstance(value,str) or len(value.strip())>limit or not empty and not value.strip():raise ValueError('画板文字为空或超过长度限制')
        return value.strip()
    checked_groups=[];group_ids=set()
    for group in groups:
        if not isinstance(group,dict):raise ValueError('无效画板分组')
        gid=ident(group.get('id'))
        if gid in group_ids:raise ValueError('画板分组ID重复')
        group_ids.add(gid);checked_groups.append({'id':gid,'label':text(group.get('label'),24)})
    checked_nodes=[];node_ids=set();cells=set()
    for node in nodes:
        if not isinstance(node,dict):raise ValueError('无效画板节点')
        nid=ident(node.get('id'));group=node.get('group');row=node.get('row')
        if nid in node_ids:raise ValueError('画板节点ID重复')
        if group not in group_ids:raise ValueError('画板节点分组不存在')
        if type(row) is not int or not 0<=row<=11:raise ValueError('画板节点row需要0至11的整数')
        if (group,row) in cells:raise ValueError('同一分组的同一行不能放两个节点')
        kind=node.get('kind','process')
        if kind not in ('process','decision','note'):raise ValueError('无效画板节点类型')
        cells.add((group,row));node_ids.add(nid)
        checked_nodes.append({'id':nid,'label':text(node.get('label'),36),'detail':text(node.get('detail',''),72,True),'group':group,'row':row,'kind':kind})
    checked_edges=[];pairs=set();connected=set()
    for edge in edges:
        if not isinstance(edge,dict):raise ValueError('无效画板关系')
        start,end=edge.get('from'),edge.get('to');kind=edge.get('kind','flow')
        if start not in node_ids or end not in node_ids or start==end:raise ValueError('画板关系必须连接两个已有的不同节点')
        if kind not in ('flow','reference','feedback'):raise ValueError('无效画板关系类型')
        label=text(edge.get('label',''),24,True)
        if (start,end,kind) in pairs:raise ValueError('画板关系重复')
        pairs.add((start,end,kind));connected.update((start,end))
        checked_edges.append({'from':start,'to':end,'label':label,'kind':kind})
    if connected!=node_ids:raise ValueError('每个画板节点都需要至少一条关系')
    if {n['group'] for n in checked_nodes}!=group_ids:raise ValueError('画板不能包含空分组')
    return {'groups':checked_groups,'nodes':checked_nodes,'edges':checked_edges}


def page_scene(page):
    return graph_scene(page['graph'],page.get('title','')) if page.get('graph') else flow_scene(page.get('diagram',[]))


def _wrapped(text,columns):
    lines=[]
    for paragraph in text.split('\n'):
        line='';size=0
        for char in paragraph:
            width=1 if ord(char)<128 else 2
            if size+width>columns and line:lines.append(line);line='';size=0
            line+=char;size+=width
        lines.append(line)
    return lines


def _route(start,end,rectangles,xs,ys):
    """Route orthogonal connectors through gutters, never through a node."""
    xs=sorted(set(xs+[start[0],end[0]]));ys=sorted(set(ys+[start[1],end[1]]))
    def inside(x,y):return any(l<x<r and t<y<b for l,t,r,b in rectangles)
    valid={(i,j) for i,x in enumerate(xs) for j,y in enumerate(ys) if not inside(x,y)}
    def clear(a,b):
        x,y=xs[a[0]],ys[a[1]];u,v=xs[b[0]],ys[b[1]]
        if x==u:return not any(l<x<r and max(min(y,v),t)<min(max(y,v),b) for l,t,r,b in rectangles)
        return not any(t<y<b and max(min(x,u),l)<min(max(x,u),r) for l,t,r,b in rectangles)
    origin=(xs.index(start[0]),ys.index(start[1]));target=(xs.index(end[0]),ys.index(end[1]))
    initial=(*origin,-1);costs={initial:0};previous={};heap=[(0,0,initial)]
    while heap:
        _,cost,current=heapq.heappop(heap);i,j,direction=current
        if cost!=costs.get(current):continue
        if (i,j)==target:
            path=[]
            while current is not None:
                path.append((xs[current[0]],ys[current[1]]));current=previous.get(current)
            path.reverse();compact=[]
            for point in path:
                if len(compact)>1 and ((compact[-2][0]==compact[-1][0]==point[0]) or (compact[-2][1]==compact[-1][1]==point[1])):compact[-1]=point
                else:compact.append(point)
            return compact
        for a,b,turn in ((i-1,j,0),(i+1,j,0),(i,j-1,1),(i,j+1,1)):
            if (a,b) not in valid or not clear((i,j),(a,b)):continue
            next_state=(a,b,turn);distance=abs(xs[a]-xs[i])+abs(ys[b]-ys[j])
            next_cost=cost+distance+(28 if direction not in (-1,turn) else 0)
            if next_cost>=costs.get(next_state,math.inf):continue
            costs[next_state]=next_cost;previous[next_state]=current
            heuristic=abs(xs[a]-end[0])+abs(ys[b]-end[1])
            heapq.heappush(heap,(next_cost+heuristic,next_cost,next_state))
    raise ValueError('画板连线布局失败，请减少交叉关系')


def graph_scene(data,title=''):
    graph=validate_graph(data);elements=[];boxes={};shape_ids={};arrow_bindings={n['id']:[] for n in graph['nodes']}
    base={'angle':0,'strokeColor':'#45574d','backgroundColor':'transparent','fillStyle':'solid','strokeWidth':1,'strokeStyle':'solid','roughness':0,'opacity':100,'seed':101,'version':1,'versionNonce':101,'isDeleted':False,'groupIds':[],'frameId':None,'index':None,'updated':0,'link':None,'locked':False,'boundElements':None}
    palette=[('#f1f6f2','#53775e'),('#f2f5f8','#597182'),('#f8f5ef','#88775b'),('#f4f5f4','#637269'),('#f5f3f0','#7f7565')]
    width,height,pitch_x,pitch_y=326,112,418,148
    max_row=max(n['row'] for n in graph['nodes']);bottom=156+max_row*pitch_y+height
    def text(label,x,y,w,size=18,color='#26392d',align='left',container=None):
        lines=_wrapped(label,max(12,int(w/size*1.8)))
        item={**base,'id':uid('text'),'type':'text','x':x,'y':y,'width':w,'height':len(lines)*size*1.3,'text':'\n'.join(lines),'originalText':label,'fontSize':size,'fontFamily':2,'textAlign':align,'verticalAlign':'middle' if container else 'top','containerId':container,'autoResize':True,'lineHeight':1.3,'strokeColor':color}
        elements.append(item);return item
    text(title or '流程与关系',72,28,len(graph['groups'])*pitch_x-60,26)
    for index,group in enumerate(graph['groups']):
        x=72+index*pitch_x;fill,color=palette[index]
        elements.append({**base,'id':uid('lane'),'type':'rectangle','x':x-20,'y':88,'width':width+40,'height':bottom-64,'backgroundColor':fill,'strokeColor':fill,'roundness':{'type':3}})
        text(group['label'],x,106,width,20,color)
        for node in (n for n in graph['nodes'] if n['group']==group['id']):
            y=156+node['row']*pitch_y;shape_ids[node['id']]=uid('node');boxes[node['id']]=(x,y,x+width,y+height,index)
    rectangles=[(x-10,y-10,r+10,b+10) for x,y,r,b,_ in boxes.values()]
    xs=[32,72+len(graph['groups'])*pitch_x-40]
    ys=[138,bottom+30]
    for x,y,r,b,_ in boxes.values():xs.extend((x-20,(x+r)/2,r+20));ys.extend((y-20,(y+b)/2,b+20))
    edge_labels=[];caption_boxes=[]
    def overlap(a,b):return max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3])
    for edge in graph['edges']:
        x,y,r,b,lane=boxes[edge['from']];u,v,s,t,target_lane=boxes[edge['to']]
        if lane==target_lane and v>y:start,end=((x+r)/2,b+12),((u+s)/2,v-12)
        elif lane==target_lane:start,end=(r+12,(y+b)/2),(s+12,(v+t)/2)
        elif lane<target_lane:start,end=(r+12,(y+b)/2),(u-12,(v+t)/2)
        else:start,end=(x-12,(y+b)/2),(s+12,(v+t)/2)
        points=_route(start,end,rectangles,xs,ys);ident=uid('edge');color='#ad8248' if edge['kind']=='feedback' else '#85978d' if edge['kind']=='reference' else '#5b7163'
        offsets=[[p[0]-start[0],p[1]-start[1]] for p in points]
        elements.append({**base,'id':ident,'type':'arrow','x':start[0],'y':start[1],'width':max(p[0] for p in points)-min(p[0] for p in points),'height':max(p[1] for p in points)-min(p[1] for p in points),'points':offsets,'strokeColor':color,'strokeWidth':1.5,'strokeStyle':'dashed' if edge['kind']=='reference' else 'solid','startBinding':{'elementId':shape_ids[edge['from']],'focus':0,'gap':12},'endBinding':{'elementId':shape_ids[edge['to']],'focus':0,'gap':12},'startArrowhead':None,'endArrowhead':'arrow','elbowed':False,'roundness':None})
        for nid in (edge['from'],edge['to']):arrow_bindings[nid].append({'id':ident,'type':'arrow'})
        if edge['label']:
            segments=sorted(zip(points,points[1:]),key=lambda p:(p[0][1]==p[1][1],abs(p[0][0]-p[1][0])+abs(p[0][1]-p[1][1])),reverse=True)
            w=min(180,max(56,sum(7 if ord(c)<128 else 14 for c in edge['label'])))
            h=len(_wrapped(edge['label'],max(12,int(w/14*1.8))))*18.2
            candidates=[]
            for a,z in segments:
                for fraction in (.5,.25,.75):
                    cx=a[0]+(z[0]-a[0])*fraction;cy=a[1]+(z[1]-a[1])*fraction
                    positions=[(cx-w/2,cy-h-4),(cx-w/2,cy+4)] if a[1]==z[1] else [(cx+6,cy-h/2),(cx-w-6,cy-h/2)]
                    for tx,ty in positions:
                        tx=max(8,tx);ty=max(136,ty)
                        box=(tx-4,ty-3,tx+w+4,ty+h+3)
                        cost=sum(overlap(box,rect[:4]) for rect in rectangles)*100+sum(overlap(box,other) for other in caption_boxes)*20
                        candidates.append((cost,tx,ty,box))
            _,tx,ty,box=min(candidates,key=lambda c:c[0]);caption_boxes.append(box)
            edge_labels.append((edge['label'],tx,ty,w,color))
    for node in graph['nodes']:
        x,y,r,b,index=boxes[node['id']];fill,color=palette[index];ident=shape_ids[node['id']]
        shape={**base,'id':ident,'type':'diamond' if node['kind']=='decision' else 'rectangle','x':x,'y':y,'width':width,'height':height,'backgroundColor':'#fffaf0' if node['kind']=='decision' else '#ffffff','strokeColor':color,'roundness':None if node['kind']=='decision' else {'type':3},'strokeStyle':'dashed' if node['kind']=='note' else 'solid','boundElements':arrow_bindings[node['id']]}
        elements.append(shape)
        if node['kind']=='decision':
            label=text(node['label'],x+54,y+34,width-108,20,color,'center',ident);shape['boundElements'].append({'id':label['id'],'type':'text'})
            if node['detail']:text(node['detail'],x+18,b+5,width-36,14,'#57645b','center')
        else:
            label=text(node['label'],x+18,y+16,width-36,22,color)
            if node['detail']:text(node['detail'],x+18,y+54,width-36,17,'#57645b')
            node_group=uid('group');shape['groupIds']=[node_group]
            for item in elements[-(3 if node['detail'] else 2):]:item['groupIds']=[node_group]
    for label,x,y,w,color in edge_labels:
        lines=_wrapped(label,max(12,int(w/14*1.8)))
        elements.append({**base,'id':uid('caption'),'type':'rectangle','x':x-3,'y':y-2,'width':w+6,'height':len(lines)*18.2+4,'backgroundColor':'#ffffff','strokeColor':'#ffffff','roundness':{'type':3}})
        text(label,x,y,w,14,color,'center')
    legend_y=bottom+68;text('实线：流程   虚线：引用 / 配置   金色：反馈 / 返工',72,legend_y,680,14,'#768078')
    return scene({'elements':elements,'appState':{'viewBackgroundColor':'#ffffff'},'files':{}})


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
