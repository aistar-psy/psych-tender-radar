import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.fetch_public_batch import run


class Response:
    status_code = 200
    def __init__(self, url, body):
        self.url, self.body = url, body
        self.headers = {'Content-Type': 'application/pdf', 'Content-Length': str(len(body))}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self): pass
    def iter_content(self, size):
        for start in range(0, len(self.body), size): yield self.body[start:start + size]


class Session:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs): return Response(url, self.body)


class PublicBatchTests(unittest.TestCase):
    def fetch(self, kind, size, declared=None):
        body = b'%PDF-1.7\n' + b'x' * (size - 9)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); queue = base / 'queue.json'
            queue.write_text(json.dumps([{'url': 'https://example.org/spec.pdf', 'kind': kind}]))
            session = Session(body)
            if declared is not None:
                response = Response('https://example.org/spec.pdf', body)
                response.headers['Content-Length'] = declared
                session.get = lambda *args, **kwargs: response
            with patch('scripts.fetch_public_batch.secure_session', return_value=session), patch('scripts.fetch_public_batch.time.sleep'):
                run(queue, base / 'out', workers=1)
            result = json.loads((base / 'out/manifest.json').read_text())[0]
            if result['status'] == 'ok':
                self.assertEqual((base / 'out' / result['path']).read_bytes(), body)
                self.assertEqual(result['sha256'], hashlib.sha256(body).hexdigest())
            return result

    def test_public_attachment_over_five_mb_is_saved_without_truncation(self):
        self.assertEqual(self.fetch('attachment', 6 * 1024 * 1024)['status'], 'ok')

    def test_notice_retains_five_mb_limit(self):
        result = self.fetch('document', 6 * 1024 * 1024)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'body_limit')

    def test_attachment_over_parser_limit_is_rejected(self):
        result = self.fetch('attachment', 30 * 1024 * 1024 + 1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'body_limit')

    def test_stream_limit_does_not_trust_an_understated_content_length(self):
        result = self.fetch('attachment', 30 * 1024 * 1024 + 1, declared='1')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'body_limit')
