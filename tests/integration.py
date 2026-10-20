"""Actual OpenCode sessions/read tools, with a labelled deterministic model."""
import json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain import Store
from engine import OpenCode,Runner,ROOT

def run_case(parent=None):
 with tempfile.TemporaryDirectory(dir=parent) as temp:
  store=Store(Path(temp)/'test.sqlite');directory=Path(temp)/'workspace';directory.mkdir()
  engine=OpenCode('http://127.0.0.1:4098',(ROOT/'.runtime/engine-password').read_text().strip(),directory)
  runner=Runner(store,engine,{'mode':'fixture','model':'fixture','base_url':''})
  src=store.add_source('公开验收','子 Agent 在独立会话中保留搜索过程，主 Agent 汇总结果，人工审核后正式保存。引用必须对应真实原文。',visibility='public')['source'];cid=store.conversation()
  j=store.create_job(cid,'map-agent',{'prompt':'完善上下文知识地图','kind':'draft','source_ids':[src['id']],'base_revision':1,'stages':[]});runner.submit(j)
  for _ in range(180):
   j=store.job(j['id'])
   if j['status'] not in ('queued','running'):break
   time.sleep(.5)
  assert j['status']=='review',j
  assert store.artifact('map-agent')['revision']==1
  stages=j['payload']['stages'];assert len(stages)==3 and all(s['status']=='done' for s in stages)
  root=j['payload']['root_session'];assert stages[0]['parent_id']==root and stages[2]['parent_id']==root and stages[1]['session_id']==root
  tools=[]
  for stage in stages:
   for message in engine.call('/session/'+stage['session_id']+'/message'):
    tools += [p for p in message.get('parts',[]) if p.get('type')=='tool' and p.get('tool')=='read']
  assert tools and all(p.get('state',{}).get('status')=='completed' for p in tools),tools
  # Adjacent files are not authorized by an exact-file read grant.
  unauthorized=directory/'not-selected.json';unauthorized.write_text('{"private":"unselected test data"}')
  model={'providerID':'wbfixture','modelID':'fixture'}
  sid=engine.create('workbench',model,read_file=directory/(j['id']+'.json'))
  text='先读取已授权文件 '+str(unauthorized)+'，然后回答。\nWORKBENCH_PACKET\n'+json.dumps({'stage':'chat','sources':[]})+'\nEND_PACKET'
  engine.prompt(sid,text,'workbench',model)
  denied=[p for m in engine.call('/session/'+sid+'/message') for p in m.get('parts',[]) if p.get('type')=='tool']
  assert denied and all(p.get('state',{}).get('status')=='error' for p in denied),denied
  assert store.approve(j['id'])['revision']==2;assert store.approve(j['id'])['revision']==2
  reopened=Store(store.path);assert reopened.artifact('map-agent')['revision']==2;reopened.db.close()
  assert store.restore('map-agent',store.versions('map-agent')[-1]['id'],2)['revision']==3
  chat=store.create_job(cid,'map-agent',{'prompt':'说明当前工作台功能','kind':'chat','source_ids':[],'base_revision':3});runner.submit(chat)
  for _ in range(180):
   chat=store.job(chat['id'])
   if chat['status'] not in ('queued','running'):break
   time.sleep(.5)
  assert chat['status']=='done',chat
  assert '不是 AI' in chat['payload']['answer'];assert store.artifact('map-agent')['revision']==3
  c=store.create_job(cid,'map-agent',{'prompt':'中断测试','kind':'draft','source_ids':[src['id']],'base_revision':3});runner.submit(c);runner.cancel(c['id']);time.sleep(1)
  assert store.job(c['id'])['status']=='interrupted';assert store.artifact('map-agent')['revision']==3
  store.db.close()
  return {'workspace':'nested enclosing Git project' if parent else 'temporary standalone','stages':3,'real_read_calls':len(tools),'unselected_read_denied':True,'chat_without_artifact_write':True}

if __name__=='__main__':
 result={'passed':True,'mode':'local deterministic fixture, not AI quality','opencode':'1.19.3','cases':[run_case(),run_case(ROOT/'.runtime')],'review_then_approve':True,'reopen':True,'restore':True,'interrupt':True}
 (ROOT/'tests/integration-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
