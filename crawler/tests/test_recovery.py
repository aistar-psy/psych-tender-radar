import json
import tempfile
import unittest
from pathlib import Path

from radar.recovery import recovery_queue, acquisition_state
from radar.paths import public_dir


class PublicLayoutTests(unittest.TestCase):
    def test_workspace_uses_publish_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'radar-workspace'
            root.mkdir()
            self.assertEqual(public_dir(root), root / 'publish')

    def test_published_crawler_uses_repository_web_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'crawler'
            root.mkdir()
            for name in ('index.html', 'app.js', 'fetch_public_notices.py'):
                (root.parent / name).write_text('')
            self.assertEqual(public_dir(root), root.parent)


class RecoveryTests(unittest.TestCase):
    def test_queue_uses_current_year_and_deduplicates_urls(self):
        def row(url, date='2026-09-01', quality='搜索线索待核验'):
            return {'sourceUrl': url, 'title': '某校心理设备采购', 'publishedAt': date, 'sourceQuality': quality}
        data = {'yearRange': {'start': '2025-09-10', 'end': '2026-09-09'}, 'archiveProjects': [
            row('https://example.org/a'), row('https://example.org/a?utm_source=x'),
            row('https://example.org/old', '2024-01-01'),
            row('https://example.org/acquired', quality='正文已取得')]}
        self.assertEqual([x['url'] for x in recovery_queue(data)], ['https://example.org/a'])

    def test_cache_miss_does_not_override_real_access_failure(self):
        state = acquisition_state({'status': 'failed', 'error_type': 'SSLError'}, {'status': 'not_in_cloud_batch'})
        self.assertEqual(state['code'], 'connection_failed')

    def test_downloaded_shell_is_not_a_successful_body(self):
        state = acquisition_state({'status': 'ok'}, {'status': 'content_unconfirmed'})
        self.assertEqual(state['code'], 'content_unavailable')

    def test_actual_verification_and_unattempted_are_distinct(self):
        self.assertEqual(acquisition_state({'status': 'failed', 'error_type': 'access_challenge'}, {})['code'], 'verification_required')
        self.assertEqual(acquisition_state({}, {})['code'], 'not_attempted')

    def test_body_success_supersedes_stale_failed_attempt(self):
        self.assertEqual(acquisition_state({'status': 'failed', 'error_type': 'HTTPError'}, {'status': 'ok'}, body_obtained=True)['code'], 'body_obtained')
