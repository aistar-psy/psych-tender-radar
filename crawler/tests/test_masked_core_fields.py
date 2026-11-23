import unittest
from radar.documents import parse_document

class MaskedCoreFieldsTests(unittest.TestCase):
    def test_masked_core_field_is_pending_even_without_login_banner(self):
        for label in ('项目编号', '招标编号', '预算金额', '采购内容'):
            raw = f'<article><h1>学校心理中心建设采购公告</h1><p>{label}：****</p><p>采购心理测评系统及培训服务。</p></article>'
            self.assertEqual(parse_document(raw.encode(), 'https://example.org/n.html')['content_status'], 'unavailable', label)

    def test_private_contact_redaction_keeps_real_purchase_body(self):
        raw = '<article><h1>学校心理中心建设采购公告</h1><p>项目编号：A2026-05</p><p>采购内容：心理测评系统2套。</p><p>预算金额：30万元</p><p>联系人：****</p></article>'
        self.assertEqual(parse_document(raw.encode(), 'https://example.org/n.html')['content_status'], 'available')

if __name__ == '__main__':
    unittest.main()
