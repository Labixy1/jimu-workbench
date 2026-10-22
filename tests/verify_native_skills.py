"""Run against a local OpenCode engine with a scripted local model, not DeepSeek.

Usage: python3 tests/verify_native_skills.py [--engine-port 4098]
The temporary workspace, model server and OpenCode sessions are disposed afterward.
"""
import argparse
import base64
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import OpenCode
from domain import Store
import task_skills


class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(request)
        index=len(self.server.requests)
        tools={t['function']['name']:t['function'] for t in request.get('tools',[])}
        if index==1:
            name='skill'
            parameters=tools[name]['parameters'].get('properties',{})
            arguments={'id' if 'id' in parameters else 'name':'native-skill-probe'}
        elif index==2:
            name='read';arguments={'filePath':self.server.reference}
        else:
            name=None
        result={'role':'assistant','content':'NATIVE_SKILL_FIXTURE_OK' if name is None else None}
        if name:result['tool_calls']=[{'id':'call_probe_'+str(index),'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]
        finish='tool_calls' if name else 'stop'
        if request.get('stream'):
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            if name:result['tool_calls'][0]['index']=0
            chunks=[{'choices':[{'index':0,'delta':result,'finish_reason':None}]},
                    {'choices':[{'index':0,'delta':{},'finish_reason':finish}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}]
            for chunk in chunks:
                chunk.update(id='chatcmpl-native-skill',object='chat.completion.chunk',created=int(time.time()),model='fixture')
                self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
        else:
            value={'id':'chatcmpl-native-skill','object':'chat.completion','model':'fixture','choices':[{'index':0,'message':result,'finish_reason':finish}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
            raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


def verify(port):
    with tempfile.TemporaryDirectory(prefix='jimu-native-skill-') as folder:
        root=Path(folder);store=Store(root/'db');task_skills.init(store)
        skill=task_skills.save(store,{'skill_md':'---\nname: native-skill-probe\ndescription: Use to verify the local Skill loading pipeline.\n---\n\n# Native skill probe\nSKILL_BODY_ONLY_AFTER_LOAD\nRead references/check.md.\n',
            'resources':[{'path':'references/check.md','content':base64.b64encode(b'RESOURCE_ONLY_AFTER_READ').decode()}]})
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);server.requests=[]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        engine=OpenCode('http://127.0.0.1:'+str(port),(ROOT/'.runtime/engine-password').read_text().strip(),root/'workspace')
        session=None
        try:
            model=engine.configure('model','http://127.0.0.1:'+str(server.server_port)+'/v1','fixture',False,[skill],'probe')
            server.reference=str(engine.skill_root/'native-skill-probe/references/check.md')
            discovered=engine.call('/skill')
            assert any(s['name']=='native-skill-probe' for s in discovered), 'Native discovery did not find the package'
            session=engine.create('workbench',model)
            answer=engine.prompt(session,'Verify the Skill pipeline with native-skill-probe, then read its reference.','workbench',model)
            assert answer=='NATIVE_SKILL_FIXTURE_OK',answer
            assert len(server.requests)==3,len(server.requests)
            initial=json.dumps(server.requests[0])
            second=json.dumps(server.requests[1]);third=json.dumps(server.requests[2])
            assert 'native-skill-probe' in initial
            assert 'SKILL_BODY_ONLY_AFTER_LOAD' not in initial
            assert 'RESOURCE_ONLY_AFTER_READ' not in initial
            assert 'SKILL_BODY_ONLY_AFTER_LOAD' in second
            assert 'RESOURCE_ONLY_AFTER_READ' not in second
            assert 'RESOURCE_ONLY_AFTER_READ' in third
            names=[t['function']['name'] for t in server.requests[0].get('tools',[])]
            assert 'bash' not in names and 'write' not in names,names
            assert all(t['status']=='completed' for t in engine.last_tools),engine.last_tools
            result={'test_type':'scripted_local_model_with_real_opencode_tools','model_calls':3,'paid_api_calls':0,
                    'discovery':True,'progressive_skill_load':True,'progressive_resource_read':True,'no_shell_or_write_tools':True,
                    'tools':engine.last_tools}
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return result
        finally:
            if session:
                try:engine.call('/session/'+session,method='DELETE',timeout=10)
                except Exception:pass
            try:engine.call('/instance/dispose',{},timeout=10)
            except Exception:pass
            server.shutdown();server.server_close();store.db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--engine-port',type=int,default=4098)
    verify(parser.parse_args().engine_port)
