"""Download candidate notice bodies with bounded concurrency; preserve evidence."""
import argparse,hashlib,json,sys,time
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.source_scan import is_challenge
from radar.pipeline import write_json
from radar.http import secure_session
from radar.paths import public_dir

# Support the local workspace and the published repository's crawler/ layout.
_root = Path(__file__).resolve().parents[1]
_worker_dir = public_dir(_root)
sys.path.insert(0, str(_worker_dir))
from fetch_public_notices import public_url as validate_url

def run(queue,out,workers=3):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'bodies').mkdir(exist_ok=True)
 rows=json.loads(Path(queue).read_text());old=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else [];results={x['url']:x for x in old}
 def fetch(row):
  url=row['url'];result={'url':url,'kind':row.get('kind','document'),'provider':'local_public_batch','read_at':datetime.now(timezone.utc).isoformat()}
  try:
   validate_url(url)
   with secure_session() as session, session.get(url,timeout=(10,20),stream=True) as r:
    result.update(status_code=r.status_code,final_url=r.url)
    r.raise_for_status();validate_url(r.url);body=b''
    for chunk in r.iter_content(65536):
     body+=chunk
     if len(body)>5*1024*1024:raise ValueError('body_limit')
    if ('html' in r.headers.get('Content-Type','').lower() or body.lstrip().lower().startswith((b'<html',b'<!doctype html'))) and is_challenge(body):raise ValueError('access_challenge')
    if not body.strip():raise ValueError('empty_body')
    digest=hashlib.sha256(body).hexdigest();path='bodies/'+digest+'.bin';(out/path).write_bytes(body)
    result.update(status='ok',status_code=r.status_code,path=path,sha256=digest,content_type=r.headers.get('Content-Type',''),final_url=r.url)
  except Exception as e:result.update(status='failed',error_type='access_challenge' if str(e)=='access_challenge' else type(e).__name__,error=str(e)[:1200])
  time.sleep(.35);return result
 pending=[r for r in rows if results.get(r['url'],{}).get('status')!='ok']
 with ThreadPoolExecutor(max_workers=workers) as pool:
  for i,f in enumerate(as_completed([pool.submit(fetch,r) for r in pending]),1):
   r=f.result();results[r['url']]=r
   if i%20==0:write_json(out/'manifest.json',list(results.values()));print(i,len(pending),'ok',sum(x['status']=='ok' for x in results.values()),flush=True)
 write_json(out/'manifest.json',list(results.values()));print({'total':len(results),'ok':sum(x['status']=='ok' for x in results.values())},flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('queue');p.add_argument('out');p.add_argument('--workers',type=int,default=3);a=p.parse_args();run(a.queue,a.out,a.workers)
