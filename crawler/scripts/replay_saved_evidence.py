"""Reparse saved public evidence into a fresh run, preserving previous snapshots."""
import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.cloud_replay import replay
from radar.fetch import canonical_url
from radar.web_export import timestamp

root=Path(__file__).resolve().parents[1]
cache=root/'data/reanalysis-cache';(cache/'bodies').mkdir(parents=True,exist_ok=True)
records={};seeds=set()

def add(url,ev,path,provider):
 if not path.exists():return
 previous=records.get(canonical_url(url))
 if previous and timestamp(previous.get('read_at'))>timestamp(ev.get('read_at') or ev.get('fetched_at')):return
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if digest!=ev.get('sha256'):raise ValueError('saved evidence hash mismatch')
 target=cache/'bodies'/(digest+'.bin')
 if not target.exists():os.link(path,target)
 records[canonical_url(url)]={'url':url,'final_url':ev.get('final_url') or ev.get('url') or url,'status':'ok','sha256':digest,
  'path':'bodies/'+digest+'.bin','content_type':ev.get('content_type',''),'read_at':ev.get('read_at') or ev.get('fetched_at'),'provider':provider}

for name in ('annual','runtime','validated','expanded','site_backfill'):
 base=root/'data'/name
 for f in (base/'runs').glob('*/execution.json'):
  for task in json.loads(f.read_text()):
   if task.get('kind')=='document' and task.get('url'):seeds.add(canonical_url(task['url']))
 for f in (base/'evidence').glob('*.json'):
  obj=json.loads(f.read_text());ev=obj.get('evidence',{})
  if ev.get('url') and ev.get('path'):add(ev['url'],ev,Path(ev['path']),ev.get('provider','local_http'))
 for f in (base/'runs').glob('*/documents.json'):
  for doc in json.loads(f.read_text()):
   if doc.get('evidence'):
    ev=doc['evidence'][0];add(doc['url'],ev,Path(ev['path']),ev.get('provider','local_http'))

for manifest in sorted((root/'data/cloud-downloads').glob('*/manifest.json')):
 rows=json.loads(manifest.read_text());rows=rows.get('results',[]) if isinstance(rows,dict) else rows
 attachment_batch='attachments' in manifest.parent.name
 for row in rows:
  if not attachment_batch and row.get('url'):seeds.add(canonical_url(row['url']))
  if row.get('status')=='ok':add(row['url'],row,manifest.parent/row['path'],'github_public_fetch')

for manifest in sorted((root/'data/public-downloads').glob('*/manifest.json')):
 rows=json.loads(manifest.read_text())
 for row in rows:
  if row.get('kind')!='attachment' and row.get('url'):seeds.add(canonical_url(row['url']))
  if row.get('status')=='ok':add(row['url'],row,manifest.parent/row['path'],row.get('provider','local_public_batch'))

for url,row in records.items():row['kind']='document' if url in seeds else 'attachment'
manifest=cache/'manifest.json';manifest.write_text(json.dumps(list(records.values()),ensure_ascii=False,indent=2))
print(json.dumps({'cached_urls':len(records),'replay_seeds':sum(r['kind']=='document' for r in records.values())}),flush=True)
print(json.dumps(replay(manifest,root/'data/reprocessed'),ensure_ascii=False),flush=True)
