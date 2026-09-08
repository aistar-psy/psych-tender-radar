import json,tempfile,unittest
from pathlib import Path
from urllib.parse import urlsplit
from radar.fetch import FetchError
try:
 from radar.pipeline import run
except ImportError:
 run=None

def fixture_fetch(url):
  path=urlsplit(url).path
  if path=='/missing.pdf':raise FetchError('blocked','HTTP 403',url)
  pages={
   '/notice':'''<html><head><title>某校心理平台采购公告</title></head><body><article><h1>某校心理平台采购公告</h1><p>发布日期：2026-09-06</p><p>项目编号：TEST-001</p><p>采购人：某校</p><p>预算金额：10万元</p><p>响应文件提交截止时间：2026年09月20日09点30分</p><table><tr><th>产品名称</th><th>数量</th><th>技术参数</th></tr><tr><td>学生心理测评系统</td><td>1套</td><td>并发用户不少于100人</td></tr></table><a href="/missing.pdf">采购文件.pdf</a></article></body></html>''',
   '/failedfirst':'<html><head><title>某校心理服务采购公告</title></head><body><article>项目编号：FAIL-2026 <p>采购人：某校</p><p>学生心理服务</p><a href="/missing.pdf">采购附件1.pdf</a><a href="/two.txt">采购附件2.txt</a></article></body></html>',
   '/two':'<html><head><title>某校心理系统采购公告</title></head><body><article>项目编号：SECOND-2026 <p>采购人：某校</p><p>学生心理系统支持100人并发</p><a href="/one.txt">采购附件1.txt</a><a href="/two.txt">采购附件2.txt</a></article></body></html>',
   '/one.txt':'心理系统支持100人并发',
   '/two.txt':'心理平台服务不少于3年',
   '/listing':'<html><body><a href="/notice">某校心理平台采购公告</a></body></html>'}
  return {'url':url,'body':pages.get(path,'').encode(),'content_type':'text/plain; charset=utf-8' if path.endswith('.txt') else 'text/html; charset=utf-8','status_code':200}

