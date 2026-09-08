import hashlib,json,tempfile,unittest
from pathlib import Path
from radar.cloud_replay import replay
class CloudReplayTests(unittest.TestCase):
 def test_unrecognized_page_remains_a_retriable_lead(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);body='<title>省政府采购网</title><div id="content">正在载入</div>'.encode();digest=hashlib.sha256(body).hexdigest();(root/'x.bin').write_bytes(body)
   (root/'manifest.json').write_text(json.dumps([{'url':'https://example.gov.cn/detail/a','status':'ok','content_type':'text/html','sha256':digest,'path':'x.bin'}]))
   result=replay(root/'manifest.json',root/'out');tasks=json.loads((Path(result['run_dir'])/'execution.json').read_text())
   self.assertEqual(tasks[0]['status'],'content_unconfirmed');self.assertGreater(result['pending_count'],0)
 def test_replay_preserves_fetch_provenance_and_missing_attachment_gap(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);body='<title>学校心理系统采购公告</title><article>采购人：某学校<p>发布时间：2026-09-07</p><p>预算金额：10万元</p><p>心理系统支持100人并发</p><a href="/a.docx">采购附件</a></article>'.encode()
   digest=hashlib.sha256(body).hexdigest();(root/'x.bin').write_bytes(body)
   (root/'manifest.json').write_text(json.dumps([{'url':'https://example.edu.cn/a','status':'ok','content_type':'text/html','sha256':digest,'path':'x.bin','read_at':'2026-09-07T08:00:00Z'}]))
   result=replay(root/'manifest.json',root/'out');docs=json.loads((Path(result['run_dir'])/'documents.json').read_text())
   self.assertEqual(len(docs),1);self.assertEqual(docs[0]['evidence'][0]['provider'],'github_public_fetch');self.assertEqual(docs[0]['attachments'][0]['status'],'not_in_cloud_batch')
 def test_hash_mismatch_is_failure_not_silent_import(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'x.bin').write_bytes(b'corrupt');(root/'manifest.json').write_text(json.dumps([{'url':'https://example.edu.cn/a','status':'ok','sha256':'no','path':'x.bin'}]));result=replay(root/'manifest.json',root/'out')
   self.assertEqual(result['processed_documents'],0)
