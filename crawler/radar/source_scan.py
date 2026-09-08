"""Auditable source-by-source discovery. A reachable homepage is not coverage."""
import argparse,hashlib,json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timedelta,date
from pathlib import Path
from urllib.parse import urlsplit,urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from .fetch import Fetcher,FetchError,save_evidence
from .discovery import normalize_url
from .search_recipes import build_recipe_plan,vocabulary_match
from .pipeline import write_json,load,PACKAGE_ROOT
PSYCH=re.compile(r'心理|心育|情绪|精神卫生|精神健康|生物反馈|沙盘|宣泄|认知训练')
NOTICE=re.compile(r'采购|招标|中标|成交|询价|磋商|竞价|比选|意向|征集|合同|公告')
NAV=re.compile(r'政府采购|交易公开|交易信息|采购公告|中标公告|招标公告|采购意向|自主采购|招标采购|采购信息|采购公示')

def in_scope(url,domains):
 try:
  h=(urlsplit(url).hostname or '').lower()
  return urlsplit(url).scheme in ('http','https') and any(h==d.lower() or h.endswith('.'+d.lower()) for d in domains if d)
 except ValueError:return False

def is_homepage(url):
 p=urlsplit(url)
 return not p.query and bool(re.fullmatch(r'/(?:index|default|home)?(?:\.(?:html?|aspx?|php))?/?',p.path,re.I))

def is_challenge(body):
 text=body.decode('utf-8','ignore') if isinstance(body,bytes) else body
 lower=text.lower()
 if any(s in lower for s in ('cf-chl-','/cdn-cgi/challenge-platform/','acw_sc__v2','challenge-form','verify you are human','人机验证','访问过于频繁')):return True
 soup=BeautifulSoup(body,'html.parser');title=soup.title.get_text(' ',strip=True) if soup.title else ''
 # Mentioning a captcha in procurement instructions is not an access challenge.
 return bool(re.search(r'^(?:安全验证|访问验证|验证码验证|访问被拒绝|access denied|robot check)\s*[.!。！]*$',title,re.I))

def extract_links(body,url,domains):
 soup=BeautifulSoup(body,'html.parser');candidates={};navigation={};pages={}
 for a in soup.select('a[href]'):
  u=normalize_url(urljoin(url,a.get('href','')));label=a.get_text(' ',strip=True) or a.get('title','')
  if not u or not in_scope(u,domains) or u==normalize_url(url) or is_homepage(u):continue
  if vocabulary_match(label) and NOTICE.search(label):candidates[u]={'url':u,'title':label}
  elif len(label)<40 and NAV.search(label):navigation[u]=u
  if re.fullmatch(r'下一页|下页|后一页|next\s*[>»]?|[>»]',label,re.I) or 'next' in a.get('rel',[]):pages[u]=u
 return list(candidates.values()),list(navigation),list(pages)

def scan_source(source,fetch=None,max_pages=4,evidence_dir=None):
 fetch=fetch or Fetcher(timeout=8,interval=1,retries=0)
 entry=normalize_url(source.get('active_url') or source['url']) or source['url']
 domains=source.get('domains') or [urlsplit(entry).hostname]
 queue=[(entry,0)];seen=set();hashes=set();found={c['url']:c for c in source.get('previous_candidates',[]) if in_scope(c.get('url',''),domains)};records=[];fetched=0;listing=False
 # Revisit the entry, then continue the saved frontier before fresh navigation.
 for page in source.get('pending_pages',[]):
  u=normalize_url(page.get('url','') if isinstance(page,dict) else page)
  depth=page.get('depth',0) if isinstance(page,dict) else 0
  if u and in_scope(u,domains) and u not in {p[0] for p in queue}:queue.append((u,depth))
 while queue and len(records)<max_pages:
  u,depth=queue.pop(0)
  if u in seen:continue
  seen.add(u);record={'url':u,'requested_url':u,'depth':depth,'status':'running'}
  try:
   if not in_scope(u,domains):raise FetchError('invalid_url','entry outside registered source domain',u)
   r=dict(fetch(u));final_url=r.get('url') or u
   record.update(final_url=final_url,redirected=normalize_url(final_url)!=u,status_code=r.get('status_code'))
   if isinstance(r.get('body'),str):r['body']=r['body'].encode()
   # Keep redirect/challenge evidence without counting it as a usable source read.
   if r.get('body'):
    record['sha256']=hashlib.sha256(r['body']).hexdigest()
    if evidence_dir:record['evidence']=save_evidence({**r,'url':final_url,'content_type':r.get('content_type','')},evidence_dir)['path']
   if not in_scope(final_url,domains):raise FetchError('redirect_out_of_scope','redirect outside registered source domain',final_url)
   if not r.get('body'):raise ValueError('empty response body')
   if r.get('status_code',200)>=400:raise ValueError('HTTP '+str(r['status_code']))
   if is_challenge(r['body']):raise FetchError('blocked','HTTP response contains an access challenge',final_url)
   digest=record['sha256'];fetched+=1
   record.update(status='ok',sha256=digest)
   seen.add(normalize_url(final_url))
   if digest in hashes:record['status']='repeated_page';records.append(record);continue
   hashes.add(digest);links,nav,nexts=extract_links(r['body'],final_url,domains)
   listing=listing or bool(nexts or links)
   for c in links:
    if c['url'] not in (entry,normalize_url(source['url'])):found.setdefault(c['url'],dict(c,source_id=source['id'],provider='source_listing',query=final_url,requested_listing_url=u,discovered_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),source_status='listing_only'))
   for n in nexts:
    if n not in seen:queue.append((n,depth))
   if depth<2:
    for n in nav:
     if n not in seen:queue.append((n,depth+1))
   record['candidates']=len(links)
  except Exception as e:record.update(status=getattr(e,'kind','fetch_error'),error=str(e)[:220])
  records.append(record)
 failures=[r for r in records if r.get('error')]
 remaining={u:{'url':u,'depth':depth} for u,depth in queue if u not in seen}
 for failed in failures:
  if failed['url']!=entry:remaining.setdefault(failed['url'],{'url':failed['url'],'depth':failed.get('depth',0)})
 status=('partial_error' if fetched else failures[0]['status']) if failures else 'partial_listing' if found else ('accessible_no_hits' if listing else 'accessible_no_listing') if fetched else 'not_executed'
 return {'source_id':source['id'],'source_url':source['url'],'entry_url':entry,'status':status,'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
         'pages_requested':len(records),'pages_fetched':fetched,'pages_failed':len(failures),'candidate_count':len(found),'candidates':list(found.values()),
         'records':records,'remaining_pages':len(remaining),'remaining_urls':list(remaining.values()),'complete':False,'limitation':'栏目抽取/有限分页；尚未验证年度时间范围完整性'}

