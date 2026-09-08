import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from radar.source_scan import in_scope,extract_links,scan_source,build_site_queries
from radar.fetch import FetchError
from radar import source_matrix,source_scan
class SourceScanTests(unittest.TestCase):
 def test_host_boundary(self):
  self.assertTrue(in_scope('https://sub.a.gov.cn/x',['a.gov.cn']))
  self.assertFalse(in_scope('https://a.gov.cn.evil.org/x',['a.gov.cn']))
 def test_home_200_not_complete(self):
  def fetch(u):return {'body':b'<title>Home</title><p>welcome</p>','url':u,'content_type':'text/html','status_code':200}
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch,max_pages=3)
  self.assertEqual(r['status'],'accessible_no_listing');self.assertFalse(r['complete']);self.assertEqual(r['candidate_count'],0)
 def test_pagination_budget_and_duplicate_url(self):
  html='<a href="/psy">学校心理测评采购公告</a><a href="/psy#x">学校心理测评采购公告</a><a href="/p2">下一页</a>'
  def fetch(u):return {'body':html.encode(),'url':u,'content_type':'text/html','status_code':200}
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch,max_pages=2)
  self.assertEqual(r['candidate_count'],1);self.assertLessEqual(r['pages_fetched'],2);self.assertFalse(r['complete'])
 def test_empty_or_error_not_covered(self):
  def fail(u):raise TimeoutError('timeout')
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fail)
  self.assertEqual(r['status'],'fetch_error');self.assertEqual(r['pages_fetched'],0)
 def test_each_source_in_first_query_pass(self):
  sources=[{'id':str(i),'domains':[f's{i}.gov.cn']} for i in range(40)]
  p=build_site_queries(sources,'2025-09-08','2026-09-07')
  self.assertEqual(len({x['source_id'] for x in p[:40]}),40)
  self.assertTrue(all(x['status']=='not_executed' for x in p))

 def test_home_and_current_page_links_are_not_notice_candidates(self):
  html='<a href="/">心理采购网</a><a href="/index.html">心理采购公告首页</a><a href="#top">学校心理测评采购公告</a><a href="/notice/1">学校心理测评采购公告</a>'
  links,_,_=extract_links(html,'https://a.gov.cn/listing',['a.gov.cn'])
  self.assertEqual([x['url'] for x in links],['https://a.gov.cn/notice/1'])

 def test_failed_listing_is_not_a_successful_zero_result(self):
  def fetch(u):
   if u=='https://a.gov.cn/':return {'url':u,'body':'<a href="/listing">政府采购</a>'.encode(),'content_type':'text/html','status_code':200}
   raise FetchError('blocked','HTTP 403',u)
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch)
  self.assertEqual(r['status'],'partial_error');self.assertEqual(r.get('pages_failed'),1)
  self.assertEqual(r['candidate_count'],0)

 def test_http_200_challenge_is_blocked_before_collecting_links(self):
  for html in ['<title>安全验证</title><form id="challenge-form">请输入验证码</form>', '<title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/a.js"></script>']:
   with self.subTest(html=html):
    def fetch(u):return {'body':(html+'<a href="/notice/1">学校心理测评采购公告</a>').encode(),'url':u,'content_type':'text/html','status_code':200}
    r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch)
    self.assertEqual(r['status'],'blocked');self.assertEqual(r['pages_fetched'],0);self.assertEqual(r['candidate_count'],0)

 def test_notice_mentioning_verification_is_not_a_challenge(self):
  def fetch(u):return {'body':'<title>采购公告</title><p>投标人登录时需要输入验证码。</p><a href="/notice/1">学校心理测评采购公告</a>'.encode(),'url':u,'content_type':'text/html','status_code':200}
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch,max_pages=1)
  self.assertEqual(r['candidate_count'],1)

 def test_active_url_and_redirect_base_are_used_and_recorded(self):
  source={'id':'a','url':'https://old.gov.cn/','active_url':'https://new.gov.cn/start','domains':['old.gov.cn','new.gov.cn']}
  def fetch(u):
   if u!='https://new.gov.cn/start':raise AssertionError('retired entry requested')
   return {'body':'<a href="notice.html">学校心理测评采购公告</a>'.encode(),'url':'https://new.gov.cn/procurement/listing/','content_type':'text/html','status_code':200}
  r=scan_source(source,fetch,max_pages=1)
  self.assertEqual([c['url'] for c in r['candidates']],['https://new.gov.cn/procurement/listing/notice.html'])
  self.assertEqual(r['candidates'][0]['query'],'https://new.gov.cn/procurement/listing/')
  self.assertEqual(r['records'][0].get('requested_url'),'https://new.gov.cn/start')
  self.assertEqual(r['records'][0].get('final_url'),'https://new.gov.cn/procurement/listing/')

 def test_outside_redirect_keeps_evidence_without_counting_source_access(self):
  def fetch(u):return {'body':b'<html>Moved elsewhere</html>','url':'https://external.org/','content_type':'text/html','status_code':200}
  with TemporaryDirectory() as directory:
   r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn']},fetch,evidence_dir=directory)
   self.assertEqual(r['pages_fetched'],0);self.assertEqual(r['candidate_count'],0)
   self.assertEqual(r['records'][0].get('final_url'),'https://external.org/')
   self.assertTrue(Path(r['records'][0].get('evidence','missing')).is_file())

 def test_site_query_plan_uses_active_host_before_retired_alias(self):
  source={'id':'a','url':'https://old.gov.cn/','active_url':'https://new.gov.cn/','domains':['old.gov.cn','new.gov.cn']}
  queries=build_site_queries([source],'2025-09-08','2026-09-07')
  self.assertIn('site:new.gov.cn ',queries[0]['query'])

 def test_pending_pagination_precedes_new_navigation_and_retains_depth(self):
  visited=[]
  def fetch(u):
   visited.append(u)
   html='<a href="/new-list">政府采购</a>' if u.endswith('/') else '<a href="/page4">下一页</a><a href="/too-deep">政府采购</a>'
   return {'url':u,'body':html.encode(),'content_type':'text/html','status_code':200}
  r=scan_source({'id':'a','url':'https://a.gov.cn/','domains':['a.gov.cn'],'pending_pages':[{'url':'https://a.gov.cn/page3','depth':2}]},fetch,max_pages=2)
  self.assertEqual(visited,['https://a.gov.cn/','https://a.gov.cn/page3'])
  self.assertIn({'url':'https://a.gov.cn/page4','depth':2},r['remaining_urls'])
  self.assertNotIn('https://a.gov.cn/too-deep',[p['url'] for p in r['remaining_urls']])
  self.assertEqual(r['remaining_pages'],len(r['remaining_urls']))


