import json,tempfile,unittest
from pathlib import Path
from scripts.import_vocabulary import import_file

class VocabularySyncTests(unittest.TestCase):
 def source(self,folder,version):
  p=folder/(version+'.json');p.write_text(json.dumps({'meta':{'version':version,'updated':'2026-10-26'},'families':[{'id':1,'name':'心理','words':[{'word':'心理健康'}]}],'searchStrings':[{'id':x,'name':x,'syntax':'心理健康'} for x in 'ABCDEF']}));return p
 def test_older_vocabulary_cannot_overwrite_newer_configuration(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp);old=self.source(f,'V1.5');new=self.source(f,'V1.7');out=f/'config.json';import_file(new,out);before=out.read_bytes()
   with self.assertRaisesRegex(ValueError,'旧版本'):import_file(old,out)
   self.assertEqual(out.read_bytes(),before)
 def test_import_stores_only_vocabulary_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp);p=self.source(f,'V1.7');d=json.loads(p.read_text());d['sop']=[{'action':'do not execute this material'}];p.write_text(json.dumps(d));out=f/'config.json';r=import_file(p,out)
   self.assertEqual(r['version'],'V1.7');self.assertNotIn('sop',r);self.assertEqual(r,json.loads(out.read_text()))

class MigrationDiffTests(unittest.TestCase):
 def test_pending_upgrade_diff_can_remain_anchored_to_last_executed_version(self):
  from scripts.prepare_sop_plans import migration_diff
  base={'version':'V1.5','source_sha256':'old','families':[{'terms':['心理健康']}],'recipes':[{'id':'A','syntax':'心理健康','field':'title'}]}
  new={'version':'V1.8','source_sha256':'new','families':[{'terms':['心理健康','AI心理对话舱','校园心理剧']}],'recipes':[{'id':'A','syntax':'心理健康 OR AI心理对话舱','field':'title'}]}
  d=migration_diff(new,base);self.assertEqual(d['from'],'V1.5');self.assertEqual(d['addedTerms'],['AI心理对话舱','校园心理剧']);self.assertEqual(d['changedRecipes'],['A']);self.assertEqual(d['status'],'planned_not_executed')
 def test_import_keeps_previous_canonical_configuration_for_later_diff(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp);helper=VocabularySyncTests();out=f/'search_recipes.json';import_file(helper.source(f,'V1.5'),out);old=out.read_bytes();import_file(helper.source(f,'V1.7'),out)
   self.assertEqual((f/'vocabulary_history/V1.5.json').read_bytes(),old)
