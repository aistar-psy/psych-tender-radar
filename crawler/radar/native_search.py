from .http import secure_session
"""Public native search pagination. No authentication or challenge bypass."""
import argparse,hashlib,json,time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urljoin,quote
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from .search_recipes import build_recipe_plan,seed_plan,match_recipes,load_recipes
from .source_scan import load_catalog,in_scope,is_challenge
from .pipeline import PACKAGE_ROOT,write_json,load

def parse_epoint(data,base):
 if 'content' in data and isinstance(data['content'],str):data=json.loads(data['content'])
 result=data.get('result',{})
 if not isinstance(result.get('records'),list) or not isinstance(result.get('totalcount'),(int,str)):raise ValueError('Unrecognized native search JSON; not zero results')
 def text(v):return BeautifulSoup(str(v or ''),'html.parser').get_text('',strip=True)
 rows=[]
 for item in result['records']:
  u=urljoin(base,item.get('linkurl',''))
  if not item.get('linkurl'):raise ValueError('Native result missing linkurl')
  rows.append({'url':u,'title':text(item.get('title')),'snippet':text(item.get('content')),'published_at':str(item.get('webdate') or '')[:10]})
 return {'total':int(result['totalcount']),'records':rows}

def paginate(get_page,max_pages=20,start_offset=0,prior_records=None,prior_pages=None):
 if max_pages<1:raise ValueError('max_pages must be positive')
 found={r['url']:r for r in prior_records or []};pages=list(prior_pages or []);offset=start_offset;hashes=set();total=None;complete=False;stop='page_budget'
 for _ in range(max_pages):
  try:
   page=get_page(offset);rows=page['records'];total=page['total'];size=page['page_size']
   if not isinstance(total,int) or total<0 or not isinstance(size,int) or size<1:raise ValueError('Invalid native pagination metadata')
   digest=hashlib.sha256(json.dumps([x['url'] for x in rows]).encode()).hexdigest()
   rec={'offset':offset,'rows':len(rows),'total':total,'sha256':digest,'status':'ok'}
   if page.get('evidence'):rec['evidence']=page['evidence']
   if rows and digest in hashes:stop='repeated_page';rec['status']=stop;pages.append(rec);break
   if not rows and offset<total:raise ValueError('Empty page before declared total; pagination not verified')
   hashes.add(digest)
   for row in rows:found.setdefault(row['url'],row)
   pages.append(rec);offset+=size
   if offset>=total:
    # Native totals count rows, but repeated duplicates can hide missing results.
    complete=len(found)>=total
    stop='exhausted' if complete else 'count_mismatch'
    break
  except Exception as e:
   stop='fetch_error';pages.append({'offset':offset,'status':stop,'error':str(e)[:250]});break
 return {'records':list(found.values()),'pages':pages,'reported_total':total,'next_offset':None if complete else offset,'pagination_complete':complete,'stop_reason':stop}

def run(source_ids=None,max_pages=20,max_queries=None,resume=False):
 now=datetime.now(ZoneInfo('Asia/Shanghai'));start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat()
 configs=load(PACKAGE_ROOT/'config/native_search.json',[]);catalog={s['id']:s for s in load_catalog()};out=PACKAGE_ROOT/'data/native-search';out.mkdir(parents=True,exist_ok=True)
 logfile=out/('queries-'+source_ids[0]+'.json' if source_ids and len(source_ids)==1 else 'queries.json')
 logs=load(logfile,[]);previous={x['id']:x for x in logs};session=secure_session();count=0
 for cfg in configs:
  if source_ids and cfg['source_id'] not in source_ids:continue
  s=catalog[cfg['source_id']];atoms=build_recipe_plan([s],start,end);seeds=seed_plan(atoms)
  for seed in seeds:
   id=hashlib.sha256(json.dumps([seed,cfg],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]
   old=previous.get(id,{}) if resume else {}
   if old.get('pagination_complete'):continue
   if max_queries is not None and count>=max_queries:break
   def get_page(offset):
    time.sleep(0.6)
    payload={**cfg['payload'],'wd':seed['keyword'],'pn':offset,'rn':10,'sdt':start+' 00:00:00','edt':end+' 23:59:59'}
    if cfg.get('adapter')=='chongqing':payload={'search':seed['keyword'],'pageIndex':offset//10+1,'pageSize':10}
    response=session.post(cfg['endpoint'],json=payload,timeout=18)
    if is_challenge(response.content):raise ValueError('Access challenge; stopped without bypass')
    response.raise_for_status();data=response.json();digest=hashlib.sha256(response.content).hexdigest();path=out/'evidence'/f'{digest}.json';write_json(path,{'url':cfg['endpoint'],'payload':payload,'response':data,'read_at':now.isoformat()})
    page=parse_epoint(data,cfg['base']);return dict(page,page_size=10,evidence=str(path.relative_to(PACKAGE_ROOT)))
   progress=paginate(get_page,max_pages,old.get('next_offset') or 0,old.get('records'),old.get('pages'))
   dates=[x.get('published_at') for x in progress['records']]
   within=all(x and start<=x<=end for x in dates)
   candidates=[];pending=[]
   for row in progress['records']:
    if not in_scope(row['url'],s['domains']):continue
    if row.get('published_at') and not start<=row['published_at']<=end:continue
    matched=match_recipes(row['title'],row.get('snippet',''))
    if not matched:pending.append(dict(row,source_id=s['id'],reason='搜索摘要未命中原式；需阅读全文后判断'))
    if matched:candidates.append(dict(row,source_id=s['id'],provider='native_search',query=seed['keyword'],recipe_ids=matched,source_status='listing_only',discovered_at=now.isoformat()))
   previous[id]={**seed,**progress,'id':id,'checked_at':now.isoformat(),'provider':'native_public_json','field_verified':cfg.get('adapter')!='chongqing','date_verified':bool(progress['records']) and within,
     'fulltext_pending':pending,'adapter':cfg.get('adapter','epoint'),'status':'ok' if progress['pages'] and all(x['status']=='ok' for x in progress['pages']) else 'partial_error','candidates':candidates,
     'recipe_sha256':load_recipes()['source_sha256'],'fulltext_status':'search_snippets_only','complete':False}
   write_json(logfile,list(previous.values()));count+=1
   print(s['id'],seed['keyword'],len(progress['records']),len(candidates),progress['stop_reason'],flush=True)
   if progress['stop_reason']=='fetch_error' and not progress['records']:break
 # Merge other source runs without losing their checkpoints.
 on_disk={q['id']:q for q in load(logfile,[])};on_disk.update(previous);previous=on_disk
 all_candidates={x['url']:x for q in previous.values() if not q.get('superseded') for x in q.get('candidates',[])}
 write_json(PACKAGE_ROOT/'data/external-discovery'/('native_'+source_ids[0]+'_candidates.json' if source_ids and len(source_ids)==1 else 'native_candidates.json'),list(all_candidates.values()))
 return {'queries_this_run':count,'queries':len(previous),'candidate_urls':len(all_candidates)}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',action='append');p.add_argument('--max-pages',type=int,default=20);p.add_argument('--max-queries',type=int);p.add_argument('--resume',action='store_true');a=p.parse_args();print(json.dumps(run(a.source,a.max_pages,a.max_queries,a.resume),ensure_ascii=False))
