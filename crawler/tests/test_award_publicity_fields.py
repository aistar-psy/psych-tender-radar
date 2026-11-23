import unittest
from radar.analysis import analyze_document
from radar.enrichment import awarded_suppliers

class AwardPublicityTests(unittest.TestCase):
    def test_standard_result_publicity_with_explicit_award_fields(self):
        title = '丰城市学生心理测评服务采购项目结果公示'
        blocks = [{'text': '三、中标（成交）信息', 'kind':'paragraph'},
                  {'text': '供应商名称：江西政通数字经济技术有限公司', 'kind':'paragraph'},
                  {'text': '中标（成交）金额（元）：948000.00', 'kind':'paragraph'},
                  {'text': '中标通知书.pdf', 'kind':'paragraph'}]
        a = analyze_document({'title': title, 'blocks': blocks}, 'https://example.org/result', '2026-11-23T09:00:00+08:00')
        self.assertEqual(a['notice_type'], '成交结果公告')
        suppliers = awarded_suppliers(title, blocks, 'https://example.org/result')
        self.assertEqual([s['name'] for s in suppliers], ['江西政通数字经济技术有限公司'])
        self.assertEqual(awarded_suppliers(title.replace('结果公示','候选结果公示'), blocks, 'https://example.org/result'), [])

if __name__ == '__main__':
    unittest.main()
