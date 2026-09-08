import gzip, importlib.util, io, time, unittest, zlib
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('cloud_worker',Path(__file__).resolve().parents[1]/'publish/fetch_public_notices.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)

class CompressedResponse(io.BytesIO):
 def __init__(self,body,encoding):
  super().__init__(body);self.headers={'Content-Encoding':encoding,'Content-Length':str(len(body))}

class CloudCompressionTests(unittest.TestCase):
 def test_ignoring_identity_negotiation_still_reads_gzip_and_deflate(self):
  original='<article>心理健康系统采购公告</article>'.encode()
  for body,encoding in [(gzip.compress(original),'gzip'),(zlib.compress(original),'deflate')]:
   self.assertEqual(worker.read_body(CompressedResponse(body,encoding),time.monotonic()+3),original)
 def test_decompression_size_limit_is_enforced(self):
  with patch.object(worker,'MAX_BODY_BYTES',1024):
   with self.assertRaises(worker.FetchFailure) as caught:
    worker.read_body(CompressedResponse(gzip.compress(b'x'*100000),'gzip'),time.monotonic()+3)
   self.assertEqual(caught.exception.category,'body_too_large')
 def test_truncated_compression_is_not_a_complete_body(self):
  body=gzip.compress(b'public procurement')[:-6]
  with self.assertRaises(worker.FetchFailure) as caught:
   worker.read_body(CompressedResponse(body,'gzip'),time.monotonic()+3)
  self.assertEqual(caught.exception.category,'incomplete_compressed_body')
