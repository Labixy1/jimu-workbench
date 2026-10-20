import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from domain import Store,Conflict
from wiki import sync_wiki
from models import save_key,model_key,deepseek_request

class WikiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Store(self.root/'db');self.source=self.s.add_source('依据','知识页和原始资料分开保存。引用必须对应真实原文，人工审核后才正式入库。',visibility='public')['source'];self.page={'title':'知识整理','summary':'原文与知识分层','content':'## 要点\n\n知识整理需要保留依据。','tags':['方法'],'links':[],'citations':[{'source_id':self.source['id'],'quote':self.source['content']}]}
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def job(self,target=None,revision=0):
  j=self.s.create_job(self.s.conversation(),'map-agent',{'kind':'wiki','source_ids':[self.source['id']],'prompt':'整理','wiki_target_id':target,'wiki_base_revision':revision,'proposal':{'page':copy.deepcopy(self.page)}});return self.s.update_job(j['id'],'review')
 def test_review_not_saved_approve_idempotent(self):
  j=self.job();self.assertFalse(any(a['kind']=='wiki' for a in self.s.artifacts()));a=self.s.approve(j['id']);self.assertEqual(a['kind'],'wiki');self.assertEqual(self.s.approve(j['id'])['id'],a['id'])
 def test_stale_update(self):
  a=self.s.save_wiki(self.page);j=self.job(a['id'],1);self.s.save_wiki(self.page,a['id'],1)
  with self.assertRaises(Conflict):self.s.approve(j['id'])
 def test_bad_quote(self):
  self.page['citations'][0]['quote']='不存在的原文引用内容'
  with self.assertRaises(ValueError):self.s.save_wiki(self.page)
 def test_invalid_links(self):
  self.page['links']=['wiki_missing']
  with self.assertRaises(ValueError):self.s.save_wiki(self.page)
 def test_links_and_markdown(self):
  a=self.s.save_wiki(self.page);self.page['title']='关联笔记';self.page['content']+='\n[['+a['id']+']]';b=self.s.save_wiki(self.page);self.assertIn(a['id'],b['body']['links']);folder=sync_wiki(self.root,self.s);self.assertIn(a['id'],(folder/(b['id']+'.md')).read_text())
 def test_archived_source_blocks_approve(self):
  j=self.job();self.s.archive('source',self.source['id'])
  with self.assertRaises(Conflict):self.s.approve(j['id'])
 def test_archive_restore(self):
  a=self.s.save_wiki(self.page);self.s.archive('artifact',a['id']);self.assertTrue(self.s.artifact(a['id'])['archived']);self.s.archive('artifact',a['id'],False);self.assertFalse(self.s.artifact(a['id'])['archived'])
 def test_wiki_restore_title(self):
  a=self.s.save_wiki(self.page);old=self.s.versions(a['id'])[0];self.page['title']='新标题';self.s.save_wiki(self.page,a['id'],1);restored=self.s.restore(a['id'],old['id'],2);self.assertEqual(restored['title'],'知识整理')
 def test_key_file_private(self):
  with patch.dict(os.environ,{},clear=True):
   save_key(self.root,'test-not-a-real-secret');self.assertEqual(model_key(self.root),'test-not-a-real-secret');self.assertEqual((self.root/'.runtime/secrets/deepseek-key').stat().st_mode&0o777,0o600)
 def test_no_key_blocks_request(self):
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(ValueError):deepseek_request(self.root,{'model':'deepseek-flash'})
 def test_official_endpoint_fixed(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-unit-key'},clear=True),patch('urllib.request.urlopen') as open_url:
   deepseek_request(self.root,{'model':'deepseek-flash','thinking':{'type':'enabled'},'max_tokens':10000,'base_url':'https://attacker.example'})
   request=open_url.call_args[0][0];self.assertEqual(request.full_url,'https://api.deepseek.com/chat/completions');body=json.loads(request.data);self.assertEqual(body['thinking']['type'],'disabled');self.assertEqual(body['max_tokens'],6000)
 def test_user_draft_is_not_asset_until_saved(self):
  j=self.job();before=len(self.s.artifacts())
  self.s.update_job(j['id'],user_draft={'title':'手动修改标题','content':'## 我的学习笔记\n保留引用依据。'})
  self.assertEqual(len(self.s.artifacts()),before)
  saved=self.s.approve(j['id']);self.assertEqual(saved['title'],'手动修改标题');self.assertIn('我的学习笔记',saved['body']['content'])
