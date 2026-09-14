"""Resumable original-recipe index discovery, with explicit page/field gaps."""
import argparse,json,hashlib
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .pipeline import PACKAGE_ROOT,write_json,load
from .source_scan import load_catalog,build_site_queries,in_scope
from .discovery import discover
from .fetch import Fetcher
from .search_recipes import match_recipes,load_recipes

def scheduled_plan(plan,offset=0):
 groups={}
 for task in plan:groups.setdefault(task['source_id'],[]).append(task)
 rows=[]
 for n in range(max((len(g) for g in groups.values()),default=0)):
  for i,group in enumerate(groups.values()):
   if n<len(group):rows.append(group[(n+i%6)%len(group)])
 if not rows:return []
 offset%=len(rows)
 return rows[offset:]+rows[:offset]

def run(max_queries=60,source_ids=None,max_pages=3):
 now=datetime.now(ZoneInfo('Asia/Shanghai'));start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat()
 sources=[s for s in load_catalog() if not source_ids or s['id'] in source_ids];plan=build_site_queries(sources,start,end)
 root=PACKAGE_ROOT/'data/external-discovery';path=root/(end+'_recipe_queries.json');old=load(path,{'executed_queries':[]});logs={x['id']:x for x in old['executed_queries']};candidates={x['url']:x for x in load(root/(end+'_recipe_combined.json'),[])}
 cursor_file=PACKAGE_ROOT/'data/source-audit'/('keyword_cursor-'+hashlib.sha256(json.dumps(sorted(source_ids or [])).encode()).hexdigest()[:8]+'.json')
 cursor=load(cursor_file,{})
 digest=load_recipes()['source_sha256'];offset=cursor.get('next_index',0) if cursor.get('recipe_sha256')==digest else 0
 fetch=Fetcher(timeout=10,retries=0,interval=1);failed=0;count=0
 for index,task in enumerate(scheduled_plan(plan,offset)):
  if task['id'] in logs:continue
  if count>=max_queries or failed>=3:break
  result=discover(task['query'],fetch,max_pages)
  row={**task,'provider':result['provider'],'status':result['status'],'error':result.get('error'),'pagination':result.get('pagination',{}),'attempts':result.get('attempts',[]),'executed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
  logs[task['id']]=row;count+=1
  write_json(cursor_file,{'next_index':(offset+index+1)%len(plan),'recipe_sha256':digest,'updated_at':now.isoformat()})
  failed=failed+1 if result['status'] not in ('ok','empty') else 0
  for hit in result['links']:
   if not in_scope(hit['url'],[task['domain']]):continue
   title=hit.get('text','');snippet=hit.get('snippet','')
   if not all(t in title+' '+snippet for t in task['terms']):continue
   candidates.setdefault(hit['url'],{'url':hit['url'],'title':title,'provider':result['provider'],'query':task['query'],'source_id':task['source_id'],'recipe_ids':match_recipes(title,snippet),'published_at':None,'source_status':'search_only','discovered_at':now.isoformat()})
  write_json(path,{'executed_queries':list(logs.values())});write_json(root/(end+'_recipe_combined.json'),list(candidates.values()))
 write_json(PACKAGE_ROOT/'data/source-audit/keyword_progress.json',{'planned':len(plan),'attempted':len(logs),'remaining':len(plan)-len(logs),'window':{'start':start,'end':end},'complete':False})
 return {'attempted_this_run':count,'attempted':len(logs),'planned':len(plan),'candidates':len(candidates)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--max-queries',type=int,default=60);p.add_argument('--source',action='append');p.add_argument('--max-pages',type=int,default=3);a=p.parse_args();print(json.dumps(run(a.max_queries,a.source,a.max_pages),ensure_ascii=False))
