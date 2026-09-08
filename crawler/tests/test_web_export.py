import unittest
try:
 from radar.web_export import public_run
except ImportError:
 public_run=None

class WebExportTests(unittest.TestCase):
 def test_product_names_share_one_identical_evidence_excerpt(self):
  from radar.web_export import public_rows
  rows=[{'name':name,'text':'同一采购表的完整内容','locator':'pdf/page:1','url':'https://example.org/a.pdf'} for name in ['心理平台','测评终端','心理平台']]
  result=public_rows(rows,('name','text','locator','url'))
  self.assertEqual(len(result),1);self.assertEqual(result[0]['name'],'心理平台、测评终端');self.assertEqual(result[0]['text'],'同一采购表的完整内容')
 def test_dedup_projects_retains_events_and_hides_local_paths(self):
  self.assertIsNotNone(public_run)
  a={'title':'学校心理系统','category':'教育核心','buyer':'学校','project_number':'X-1','parameters':[{'text':'系统支持100人','locator':'pdf/page:2','url':'https://example.org/a.pdf'}],'products':[],'amounts':[]}
  docs=[{'project_id':'p1','analysis':a,'url':'https://example.org/notice','detail_status':'部分完成','attachments':[],'evidence':[{'path':'/Users/private/raw.bin'}]},
        {'project_id':'p1','analysis':{**a,'title':'学校心理系统更正公告','notice_type':'更正公告'},'url':'https://example.org/correction','detail_status':'部分完成','attachments':[{'name':'采购附件','status':'failed','error':'/Users/private/file permission denied','url':'https://example.org/a.pdf'}]}]
  result=public_run({'run_id':'r1','window_start':'2026-08-31','window_end':'2026-09-07'},docs,[{'kind':'search','status':'blocked','region':'吉林'},{'kind':'search','status':'not_executed','region':'海南'}])
  self.assertEqual(len(result['projects']),1)
  self.assertEqual(len(result['projects'][0]['events']),2)
  self.assertEqual(result['coverage']['executed'],1)
  self.assertEqual(result['coverage']['failed'],1)
  self.assertEqual(result['coverage']['unexecuted'],1)
  self.assertNotIn('/Users/',str(result))
 def test_non_http_links_and_unproven_missing_values_not_published(self):
  self.assertIsNotNone(public_run)
  d={'project_id':'p2','url':'javascript:alert(1)','analysis':{'title':'x','category':'待核验','parameters':[{'text':'x','url':'file:///secret','locator':'line1'}]}}
  result=public_run({'run_id':'r2'},[d],[])
  self.assertEqual(result['projects'][0]['sourceUrl'],'')
  self.assertEqual(result['projects'][0]['parameters'][0]['url'],'')
  self.assertIsNone(result['projects'][0]['deadline'])

class LifecycleExportTests(unittest.TestCase):
 def test_reparsed_same_url_uses_latest_version_even_if_corrected_date_is_earlier(self):
  from radar.web_export import latest_document_versions
  old={'url':'https://example.gov.cn/a','fetched_at':'2026-09-07T08:00:00+08:00','analysis':{'published_at':'2026-09-07'}}
  corrected={'url':'https://example.gov.cn/a','fetched_at':'2026-09-07T09:00:00+08:00','analysis':{'published_at':'2026-08-01'}}
  other_notice={'url':'https://example.gov.cn/b','fetched_at':'2026-09-07T08:00:00+08:00','analysis':{'published_at':'2026-08-03'}}
  result=latest_document_versions([old,corrected,other_notice])
  self.assertEqual(len(result),2);self.assertIn(corrected,result);self.assertNotIn(old,result)
 def test_correction_does_not_use_richer_old_budget_as_effective(self):
  original={'project_id':'p','url':'https://example.org/a','analysis':{'title':'心理系统招标公告','category':'教育核心','published_at':'2026-09-01','notice_type':'招标公告','deadline':'2026-09-05','parameters':[{'text':'支持100人','locator':'line:1','url':'https://example.org/a'}],'amounts':[{'type':'预算','value':100000,'currency':'CNY'}]}}
  correction={'project_id':'p','url':'https://example.org/b','analysis':{'title':'心理系统更正公告','category':'教育核心','published_at':'2026-09-03','notice_type':'更正公告','deadline':'2026-09-20','parameters':[{'text':'更正为200人','locator':'line:2','url':'https://example.org/b'}],'amounts':[{'type':'预算','value':50000,'currency':'CNY'}]}}
  p=public_run({'run_id':'r'},[original,correction],[])['projects'][0]
  self.assertEqual(p['deadline'],'2026-09-20');self.assertFalse(p['amountEligible']);self.assertEqual(len(p['parameters']),2)
 def test_cross_run_retains_events_and_parameter_sources(self):
  from radar.web_export import merge_project
  newer={'id':'p','publishedAt':'2026-09-03','sourceQuality':'正文已取得','events':[{'url':'https://b.gov.cn/2','type':'成交公告','publishedAt':'2026-09-03'}],'parameters':[],'products':[],'gaps':[],'amounts':[{'type':'成交','value':50000}]}
  older={'id':'p','publishedAt':'2026-09-01','sourceQuality':'正文已取得','events':[{'url':'https://a.gov.cn/1','type':'招标公告','publishedAt':'2026-09-01'}],'parameters':[{'text':'100并发','url':'https://a.gov.cn/1','locator':'line:2'}],'products':[],'gaps':[],'amounts':[{'type':'预算','value':100000}]}
  p=merge_project(newer,older);self.assertEqual(len(p['events']),2);self.assertEqual(len(p['parameters']),1);self.assertEqual(p['amounts'][0]['type'],'成交')

