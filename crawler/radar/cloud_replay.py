"""Analyze successful, hash-verified public downloads from the cloud fallback."""
import argparse,hashlib,json
from pathlib import Path
from . import pipeline
from .fetch import canonical_url,FetchError

def replay(manifest_path,root=None):
 manifest_path=Path(manifest_path).resolve();rows=json.loads(manifest_path.read_text());rows=rows.get('results',[]) if isinstance(rows,dict) else rows
 records={canonical_url(r['url']):r for r in rows if r.get('status')=='ok'}
 class CachedFetch:
  def __init__(self,*a,**kw):pass
  def __call__(self,url):
   r=records.get(canonical_url(url))
   if not r:raise FetchError('not_in_cloud_batch','本轮云端只补抓公告，附件或其他链接尚未下载',url)
   path=(manifest_path.parent/r['path']).resolve()
   if not path.is_relative_to(manifest_path.parent):raise ValueError('artifact path outside manifest directory')
   body=path.read_bytes()
   if hashlib.sha256(body).hexdigest()!=r['sha256']:raise ValueError('download hash mismatch')
   return {'body':body,'url':r.get('final_url') or r['url'],'content_type':r.get('content_type',''),'status_code':r.get('status_code',200),'sha256':r['sha256'],'fetched_at':r.get('read_at'),'provider':r.get('provider') or 'github_public_fetch'}
 return pipeline.run(root=Path(root) if root else pipeline.PACKAGE_ROOT/'data/cloud_replay',seeds=[u for u,r in records.items() if r.get('kind')!='attachment'],no_discovery=True,
   max_documents=len(records),max_attachments=8,max_seconds=900,window_days=365,fetcher=CachedFetch())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--data-dir');a=p.parse_args();print(json.dumps(replay(a.manifest,a.data_dir),ensure_ascii=False))
