"""Evidence-backed display fields; never turn snippets into acquired bodies."""
import hashlib,json,re
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlsplit
from .search_recipes import load_recipes,keyword_text,match_recipes

def match_evidence(title,blocks,url,body_label='正文'):
 sources=[{'text':title,'locator':'title','source_url':url,'field':'标题'}]+[{**b,'field':body_label} for b in blocks]
 out=[]
 for family in load_recipes()['families']:
  for term in family['terms']:
   for b in sources:
    text=keyword_text(b.get('text',''));i=text.casefold().find(term.casefold())
    if i>=0:
     out.append({'term':term,'point':family['name'],'field':b['field'],'locator':b.get('locator','document'),'url':b.get('source_url',url),'text':text[max(0,i-50):i+len(term)+90]});break
 return out

def awarded_suppliers(title,blocks,url):
 if not re.search(r'(?:中标|成交).*?(?:公告|结果|通知书)',title) or re.search(r'候选|废标|终止|更正',title):return []
 out=[];seen=set();headers={}
 def add(value,b):
  name=value.strip(' ：:　').split('供应商地址')[0].strip()
  if not 3<=len(name)<=100 or re.search(r'详见|填写|名称|联系人|地址|资格|不得|应当|应具备|^/|^无$',name):return
  if name not in seen:seen.add(name);out.append({'name':name,'url':b.get('source_url',url),'locator':b.get('locator','document'),'text':b['text']})
 for b in blocks:
  line=b.get('text','');cells=[s.strip() for s in line.split('|')];key=(b.get('source_url',url),b.get('locator','').rsplit('/row:',1)[0])
  for m in re.finditer(r'(?:供应商名称|中标(?:单位|人)(?:名称)?|成交(?:供应商|单位)(?:名称)?)\s*[:：]\s*([^\n|；;]{3,100})',line):add(m[1],b)
  if b.get('kind')=='table_row':
   indices=[i for i,c in enumerate(cells) if re.fullmatch(r'供应商名称|中标单位(?:名称)?|成交供应商(?:名称)?',c)]
   if indices:
    if len(cells)==2 and indices==[0]:add(cells[1],b)
    else:headers[key]=indices
   elif key in headers:
    for i in headers[key]:
     if i<len(cells):add(cells[i],b)
 return out

def purchase_time(blocks,published):
 values=[];headers={}
 for b in blocks:
  text=b.get('text','');cells=[s.strip() for s in text.split('|')];key=(b.get('source_url',''),b.get('locator','').rsplit('/row:',1)[0])
  if b.get('kind')=='table_row':
   indices=[i for i,c in enumerate(cells) if re.search(r'预计采购时间|计划采购时间',c)]
   if indices:headers[key]=indices
   elif key in headers:
    for i in headers[key]:
     if i<len(cells):
      m=re.search(r'(20\d{2})[年/-](\d{1,2})',cells[i])
      if m:values.append(f'{m[1]}-{int(m[2]):02}')
  m=re.search(r'(?:预计采购时间|计划采购时间)\s*[:：]\s*(20\d{2})[年/-](\d{1,2})',text)
  if m:values.append(f'{m[1]}-{int(m[2]):02}')
 return {'value':'、'.join(dict.fromkeys(values)),'label':'预计采购月份'} if values else {'value':published,'label':'公告发布'}

@lru_cache(maxsize=3000)
def parsed_evidence(path):
 try:
  parsed=json.loads(Path(path).with_suffix('.json').read_text()).get('parsed',{})
  raw=Path(path).read_bytes()
  if b'<html' in raw[:2000].lower() or b'<!doctype html' in raw[:2000].lower():
   from .documents import parse_document
   # Recheck historical HTML with current body/summary rules.
   ev=json.loads(Path(path).with_suffix('.json').read_text()).get('evidence',{})
   return parse_document(raw,ev.get('url','https://invalid.example/'),'text/html')
  return parsed
 except (OSError,ValueError):return {}

