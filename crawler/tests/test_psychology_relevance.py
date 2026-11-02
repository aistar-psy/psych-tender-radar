"""Purchase relevance must survive words used as slogans or service etiquette."""
import unittest
from radar.analysis import analyze_document
from radar.public_safety import public_project_exclusion

class PsychologyRelevanceTests(unittest.TestCase):
    def project(self, title, text):
        return {'title':title,'sourceUrl':'https://e.gov.cn/notice/1.html',
                'sourceQuality':'正文已取得','fullTexts':[{'path':'bodies/fixture.json'}],
                'relevance':analyze_document({'title':title,'text':text},'https://e.gov.cn/notice/1.html','2026-11-02T12:00:00+08:00').get('relevance',{})}

    def test_urgent_visitors_are_not_psychology_procurement(self):
        p=self.project('资产管理中心政府采购意向','采购内容：政务服务中心房屋租赁项目；响应办事人员的急切心理，设置人性化的引导和停车服务。预算金额：7415万元。')
        self.assertEqual(public_project_exclusion(p),'psychology_evidence_missing')

    def test_cultural_runxin_slogan_is_not_mental_health(self):
        p=self.project('《乡村文艺·以文润心焕发农村思政工作新气象》项目合同公告','采购舞台剧创排及思政创新经验交流展演，包括编导费、服装制作费、舞美制作费。')
        self.assertEqual(public_project_exclusion(p),'psychology_evidence_missing')

    def test_core_idea_and_supplier_name_do_not_prove_psychology_purchase(self):
        for text in ['核心理念是传播唐诗文化，采购景观设计制作。','供应商(乙方)：某某心理有限公司\n采购内容：办公家具。','保安人员须具备良好的心理素质。采购内容：物业服务。']:
            with self.subTest(text=text):
                self.assertEqual(public_project_exclusion(self.project('政府采购合同公告',text)),'psychology_evidence_missing')

    def test_runxin_with_actual_mental_health_service_survives(self):
        p=self.project('学校润心行动服务采购公告','采购内容：为学生提供心理咨询服务和情绪调节训练。')
        self.assertIsNone(public_project_exclusion(p))
        self.assertEqual(p['relevance'].get('status'),'related')
        self.assertTrue(p['relevance'].get('evidence'))

    def test_real_psychology_subpackage_in_broad_mother_title_survives(self):
        p=self.project('智慧校园设备采购公告','第一包：智慧黑板；第二包：心理测评系统和心理沙盘设备。')
        self.assertIsNone(public_project_exclusion(p))
        self.assertEqual(p['relevance'].get('status'),'related')

    def test_distinctive_psychology_facilities_and_training_survive(self):
        for title,text in [('心灵驿站购买服务项目','采购社区康复服务'),('学校安保服务采购','购买心理素质培训课程'),('青少年服务采购','采购情绪管理能力提升课程')]:
            with self.subTest(title=title):
                self.assertEqual(self.project(title,text)['relevance'].get('status'),'related')

    def test_unread_mother_package_remains_unconfirmed_not_proven_unrelated(self):
        from radar.relevance import assess_relevance
        r=assess_relevance('智慧校园采购公告',[],body_available=False)
        self.assertEqual(r['status'],'unconfirmed')
        self.assertIsNone(public_project_exclusion({'title':'智慧校园采购公告','sourceUrl':'https://e.gov.cn/notice/1','relevance':r}))

    def test_marketing_and_logistics_sand_tables_are_not_psychology(self):
        for text in ['采购内容：城市规划沙盘模型制作。','采购内容：数字营销沙盘设备。','采购内容：汽车车间物流仿真沙盘。']:
            with self.subTest(text=text):
                self.assertEqual(public_project_exclusion(self.project('教学实训设备采购合同公告',text)),'psychology_evidence_missing')

    def test_inline_supplier_field_cannot_hide_purchased_psychology_service(self):
        p=self.project('综合服务采购公告','中标单位：某物业有限公司，服务内容：心理咨询与辅导服务。')
        self.assertEqual(p['relevance']['status'],'related')

    def test_split_supplier_name_alone_does_not_prove_purchased_service(self):
        p=self.project('设备采购公告','供应商名称：\n某心理科技有限公司\n采购内容：办公桌椅。')
        self.assertEqual(public_project_exclusion(p),'psychology_evidence_missing')

    def test_explicit_emotion_monitoring_subpackage_is_relevant(self):
        p=self.project('智慧校园采购公告','标的名称：无感情绪监测系统，服务范围：监测学生情绪变化并生成预警。')
        self.assertEqual(p['relevance']['status'],'related')

    def test_evidence_excerpt_contains_late_purchase_signal(self):
        p=self.project('学校设备采购公告','普通设备说明。'*200+'采购心理测评系统。')
        self.assertIn('心理测评',p['relevance']['evidence'][0]['text'])

    def test_supplier_name_in_separate_evidence_block_is_not_a_purchase(self):
        from radar.relevance import assess_relevance
        r=assess_relevance('家具采购合同公告',[{'text':'供应商名称：','locator':'p:1'}, {'text':'某心理科技有限公司','locator':'p:2'}, {'text':'采购内容：办公桌椅。','locator':'p:3'}],body_available=True)
        self.assertEqual(r['status'],'review_required')

    def test_normal_enrichment_rechecks_body_uses_same_publication_gate(self):
        import json,tempfile
        from pathlib import Path
        from radar.enrichment import enrich
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'publish';out.mkdir()
            url='https://e.gov.cn/notice/1'
            for title,text,want in [('房屋租赁采购公告','采购房屋租赁，响应办事人员的急切心理。','psychology_evidence_missing'),('智慧校园采购公告','采购无感情绪监测系统，监测学生情绪变化并生成预警。',None)]:
                path=root/(str(abs(hash(text)))+'.txt');path.write_text(text)
                path.with_suffix('.json').write_text(json.dumps({'parsed':{'status':'ok','content_status':'available','title':title,'text':text,'blocks':[{'text':text,'locator':'requirement:1'}]}}))
                d={'url':url,'analysis':{'title':title},'evidence':[{'path':str(path),'url':url,'content_type':'text/plain','fetched_at':'2026-11-02T12:00:00+08:00','sha256':'proof'}]}
                p={'title':title,'sourceUrl':url,'sourceQuality':'正文已取得','events':[],'parameters':[],'amountEligible':True}
                enrich([p],[d],out)
                self.assertEqual(public_project_exclusion(p),want)
                self.assertTrue(p['fullTexts'])

    def test_consumer_psychology_research_is_a_real_purchase(self):
        for text in ['采购内容：消费心理测评系统及行为实验室建设。','采购内容：从众心理实验设备和配套课程。']:
            with self.subTest(text=text):self.assertEqual(self.project('大学实验设备采购公告',text)['relevance']['status'],'related')

    def test_property_classification_does_not_reintroduce_removed_supplier_name(self):
        r=analyze_document({'title':'学校物业服务采购公告','text':'供应商(乙方)：某心理有限公司\n采购内容：普通保洁服务。'},'https://e.gov.cn/a','2026-11-02T12:00:00+08:00')
        self.assertEqual(r['category'],'待核验')
