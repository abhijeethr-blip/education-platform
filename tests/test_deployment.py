import json
import sys
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler

class DeploymentTests(unittest.TestCase):
    def test_provider_config_and_container(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('healthCheckPath', (root/'render.yaml').read_text())
        self.assertIn('healthcheckPath', (root/'railway.json').read_text())
        self.assertIn('USER appuser', (root/'Dockerfile').read_text())

    def test_http_smoke(self):
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        t=Thread(target=httpd.serve_forever,daemon=True)
        t.start()
        try:
            with urlopen(f'http://127.0.0.1:{httpd.server_port}/health',timeout=5) as r:
                self.assertEqual(json.load(r),{'status':'ok'})
            with urlopen(f'http://127.0.0.1:{httpd.server_port}/',timeout=5) as r:
                self.assertEqual(r.status,200)
                self.assertIn(b'html',r.read(200).lower())
        finally:
            httpd.shutdown()
            httpd.server_close()