def build_site_queries(sources,start,end):
 return build_recipe_plan(sources,start,end)

def load_catalog():
 rows=[]
 for file in ('source_catalog.json','aggregator_catalog.json','owner_catalog.json','legacy_catalog.json'):
  rows.extend(load(PACKAGE_ROOT/'config'/file,[]))
 return list({x['id']:x for x in rows}.values())

def run_scan(max_pages=4,workers=4,timeout=8,limit=None,resume=False):
 sources=load_catalog();now=datetime.now(ZoneInfo('Asia/Shanghai'));root=PACKAGE_ROOT/'data/source-audit';root.mkdir(exist_ok=True,parents=True)
 start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat()
 write_json(root/'site_query_plan.json',build_site_queries(sources,start,end))
 selected=sources[:limit] if limit else sources
 previous={r['source_id']:r for r in load(root/'scan_results.json',[])}
 merged=dict(previous) if resume else {};pending=[];skipped=0
 for s in selected:
  old=previous.get(s['id'],{});records=old.get('records',[])
  entry=normalize_url(s.get('active_url') or s['url'])
  same_entry=bool(records and normalize_url(records[0].get('url',''))==entry)
  if resume and same_entry:
   skipped+=1
   continue
  pending.append({**s,'pending_pages':old.get('remaining_urls',[]) if same_entry else [],'previous_candidates':old.get('candidates',[]) if same_entry else []})
 with ThreadPoolExecutor(max_workers=workers) as pool:
  futures={pool.submit(scan_source,s,Fetcher(timeout=timeout,interval=1,retries=0),max_pages,root/'evidence'):s for s in pending}
  for future in as_completed(futures):
   result=future.result();merged[result['source_id']]=result;write_json(root/'scan_results.json',list(merged.values()))
 results=list(merged.values());write_json(root/'scan_results.json',results)
 candidates=list({x['url']:x for r in results for x in r['candidates']}.values());write_json(root/'listing_candidates.json',candidates)
 report={'generated_at':now.isoformat(),'source_entries':len(sources),'unique_domains':len({d for s in sources for d in s['domains']}),
         'probed':len(results),'probed_this_run':len(pending),'skipped':skipped,'accessible':sum(r['pages_fetched']>0 for r in results),'with_candidates':sum(r['candidate_count']>0 for r in results),
         'failed':sum(r['pages_fetched']==0 for r in results),'pages':sum(r['pages_fetched'] for r in results),'candidates':len(candidates),
         'partial_errors':sum(r['status']=='partial_error' for r in results),'pages_failed':sum(r.get('pages_failed',sum(bool(p.get('error')) for p in r.get('records',[]))) for r in results),
         'complete_sources':0,'status':'partial'}
 write_json(root/'summary.json',report);return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--max-pages',type=int,default=4);p.add_argument('--workers',type=int,default=4);p.add_argument('--timeout',type=float,default=8);p.add_argument('--limit',type=int);p.add_argument('--resume',action='store_true',help='只探测新增或入口变化来源，保留已记录结果（含失败）')
 a=p.parse_args();print(json.dumps(run_scan(a.max_pages,a.workers,a.timeout,a.limit,a.resume),ensure_ascii=False))
