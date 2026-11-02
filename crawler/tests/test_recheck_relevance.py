import json,tempfile,unittest
from pathlib import Path

class RecheckRelevanceTests(unittest.TestCase):
    def test_current_and_historical_rows_are_rechecked_without_deleting_private_evidence(self):
        from scripts.recheck_relevance import refresh
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);public=root/'publish';(public/'bodies').mkdir(parents=True)
            bad={'id':'bad','title':'房屋租赁采购公告','category':'其他心理','sourceUrl':'https://e.gov.cn/bad','sourceQuality':'正文已取得','publishedAt':'2026-10-23','amountEligible':False,'fullTexts':[{'path':'bodies/bad.json','url':'https://e.gov.cn/bad'}]}
            good={'id':'good','title':'智慧校园采购公告','category':'教育核心','sourceUrl':'https://e.gov.cn/good','sourceQuality':'正文已取得','publishedAt':'2026-10-23','amountEligible':True,'fullTexts':[{'path':'bodies/good.json','url':'https://e.gov.cn/good'}]}
            (public/'bodies/bad.json').write_text(json.dumps({'text':'采购房屋租赁；响应办事人员的急切心理。'}))
            (public/'bodies/good.json').write_text(json.dumps({'text':'需求包括心理测评系统。'}))
            data={'builtAt':'2026-11-02T10:00:00+08:00','defaultRunId':'r1','archiveProjects':[bad,good], 'runs':[{'id':'r1','projects':[bad,good]}],'yearRange':{'start':'2025-11-03','end':'2026-11-02'}}
            (public/'data.js').write_text('window.RADAR_DATA = '+json.dumps(data)+';\n')
            report=refresh(public,root/'audit')
            s=(public/'data.js').read_text();after=json.loads(s[s.index('{'):s.rfind(';')])
            self.assertEqual([p['id'] for p in after['archiveProjects']],['good'])
            self.assertEqual([p['id'] for p in after['runs'][0]['projects']],['good'])
            self.assertEqual(after['archiveProjects'][0]['relevance']['status'],'related')
            self.assertTrue((root/'audit/quarantined.json').exists())
            self.assertTrue((root/'audit/bodies/bad.json').exists())
            self.assertEqual(report['archiveRemoved'],1)

    def test_regular_export_audit_keeps_review_rows_and_texts_for_next_report(self):
        from radar.relevance import attach_relevance_audit
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);public=root/'publish';(public/'bodies').mkdir(parents=True)
            (public/'bodies/proof.json').write_text('{"text":"文化舞台剧创排"}')
            project={'id':'bad','title':'以文润心舞台剧采购合同公告','sourceUrl':'https://e.gov.cn/notice/2','publishedAt':'2026-10-23','relevance':{'reason':'已取得文本未发现心理采购用途'},'fullTexts':[{'path':'bodies/proof.json'}]}
            data={'builtAt':'2026-11-02T12:00:00+08:00','archiveProjects':[],'yearRange':{'start':'2025-11-03','end':'2026-11-02'}}
            attach_relevance_audit(data,[{'scope':'archive','reason':'psychology_evidence_missing','project':project}],root/'audit',public)
            self.assertEqual(data['relevanceAudit']['annualRemoved'],1)
            self.assertEqual(data['relevanceAudit']['reviewRows'][0]['sourceUrl'],'https://e.gov.cn/notice/2')
            self.assertTrue((root/'audit/quarantined.json').exists())
            self.assertTrue((root/'audit/bodies/proof.json').exists())
