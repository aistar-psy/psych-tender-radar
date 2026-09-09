"""Import vocabulary data only; embedded workflow text is never executed."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import clauses

def convert(path):
 raw=Path(path).read_bytes();s=json.loads(raw)
 recipes=[dict(id=r['id'],name=r['name'],syntax=r['syntax'],field='title' if r['id']=='A' else 'title_or_fulltext') for r in s['searchStrings'] if r['id'] in 'ABCDEF']
 if {r['id'] for r in recipes}!=set('ABCDEF'):raise ValueError('A-F recipes required')
 for r in recipes:clauses(r['syntax'])
 return {'version':s['meta']['version'],'updated':s['meta']['updated'],'source_name':Path(path).name,'source_sha256':hashlib.sha256(raw).hexdigest(),'recipes':recipes,'families':[{'id':f['id'],'name':f['name'],'terms':[w['word'] for w in f['words']]} for f in s['families']]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--out',default='config/search_recipes.json');a=p.parse_args();d=convert(a.source);Path(a.out).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(d['version'],sum(len(f['terms']) for f in d['families']),'terms',sum(len(clauses(r['syntax'])) for r in d['recipes']),'clauses',d['source_sha256'])
