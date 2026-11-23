import unittest
from radar.candidate_urls import is_listing_url
from radar.public_safety import public_project_exclusion
from radar.relevance import assess_relevance

class WeeklyRelevanceTests(unittest.TestCase):
    def test_mental_health_department_lift_is_general_facility(self):
        title = '杨凌示范区医院精神心理科电梯更换采购项目合同公告'
        blocks = [{'text': '采购标的：精神心理科电梯更换，1台。', 'locator': 'row:1'}]
        self.assertEqual(assess_relevance(title, blocks, body_available=True)['status'], 'review_required')
        blocks.append({'text': '另采购心理健康评估软件1套。', 'locator': 'row:2'})
        self.assertEqual(assess_relevance(title, blocks, body_available=True)['status'], 'related')

    def test_policy_application_roundup_is_not_a_market_project(self):
        p = {'sourceUrl': 'https://shanghai.jianyu360.cn/jybx/20260801_26073174425932.html',
             'title': '【招标信用】【政策通报】2026年近期申报项目汇总（截止7月31日）'}
        self.assertIsNotNone(public_project_exclusion(p))
        p['title'] = '学校心理健康教育项目采购公告'
        self.assertIsNone(public_project_exclusion(p))

    def test_observed_date_and_trading_search_routes_are_discovery_only(self):
        self.assertTrue(is_listing_url('https://1301.bidcenter.com.cn/datelist-2026-11-9-1-2.html'))
        self.assertTrue(is_listing_url('https://ss.ebnew.com/tradingSearch/index.htm?key=心理'))
        self.assertFalse(is_listing_url('https://www.ebnew.com/businessShow/710779365.html'))
        self.assertFalse(is_listing_url('https://example.edu.cn/datelist-2026-11-9-1-2.html'))

if __name__ == '__main__':
    unittest.main()
