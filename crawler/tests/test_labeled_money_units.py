import unittest
from radar.analysis import analyze_document

class LabeledMoneyUnitTests(unittest.TestCase):
    def parse(self, text):
        blocks = [{'text':x,'kind':'paragraph','locator':f'line:{i}'} for i,x in enumerate(text.splitlines())]
        d = analyze_document({'title':'学校心理服务采购项目结果公示','blocks':blocks}, 'https://example.org/n', '2026-11-23T09:00:00+08:00')
        return [(x['type'], x['value']) for x in d['amounts']]

    def test_unit_before_value_and_explicit_total_price_type(self):
        self.assertEqual(self.parse('中标类型：总价中标\n中标（成交）金额（元）\\（%）：948000.00'), [('成交',948000)])
        self.assertEqual(self.parse('预算金额（万元）：32'), [('预算',320000)])

    def test_rate_and_conflicting_currency_labels_stay_unconfirmed(self):
        for text in ('中标（成交）金额（元）\\（%）：95.00',
                     '中标类型：费率中标\n中标（成交）金额（元）\\（%）：95.00',
                     '预算金额（元/人）：100',
                     '预算金额（万元）：32元'):
            self.assertEqual(self.parse(text), [], text)

if __name__ == '__main__':
    unittest.main()
