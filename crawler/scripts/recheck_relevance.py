"""Recheck saved public texts with current relevance rules, without refetching.

The before snapshot and quarantined rows/texts remain private. Normal future
exports apply the same gate during enrichment; this is also useful after a
rule change when existing, unchanged body evidence can be reused.
"""
import argparse
import collections
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from radar.relevance import assess_relevance, attach_relevance_audit
from radar.public_safety import public_project_exclusion, redact_public
from radar.web_export import write_run_history


def refresh(public, audit_dir):
    public, audit_dir = Path(public), Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=False)
    raw = (public/'data.js').read_text()
    data = json.loads(raw[raw.index('{'):raw.rfind(';')])
    (audit_dir/'before.js').write_text(raw)
    # Load the complete history before write_run_history replaces its files.
    for run in data['runs']:
        if run.get('projectsRef'):
            obj = json.loads((public/run.pop('projectsRef')).read_text())
            run['projects'] = obj if isinstance(obj, list) else obj['projects']
    quarantined, reasons = [], {'archive': collections.Counter(), 'historicalRunRows': collections.Counter()}
    original_count = len(data['archiveProjects'])
    body_cache = {}

    def recheck(rows, scope):
        kept = []
        for p in rows:
            blocks = []
            for ref in p.get('fullTexts', []):
                path = ref['path']
                if not path.startswith('bodies/') or '..' in Path(path).parts:
                    raise ValueError('Invalid public body path')
                if path not in body_cache:
                    obj = json.loads((public/path).read_text())
                    body_cache[path] = [{'text': text, 'locator': path+':line:'+str(i),
                                         'source_url': ref.get('url', '')}
                                        for i, text in enumerate(obj.get('text', '').splitlines(), 1) if text.strip()]
                blocks.extend(body_cache[path])
            p['relevance'] = assess_relevance(p['title'], blocks, body_available=bool(blocks) and p.get('sourceQuality')=='正文已取得')
            if p['relevance']['status'] != 'related':
                p['amountEligible'] = False
            reason = public_project_exclusion(p)
            if reason:
                reasons[scope][reason] += 1
                quarantined.append({'scope': scope, 'reason': reason, 'project': p})
                for ref in p.get('fullTexts', []):
                    dest = audit_dir/ref['path']; dest.parent.mkdir(exist_ok=True, parents=True)
                    if not dest.exists(): shutil.copy2(public/ref['path'], dest)
            else:
                kept.append(p)
        return kept

    data['archiveProjects'] = recheck(data['archiveProjects'], 'archive')
    for run in data['runs']:
        run['projects'] = recheck(run.get('projects', []), 'historicalRunRows')
    built = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    annual = lambda p: any(data['yearRange']['start']<=str(d)[:10]<=data['yearRange']['end'] for d in [p.get('publishedAt')]+[e.get('publishedAt') for e in p.get('events', [])] if d)
    data['builtAt'] = built
    receipt = attach_relevance_audit(data, quarantined, audit_dir, public)
    for scope, counts in reasons.items():
        existing = data.setdefault('publicationExclusions', {}).setdefault(scope, {})
        for key,value in counts.items(): existing[key] = existing.get(key, 0)+value
    if 'sourceCoverage' in data:
        from radar.source_matrix import matrix
        from radar.fetch import canonical_url
        candidates = {}
        for f in (public.parent/'data/external-discovery').glob('*combined.json'):
            candidates.update({canonical_url(r['url']): r for r in json.loads(f.read_text()) if r.get('url')})
        data['sourceCoverage'] = matrix(data['archiveProjects'], candidates)
    if 'archiveCoverage' in data:
        data['archiveCoverage']['monthsCovered'] = sorted({str(p.get('publishedAt'))[:7] for p in data['archiveProjects'] if annual(p)})
    refs = {r['path'] for p in data['archiveProjects']+[p for run in data['runs'] for p in run['projects']] for r in p.get('fullTexts', [])}
    for f in (public/'bodies').glob('*.json'):
        if re.fullmatch(r'[a-f0-9]{64}\.json', f.name) and 'bodies/'+f.name not in refs:
            f.unlink()
    data = redact_public(data)
    write_run_history(data, public)
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')
    (public/'data.js').write_text('window.RADAR_DATA = '+encoded+';\n')
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.batch): parser.error('batch must be a simple name')
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(refresh(root/'publish', root/'data/relevance-audit'/args.batch), ensure_ascii=False))