class ScanRunTests(unittest.TestCase):
 def source(self,id,active_url=None):
  return {'id':id,'url':f'https://{id}.gov.cn/','domains':[f'{id}.gov.cn'],**({'active_url':active_url} if active_url else {})}

 def old_result(self,id,failed=False):
  return {'source_id':id,'status':'blocked' if failed else 'accessible_no_listing','pages_fetched':0 if failed else 1,'candidate_count':0,'candidates':[],
          'records':[{'url':f'https://{id}.gov.cn/','status':'blocked' if failed else 'ok',**({'error':'HTTP 403'} if failed else {})}],
          'remaining_urls':[{'url':f'https://{id}.gov.cn/page3','depth':1}]}

 def test_resume_preserves_success_failure_and_queue_only_probes_new_or_changed_entry(self):
  sources=[self.source('old'),self.source('failed'),self.source('changed','https://changed.gov.cn/new-entry'),self.source('new')]
  previous=[self.old_result('old'),self.old_result('failed',True),self.old_result('changed')];visited=[]
  def fetch(u):
   visited.append(u)
   return {'url':u,'body':b'<html>Welcome</html>','content_type':'text/html','status_code':200}
  with TemporaryDirectory() as directory:
   root=Path(directory);audit=root/'data/source-audit';audit.mkdir(parents=True)
   (audit/'scan_results.json').write_text(json.dumps(previous))
   with patch.object(source_scan,'PACKAGE_ROOT',root),patch.object(source_scan,'load_catalog',return_value=sources),patch.object(source_scan,'Fetcher',return_value=fetch):
    report=source_scan.run_scan(workers=1,resume=True)
    self.assertEqual(set(visited),{'https://changed.gov.cn/new-entry','https://new.gov.cn/'})
    results={r['source_id']:r for r in json.loads((audit/'scan_results.json').read_text())}
    self.assertEqual(results['old'],previous[0]);self.assertEqual(results['failed'],previous[1])
    self.assertEqual(report['probed'],4);self.assertEqual(report['probed_this_run'],2);self.assertEqual(report['skipped'],2)
    visited.clear();source_scan.run_scan(workers=1,resume=True)
    self.assertEqual(visited,[])
    self.assertEqual(len(json.loads((audit/'scan_results.json').read_text())),4)

 def test_default_reprobes_same_entry_and_continues_saved_pagination(self):
  visited=[]
  def fetch(u):
   visited.append(u)
   html='<a href="/new-list">政府采购</a>' if u.endswith('/') else '<a href="/page4">下一页</a>'
   return {'url':u,'body':html.encode(),'content_type':'text/html','status_code':200}
  with TemporaryDirectory() as directory:
   root=Path(directory);audit=root/'data/source-audit';audit.mkdir(parents=True)
   previous=self.old_result('a');previous['candidates']=[{'url':'https://a.gov.cn/notice1','title':'历史心理采购公告'}];previous['candidate_count']=1
   (audit/'scan_results.json').write_text(json.dumps([previous]))
   with patch.object(source_scan,'PACKAGE_ROOT',root),patch.object(source_scan,'load_catalog',return_value=[self.source('a')]),patch.object(source_scan,'Fetcher',return_value=fetch):
    report=source_scan.run_scan(max_pages=2,workers=1)
   result=json.loads((audit/'scan_results.json').read_text())[0]
   self.assertEqual(visited,['https://a.gov.cn/','https://a.gov.cn/page3'])
   self.assertIn({'url':'https://a.gov.cn/page4','depth':1},result['remaining_urls'])
   self.assertEqual(report['probed_this_run'],1);self.assertEqual(report['skipped'],0)
   self.assertIn('https://a.gov.cn/notice1',[c['url'] for c in result['candidates']])


