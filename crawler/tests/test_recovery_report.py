import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
from scripts.recovery_report import build

class RecoveryReportTests(unittest.TestCase):
 def test_corrected_amount_is_labeled_in_annual_table_and_excluded_from_totals(self):
  project={'id':'p','title':'学校心理项目结果更正公告','publishedAt':'2026-07-22','sourceUrl':'https://example.gov.cn/correction','sourceQuality':'正文已取得','category':'教育核心','amountEligible':False,'amountScope':'含更正与历史公告，字段生效待复核，不计入合计','amounts':[{'type':'成交','value':7605584}]}
  snapshot={'builtAt':'2026-10-26T11:00:00+08:00','yearRange':{'start':'2025-10-27','end':'2026-10-26'},'weekRange':{'start':'2026-10-26','end':'2026-10-26'},'archiveProjects':[project]}
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);pub=root/'publish';pub.mkdir();(root/'docs').mkdir();(pub/'data.js').write_text('window.RADAR_DATA = '+json.dumps(snapshot)+';\n');before=root/'before.json';before.write_text(json.dumps(snapshot))
   with patch('scripts.recovery_report.ROOT',root),patch('scripts.recovery_report.public_dir',return_value=pub),contextlib.redirect_stdout(io.StringIO()):build(before,'test')
   soup=BeautifulSoup((pub/'annual-projects.html').read_text(),'html.parser');row=soup.select_one('#annual tbody tr');self.assertIn('不计入合计',row.find_all('td')[3].get_text())
   result=json.loads((root/'data/recovery/test/result.json').read_text());self.assertEqual(result['weekAmounts']['成交']['yuan'],0)
