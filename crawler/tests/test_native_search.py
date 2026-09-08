import unittest
from radar.native_search import paginate,parse_epoint
class NativeTests(unittest.TestCase):
 def test_page_two_is_read_and_deduplicated(self):
  calls=[]
  def get(offset):
   calls.append(offset);return {'total':3,'records':[{'url':'https://a.cn/'+str(i)} for i in ([1,2] if offset==0 else [2,3])],'page_size':2}
  r=paginate(get,max_pages=4)
  self.assertEqual(calls,[0,2]);self.assertEqual(len(r['records']),3);self.assertEqual(r['stop_reason'],'exhausted')
 def test_repeating_or_failed_page_never_means_complete(self):
  r=paginate(lambda n:{'total':9,'records':[{'url':'https://a.cn/1'}],'page_size':1},max_pages=4)
  self.assertFalse(r['pagination_complete']);self.assertEqual(r['stop_reason'],'repeated_page')
  def get(n):
   if n:raise TimeoutError('timeout')
   return {'total':9,'records':[{'url':'https://a.cn/1'}],'page_size':1}
  r=paginate(get);self.assertEqual(r['next_offset'],1);self.assertFalse(r['pagination_complete'])
 def test_budget_preserves_cursor_and_explicit_zero(self):
  r=paginate(lambda n:{'total':9,'records':[{'url':'https://a.cn/'+str(n)}],'page_size':1},max_pages=2)
  self.assertEqual(r['next_offset'],2);self.assertEqual(r['stop_reason'],'page_budget')
  r=paginate(lambda n:{'total':0,'records':[],'page_size':10});self.assertTrue(r['pagination_complete'])
 def test_unknown_json_and_premature_empty_are_errors(self):
  with self.assertRaises(ValueError):parse_epoint({'code':200,'content':'{}'},'https://a.cn/')
  r=paginate(lambda n:{'total':10,'records':[],'page_size':10})
  self.assertFalse(r['pagination_complete'])

 def test_highlight_spans_do_not_split_chinese_keywords(self):
  row=parse_epoint({'result':{'totalcount':1,'records':[{'title':'心灵<em>驿站</em>采购','linkurl':'/a'}]}},'https://a.cn')['records'][0]
  self.assertEqual(row['title'],'心灵驿站采购')
