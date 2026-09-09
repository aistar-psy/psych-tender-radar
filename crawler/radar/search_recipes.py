"""Versioned A-F Boolean recipes, portable without assuming engine OR support.

Each atom is one AND clause. Their union equals the original expression. Native
single-keyword seeds are only supersets: original fields/logic must be checked on
retrieved titles/full text. Search snippets never establish full-text absence.
"""
import hashlib,json,re
from datetime import date,timedelta
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def load_recipes():
 return json.loads((Path(__file__).resolve().parent.parent/'config/search_recipes.json').read_text())

def clauses(expression):
 tokens=re.findall(r'\(|\)|\bAND\b|\bOR\b|[^\s()]+',expression);i=0
 def factor():
  nonlocal i
  if i>=len(tokens):raise ValueError('missing Boolean operand')
  t=tokens[i];i+=1
  if t=='(':
   result=union()
   if i>=len(tokens) or tokens[i]!=')':raise ValueError('unclosed expression')
   i+=1;return result
  if t in ('AND','OR',')'):raise ValueError('unexpected Boolean operator')
  return [(t,)]
 def intersection():
  nonlocal i
  result=factor()
  while i<len(tokens) and tokens[i]=='AND':
   i+=1;right=factor()
   if len(result)*len(right)>10000:raise ValueError('expression too large')
   result=[tuple(dict.fromkeys(a+b)) for a in result for b in right]
  return result
 def union():
  nonlocal i
  result=intersection()
  while i<len(tokens) and tokens[i]=='OR':i+=1;result+=intersection()
  return list(dict.fromkeys(result))
 result=union()
 if i!=len(tokens):raise ValueError('unexpected trailing expression')
 return result

def keyword_text(text):
 # Prevent the word boundary 中心 / 理化 from manufacturing a 心理 keyword.
 return str(text or '').replace('中心理化','中心 理化')

def match_recipes(title,fulltext=''):
 title=keyword_text(title);fulltext=keyword_text(fulltext)
 out=[]
 for r in load_recipes()['recipes']:
  text=title if r['field']=='title' else title+' '+fulltext
  if any(all(t.casefold() in text.casefold() for t in clause) for clause in clauses(r['syntax'])):out.append(r['id'])
 return out

def vocabulary_match(text):
 text=keyword_text(text)
 return bool(match_recipes(text) or any(t.casefold() in text.casefold() for f in load_recipes()['families'] for t in f['terms']))

def build_recipe_plan(sources,start,end):
 if date.fromisoformat(start)>date.fromisoformat(end):raise ValueError('invalid date window')
 exclusive=(date.fromisoformat(end)+timedelta(days=1)).isoformat();out=[]
 # Round robin across recipes and sources so limited slices do not starve F/B/C.
 recipes=load_recipes()['recipes'];groups={r['id']:clauses(r['syntax']) for r in recipes}
 for n in range(max(map(len,groups.values()))):
  for r in recipes:
   if n>=len(groups[r['id']]):continue
   terms=list(groups[r['id']][n]);atom=f"{r['id']}.{n+1:03d}"
   for s in sources:
    from urllib.parse import urlsplit
    active=urlsplit(s.get('active_url') or s.get('url','')).hostname
    domain=next((d for d in sorted(s['domains'],key=len) if active and (active==d or active.endswith('.'+d))),active or s['domains'][0])
    query=f'site:{domain} '+ ' '.join('"'+t+'"' for t in terms)+f' after:{start} before:{exclusive}'
    identity=[s['id'],atom,domain,start,end,load_recipes()['source_sha256']]
    out.append({'id':hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24], 'source_id':s['id'],'domain':domain,'query':query,
      'recipe_id':r['id'],'atom_id':atom,'terms':terms,'original_syntax':r['syntax'],'requested_field':r['field'],
      'effective_field':'search_index','field_verified':False,'start':start,'end':end,'status':'not_executed',
      'recipe_version':load_recipes()['version'],'recipe_sha256':load_recipes()['source_sha256']})
 return out

def seed_plan(atoms):
 """Lossless broad keyword cover, followed by original recipe local filtering.

 Shorter original terms reduce redundant requests (心理 covers 心理健康/心理测评).
 This does NOT assert native field, dates or pagination have been verified.
 """
 terms={t for a in atoms for t in a['terms']}
 terms=sorted(terms,key=lambda t:(-sum(any(t==part or t in ('心理','心育') and t in part for part in a['terms']) for a in atoms),len(t),t))
 out={}
 for a in atoms:
  keyword=next(t for t in terms if any(t==part or t in ('心理','心育') and t in part for part in a['terms']))
  key=(a['source_id'],keyword,a['start'],a['end'])
  if key not in out:out[key]={'source_id':a['source_id'],'keyword':keyword,'start':a['start'],'end':a['end'],'atom_ids':[],'recipe_ids':[],'field':'title_or_fulltext','postfilter_required':True}
  out[key]['atom_ids'].append(a['id'])
  if a['recipe_id'] not in out[key]['recipe_ids']:out[key]['recipe_ids'].append(a['recipe_id'])
 return list(out.values())


def build_region_plan(regions,start,end):
 sources=[{'id':r,'domains':['placeholder.invalid']} for r in dict.fromkeys(regions)]
 result=build_recipe_plan(sources,start,end)
 for row in result:
  row['region']=row.pop('source_id');row.pop('domain')
  row['query']=row['region']+' '+row['query'].split(' ',1)[1]
  row['channel']=row['recipe_id'];row['group_index']=int(row['atom_id'].split('.')[1])-1;row['primary']=row['group_index']==0
 return result