class SourceMatrixTests(unittest.TestCase):
 def matrix_for(self,logs,probe=None):
  source={'id':'a','name':'采购站','url':'https://a.gov.cn/','domains':['a.gov.cn'],'region':'北京','tier':'政府'}
  with patch.object(source_matrix,'load_catalog',return_value=[source]),patch.object(source_matrix,'query_logs',return_value=logs),patch.object(source_matrix,'load',side_effect=lambda path,default: ['北京'] if str(path).endswith('regions.json') else ([probe] if probe else [])):
   return source_matrix.matrix([],{})

 def test_negated_site_does_not_count_as_targeted_search(self):
  result=self.matrix_for([{'query':'北京 心理采购 -site:a.gov.cn','domain':'a.gov.cn','region':'北京','status':'completed'}])
  self.assertEqual(result['summary']['queried'],0)
  self.assertEqual(result['sources'][0]['indexQueries'],0)

 def test_failed_and_unexecuted_queries_do_not_count_as_success(self):
  result=self.matrix_for([{'query':'site:a.gov.cn 心理采购','status':'blocked','region':'北京','error':'HTTP 403'},{'query':'site:a.gov.cn 心育招标','status':'not_executed','region':'北京'}])
  row=result['sources'][0]
  self.assertEqual(row['indexQueries'],0);self.assertEqual(row.get('failedQueries'),1)
  self.assertEqual(result['summary']['queried'],0);self.assertEqual(result['summary']['provinceQueries'],0)
  self.assertIn('403',row['issue']);self.assertNotIn('无已入库线索',row['coverageStatus'])

 def test_positive_subdomain_search_and_recognized_empty_are_successful(self):
  result=self.matrix_for([{'query':'(site:sub.a.gov.cn) 心理采购','status':'completed_empty_results','region':'北京'}])
  self.assertEqual(result['sources'][0]['indexQueries'],1);self.assertEqual(result['summary']['provinceQueries'],1)

 def test_failed_probe_is_shown_as_failed_not_only_connected(self):
  result=self.matrix_for([],{'source_id':'a','status':'fetch_error','pages_fetched':0,'records':[{'status':'blocked','error':'HTTP 403'}]})
  self.assertIn('失败',result['sources'][0]['coverageStatus'])

 def test_nation_and_city_do_not_inflate_province_count(self):
  result=self.matrix_for([{'query':'site:a.gov.cn 心理','status':'executed','region':r} for r in ['北京','全国','深圳']])
  self.assertEqual(result['summary']['provinceQueries'],1)
