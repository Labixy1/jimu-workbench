import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import OpenCode


class PortTests(unittest.TestCase):
    def test_structured_tasks_cannot_launch_connected_browser_or_file_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=OpenCode('http://127.0.0.1:4098','fixture-token',directory)
            mcp={'browser_use':{'type':'local','command':['fixture-mcp'],'enabled':True}}
            with patch('mcp_connections.config',return_value=mcp),patch.object(engine,'call',return_value=None):
                engine.configure('fixture',model='fixture',allow_connectors=False)
            config=json.loads((Path(directory)/'opencode.json').read_text())
            self.assertTrue(config['mcp']['browser_use']['enabled'])
            for agent in config['agent'].values():
                self.assertEqual(agent['permission'],{'*':'deny'})
                self.assertFalse(agent['tools']['read'])
                self.assertFalse(agent['tools']['browser_use_*'])
            reply={'parts':[{'type':'text','text':'fixture response'}]}
            with patch('mcp_connections.config',return_value=mcp),patch.object(engine,'call',side_effect=[reply,[]]) as call:
                engine.prompt('ses_fixture','fixture task','workbench',{'providerID':'fixture','modelID':'fixture'})
            body=call.call_args_list[0].args[1]
            self.assertFalse(body['tools']['read'])
            self.assertFalse(body['tools']['browser_use_*'])

    def test_gateway_tracks_selected_port_without_remote_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=OpenCode('http://127.0.0.1:4098','local-test-token',directory,
                            gateway_url='http://127.0.0.1:8769/')
            with patch.object(engine,'call',return_value=None):
                for mode,suffix in [('fixture','/fixture/v1'),('deepseek','/model/v1')]:
                    engine.configure(mode,model='local-test-model')
                    config=json.loads((Path(directory)/'opencode.json').read_text())
                    provider=next(iter(config['provider'].values()))
                    self.assertEqual(provider['options']['baseURL'],'http://127.0.0.1:8769'+suffix)
                engine.configure('model','https://provider.example/v1/',model='local-test-model')
                config=json.loads((Path(directory)/'opencode.json').read_text())
                self.assertEqual(config['provider']['wbmodel']['options']['baseURL'],'https://provider.example/v1')
