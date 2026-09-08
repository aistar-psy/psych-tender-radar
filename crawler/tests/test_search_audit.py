import unittest
from radar.search_audit import audit_status
class AuditTests(unittest.TestCase):
 def test_index_empty_never_proves_native_empty(self):
  r=audit_status([],{'status':'connection_failed'},191)
  self.assertFalse(r['verifiedEmpty']);self.assertIn('连接',r['nativeStatus'])
 def test_partial_pages_cannot_prove_empty(self):
  q={'atom_ids':['a'],'records':[],'pages':[{'status':'ok'}],'pagination_complete':False,'field_verified':True,'date_verified':True}
  self.assertFalse(audit_status([q],{},1)['verifiedEmpty'])
 def test_fulltext_snippets_and_missing_atoms_cannot_prove_empty(self):
  q={'atom_ids':['a'],'records':[],'pages':[{'status':'ok'}],'pagination_complete':True,'field_verified':True,'date_verified':True,'fulltext_status':'search_snippets_only'}
  self.assertFalse(audit_status([q],{},1)['verifiedEmpty'])
 def test_known_native_hits_override_zero_index(self):
  q={'records':[{'url':'https://a.cn/1'}],'reported_total':10,'pages':[{'status':'ok'}]}
  self.assertIn('结果',audit_status([q],{},191)['nativeStatus'])
