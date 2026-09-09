import unittest
from radar.analysis import analyze_document


def analyze(text):
    doc={'title':'公告','text':text,'blocks':[{'text':line,'locator':f'line:{i}','kind':'paragraph'} for i,line in enumerate(text.splitlines(),1)],'warnings':[],'status':'ok'}
    return analyze_document(doc,'https://e/a','2026-09-07T12:00:00+08:00')


class AnalysisTests(unittest.TestCase):
    def test_chongqing_project_number_and_title_notice_type(self):
        d={'title':'学校心理设备询价公告','text':'项目号：\nFDX26A00518\n预算金额：721,669.00元\n如发布更正公告，以更正为准。'}
        a=analyze_document(d,'https://e/a','2026-09-09T12:00:00+08:00')
        self.assertEqual(a['project_number'],'FDX26A00518')
        self.assertEqual(a['notice_type'],'询价公告')

    def test_contract_amount_has_its_own_scope(self):
        a=analyze('某学校心理服务中心工程政府采购合同公告\n合同金额：576,500.00元')
        self.assertEqual(a['notice_type'],'合同公告')
        self.assertEqual([(v['type'],v['value']) for v in a['amounts']],[('合同',576500)])

    def test_award_publication_variant_is_procurement(self):
        self.assertTrue(analyze('某医院心理测评系统项目中标公示\n中标人：某科技公司\n中标价格：5.45万元')['is_procurement'])

    def test_numeric_support_group_cannot_be_buyer(self):
        result=analyze('采购人:498912314\n采购人信息\n名称：某市第一中学\n地址：某市')
        self.assertEqual(result['buyer'],'某市第一中学')
        self.assertEqual(result['buyer_evidence']['url'],'https://e/a')
        self.assertTrue(result['buyer_evidence']['locator'])
        self.assertIsNone(analyze('QQ服务群(工作日)\n采购人:498912314')['buyer'])
        self.assertEqual(analyze('1.采购人（甲方）：洛阳市第五人民医院')['buyer'],'洛阳市第五人民医院')

    def test_buyer_horizontal_table_uses_named_column(self):
        doc={'title':'采购意向','blocks':[{'text':'序号 | 采购单位名称 | 采购项目名称','kind':'table_row','locator':'html/table:1/row:1'}, {'text':'1 | 济源职业技术学院 | 心理健康中心设备采购项目','kind':'table_row','locator':'html/table:1/row:2'}]}
        result=analyze_document(doc,'https://e/a','2026-09-07T12:00:00+08:00')
        self.assertEqual(result['buyer'],'济源职业技术学院')
        self.assertEqual(result['buyer_evidence']['locator'],'html/table:1/row:2')

    def test_results_and_procurement_publicity_are_recognized(self):
        for wording in ('青少年心理健康教育辅导活动中标（成交）结果公告','心理咨询室采购中标（成交）明细','心理设备成交结果公告','工程项目采购信息公告\n根据学校采购流程，现进行采购公示'):
            self.assertTrue(analyze(wording)['is_procurement'],wording)
        self.assertTrue(analyze('学校心理教育咨询服务项目市场比选公告\n供应商资格要求：符合政府采购法。\n报价文件递交')['is_procurement'])
        self.assertFalse(analyze('学校活动方案比选公告\n同学自愿参加')['is_procurement'])

    def test_unavailable_body_is_unknown_even_with_procurement_title(self):
        doc={'title':'学校心理设备采购公告','text':'发布时间：2026-09-01','status':'partial','content_status':'unavailable'}
        result=analyze_document(doc,'https://e/a','2026-09-07T12:00:00+08:00')
        self.assertIsNone(result['is_procurement'])
        self.assertTrue(result['procurement_hint'])

    def test_categories_use_purchase_context(self):
        for text, expected in [
            ('大数据中心采购校园心理健康教育平台','教育核心'),
            ('儿童医院采购儿童心理诊疗设备','其他心理'),
            ('心理病房采购普通椅、轮椅','排除'),
            ('学生健康画像大数据平台','待核验'),
            ('学校采购心理咨询室设备','教育核心'),
            ('教育局教师心理健康培训','教育相关'),
        ]:
            with self.subTest(text=text): self.assertEqual(analyze(text)['category'],expected)

    def test_evidence_metadata_and_separate_amounts(self):
        result=analyze('项目编号：ABC-2026-01\n发布时间：2026年9月1日\n响应文件提交截止时间：2026年9月10日 09:30\n预算金额：20万元；最高限价：180000元；成交金额：17.5万元\n心理测评系统：并发用户≥100，数量2套')
        self.assertEqual(result['project_number'],'ABC-2026-01')
        self.assertEqual(result['published_at'],'2026-09-01')
        self.assertEqual(result['deadline'],'2026-09-10T09:30:00+08:00')
        self.assertEqual({x['type']:x['value'] for x in result['amounts']},{'预算':200000,'限价':180000,'成交':175000})
        self.assertTrue(result['products']); self.assertTrue(result['parameters'])
        self.assertTrue(all(x['locator'] and x['url']=='https://e/a' for x in result['parameters']))

    def test_missing_metadata_is_not_inferred(self):
        result=analyze('校园心理测评系统\n2025-01-01 联系电话 12345678')
        self.assertIsNone(result['published_at']); self.assertIsNone(result['deadline'])
        self.assertEqual(result['amounts'],[]); self.assertEqual(result['parameters'],[])

    def test_invalid_dates_and_ambiguous_money_are_not_facts(self):
        result=analyze('发布日期：2026-02-30\n预算金额：20\n文件售价：500元')
        self.assertIsNone(result['published_at']); self.assertEqual(result['amounts'],[])

    def test_buyer_and_notice_type_keep_explicit_evidence(self):
        result=analyze('采购人：某市教育局\n校园心理测评平台更正公告')
        self.assertEqual(result['buyer'],'某市教育局')
        self.assertEqual(result['notice_type'],'更正公告')

    def test_attachment_sources_are_preserved_for_every_candidate(self):
        doc={'title':'校园心理采购','text':'心理测评系统：并发≥100，预算金额：2万元','blocks':[{'text':'心理测评系统：并发≥100，预算金额：2万元','locator':'pdf/page:1','kind':'page','source_url':'https://e/file.pdf'}]}
        result=analyze_document(doc,'https://e/notice','2026-09-07T12:00:00+08:00')
        for key in ('category_evidence','products','parameters','amounts'):
            self.assertTrue(result[key])
            self.assertTrue(all(x['url']=='https://e/file.pdf' for x in result[key]))

    def test_chinese_clock_and_response_deadline_context(self):
        result=analyze('校园心理采购\n获取采购文件截止时间：2026年09月02日09点30分\n响应文件提交截止时间：2026年09月07日09点30分')
        self.assertEqual(result['deadline'],'2026-09-07T09:30:00+08:00')
        self.assertIsNone(analyze('获取文件截止时间：2026-09-02 09:30')['deadline'])
        self.assertEqual(analyze('提交响应文件\n截止时间：2026年09月07日09点30分')['deadline'],'2026-09-07T09:30:00+08:00')

    def test_fulfillment_parameters_use_psych_purchase_context(self):
        result=analyze('校园心理测评系统采购\n部署期限：合同签订后30日\n云服务≥1年\n软件服务≥3年\n联系电话：12345678\n公告编号：20260907')
        parameters='\n'.join(p['text'] for p in result['parameters'])
        for expected in ('部署期限','云服务≥1年','软件服务≥3年'): self.assertIn(expected,parameters)
        self.assertNotIn('联系电话',parameters); self.assertNotIn('公告编号',parameters)
        self.assertEqual(analyze('办公软件采购\n云服务≥1年')['parameters'],[])

    def test_youth_and_family_education_are_related_not_medical(self):
        for body in ('未成年人保护中心青少年心理辅导服务采购','家庭教育心理健康培训采购'):
            self.assertEqual(analyze(body)['category'],'教育相关')
        self.assertEqual(analyze('儿童医院青少年心理诊疗采购')['category'],'其他心理')

    def test_getting_bid_documents_is_not_submission(self):
        self.assertIsNone(analyze('获取投标文件截止时间：2026年9月7日09点30分')['deadline'])

    def test_buyer_section_and_tabular_product_names(self):
        from radar.documents import parse_document
        raw='''<article><h1>校园心理采购公告</h1><p>1.采购人信息</p><p>名 称：某学院</p><p>地址：某市</p><p>2.采购代理机构信息</p><p>名称：某代理公司</p><table><tr><td>序号</td><td colspan="2">标的名称</td><td>数量</td><td>单位</td></tr><tr><td>1</td><td>AI访谈评估</td><td>干预练习</td><td>1</td><td>套</td></tr><tr><td>2</td><td>AGI陪伴</td><td>职工陪伴</td><td>2</td><td>套</td></tr></table></article>'''
        doc=parse_document(raw.encode(),'https://e/n.htm')
        result=analyze_document(doc,'https://e/n.htm','2026-09-07T09:00:00+08:00')
        self.assertEqual(result['buyer'],'某学院')
        names={p['name'] for p in result['products']}
        self.assertTrue({'AI访谈评估','干预练习','AGI陪伴','职工陪伴'}<=names)
        self.assertEqual(len(result['parameters']),2)
        self.assertTrue(all(p['locator'].startswith('html/table:1/row:') for p in result['parameters']))
        self.assertNotIn('标的名称',names)

    def test_psych_activity_news_is_not_procurement(self):
        self.assertFalse(analyze('学校开展心理健康活动，师生积极参加。')['is_procurement'])
        self.assertTrue(analyze('校园心理设备采购公告\n预算金额：2万元')['is_procurement'])

    def test_lifecycle_notices_are_procurement_in_project_context(self):
        for stage in ('更正公告','终止公告','废标公告'):
            doc={'title':'学校心理服务'+stage,'text':'原响应截止时间修改为另行通知，其余不变。','blocks':[]}
            self.assertTrue(analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')['is_procurement'])
        doc={'title':'学校心理活动终止公告','text':'因雨取消活动。','blocks':[]}
        self.assertFalse(analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')['is_procurement'])

    def test_historical_fields_use_buyer_address_not_agent(self):
        result=analyze('采购人信息\n名称：某大学\n地址：江苏省南京市某路\n采购代理机构信息\n名称：代理公司\n地址：北京市某路\n发布日期：2026-09-01\n五、开启\n时间：2026年09月10日09点30分')
        self.assertEqual(result['province'],'江苏省')
        self.assertEqual(result['buyer_type'],'G/事业单位')
        self.assertIn('推断',str(result['buyer_type_evidence']))
        self.assertEqual(result['opening_at'],'2026-09-10T09:30:00+08:00')
        self.assertEqual(result['bid_at'],'2026-09-01')
        self.assertEqual(result['bid_at_semantics'],'公开发布日期')

    def test_agent_only_address_does_not_set_province(self):
        result=analyze('采购人：某科技集团有限公司\n采购代理机构信息\n名称：代理公司\n地址：广东省深圳市\n响应截止时间：2026-09-10 09:30')
        self.assertIsNone(result['province']); self.assertIsNone(result['opening_at'])
        self.assertEqual(result['buyer_type'],'B/企业')
        self.assertIsNone(result['bid_at'])

    def test_explicit_project_province_and_unknown_buyer(self):
        result=analyze('项目实施地点：广西壮族自治区南宁市\n开标时间：2026年09月10日 10:00')
        self.assertEqual(result['province'],'广西壮族自治区')
        self.assertEqual(result['buyer_type'],'未知')
        self.assertEqual(result['opening_at'],'2026-09-10T10:00:00+08:00')
        self.assertEqual(analyze('采购人信息\n名称：某学校\n地址：上海市浦东新区')['province'],'上海市')

    def test_metadata_time_and_bid_notification_amount_columns(self):
        doc={'title':'学校心理采购中标通知书','text':'','blocks':[{'text':'时间：2026-03-19 来源：学校','kind':'metadata','locator':'html/meta:1'},{'text':'供应商 | 成交金额（元）','kind':'table_row','locator':'html/table:1/row:1'},{'text':'某公司 | 139520','kind':'table_row','locator':'html/table:1/row:2'}]}
        result=analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')
        self.assertEqual(result['published_at'],'2026-03-19')
        self.assertTrue(result['is_procurement'])
        self.assertEqual(result['amounts'][0]['value'],139520)
        self.assertEqual(result['amounts'][0]['type'],'成交')
        self.assertEqual(analyze('信息提供日期：2026-09-07 10:38')['published_at'],'2026-09-07T10:38:00+08:00')
        self.assertIsNone(analyze('时间：2026-03-19 来源：部署服务')['published_at'])

    def test_unparsed_labeled_money_is_explicit(self):
        result=analyze('校园心理采购\n预算金额：人民币柒拾伍万元整（¥750,000.00）')
        self.assertTrue(result['amounts'] or any('金额待核验' in w for w in result['warnings']))

    def test_page_publish_date_precedes_original_procurement_table_date(self):
        doc={'title':'心理仪器结果公告','text':'','blocks':[{'text':'公告发布日期 | 2025/11/07 17:22','kind':'table_row','locator':'html/table:1/row:1'},{'text':'发布日期：2025-11-13','kind':'paragraph','locator':'html/line:1'}]}
        self.assertEqual(analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')['published_at'],'2025-11-13')

    def test_cross_block_money_preserves_source_locators(self):
        doc={'title':'学校心理采购','text':'','blocks':[{'text':v,'kind':'paragraph','locator':f'html/line:{i}','source_url':'https://e/a'} for i,v in enumerate(('最高限价：','7','万元','采购预算 | ￥97,000.00 | 成交金额 | ￥94,800.00'),1)]}
        result=analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')
        self.assertEqual({(v['type'],v['value']) for v in result['amounts']},{('限价',70000),('预算',97000),('成交',94800)})
        limit=next(v for v in result['amounts'] if v['type']=='限价')
        self.assertEqual(limit['locator'],'html/line:1')
        self.assertEqual(limit['source_locators'],['html/line:1','html/line:2','html/line:3'])

    def test_title_controls_procurement_domain_not_footer(self):
        for title,body,category in [('安徽新华学院心理健康信息化管理平台采购项目招标公告','集团其他院校包含医院。友情链接空调采购。','教育核心'),('湖北科技学院附属第二医院社会心理服务云平台采购意向公开','平台覆盖学校社区机关等。','其他心理')]:
            doc={'title':title,'text':body,'blocks':[]}
            self.assertEqual(analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')['category'],category)

    def test_parenthetical_budget_and_currency_table_values(self):
        result=analyze('校园心理采购\n预算金额（亦是最高限价）：人民币14万元')
        self.assertIn(('预算',140000),{(v['type'],v['value']) for v in result['amounts']})

    def test_generic_publication_metadata_precedes_old_table_date(self):
        doc={'title':'心理设备结果公告','text':'','blocks':[{'text':'公告发布日期 | 2025/11/07','kind':'table_row','locator':'html/table:1/row:1'},{'text':'时间：2025-11-13 来源：学校','kind':'metadata','locator':'html/time:1'}]}
        self.assertEqual(analyze_document(doc,'https://e/a','2026-09-07T09:00:00+08:00')['published_at'],'2025-11-13')
