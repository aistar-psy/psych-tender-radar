"""Follow explicit original-publication/attachment links from saved public HTML."""
import json,re,sys,hashlib
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.documents import parse_document
from radar.pipeline import PACKAGE_ROOT,write_json
from radar.search_recipes import vocabulary_match
from radar.fetch import canonical_url
from radar.web_export import timestamp
from radar.recovery import latest_receipts
root=PACKAGE_ROOT;latest={};relations=[];queue={}
old_path=root/'data/source-trace/links.json'
old={(x['from_url'],x['to_url']):x for x in json.loads(old_path.read_text())} if old_path.exists() else {}
for m in sorted((root/'data/public-downloads').glob('*/manifest.json')):
 for r in json.loads(m.read_text()):
  if r.get('status')=='ok' and 'html' in r.get('content_type',''):
   prior=latest.get(r['url'])
   if not prior or timestamp(r.get('read_at'))>timestamp(prior[0].get('read_at')):latest[r['url']]=(r,m.parent/r['path'])
for r,path in latest.values():
 try:d=parse_document(path.read_bytes(),r.get('final_url') or r['url'],r['content_type'])
 except Exception:continue
 if not vocabulary_match(d.get('title','')+' '+d.get('text','')):continue
 for l in d.get('links',[])+[dict(l,kind='attachment') for l in r.get('frame_links',[])]+r.get('origin_links',[]):
  u=l['url'];p=urlsplit(u);txt=l.get('text','');host=p.hostname or ''
  attachment=l.get('kind')=='attachment'
  original=bool(re.search(r'原文|原始公告|来源网站|信息来源|查看来源|原公告链接',txt)) and p.path not in ('','/')
  # An exact matching notice title on another publisher is a trace candidate.
  matching_title=len(txt)>15 and d.get('title','') and (txt in d['title'] or d['title'] in txt) and host!=urlsplit(r['url']).hostname
  if not (attachment or original or matching_title) or p.scheme not in ('http','https'):continue
  if re.search(r'投诉操作手册|用户手册|系统操作手册|CA.*指南|办事指南|隐私|免责声明|APP\s*下载|下载\s*APP|下载中心|客户端下载',txt,re.I):continue
  rel={'from_url':r['url'],'to_url':u,'link_text':txt,'kind':'public_attachment' if attachment else 'original_publication_candidate','status':old.get((r['url'],u),{}).get('status','pending_read'),'evidence_sha256':r['sha256']};relations.append(rel)
  queue[canonical_url(u)]={'url':u,'title':txt,'kind':'attachment' if attachment else 'document','parent_url':r['url']}
receipts=latest_receipts(root)
for rel in relations:
 r=receipts.get(canonical_url(rel['to_url']),{})
 if r:rel.update(status='downloaded_pending_parse' if r['status']=='ok' else 'read_failed',read_at=r.get('read_at'),error_type=r.get('error_type'))
write_json(root/'data/source-trace/links.json',relations);write_json(root/'data/source-trace/fetch_queue.json',list(queue.values()));print('saved HTML',len(latest),'relations',len(relations),'unique linked documents',len(queue))
