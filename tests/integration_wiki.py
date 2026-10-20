"""Real OpenCode Wiki workflow; deterministic model, not quality evaluation."""
import json,tempfile,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain import Store
from engine import OpenCode,Runner,ROOT
from wiki import sync_wiki
with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as d:
 store=Store(Path(d)/'db');workspace=Path(d)/'workspace';workspace.mkdir()
 engine=OpenCode('http://127.0.0.1:4098',(ROOT/'.runtime/engine-password').read_text().strip(),workspace)
 runner=Runner(store,engine,{'mode':'fixture','model':'fixture'})
 source=store.add_source('公开验收','Wiki 应把原文与知识分层，保留引用，标记不确定项，人工确认之后才能成为正式知识。',visibility='public')['source']
 job=store.create_job(store.conversation(),'map-agent',{'kind':'wiki','prompt':'整理知识','source_ids':[source['id']],'base_revision':1})
 runner.submit(job)
 for _ in range(180):
  job=store.job(job['id'])
  if job['status'] not in ('running','queued'):break
  time.sleep(.5)
 assert job['status']=='review',job
 assert not any(a['kind']=='wiki' for a in store.artifacts())
 page=store.approve(job['id']);assert page['kind']=='wiki';assert store.approve(job['id'])['id']==page['id']
 folder=sync_wiki(Path(d),store);assert (folder/(page['id']+'.md')).is_file()
 result={'passed':True,'mode':'fixture, not AI quality','stages':len(job['payload']['stages']),'approved_wiki':True,'exact_quote':True,'markdown_file':True}
 (ROOT/'tests/wiki-integration-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));store.db.close()
