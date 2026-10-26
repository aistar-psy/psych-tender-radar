import json,tempfile,unittest,subprocess
from pathlib import Path
from radar.sop_export import build_payload

class SopExportTests(unittest.TestCase):
 def test_config_upgrade_never_relabels_historical_extraction(self):
  config={'version':'V1.7','updated':'2026-10-26','source_sha256':'abc','recipes':[{'id':'A','name':'串A','syntax':'心理健康','field':'title'}],'families':[{'id':1,'name':'心理词','terms':['心理健康']}]}
  snapshot={'builtAt':'2026-10-26T10:00:00+08:00','archiveProjects':[{'id':'p','title':'心理项目','keywordVersion':'V1.5','sourceQuality':'正文已取得','private':'/Users/secret'}],'yearRange':{},'weekRange':{}}
  out=build_payload(config,snapshot,{'steps':[]},{'weeklyExecution':{'vocabulary':{'version':'V1.5','source_sha256':'old'}}},[],{'addedTerms':['AI心理对话舱']})
  self.assertEqual(out['configuration']['version'],'V1.7');self.assertEqual(out['lastDataset']['extractionVersions'],['V1.5']);self.assertEqual(out['lastDataset']['executionVersion'],'V1.5');self.assertEqual(out['migration']['status'],'planned_not_executed');self.assertNotIn('/Users/secret',json.dumps(out));self.assertNotIn('archiveProjects',out)
 def test_matching_query_is_partial_progress_not_annual_completion(self):
  c={'version':'V1.7','updated':'2026-10-26','source_sha256':'new','recipes':[],'families':[]}
  q=[{'recipe_sha256':'new','status':'completed_with_candidates','atom_id':'A.001','recipe_id':'A'},{'recipe_sha256':'old','status':'ok'},{'recipe_sha256':'new','status':'ok','channel':'mother_bundle_wide','recipe_id':'C'},{'recipe_sha256':'new','status':'not_executed'}]
  out=build_payload(c,{'archiveProjects':[]},{'steps':[]},{},q,{})
  self.assertEqual(out['migration']['queriesExecuted'],1);self.assertEqual(out['migration']['status'],'partial');self.assertFalse(out['migration']['annualComplete'])

class SopStateTests(unittest.TestCase):
 def test_large_valid_backup_roundtrips_through_export_and_import(self):
  root=Path(__file__).resolve().parents[1]
  js="""const a=require('node:assert/strict'),s=require('./publish/sop-state.js');
  const ids=['scope','discovery','evidence','classification','fields','publication','recovery','vocabulary'],weeks={};
  for(let i=0;i<8;i++){const d=new Date('2026-10-26T00:00:00+08:00');d.setUTCDate(d.getUTCDate()+i*7);weeks[s.weekKey(d)]=Object.fromEntries(ids.map(id=>[id,{status:'完成',evidence:'证'.repeat(6000),updatedAt:new Date().toISOString()}]));}
  const original=s.validateBackup({schemaVersion:1,weeks},ids),text=s.stringifyBackup(original,ids);
  a.ok(Buffer.byteLength(text)>1024*1024);a.deepEqual(s.parseBackup(text,ids),original);
  a.throws(()=>s.checkBackupSize(s.MAX_BACKUP_BYTES+1),/备份文件/);console.log('Large exported backup restored');"""
  result=subprocess.run(['node','-e',js],cwd=root,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_week_evidence_and_backup_rules(self):
  root=Path(__file__).resolve().parents[1]
  js="""const a=require('node:assert/strict'),s=require('./publish/sop-state.js');
  a.equal(s.weekKey(new Date('2026-10-25T15:59:59Z')),'2026-10-19');a.equal(s.weekKey(new Date('2026-10-25T16:00:00Z')),'2026-10-26');
  a.throws(()=>s.validateRecord({status:'完成',evidence:''}),/证据/);a.equal(s.validateRecord({status:'完成',evidence:'公开日志链接'}).status,'完成');
  a.throws(()=>s.validateBackup({schemaVersion:1,weeks:{'2026-10-26':{unknown:{status:'完成',evidence:'log'}}}},['scope']),/阶段/);
  a.throws(()=>s.validateBackup({schemaVersion:1,weeks:{'2026-10-27':{}}},['scope']),/周一/);
  a.throws(()=>s.validateBackup({schemaVersion:1,weeks:{'2026-10-26':{scope:{status:'完成',evidence:''}}}},['scope']),/证据/);
  const b=s.validateBackup({schemaVersion:1,weeks:{'2026-10-26':{scope:{status:'部分完成',evidence:'log'}}}},['scope']);a.equal(b.weeks['2026-10-26'].scope.status,'部分完成');
  a.throws(()=>s.save({setItem(){throw new Error('quota')}},{}),/保存失败/);console.log('SOP state rules passed');"""
  result=subprocess.run(['node','-e',js],cwd=root,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
