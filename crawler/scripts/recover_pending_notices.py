"""Repeatable HTTP -> browser -> source/attachment -> parse/export recovery."""
import argparse,json,os,subprocess,sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.documents import parse_document
from radar.analysis import analyze_document
from radar.recovery import recovery_queue
from radar.fetch import canonical_url
from radar.paths import public_dir
ROOT=Path(__file__).resolve().parents[1]


def browser_queue(queue, manifest):
    manifest=Path(manifest)
    rows={canonical_url(r['url']):r for r in json.loads(manifest.read_text())}
    pending=[]
    for seed in queue:
        row=rows.get(canonical_url(seed['url']),{})
        if row.get('status')!='ok':pending.append(seed);continue
        try:
            d=parse_document((manifest.parent/row['path']).read_bytes(),row.get('final_url') or row['url'],row.get('content_type',''))
            analysis=analyze_document(d,seed['url'],datetime.now().astimezone().isoformat())
            if d.get('content_status')=='unavailable' or analysis.get('is_procurement') is not True:pending.append(seed)
        except Exception:pending.append(seed)
    return pending


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--queue');parser.add_argument('--batch',default=datetime.now().strftime('%Y%m%dT%H%M%S')+'-recovery');parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();base=ROOT/'data/recovery'/args.batch;base.mkdir(parents=True,exist_ok=True)
    source=(public_dir(ROOT)/'data.js').read_text();data=json.loads(source[source.index('{'):source.rfind(';')])
    queue=json.loads(Path(args.queue).read_text()) if args.queue else recovery_queue(data)
    q=base/'queue.json';q.write_text(json.dumps(queue,ensure_ascii=False,indent=2))
    if not (base/'before.json').exists():(base/'before.json').write_text(json.dumps(data,ensure_ascii=False))
    if args.prepare_only:print(json.dumps({'queue':str(q),'count':len(queue)}));return
    def run(*parts):subprocess.run([str(p) for p in parts],cwd=ROOT,check=True)
    http=ROOT/'data/public-downloads'/(args.batch+'-http');browser=ROOT/'data/public-downloads'/(args.batch+'-browser');linked=ROOT/'data/public-downloads'/(args.batch+'-linked')
    run(sys.executable,'scripts/fetch_public_batch.py',q,http,'--workers','3')
    browser_rows=browser_queue(queue,http/'manifest.json');bq=base/'browser.json';bq.write_text(json.dumps(browser_rows,ensure_ascii=False,indent=2))
    if browser_rows:run('node','scripts/browser_notice_fetch.cjs',bq,browser,'3')
    for _ in range(2):
        run(sys.executable,'scripts/trace_public_sources.py')
        run(sys.executable,'scripts/fetch_public_batch.py','data/source-trace/fetch_queue.json',linked,'--workers','3')
    run(sys.executable,'scripts/replay_saved_evidence.py')
    run(sys.executable,'-m','radar.web_export')
    run(sys.executable,'scripts/recovery_report.py','--before',base/'before.json','--batch',args.batch)
    print(json.dumps({'batch':args.batch,'queue':len(queue),'browser_queue':len(browser_rows),'status':'exported; inspect actual body counts and remaining gaps before publishing'}))

if __name__=='__main__':main()
