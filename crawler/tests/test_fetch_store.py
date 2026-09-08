import tempfile, threading, unittest
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
try:
 from radar.fetch import Fetcher, FetchError
 from radar.store import Store
except ImportError:
 Fetcher = Store = None
 FetchError = Exception

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  if self.path=='/blocked': self.send_response(403);self.end_headers();return
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
  self.wfile.write(b'x'*4096 if self.path=='/large' else '<html>心理健康采购</html>'.encode())

class FetchStoreTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.url='http://127.0.0.1:'+str(cls.server.server_port)
 @classmethod
 def tearDownClass(cls): cls.server.shutdown();cls.server.server_close()
 def test_fetch_preserves_raw_bytes_and_classifies_block(self):
  self.assertIsNotNone(Fetcher,'Fetcher must exist')
  f=Fetcher(interval=0,max_bytes=1024)
  self.assertIn('心理'.encode(),f(self.url+'/ok')['body'])
  with self.assertRaises(FetchError) as ctx:f(self.url+'/blocked')
  self.assertEqual(ctx.exception.kind,'blocked')
 def test_size_limit_does_not_silently_truncate(self):
  self.assertIsNotNone(Fetcher)
  with self.assertRaises(FetchError) as ctx:Fetcher(interval=0,max_bytes=1024)(self.url+'/large')
  self.assertEqual(ctx.exception.kind,'too_large')
 def test_versions_preserved_and_repeated_import_not_new_project(self):
  self.assertIsNotNone(Store)
  with tempfile.TemporaryDirectory() as t:
   s=Store(Path(t)/'radar.db')
   d={'title':'某校心理系统','project_number':'X-2026-001','buyer':'某校','category':'教育核心'}
   p=s.save_document(self.url+'/notice',d,'hash1','run1')
   self.assertEqual(p,s.save_document(self.url+'/notice',d,'hash1','run2'))
   self.assertEqual(p,s.save_document(self.url+'/notice',d,'hash2','run3'))
   self.assertEqual(s.counts()['projects'],1)
   self.assertEqual(s.counts()['versions'],2)
   s.close()
 def test_backlog_success_resolves_without_deleting_history(self):
  self.assertIsNotNone(Store)
  with tempfile.TemporaryDirectory() as t:
   s=Store(Path(t)/'radar.db');s.backlog('u','attachment','403')
   s.backlog('u','attachment','403');self.assertEqual(s.pending()[0]['attempts'],2)
   s.resolve('u');self.assertEqual(s.pending(),[]);s.close()
