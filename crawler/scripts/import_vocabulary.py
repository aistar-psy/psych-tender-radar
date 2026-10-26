"""Import vocabulary data only; embedded workflow text is never executed."""
import argparse,hashlib,json,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import clauses

def import_file(source,out):
 d=convert(source);out=Path(out)
 if out.exists():
  previous=json.loads(out.read_text())
  version=lambda v:tuple(int(x) for x in re.findall(r'\d+',v))
  if version(d['version'])<version(previous['version']) or (d['version']==previous['version'] and d['updated']<previous['updated']):
   raise ValueError('旧版本词库不能覆盖当前配置；请核对版本和更新日期')
  if out.name=='search_recipes.json' and re.fullmatch(r'V?\d+(?:\.\d+)*',previous['version']):
   history=out.parent/'vocabulary_history';history.mkdir(exist_ok=True)
   archived=history/(previous['version']+'.json')
   if not archived.exists():archived.write_bytes(out.read_bytes())
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 return d

def convert(path):
 raw=Path(path).read_bytes();s=json.loads(raw)
 recipes=[dict(id=r['id'],name=r['name'],syntax=r['syntax'],field='title' if r['id']=='A' else 'title_or_fulltext') for r in s['searchStrings'] if r['id'] in 'ABCDEF']
 if {r['id'] for r in recipes}!=set('ABCDEF'):raise ValueError('A-F recipes required')
 for r in recipes:clauses(r['syntax'])
 return {'version':s['meta']['version'],'updated':s['meta']['updated'],'source_name':Path(path).name,'source_sha256':hashlib.sha256(raw).hexdigest(),'recipes':recipes,'families':[{'id':f['id'],'name':f['name'],'terms':[w['word'] for w in f['words']]} for f in s['families']]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--out',default='config/search_recipes.json');a=p.parse_args();d=import_file(a.source,a.out);print(d['version'],sum(len(f['terms']) for f in d['families']),'terms',sum(len(clauses(r['syntax'])) for r in d['recipes']),'clauses',d['source_sha256'])
