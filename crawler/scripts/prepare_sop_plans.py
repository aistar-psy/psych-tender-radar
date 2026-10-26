"""Plan original A-F and extra mother-bundle discovery without claiming execution."""
import hashlib,json,sys
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import load_recipes,build_recipe_plan,clauses
from radar.source_scan import load_catalog

ROOT=Path(__file__).resolve().parents[1]
def migration_diff(config,baseline):
 before={t for f in baseline['families'] for t in f['terms']};after={t for f in config['families'] for t in f['terms']}
 old={r['id']:(r['syntax'],r['field']) for r in baseline['recipes']}
 return {'from':baseline['version'],'to':config['version'],'baselineSha256':baseline.get('source_sha256'),
  'addedTerms':sorted(after-before),'removedTerms':sorted(before-after),
  'changedRecipes':[r['id'] for r in config['recipes'] if old.get(r['id'])!=(r['syntax'],r['field'])],
  'terms':len(after),'atoms':sum(len(clauses(r['syntax'])) for r in config['recipes']),
  'status':'planned_not_executed','historicalDataVersion':baseline['version'],'newSha256':config['source_sha256']}

def prepare():
 now=datetime.now(ZoneInfo('Asia/Shanghai'));start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat();config=load_recipes();sources=load_catalog();original=build_recipe_plan(sources,start,end)
 recipe=next(r for r in config['recipes'] if r['id']=='C');terms=list(dict.fromkeys(t for branch in clauses(recipe['syntax']) for t in branch if t not in ('心理健康','心理','心育')));wide=[]
 for source in sources:
  domain=next(q['domain'] for q in original if q['source_id']==source['id'])
  for term in terms:
   identity=[source['id'],term,start,end,config['source_sha256'],'mother_bundle_wide']
   wide.append({'id':hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24],'source_id':source['id'],'domain':domain,'query':'site:'+domain+' "'+term+'" after:'+start+' before:'+(now+timedelta(days=1)).date().isoformat(),'keyword':term,'start':start,'end':end,'recipe_id':'C','recipe_sha256':config['source_sha256'],'channel':'mother_bundle_wide','postfilter_required':True,'fulltext_status':'pending','status':'not_executed','original_syntax':recipe['syntax']})
 folder=ROOT/'data/sop-plan'/now.strftime('%Y%m%d')/config['source_sha256'][:12];folder.mkdir(parents=True,exist_ok=True)
 for name,rows in [('original_queries.json',original),('mother_bundle_queries.json',wide)]: (folder/name).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 summary={'version':config['version'],'sha256':config['source_sha256'],'window':{'start':start,'end':end},'sources':len(sources),'originalQueriesPlanned':len(original),'motherBundleQueriesPlanned':len(wide),'status':'planned_not_executed','originalQueriesExecuted':0,'motherBundleQueriesExecuted':0}
 # An imported-but-unexecuted intermediate version is not the diff baseline.
 migration_path=ROOT/'config/vocabulary_migration.json';prior=json.loads(migration_path.read_text()) if migration_path.exists() else {}
 reports=[json.loads(p.read_text()) for p in (ROOT/'data/recovery').glob('*/result.json')]
 executed=next((r['weeklyExecution']['vocabulary']['version'] for r in sorted(reports,key=lambda r:r.get('builtAt',''),reverse=True) if r.get('weeklyExecution',{}).get('vocabulary',{}).get('version')),prior.get('from'))
 if executed and all(c in 'V0123456789.' for c in executed):
  baseline_path=ROOT/'config/vocabulary_history'/(executed+'.json')
  if baseline_path.exists():migration_path.write_text(json.dumps(migration_diff(config,json.loads(baseline_path.read_text())),ensure_ascii=False,indent=2)+'\n')
 (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False));return summary
if __name__=='__main__':prepare()