def document_parts(d):
 out=[]
 for i,ev in enumerate(d.get('evidence',[])):
  if i==0 and d.get('main_content_status')=='unavailable':continue
  parsed=parsed_evidence(ev.get('path',''))
  if parsed.get('status') not in ('ok','parsed','partial') or parsed.get('content_status')=='unavailable':continue
  blocks=[{**b,'source_url':ev.get('url') or d['url']} for b in parsed.get('blocks',[])];text=parsed.get('text') or '\n'.join(b['text'] for b in blocks)
  if not text.strip():continue
  out.append({'title':parsed.get('title') or d['analysis'].get('title'),'url':ev.get('url') or d['url'],'readAt':ev.get('fetched_at'),'sha256':ev.get('sha256'),'kind':'公告正文' if i==0 else '公开附件','text':text,'blocks':blocks,'contentType':ev.get('content_type'),'provider':ev.get('provider')})
 return out

def enrich(projects,documents,out):
 by_url={d['url']:d for d in documents};parts={};out=Path(out);bodydir=out/'bodies';bodydir.mkdir(exist_ok=True)
 from .source_scan import load_catalog
 catalog=load_catalog()
 tracefile=Path(__file__).resolve().parents[1]/'data/source-trace/links.json'
 traces=json.loads(tracefile.read_text()) if tracefile.exists() else []
 def source_name(url):
  host=urlsplit(url).hostname or ''
  return next((s['name'] for s in catalog if any(host==h or host.endswith('.'+h) for h in s['domains'])),host)
 for p in projects:
  urls=list(dict.fromkeys([p['sourceUrl']]+[e['url'] for e in p.get('events',[])]));allblocks=[];refs=[];winners=[]
  for url in urls:
   d=by_url.get(url)
   if not d:continue
   if url not in parts:parts[url]=document_parts(d)
   blocks=[b for part in parts[url] for b in part['blocks']];allblocks+=blocks
   winners+=awarded_suppliers(d['analysis']['title'],blocks,url)
   for part in parts[url]:
    # Text is stored separately to keep the searchable index small.
    content={k:v for k,v in part.items() if k!='blocks'};encoded=json.dumps(content,ensure_ascii=False)
    name=hashlib.sha256(encoded.encode()).hexdigest()+'.json';target=bodydir/name
    if not target.exists():target.write_text(encoded)
    refs.append({k:v for k,v in content.items() if k!='text'}|{'path':'bodies/'+name,'characters':len(part['text'])})
  if p.get('sourceQuality')=='正文已取得' and not refs:
   p.update(sourceQuality='搜索线索待核验',amountEligible=False,detailStatus='历史页面仅有摘要或正文不可用，待追查原始发布源')
  body_obtained=p.get('sourceQuality')=='正文已取得'
  matchblocks=allblocks if body_obtained else [{'text':x['text'],'locator':'search_snippet','source_url':x['url']} for x in p.get('parameters',[])]
  hits=match_evidence(p['title'],matchblocks,p['sourceUrl'],'正文' if body_obtained else '搜索摘要待核验')
  p.update(keywordVersion=load_recipes()['version'],matchEvidence=hits,matchedTerms=list(dict.fromkeys(h['term'] for h in hits)),matchPoints=list(dict.fromkeys(h['point'] for h in hits)),recipeIds=match_recipes(p['title'],'\n'.join(b['text'] for b in matchblocks)),winners=list({(w['name'],w['url']):w for w in winners}.values()),fullTexts=list({ref['path']:ref for ref in refs}.values()),procurementTime=purchase_time(allblocks,p.get('publishedAt')),sourceNames=list(dict.fromkeys(source_name(u) for u in urls)),sourceLinks=[{'name':source_name(u),'url':u} for u in urls])
  read_links={x['url'] for x in refs}
  p['sourceTrace']=[{'fromUrl':t['from_url'],'url':t['to_url'],'label':t['link_text'],'kind':'公开附件' if t['kind']=='public_attachment' else '原文跳转链接','status':'已取得文本' if t['to_url'] in read_links else ('读取失败，待补抓' if t.get('status')=='read_failed' else '响应或跳转待核实')} for t in traces if t['from_url'] in urls]
  p['winnerStatus']='正文提取，按原公告复核' if winners else '未取得中标信息'
 return projects
