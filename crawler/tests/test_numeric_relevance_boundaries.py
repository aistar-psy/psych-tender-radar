import unittest
from radar.relevance import assess_relevance
from radar.web_export import public_run

class EvidenceBoundaryTests(unittest.TestCase):
    def test_hotline_digits_inside_a_price_are_not_psychology(self):
        for value in ('1235600.00', '12356.2', '12356元', '123550元'):
            r = assess_relevance('生物样本测序服务结果公告', [{'text': '成交金额：'+value}], body_available=True)
            self.assertEqual(r['status'], 'review_required', value)
        r = assess_relevance('12356热线服务项目', [{'text': '提供12356热线咨询服务。'}], body_available=True)
        self.assertEqual(r['status'], 'related')

    def test_chemical_laboratory_and_truncated_center_heading_are_not_psychology(self):
        title = '公安司法鉴定中心理化实验室扩建项目'
        r = assess_relevance(title, [{'text': '采购化学分析仪器。'}, {'text': '公安司法鉴定中心理'}], body_available=True)
        self.assertEqual(r['status'], 'review_required')
        r = assess_relevance('学校心理咨询中心理化设备及心理测评平台采购', [{'text': '采购心理测评平台。'}], body_available=True)
        self.assertEqual(r['status'], 'related')

    def test_explicit_school_mixed_rooms_do_not_sum_whole_contract(self):
        title = '聚奎中学录播室、理化生科技室、美术室、心理咨询室设施设备采购中标结果公告'
        d = {'project_id': 'p', 'url': 'https://example.org/n',
             'analysis': {'title': title, 'category': '教育核心', 'amounts': [{'type': '成交', 'value': 14700}]}}
        p = public_run({'run_id':'test'}, [d], [])['projects'][0]
        self.assertFalse(p['amountEligible'])

if __name__ == '__main__':
    unittest.main()