class CloudAttemptExportTests(unittest.TestCase):
 def test_new_content_unconfirmed_status_does_not_republish_old_shell_as_body(self):
  import json,tempfile
  from pathlib import Path
  from unittest.mock import patch
  from radar.web_export import export
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);discovery=root/'data/external-discovery';discovery.mkdir(parents=True)
   url='https://example.gov.cn/a';(discovery/'test_combined.json').write_text(json.dumps([{'url':url,'title':'学校心理设备采购公告'}]))
   old=root/'old';new=root/'new';old.mkdir();new.mkdir()
   for directory,docs,status,when in [(old,[{'url':url,'project_id':'p','fetched_at':'2026-09-07T08:00:00+08:00','analysis':{'title':'错误解析的空壳采购公告','category':'教育核心'}}],'ok','08'),(new,[],'content_unconfirmed','09')]:
    (directory/'summary.json').write_text(json.dumps({'run_id':directory.name,'actual_started_at':f'2026-09-07T{when}:00:00+08:00'}));(directory/'documents.json').write_text(json.dumps(docs));(directory/'execution.json').write_text(json.dumps([{'kind':'document','url':url,'status':status}]))
   with patch('radar.web_export.ROOT',root),patch('radar.source_matrix.matrix',return_value={}),patch('radar.source_matrix.query_logs',return_value=[]):export(root/'out',[old,new])
   data=json.loads((root/'out/data.js').read_text().removeprefix('window.RADAR_DATA = ').rstrip(';\n'))
   self.assertEqual(data['archiveProjects'][0]['sourceQuality'],'搜索线索待核验');self.assertEqual(data['archiveCoverage']['fetched'],0);self.assertEqual(data['archiveCoverage']['failed'],1)
   (new/'execution.json').write_text(json.dumps([{'kind':'document','url':url,'status':'not_procurement'}]))
   with patch('radar.web_export.ROOT',root),patch('radar.source_matrix.matrix',return_value={}),patch('radar.source_matrix.query_logs',return_value=[]):export(root/'out',[old,new])
   data=json.loads((root/'out/data.js').read_text().removeprefix('window.RADAR_DATA = ').rstrip(';\n'))
   self.assertEqual(data['archiveProjects'],[]);self.assertEqual(data['archiveCoverage']['fetched'],0);self.assertEqual(data['archiveCoverage']['excluded'],1)
 def test_failed_cloud_attempt_is_not_pending_or_a_successful_document(self):
  import json,tempfile
  from pathlib import Path
  from radar.web_export import cloud_attempts
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)/'batch';folder.mkdir()
   (folder/'manifest.json').write_text(json.dumps([
    {'url':'https://example.gov.cn/a','status':'ok','read_at':'2026-09-07T01:00:00Z'},
    {'url':'https://example.gov.cn/b','status':'failed','error_type':'timeout','read_at':'2026-09-07T01:00:00Z'}]))
   summary,status=cloud_attempts(Path(tmp))
   self.assertEqual(summary['downloaded'],1);self.assertEqual(summary['failed'],1)
   self.assertEqual(status['https://example.gov.cn/b'],'cloud_timeout')
   self.assertNotIn('https://example.gov.cn/a',status)
