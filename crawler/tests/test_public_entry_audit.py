import json,os,subprocess,tempfile,unittest
from pathlib import Path

class PublicEntryAuditTests(unittest.TestCase):
 def test_two_source_queue_with_four_workers_visits_each_entry_once(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp);(f/'scripts').mkdir();script=f/'scripts/public_entry_audit.cjs';script.write_text((root/'scripts/public_entry_audit.cjs').read_text())
   stub=f/'browser.cjs';stub.write_text("""const page=()=>({setDefaultTimeout(){},async goto(){return{status:()=>200}},async title(){return '公开检索'},url(){return 'https://example.gov.cn'},locator(){return {async innerText(){return '公开入口'},async count(){return 0},async evaluateAll(){return []}}},async content(){return '<html>公开入口</html>'},async close(){}});module.exports={chromium:{async launch(){return{async newContext(){return{async newPage(){await new Promise(setImmediate);return page()},async close(){}}},async close(){}}}}};""")
   plan=f/'plan.json';plan.write_text(json.dumps([{'id':'first','url':'https://example.gov.cn/1'},{'id':'second','url':'https://example.gov.cn/2'}]))
   result=subprocess.run(['node',str(script),str(plan),'fixture'],env=dict(os.environ,PLAYWRIGHT_MODULE=str(stub)),text=True,capture_output=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   rows=json.loads((f/'data/source-audit/browser-checks-fixture/results.json').read_text());self.assertEqual(sorted(r['source_id'] for r in rows),['first','second'])