class PipelineTests(unittest.TestCase):
 url='https://fixture.example.gov.cn'
 def test_real_pipeline_has_parameter_evidence_and_attachment_gap(self):
  self.assertIsNotNone(run,'pipeline must be implemented')
  with tempfile.TemporaryDirectory() as t:
   result=run(root=Path(t),seeds=[self.url+'/notice'],no_discovery=True,max_documents=5,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   self.assertEqual(result['counts']['projects'],1)
   docs=json.loads(Path(result['run_dir'],'documents.json').read_text())
   self.assertEqual(docs[0]['analysis']['category'],'教育核心')
   self.assertTrue(docs[0]['analysis']['parameters'])
   self.assertEqual(docs[0]['detail_status'],'部分完成')
   self.assertEqual(docs[0]['main_content_status'],'available')
   self.assertEqual(docs[0]['attachments'][0]['status'],'blocked')
   report=Path(result['report']).read_text();self.assertIn('教育核心',report);self.assertIn('部分完成',report)
   again=run(root=Path(t),seeds=[self.url+'/notice'],no_discovery=True,max_documents=5,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   self.assertEqual(again['counts']['projects'],1)
 def test_budget_preserves_unprocessed_urls(self):
  self.assertIsNotNone(run)
  with tempfile.TemporaryDirectory() as t:
   result=run(root=Path(t),seeds=[self.url+'/notice',self.url+'/second'],no_discovery=True,max_documents=1,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   self.assertGreaterEqual(result['pending_count'],1)
   self.assertEqual(result['status'],'partial')

 def test_attachment_budget_resumes_beyond_first_file(self):
  with tempfile.TemporaryDirectory() as t:
   first=run(root=Path(t),seeds=[self.url+'/two'],no_discovery=True,max_documents=1,max_attachments=1,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   docs=json.loads(Path(first['run_dir'],'documents.json').read_text())
   self.assertTrue(any(a['status']=='deferred' for a in docs[0]['attachments']))
   second=run(root=Path(t),seeds=[],no_discovery=True,max_documents=1,max_attachments=1,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   docs=json.loads(Path(second['run_dir'],'documents.json').read_text())
   self.assertEqual({a['status'] for a in docs[0]['attachments']},{'ok'})
   self.assertTrue(any('3年' in p['text'] for p in docs[0]['analysis']['parameters']))
   self.assertEqual(second['counts']['projects'],1)
   self.assertEqual(second['counts']['versions'],2)

 def test_failed_first_attachment_does_not_starve_second(self):
  with tempfile.TemporaryDirectory() as t:
   run(root=Path(t),seeds=[self.url+'/failedfirst'],no_discovery=True,max_documents=1,max_attachments=1,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   second=run(root=Path(t),seeds=[],no_discovery=True,max_documents=1,max_attachments=1,interval=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fixture_fetch)
   docs=json.loads(Path(second['run_dir'],'documents.json').read_text())
   self.assertTrue(any(a['url'].endswith('/two.txt') and a['status']=='ok' for a in docs[0]['attachments']))

class AttachmentRecoveryTests(unittest.TestCase):
 url='https://fixture.example.gov.cn/shell'
 attachment='https://files.example.gov.cn/procurement.txt'
 shell='<html><head><title>某学校心理测评系统采购公告</title></head><body><h1>某学校心理测评系统采购公告</h1><p>发布日期：2026-09-06</p><div id="zbDiv"></div><a href="https://files.example.gov.cn/procurement.txt">采购文件附件.txt</a></body></html>'

 def test_shell_recovers_parameters_from_public_attachment_but_parent_body_stays_pending(self):
  visited=[]
  def fetch(url):
   visited.append(url)
   text=self.shell if url==self.url else '项目编号：RECOVER-001\n采购人：某学校\n预算金额：12万元\n学生心理测评系统支持100人并发'
   return {'url':url,'body':text.encode(),'content_type':'text/html' if url==self.url else 'text/plain','status_code':200}
  with tempfile.TemporaryDirectory() as t:
   result=run(root=t,seeds=[self.url],no_discovery=True,max_documents=1,as_of='2026-09-07T09:00:00+08:00',fetcher=fetch)
   directory=Path(result['run_dir']);docs=json.loads((directory/'documents.json').read_text());tasks=json.loads((directory/'execution.json').read_text());pending=json.loads((directory/'backlog.json').read_text())
   self.assertEqual(visited,[self.url,self.attachment]);self.assertEqual(len(docs),1)
   self.assertEqual(docs[0]['main_content_status'],'unavailable');self.assertEqual(docs[0]['detail_status'],'部分完成')
   self.assertEqual(docs[0]['analysis']['content_status'],'attachment_only')
   self.assertTrue(docs[0]['analysis']['is_procurement']);self.assertEqual(docs[0]['analysis']['published_at'],'2026-09-06')
   self.assertTrue(any(p['url']==self.attachment and '100人' in p['text'] for p in docs[0]['analysis']['parameters']))
   self.assertEqual(docs[0]['analysis']['amounts'][0]['url'],self.attachment)
   self.assertEqual(tasks[0]['status'],'partial');self.assertEqual(result['status'],'partial')
   self.assertTrue(any(p['id']==self.url and '正文' in p['error'] for p in pending))
   visited.clear()
   second=run(root=t,seeds=[],no_discovery=True,max_documents=1,max_attachments=0,as_of='2026-09-07T09:00:00+08:00',fetcher=fetch)
   cached=json.loads(Path(second['run_dir'],'documents.json').read_text())[0]
   self.assertEqual(visited,[self.url]);self.assertEqual(cached['main_content_status'],'unavailable')
   self.assertEqual(cached['attachments'][0]['freshness'],'cached')

 def test_unusable_attachment_does_not_confirm_shell_or_finish_body(self):
  for blocked in (True,False):
   with self.subTest(blocked=blocked),tempfile.TemporaryDirectory() as t:
    visited=[]
    def fetch(url):
     visited.append(url)
     if url==self.attachment and blocked:raise FetchError('blocked','HTTP 403',url)
     text=self.shell if url==self.url else '<html><body>请登录后下载采购文件，用户名 密码 验证码</body></html>'
     return {'url':url,'body':text.encode(),'content_type':'text/html','status_code':200}
    result=run(root=t,seeds=[self.url],no_discovery=True,max_documents=1,as_of='2026-09-07T09:00:00+08:00',fetcher=fetch)
    directory=Path(result['run_dir']);tasks=json.loads((directory/'execution.json').read_text());pending=json.loads((directory/'backlog.json').read_text())
    self.assertEqual(visited,[self.url,self.attachment]);self.assertEqual(result['processed_documents'],0)
    self.assertEqual(tasks[0]['status'],'content_unconfirmed');self.assertEqual(json.loads((directory/'documents.json').read_text()),[])
    self.assertTrue(any(p['id']==self.url for p in pending));self.assertTrue(any(p['id']==self.attachment for p in pending))

 def test_shell_without_procurement_hint_requires_procurement_evidence_in_attachment(self):
  shell=self.shell.replace('某学校心理测评系统采购公告','心理健康教育资源库管理系统').replace('采购文件附件.txt','公开附件.txt')
  for procurement in (True,False):
   with self.subTest(procurement=procurement),tempfile.TemporaryDirectory() as t:
    visited=[]
    def fetch(url):
     visited.append(url)
     text=shell if url==self.url else ('项目编号：CONTRACT-001\n采购人：某学校\n学生心理测评系统支持100人并发' if procurement else '系统操作说明：打开设置菜单。')
     return {'url':url,'body':text.encode(),'content_type':'text/html' if url==self.url else 'text/plain','status_code':200}
    result=run(root=t,seeds=[self.url],no_discovery=True,max_documents=1,as_of='2026-09-07T09:00:00+08:00',fetcher=fetch)
    directory=Path(result['run_dir']);docs=json.loads((directory/'documents.json').read_text());tasks=json.loads((directory/'execution.json').read_text())
    self.assertEqual(visited,[self.url,self.attachment]);self.assertEqual(len(docs),int(procurement))
    self.assertEqual(tasks[0]['status'],'partial' if procurement else 'content_unconfirmed')

 def test_empty_shell_without_public_attachment_stays_content_unconfirmed(self):
  def fetch(url):return {'url':url,'body':b'<html><body><div id="zbDiv"></div></body></html>','content_type':'text/html','status_code':200}
  with tempfile.TemporaryDirectory() as t:
   result=run(root=t,seeds=[self.url],no_discovery=True,max_documents=1,as_of='2026-09-07T09:00:00+08:00',fetcher=fetch)
   tasks=json.loads(Path(result['run_dir'],'execution.json').read_text())
   self.assertEqual(tasks[0]['status'],'content_unconfirmed');self.assertEqual(result['processed_documents'],0)

class ReportBoundaryTests(unittest.TestCase):
 def test_expired_deadline_is_not_current_opportunity(self):
  from radar.report import opportunity_state
  self.assertEqual(opportunity_state({'notice_type':'采购公告','deadline':'2026-09-07T09:30:00+08:00'},'2026-09-07T12:00:00+08:00'),'原定响应截止已过；更正/结果待核验')
 def test_attachment_login_page_is_rejected(self):
  from radar.pipeline import attachment_usable
  self.assertFalse(attachment_usable({'status':'ok','text':'请登录后下载采购文件，用户名 密码 登录'},'text/html'))
