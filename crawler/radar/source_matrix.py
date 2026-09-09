"""Separate registered scope, connection probes, indexed searches and actual reads."""
import json,re
from pathlib import Path
from urllib.parse import urlsplit
from .source_scan import load_catalog,in_scope
from .pipeline import PACKAGE_ROOT,load
from .search_audit import load_audits,audit_status
from .search_recipes import load_recipes,clauses

QUERY_SUCCEEDED={'ok','empty','executed','completed','completed_with_candidates','completed_no_relevant_candidates','completed_empty_results','completed_no_new_original_match','completed_listing_only'}
QUERY_PENDING={'not_executed','not_configured','running','planned','queued'}

def query_targets(query,domains):
 text=query.get('query','')
 operations=list(re.finditer(r'(?<![\w-])(-?)site:\s*(["\']?[^\s()"\']+["\']?)',text,re.I))
 if operations:
  # A domain metadata field must not turn an explicit -site exclusion into a hit.
  return any(not m.group(1) and in_scope('https://'+m.group(2).strip('"\''),domains) for m in operations)
 domain=query.get('domain')
 return bool(domain and in_scope('https://'+domain,domains))

def query_logs():
 rows=[]
 for f in (PACKAGE_ROOT/'data/external-discovery').glob('*_queries.json'):
  obj=load(f,{})
  if isinstance(obj,dict):rows.extend({**x,'log':f.name} for x in obj.get('executed_queries',[]))
 return rows

def public_issue(errors,probe):
 text=' '.join(str(x) for x in errors)
 if re.search(r'SSL|TLS|CERTIFICATE|certificate',text):return '本机安全连接未成功，已转入补读或重试队列'
 if re.search(r'timed? out|timeout|超时',text,re.I):return '网站连接或读取超时，待重试'
 if '404' in text:return '入口返回404，需核对最新地址'
 if re.search(r'403|401|429|blocked|challenge|captcha',text,re.I):return '网站拒绝访问或需要验证'+('（HTTP '+re.search(r'403|401|429',text).group(0)+'）' if re.search(r'403|401|429',text) else '')+'，公开内容待补'
 if 'redirect' in text:return '入口发生跳转，需核验新网址'
 if errors:return '本轮连接或检索未成功，已保留诊断记录'
 return '有限栏目读取，年度分页未完成' if probe.get('pages_fetched') else '尚无本地栏目读取证据'

def matrix(projects,candidates):
 native,checks,total_atoms=load_audits(PACKAGE_ROOT)
 catalog=load_catalog();probes={r['source_id']:r for r in load(PACKAGE_ROOT/'data/source-audit/scan_results.json',[])};logs=query_logs();rows=[]
 for s in catalog:
  dom=s['domains'];r=probes.get(s['id'],{});targeted=[q for q in logs if query_targets(q,dom)]
  qs=[q for q in targeted if q.get('status') in QUERY_SUCCEEDED]
  failed_qs=[q for q in targeted if q.get('status') not in QUERY_SUCCEEDED|QUERY_PENDING]
  hits={u for u in candidates if in_scope(u,dom)}
  docs={e['url'] for p in projects for e in p.get('events',[]) if in_scope(e.get('url',''),dom)}
  audit=audit_status([q for q in native if q.get('source_id')==s['id']],checks.get(s['id'],{}),total_atoms)
  state='已取得部分正文' if docs else '已发现线索·正文待补' if hits else '站内已发现结果·待筛选入库' if audit['nativeResultUrls'] else '站外索引未命中·站内未核实' if qs else '定向检索失败·待重试' if failed_qs else '连接探测失败·待重试' if r and not r.get('pages_fetched') else '栏目读取部分失败·待重试' if r.get('status')=='partial_error' else '仅连接探测·待接检索' if r else '待接入'
  errors=[x.get('error') for x in r.get('records',[]) if x.get('error')]
  errors.extend(q.get('error') or '检索未确认成功：'+str(q.get('status','unknown')) for q in failed_qs)
  rows.append({'id':s['id'],'name':s['name'],'url':s.get('active_url') or s['url'],'registeredUrl':s['url'],'tier':s['tier'],'region':s['region'],
     'domains':dom,'probeStatus':r.get('status','unprobed'),'pages':r.get('pages_fetched',0),'indexQueries':len(qs),
     'queryAttempts':len(qs)+len(failed_qs),'failedQueries':len(failed_qs),'unexecutedQueries':sum(q.get('status') in QUERY_PENDING for q in targeted),
     **audit,'indexRecipeAtoms':len({q.get('atom_id') for q in qs if q.get('atom_id') and q.get('recipe_sha256')==load_recipes()['source_sha256']}),'candidates':len(hits),'documents':len(docs),'coverageStatus':state,'issue':audit['diagnosis'] or public_issue(errors,r),
     'provenance':s.get('provenance_url'),'checkedAt':r.get('checked_at'),'complete':False})
 return {'sources':rows,'searchRecipes':[{**r,'atoms':len(clauses(r['syntax']))} for r in load_recipes()['recipes']], 'recipeVersion':load_recipes()['version'],'summary':{'registered':len(rows),'domains':len({d for r in rows for d in r['domains']}),
   'probed':sum(r['probeStatus']!='unprobed' for r in rows),'accessible':sum(r['pages']>0 for r in rows),
   'queried':sum(r['indexQueries']>0 for r in rows),'withDocuments':sum(r['documents']>0 for r in rows),'complete':0,
   'nativeSources':sum(r['nativePages']>0 for r in rows),'nativePages':sum(r['nativePages'] for r in rows),'verifiedEmpty':sum(r['verifiedEmpty'] for r in rows),
   'failedQueries':sum(r['failedQueries'] for r in rows),
   'provinceQueries':len({q.get('region') for q in logs if q.get('region') in set(load(PACKAGE_ROOT/'config/regions.json',[])) and q.get('status') in QUERY_SUCCEEDED})},
   'limitation':'登记网站不是已完成采集；首页可访问不是检索成功；已发现部分公告不是近一年完整覆盖。省级查询仅计检索地区，不自动记为该省每个网站已检索。商业付费及非公开数据存在缺口。'}
