import copy,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain import Store,Conflict
from server import validate_url
class DomainTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'db');self.src=self.s.add_source('证据','子 Agent 将搜索过程保存在独立会话中，主会话接收结论和原文引用。',visibility='public')['source'];self.a=self.s.artifact('map-agent');self.cid=self.s.conversation();self.c=[{'module_id':'context','summary':'当前上下文包含相关材料。','points':['保留来源'],'commerce':'保留指标口径','citations':[{'source_id':self.src['id'],'quote':self.src['content']}]}]
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def job(self):
  j=self.s.create_job(self.cid,'map-agent',{'base_revision':1,'source_ids':[self.src['id']],'prompt':'补充','proposal':{'changes':self.c}});return self.s.update_job(j['id'],'review')
 def test_dedup(self):self.assertTrue(self.s.add_source('不同标题',self.src['content'])['duplicate']);self.assertEqual(len(self.s.sources()),1)
 def test_empty(self):
  with self.assertRaises(ValueError):self.s.add_source('','')
 def test_exact_quote(self):
  c=copy.deepcopy(self.c);c[0]['citations'][0]['quote']='不在原文中的至少八个字'
  with self.assertRaises(ValueError):self.s.validate_changes(c,self.a,{self.src['id']:self.src})
 def test_selected_sources(self):
  with self.assertRaises(ValueError):self.s.validate_changes(self.c,self.a,{})
 def test_module(self):
  c=copy.deepcopy(self.c);c[0]['module_id']='../../invalid'
  with self.assertRaises(ValueError):self.s.validate_changes(c,self.a,{self.src['id']:self.src})
 def test_duplicate_module(self):
  with self.assertRaises(ValueError):self.s.validate_changes(self.c*2,self.a,{self.src['id']:self.src})
 def test_review_does_not_write(self):self.job();self.assertEqual(self.s.artifact('map-agent')['revision'],1)
 def test_approve_idempotent_persistent(self):
  j=self.job();self.assertEqual(self.s.approve(j['id'])['revision'],2);self.assertEqual(self.s.approve(j['id'])['revision'],2);s=Store(self.s.path);self.assertEqual(s.artifact('map-agent')['revision'],2);s.db.close()
 def test_stale(self):
  a=self.job();b=self.job();self.s.approve(a['id'])
  with self.assertRaises(Conflict):self.s.approve(b['id'])
 def test_restore(self):
  j=self.job();self.s.approve(j['id']);old=self.s.versions('map-agent')[-1];a=self.s.restore('map-agent',old['id'],2);self.assertEqual(a['revision'],3);self.assertEqual(a['body'],self.a['body']);self.assertEqual(len(self.s.versions('map-agent')),3)
 def test_busy(self):
  self.s.create_job(self.cid,'map-agent',{})
  with self.assertRaises(Conflict):self.s.create_job(self.cid,'map-agent',{})
 def test_restart(self):
  j=self.s.create_job(self.cid,'map-agent',{});s=Store(self.s.path);self.assertEqual(s.job(j['id'])['status'],'interrupted');s.db.close()
 def test_interrupted_is_terminal(self):
  j=self.s.create_job(self.cid,'map-agent',{})
  self.s.update_job(j['id'],'interrupted',error='cancelled')
  self.s.update_job(j['id'],'review',proposal={'changes':self.c})
  self.assertEqual(self.s.job(j['id'])['status'],'interrupted')
  self.assertNotIn('proposal',self.s.job(j['id'])['payload'])
  with self.assertRaises(Conflict):self.s.approve(j['id'])
 def test_rejected(self):
  j=self.job();self.s.update_job(j['id'],'rejected')
  with self.assertRaises(Conflict):self.s.approve(j['id'])
 def test_ssrf(self):
  for u in ['http://127.0.0.1:80','http://169.254.169.254/','http://user:pass@example.com/','file:///etc/passwd']:
   with self.assertRaises(ValueError):validate_url(u)
 def test_local_model(self):self.assertEqual(validate_url('http://127.0.0.1:11434/v1',local=True),'http://127.0.0.1:11434/v1')
if __name__=='__main__':unittest.main()
