import unittest
from radar.enrichment import match_evidence, awarded_suppliers, purchase_time
class EnrichmentTests(unittest.TestCase):
 def test_contract_supplier_and_signing_date_are_explicit(self):
  rows=[{'text':'供应商(乙方)：某心理健康服务协会','locator':'p:1'}, {'text':'合同签订日期','locator':'p:2'}, {'text':'2024年11月25日','locator':'p:3'}]
  found=awarded_suppliers('学校心理服务中心政府采购合同公告',rows,'https://example.org')
  self.assertEqual(found[0]['name'],'某心理健康服务协会')
  self.assertEqual(found[0]['role'],'合同供应商')
  self.assertEqual(purchase_time(rows,'2026-09-07'),{'value':'2024-11-25','label':'合同签订'})

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


class FullTextEvidenceTests(unittest.TestCase):
 def test_access_pages_and_scan_watermarks_are_not_exported_as_full_text(self):
  from unittest.mock import patch
  from radar.enrichment import document_parts
  samples=[('请输入验证码下载附件','text/html'),('用户登录\n获取短信验证码','text/html'),('千 里 马 提 示\n很抱歉，此功能只支持付费用户。 我要了解收费服务>>','text/html'),('扫描全能王 创建\n扫描全能王 创建','application/pdf'),('1\n2\n3','application/pdf'),('copryright ©️ 采购与招标网 2016','text/html')]
  for text,ct in samples:
   with self.subTest(text=text),patch('radar.enrichment.parsed_evidence',return_value={'status':'ok','text':text,'blocks':[{'text':text}]}):
    d={'url':'https://e/a','analysis':{'title':'心理设备采购'},'evidence':[{'path':'unused','content_type':ct}]}
    self.assertEqual(document_parts(d),[])

 def test_short_real_requirement_is_retained(self):
  from unittest.mock import patch
  from radar.enrichment import document_parts
  text='采购需求：运动心理多模态数据采集分析平台，数量1套。'
  with patch('radar.enrichment.parsed_evidence',return_value={'status':'ok','text':text,'blocks':[{'text':text}]}):
   d={'url':'https://e/a','analysis':{'title':'心理设备采购'},'evidence':[{'path':'unused','content_type':'application/pdf'}]}
   self.assertEqual(document_parts(d)[0]['text'],text)


class WinnerEvidenceTests(unittest.TestCase):
 def test_ranked_bidders_are_not_all_winners(self):
  rows=[{'text':'供应商名称 | 最终报价 | 排序','kind':'table_row','locator':'html/table:1/row:1'},{'text':'重庆玖立科技有限公司 | 709722 | 1','kind':'table_row','locator':'html/table:1/row:2'},{'text':'重庆臻颠商贸有限公司 | 717619 | 2','kind':'table_row','locator':'html/table:1/row:3'},{'text':'供应商名称：','locator':'line:1'},{'text':'重庆玖立科技有限公司','locator':'line:2'}]
  found=awarded_suppliers('心理设备中标（成交）结果公告',rows,'https://e/a')
  self.assertEqual([r['name'] for r in found],['重庆玖立科技有限公司'])
  self.assertEqual(awarded_suppliers('心理设备中标结果公告',rows[:3],'https://e/a'),[])

 def test_procurement_result_award_table_identifies_supplier(self):
  rows=[{'text':'供应商名称 | 供应商地址 | 中标（成交）金额 | 评审总得分','kind':'table_row','locator':'html/table:1/row:1'},{'text':'中国电信股份有限公司延安分公司 | 延安市 | 350000元 | 90.81','kind':'table_row','locator':'html/table:1/row:2'}]
  self.assertEqual(awarded_suppliers('富县心理健康信息化管理平台采购项目采购结果公告',rows,'https://e/a')[0]['name'],'中国电信股份有限公司延安分公司')
