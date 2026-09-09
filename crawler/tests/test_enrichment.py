import unittest
from radar.enrichment import match_evidence, awarded_suppliers, purchase_time
class EnrichmentTests(unittest.TestCase):
 def test_updated_terms_and_real_location(self):
  hits=match_evidence('某学院设备采购',[{'text':'银龄心理融合实训室；心理仪器','locator':'table:2/row:1','source_url':'https://example.edu.cn/a.pdf'}],'https://example.edu.cn/notice')
  self.assertTrue(any(x['term']=='银龄心理' and x['field']=='正文' and x['url'].endswith('a.pdf') for x in hits))
  self.assertFalse(match_evidence('疾控中心理化所设备采购',[],'https://example.edu.cn'))
 def test_recipe_aliases_are_filterable(self):
  self.assertTrue(any(h['term']=='防霸凌' for h in match_evidence('学校防霸凌预警项目',[],'https://example.org/')))
  self.assertFalse(match_evidence('服务平台建设',[],'https://example.org/'))
 def test_award_is_not_buyer_or_bidder_qualification(self):
  rows=[{'text':'三、中标（成交）信息','locator':'p:1'},{'text':'供应商名称：北京飞宇星科技有限公司','locator':'p:2'},{'text':'四、主要标的信息','locator':'p:3'},{'text':'采购人信息 名称：国际关系学院','locator':'p:4'}]
  self.assertEqual(awarded_suppliers('心理实验室设备中标公告',rows,'https://example.edu.cn')[0]['name'],'北京飞宇星科技有限公司')
  self.assertEqual(awarded_suppliers('心理实验室设备招标公告',rows,'https://example.edu.cn'),[])
  self.assertEqual(awarded_suppliers('心理实验室中标候选人公示',rows,'https://example.edu.cn'),[])
 def test_intent_month_not_publication_date(self):
  rows=[{'kind':'table_row','text':'项目名称 | 预计采购时间 | 预算金额','locator':'table:1/row:1'},{'kind':'table_row','text':'心理平台 | 2026年09月 | 100','locator':'table:1/row:2'}]
  self.assertEqual(purchase_time(rows,'2026-07-31')['value'],'2026-09')
  self.assertEqual(purchase_time([],'2026-07-31')['label'],'公告发布')
