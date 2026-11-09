import unittest

from radar.analysis import analyze_document
from radar.enrichment import awarded_suppliers

URL = 'https://example.gov.cn/notice'
NOW = '2026-11-09T09:00:00+08:00'

def blocks(lines, kind='paragraph'):
    return [{'text':s,'kind':kind,'locator':f'html/table:1/row:{i+1}'} for i,s in enumerate(lines)]

class WeeklyBoundaryTests(unittest.TestCase):
    def test_award_amount_uses_explicit_adjacent_currency_column(self):
        rows=blocks(['包号 | 采购内容 | 供应商名称 | 地 址 | 中标金额 | 单位 | 备注信息',
                     'P1 | 心理测评设备 | 示例心理科技有限公司 | 示例路 | 579,900.00 | 元 | 评审总分：89.96'],
                    'table_row')
        result=analyze_document({'title':'学校心理设备采购项目中标公告','blocks':rows},URL,NOW)
        self.assertEqual([(r['type'],r['value']) for r in result['amounts']],[('成交',579900.0)])
        explicit=blocks(['货物名称 | 预算金额（万元） | 单位 | 数量','心理测评设备 | 15 | 套 | 1'],'table_row')
        amount=analyze_document({'title':'心理测评设备采购公告','blocks':explicit},URL,NOW)['amounts']
        self.assertEqual([(r['type'],r['value']) for r in amount],[('预算',150000.0)])
        conflict=[explicit[0],{**explicit[1],'text':'心理测评设备 | 15 | 元 | 1'}]
        self.assertEqual(analyze_document({'title':'心理测评设备采购公告','blocks':conflict},URL,NOW)['amounts'],[])
        for unit in ('元/人','套',''):
            wrong=[rows[0],{**rows[1],'text':rows[1]['text'].replace('| 元 |','| '+unit+' |')}]
            self.assertEqual(analyze_document({'title':'学校心理设备采购项目中标公告','blocks':wrong},URL,NOW)['amounts'],[])

    def test_award_table_address_is_not_a_supplier(self):
        rows=blocks(['包号 | 采购内容 | 供应商名称 | 地 址 | 中标金额 | 单位',
                     'P1 | 心理测评设备 | 示例心理科技有限公司 | 示例路 | 579900 | 元'],'table_row')
        self.assertEqual([x['name'] for x in awarded_suppliers('学校心理设备采购中标公告',rows,URL)],['示例心理科技有限公司'])

    def test_numbered_buyer_and_result_labels_can_span_blocks(self):
        rows=blocks(['3.采购人名称：','示例银行工会','4.采购方式：','竞争性磋商',
                     '10.成交供应商：','示例心理咨询有限公司','11.成交金额：','2,592,000.00元'])
        title='示例银行工会员工心理健康服务采购项目结果公告'
        self.assertEqual(analyze_document({'title':title,'blocks':rows},URL,NOW)['buyer'],'示例银行工会')
        self.assertEqual([x['name'] for x in awarded_suppliers(title,rows,URL)],['示例心理咨询有限公司'])
        wrong=[{**rows[0]},{**rows[2]}]
        self.assertIsNone(analyze_document({'title':title,'blocks':wrong},URL,NOW)['buyer'])
        self.assertEqual(awarded_suppliers(title.replace('结果公告','候选公示'),rows,URL),[])

    def test_linked_recovery_stays_in_batch_and_avoids_repeat_requests(self):
        from scripts.recover_pending_notices import select_linked_queue
        a='https://example.gov.cn/a';b='https://example.gov.cn/b'
        rows=[{'parent_url':a,'url':a+'/new','kind':'document'},
              {'parent_url':a,'url':a+'/saved.pdf','kind':'attachment'},
              {'parent_url':a,'url':a+'/tried.pdf','kind':'attachment'},
              {'parent_url':b,'url':b+'/old.pdf','kind':'attachment'}]
        self.assertEqual(select_linked_queue(rows,{a},{a+'/saved.pdf'},{a+'/tried.pdf'}),rows[:1])

    def test_saved_original_can_lead_to_new_attachment_even_when_shared(self):
        from scripts.recover_pending_notices import select_linked_queue, trace_queue
        a='https://example.gov.cn/a';b='https://example.gov.cn/b';old='https://example.gov.cn/old'
        rows=[
            {'from_url':a,'to_url':b,'kind':'original_publication_candidate'},
            {'from_url':b,'to_url':b+'/need.pdf','kind':'public_attachment'},
            {'from_url':old,'to_url':b+'/need.pdf','kind':'public_attachment'},
        ]
        chosen=select_linked_queue(trace_queue(rows),{a},{b},set())
        self.assertEqual([(r['parent_url'],r['url'],r['kind']) for r in chosen],
                         [(b,b+'/need.pdf','attachment')])

    def test_explicit_mixed_procurement_does_not_sum_whole_bundle_as_psychology(self):
        from radar.web_export import public_run
        for title,eligible in [('小学心理及其他部室设备采购项目竞争性谈判公告',False),
                               ('学校人工智能通识教育实验室和AI心理健康平台采购项目竞争性谈判公告',False),
                               ('中学公寓楼物业管理服务采购结果公告',False),
                               ('受助人员站内照料及医疗救治期间特殊护理服务项目中标公告',False),
                               ('小学心理辅导室设备采购项目竞争性谈判公告',True)]:
            d={'project_id':'p','url':URL,'analysis':{'title':title,'category':'教育核心',
               'amounts':[{'type':'预算','value':739836,'currency':'CNY'}]}}
            p=public_run({'run_id':'test'},[d],[])['projects'][0]
            self.assertIs(p['amountEligible'],eligible,title)
            self.assertEqual(p['amounts'][0]['value'],739836)

    def test_stage_can_come_from_explicit_document_fields(self):
        title='示例银行工会心理健康服务采购项目结果公告'
        rs=blocks(['10.成交供应商：','示例心理咨询有限公司','11.成交金额：','2592000元'])
        self.assertEqual(analyze_document({'title':title,'blocks':rs},URL,NOW)['notice_type'],'成交结果公告')
        title='学校心理测评设备采购项目'
        rs=blocks(['2.供应商（乙方）：示例心理科技有限公司','合同公告日期：2026-11-06'])
        a=analyze_document({'title':title,'blocks':rs},URL,NOW)
        self.assertEqual(a['notice_type'],'合同公告')
        self.assertEqual([(x['name'],x['role']) for x in awarded_suppliers(title,rs,URL,notice_type=a['notice_type'])],
                         [('示例心理科技有限公司','合同供应商')])
        self.assertEqual(awarded_suppliers(title,rs,URL),[])

    def test_brainwave_biofeedback_treatment_has_direct_psychology_use(self):
        title='县医院脑电生物反馈治疗仪和认知能力评估系统采购招标公告'
        a=analyze_document({'title':title,'blocks':blocks(['采购范围：脑电生物反馈治疗仪、认知能力评估系统。'])},URL,NOW)
        self.assertEqual(a['category'],'其他心理')
        self.assertEqual(a['relevance']['status'],'related')

    def test_numbered_procurement_id_can_split_across_label_blocks(self):
        rows=blocks(['1.项目名称：','员工心理健康服务','2.采购','编号：','0733-26133479'])
        a=analyze_document({'title':'员工心理健康服务采购项目结果公告','blocks':rows},URL,NOW)
        self.assertEqual(a['project_number'],'0733-26133479')
        wrong=rows[:4]+[{**rows[-1],'source_url':'https://example.gov.cn/unrelated.pdf'}]
        self.assertIsNone(analyze_document({'title':'员工心理健康服务采购项目结果公告','blocks':wrong},URL,NOW)['project_number'])
