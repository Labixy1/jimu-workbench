import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import OpenCode


class PortTests(unittest.TestCase):
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
