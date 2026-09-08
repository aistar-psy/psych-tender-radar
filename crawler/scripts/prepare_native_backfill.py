"""Merge native search candidates without turning search snippets into notices."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import match_recipes
from radar.source_scan import load_catalog,in_scope
from radar.pipeline import write_json
root=Path(__file__).resolve().parents[1];catalog={s['id']:s for s in load_catalog()};queries={}
for f in sorted((root/'data/native-search').glob('queries*.json')):
 for q in json.loads(f.read_text()):queries[q['id']]=q
candidates={};pending={}
for q in queries.values():
 if q.get('superseded'):continue
 s=catalog[q['source_id']]
 for row in q.get('records',[]):
  if row.get('link_verified') is False:continue
  if not in_scope(row['url'],s['domains']):continue
  if row.get('published_at') and not q['start']<=row['published_at']<=q['end']:continue
  matches=match_recipes(row['title'],row.get('snippet',''))
  item=dict(row,source_id=s['id'],region=s['region'],province=s['region'],query=q['keyword'],recipe_ids=matches,provider='native_search',source_status='listing_only',discovered_at=q['checked_at'],date_evidence='站内结果列表，正文待核验')
  (candidates if matches else pending)[row['url']]=item
for url in candidates:pending.pop(url,None)
write_json(root/'data/external-discovery/native_combined.json',list(candidates.values()))
write_json(root/'data/native-search/fulltext_pending.json',list(pending.values()))
write_json(root/'data/native-search/fetch_queue.json',list(candidates.values()))
print(json.dumps({'candidate_urls':len(candidates),'additional_fulltext_pending':len(pending)},ensure_ascii=False))
