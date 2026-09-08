"""Evidence-based native search status; engine emptiness is never source absence."""
import json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .search_recipes import load_recipes,clauses

def audit_status(queries,check,total_atoms):
 attempted={a for q in queries for a in q.get('atom_ids',[])}
 paged={a for q in queries if q.get('pagination_complete') for a in q.get('atom_ids',[])}
 verified={a for q in queries if q.get('pagination_complete') and q.get('field_verified') and q.get('date_verified') and q.get('fulltext_status')=='verified' for a in q.get('atom_ids',[])}
 hits={x['url'] for q in queries for x in q.get('records',[])};visible={x['title'] for q in queries for x in q.get('listings',[])};pages=[p for q in queries for p in q.get('pages',[])];failed=[p for p in pages if p.get('status')!='ok']
 empty=len(verified)==total_atoms and not hits and not visible and not failed
 labels={'connection_failed':'站内连接未成功','challenge':'站内需要人机验证','registration_prompt':'站内出现注册提示','render_failed':'检索页未加载出结果','entry_only':'仅入口可访问·站内检索待核实','not_tested':'站内尚未核实','native_results':'站内结果已验证·详情待补'}
 native='站内已返回结果' if hits or visible else '原式与年度分页已核验·无命中' if empty else '站内请求失败·待补' if failed else '部分词无命中·不足以判定网站无信息' if queries else labels.get(check.get('status'),'站内尚未核实')
 return {'nativeStatus':native,'nativeQueries':len(queries),'nativePages':sum(x.get('status')=='ok' for x in pages),'nativeFailedPages':len(failed),
  'recipeAtomsAttempted':len(attempted),'recipeAtomsPaged':len(paged),'recipeAtomsPlanned':total_atoms,'nativeResultUrls':len(hits),'nativeVisibleRows':len(visible),
  'verifiedEmpty':empty,'paginationStatus':f"{sum(x.get('pagination_complete',False) for x in queries)} / {len(queries)} 条检索翻页完毕" if queries else '尚无站内分页证据',
  'diagnosis':check.get('reason','')}

def load_audits(root):
 def read(path,default):
  try:return json.loads(path.read_text())
  except FileNotFoundError:return default
 now=datetime.now(ZoneInfo('Asia/Shanghai'));start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat()
 all_queries=list({q['id']:q for f in sorted((root/'data/native-search').glob('queries*.json')) for q in read(f,[])}.values())
 # Historical windows remain evidence, but never count towards current completion.
 queries=[q for q in all_queries if q.get('start')==start and q.get('end')==end and q.get('recipe_sha256')==load_recipes()['source_sha256'] and not q.get('superseded')]
 return queries,{r['source_id']:r for r in read(root/'data/source-audit/native_checks.json',[])},sum(len(clauses(r['syntax'])) for r in load_recipes()['recipes'])
