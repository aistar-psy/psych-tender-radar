"""Re-analyze saved evidence without refetching; retain original snapshots for audit."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.documents import parse_document
from radar.analysis import analyze_document
from radar.pipeline import attachment_usable
from radar.report import render
root=Path(__file__).resolve().parents[1]
for folder in ('annual','runtime','validated'):
 for file in (root/'data'/folder/'runs').glob('*/documents.json'):
  docs=json.loads(file.read_text()); summary=json.loads((file.parent/'summary.json').read_text())
  original=file.with_name('documents.original.json')
  if not original.exists():original.write_text(file.read_text())
  for d in docs:
   base=None
   for i,ev in enumerate(d['evidence']):
    raw=Path(ev['path'])
    if not raw.exists():continue
    parsed=parse_document(raw.read_bytes(),ev['url'],ev['content_type'])
    if i==0:base=parsed;continue
    status=next((a['status'] for a in d.get('attachments',[]) if a['url']==ev['url']),None)
    if status not in ('ok','parsed') or not attachment_usable(parsed,ev['content_type']):continue
    base['blocks'].extend({**b,'source_url':ev['url']} for b in parsed['blocks']);base['text']+='\n'+parsed['text']
   if base:d['analysis']=analyze_document(base,d['url'],summary['window_end'])
  file.write_text(json.dumps(docs,ensure_ascii=False,indent=2))
  render(file.parent,summary,docs,json.loads((file.parent/'execution.json').read_text()),json.loads((file.parent/'backlog.json').read_text()))
  print(folder,len(docs))
