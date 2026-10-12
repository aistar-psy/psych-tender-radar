import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from radar.web_export import write_run_history
from radar.enrichment import enrich


class PublicExportPrivacyTests(unittest.TestCase):
    def test_encoded_keys_html_links_and_nested_values_are_sanitized(self):
        from radar.public_safety import redact_public
        signed='https://example.gov.cn/a.pdf?id=7&amp;Access_Code=fixture-secret'
        value={'url':signed,'nested':[{'text':'附件 '+signed},3,None]}
        result=redact_public(value)
        self.assertNotIn('fixture-secret',json.dumps(result))
        self.assertEqual(result['nested'][1:],[3,None])
        self.assertIn('fixture-secret',value['url'])

    def test_ordinary_search_parameters_and_body_text_are_preserved(self):
        from radar.public_safety import redact_public
        value={'url':'https://example.gov.cn/a?id=7&keyword=心理&categoryNum=014', 'text':'心理设备采购要求'}
        self.assertEqual(redact_public(value),value)

    def test_url_user_credentials_are_not_published(self):
        from radar.public_safety import redact_public
        self.assertEqual(redact_public('https://name:fixture-secret@example.org/a'), '')

    def test_history_keeps_public_notice_links_but_removes_access_parameters(self):
        secret='fixture-private-download-code'
        public='https://example.gov.cn/notice?id=42&categoryNum=014005001'
        protected='https://example.gov.cn/file.pdf?%61ccessCode='+secret
        projects=[{'sourceUrl':public,'fullTexts':[{'url':protected}], 'parameters':[{'text':'下载 '+protected}]}]
        with tempfile.TemporaryDirectory() as tmp:
            data={'defaultRunId':'current','runs':[{'id':'old','projects':projects}]}
            write_run_history(data,Path(tmp))
            text=(Path(tmp)/data['runs'][0]['projectsRef']).read_text()
            self.assertNotIn(secret,text)
            self.assertEqual(json.loads(text)[0]['sourceUrl'],public)

    def test_saved_body_does_not_publish_signed_download_url(self):
        secret='fixture-private-signature'
        source='https://example.gov.cn/notice?id=42'
        signed='https://example.gov.cn/spec.pdf?X-Amz-Signature='+secret
        part={'title':'心理设备采购需求','url':signed,'readAt':'2026-10-12','sha256':'fixture',
              'kind':'公开附件','text':'采购参数：心理测评设备一套。下载地址 '+signed,
              'blocks':[{'text':'心理测评设备一套。','locator':'pdf/page:1','source_url':signed}]}
        project={'sourceUrl':source,'title':'心理设备采购','sourceQuality':'正文已取得','events':[]}
        doc={'url':source,'analysis':{'title':'心理设备采购'},'evidence':[]}
        with tempfile.TemporaryDirectory() as tmp, patch('radar.enrichment.document_parts',return_value=[part]):
            enrich([project],[doc],Path(tmp))
            text=(Path(tmp)/project['fullTexts'][0]['path']).read_text()
            self.assertNotIn(secret,text)
            self.assertIn('心理测评设备一套',text)
