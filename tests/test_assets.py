import base64,io,zipfile,unittest
import test_api
from asset_files import parse
class AssetTests(unittest.TestCase):
 setUp=test_api.ApiTests.setUp
 tearDown=test_api.ApiTests.tearDown
 request=test_api.ApiTests.request
 def upload(self,name,raw):
  return self.request('/api/assets/import',{'name':name,'base64':base64.b64encode(raw).decode(),'category':'record'})
 def test_board_import_preview_asset(self):
  import json
  status,r=self.upload('Board.excalidraw',json.dumps({'elements':[],'appState':{}}).encode())
  self.assertEqual(status,200)
  self.assertEqual(r['artifact']['kind'],'board')
  self.assertEqual(r['artifact']['body']['scene']['elements'],[])
 def test_text_import_metadata_and_file(self):
  status,r=self.upload('记录.txt','虚构示例，本人负责整理记录，未确认上线效果。'.encode());self.assertEqual(status,200)
  sid=r['source']['id'];state=self.request('/api/state')[1];self.assertEqual(state['asset_meta'][sid]['extension'],'.txt')
  self.assertEqual(self.request('/api/assets/meta',{'id':sid,'category':'record','favorite':True})[0],200)
  self.assertEqual(self.request('/api/state')[1]['asset_meta'][sid]['favorite'],1)
 def test_html_never_contains_scripts(self):
  self.assertEqual(parse(b'<h1>Header</h1><script>steal()</script><iframe>hidden</iframe><p>Body</p>','.html').strip(),'Header\n\nBody')
 def test_html_head_is_not_reading_content(self):
  self.assertEqual(parse(b'<head><title>Not body</title><style>hidden</style></head><p>Readable</p>','.html'),'Readable')
 def test_docx_extracts_paragraphs(self):
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>明确标注的虚构内容</w:t></w:r></w:p></w:body></w:document>')
  self.assertIn('虚构内容',parse(buffer.getvalue(),'.docx'))
 def test_unsupported_and_empty_rejected(self):
  self.assertEqual(self.upload('run.exe',b'MZbinary')[0],200)
  self.assertEqual(self.upload('empty.txt',b' ')[0],400)
  self.assertEqual(len(self.app.store.sources()),1)
 def test_note_quote_guard_and_readback(self):
  sid=self.upload('note.txt','文章原句：工具成功不等于业务成功。'.encode())[1]['source']['id']
  self.assertEqual(self.request('/api/notes',{'kind':'source','id':sid,'quote':'不存在的句子','text':'我的理解'})[0],400)
  self.assertEqual(self.request('/api/notes',{'kind':'source','id':sid,'quote':'工具成功不等于业务成功','text':'我的理解'})[0],200)
  self.assertEqual(len(self.request('/api/notes?kind=source&id='+sid)[1]),1)
 def test_notes_not_knowledge_or_model_claims(self):
  page=self.app.store.save_wiki({'title':'个人理解','summary':'手动','content':'## 理解\n先检查事实，再验证业务效果。','tags':[]})
  self.assertEqual(self.request('/api/notes',{'kind':'wiki','id':page['id'],'text':'明天继续阅读'})[0],200)
  self.assertEqual(page['revision'],1)
 def test_demo_does_not_fall_back_to_personal_space(self):
  self.assertEqual(self.request('/api/state?space=demo')[0],400)
 def test_asset_meta_rejects_unknown_category(self):
  sid=self.upload('note.txt','示例正文记录。'.encode())[1]['source']['id']
  self.assertEqual(self.request('/api/assets/meta',{'id':sid,'category':'unknown'})[0],400)
 def test_original_download_is_unchanged(self):
  import urllib.request
  raw='示例正文，原始附件应保持不变。'.encode();sid=self.upload('original.txt',raw)[1]['source']['id']
  with urllib.request.urlopen(self.url+'/api/assets/'+sid+'/file') as response:
   self.assertEqual(response.read(),raw)
   self.assertIn('attachment',response.headers['Content-Disposition'])
 def test_file_routes_reject_wrong_type_and_invalid_page(self):
  sid=self.upload('note.txt','只有文字的示例记录。'.encode())[1]['source']['id']
  self.assertEqual(self.request('/api/assets/'+sid+'/info')[0],400)
  self.assertEqual(self.request('/api/assets/'+sid+'/page/0')[0],400)
 def test_demo_space_has_independent_notes_and_sources(self):
  from server import App
  from pathlib import Path
  demo=App(Path(self.tmp.name)/'demo',None);demo.credential_root=self.app.root
  self.server.demo_app=demo
  try:
   sid=self.request('/api/assets/import?space=demo',{'name':'demo.txt','base64':base64.b64encode('独立的虚构示例内容。'.encode()).decode(),'category':'article'})[1]['source']['id']
   self.assertEqual(self.request('/api/notes?space=demo',{'kind':'source','id':sid,'text':'示例笔记'})[0],200)
   self.assertEqual(self.request('/api/state')[1]['sources'],[])
   self.assertEqual(self.request('/api/notes?kind=source&id='+sid)[1],[])
   self.assertEqual(self.request('/api/model/key?space=demo',{'key':'not-a-real-key'})[0],400)
  finally:demo.store.db.close()
