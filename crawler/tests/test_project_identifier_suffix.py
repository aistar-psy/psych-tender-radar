import unittest
from radar.analysis import analyze_document
from radar.web_export import public_run

class IdentifierSuffixTests(unittest.TestCase):
    def test_title_suffix_is_not_part_of_identifier(self):
        for raw, expected in [('TC269X089）中标结果公告','TC269X089'), ('HW26054）竞争性磋商成交结果公告','HW26054'), ('ABC(2026)-50','ABC(2026)-50')]:
            a = analyze_document({'title':'心理设备采购公告','text':'项目编号：'+raw}, 'https://example.org/n', '2026-11-23T09:00:00+08:00')
            self.assertEqual(a['project_number'], expected)
            d = {'project_id':'p','url':'https://example.org/n','analysis':{'title':'心理设备采购公告','project_number':raw}}
            self.assertEqual(public_run({'run_id':'test'}, [d], [])['projects'][0]['number'], expected)

if __name__ == '__main__':
    unittest.main()
