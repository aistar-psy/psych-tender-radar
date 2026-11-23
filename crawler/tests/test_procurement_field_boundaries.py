import unittest
from radar.analysis import analyze_document
from radar.web_export import public_run, merge_project

class ProcurementFieldsTests(unittest.TestCase):
    def test_complete_chinese_bracket_project_id(self):
        doc = {'title': '医院心理健康管理服务采购公告', 'text': '项目编号：西交二院信网2026【46】'}
        self.assertEqual(analyze_document(doc, 'https://example.org/n', '2026-11-23T09:00:00+08:00')['project_number'], '西交二院信网2026【46】')

    def test_terminated_notice_stops_amount_aggregation(self):
        url = 'https://example.org/n'
        d = {'project_id': 'p', 'url': url, 'analysis': {
            'title': '学校心理设备采购项目废标公告', 'notice_type': '废标公告', 'category': '教育核心',
            'amounts': [{'type': '预算', 'value': 322809, 'currency': 'CNY'}]}}
        p = public_run({'run_id': 'test'}, [d], [])['projects'][0]
        self.assertFalse(p['amountEligible'])
        older = {'title': '心理设备采购项目结果公告', 'publishedAt': '2026-11-15',
                 'amountEligible': True, 'amounts': [{'type': '成交', 'value': 100000}],
                 'events': [{'type': '成交公告', 'title': '心理设备采购项目结果公告'}]}
        latest = {'title': '心理设备采购项目废标公告', 'publishedAt': '2026-11-16',
                  'amountEligible': True, 'events': [{'type': '废标公告'}]}
        self.assertFalse(merge_project(latest, older)['amountEligible'])

if __name__ == '__main__':
    unittest.main()
