"""Public SOP/configuration metadata, kept separate from historical collection."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .search_recipes import clauses
from .paths import public_dir

ROOT=Path(__file__).resolve().parents[1]
SUCCEEDED={'ok','empty','executed','completed','completed_with_candidates','completed_no_relevant_candidates','completed_empty_results','completed_no_new_original_match','completed_listing_only'}

def build_payload(config,snapshot,sop,report,queries,migration):
    digest=config['source_sha256']
    successful=[q for q in queries if q.get('recipe_sha256')==digest and q.get('status') in SUCCEEDED and q.get('atom_id') and q.get('recipe_id') in tuple('ABCDEF')]
    rows=snapshot.get('archiveProjects',[]);period=snapshot.get('yearRange',{})
    if period.get('start') and period.get('end'):
        rows=[p for p in rows if any(period['start']<=str(d)[:10]<=period['end'] for d in [p.get('publishedAt')]+[e.get('publishedAt') for e in p.get('events',[])] if d)]
    vocabulary=report.get('weeklyExecution',{}).get('vocabulary',{})
    return {'schemaVersion':1,'builtAt':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'configuration':{'version':config['version'],'updated':config['updated'],'sourceSha256':digest,
            'terms':sum(len(f['terms']) for f in config['families']),'atoms':sum(len(clauses(r['syntax'])) for r in config['recipes']),
            'families':[{'id':f['id'],'name':f['name'],'terms':f['terms']} for f in config['families']],
            'recipes':[{k:r[k] for k in ('id','name','syntax','field')}|{'atoms':len(clauses(r['syntax']))} for r in config['recipes']]},
        'lastDataset':{'builtAt':snapshot.get('builtAt'),'yearRange':period,'weekRange':snapshot.get('weekRange',{}),
            'records':len(rows),'bodies':sum(p.get('sourceQuality')=='正文已取得' for p in rows),
            'extractionVersions':sorted({p['keywordVersion'] for p in rows if p.get('keywordVersion')}),
            'executionVersion':vocabulary.get('version'),'executionSha256':vocabulary.get('source_sha256')},
        'migration':{'from':migration.get('from'),'to':config['version'],'addedTerms':migration.get('addedTerms',[]),
            'removedTerms':migration.get('removedTerms',[]),'changedRecipes':migration.get('changedRecipes',[]),
            'queriesExecuted':len(successful),'status':'partial' if successful else 'planned_not_executed','annualComplete':False},
        'sop':sop}

def export(root=None,out=None):
    root=Path(root or ROOT);out=Path(out or public_dir(root));out.mkdir(parents=True,exist_ok=True)
    read=lambda p:json.loads(p.read_text())
    config=read(root/'config/search_recipes.json');sop=read(root/'config/sop.json');migration=read(root/'config/vocabulary_migration.json')
    text=(out/'data.js').read_text();snapshot=json.loads(text[text.index('{'):text.rfind(';')])
    reports=[read(f) for f in (root/'data/recovery').glob('*/result.json')]
    report=next((r for r in reports if r.get('builtAt')==snapshot.get('builtAt')), {})
    queries=[]
    for f in (root/'data/external-discovery').glob('*_queries.json'):
        obj=read(f)
        if isinstance(obj,dict):queries.extend(obj.get('executed_queries',[]))
    payload=build_payload(config,snapshot,sop,report,queries,migration)
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e')
    (out/'sop-data.js').write_text('window.RADAR_SOP = '+encoded+';\n')
    assets=('sop.html','sop.css','sop-data.js','sop-state.js','sop.js')
    if all((out/name).exists() for name in assets):
        page=(out/'sop.html').read_text()
        page=page.replace('<link rel="stylesheet" href="sop.css?v=20261026">','<style>'+(out/'sop.css').read_text()+'</style>')
        for name in ('sop-data.js','sop-state.js','sop.js'):
            page=page.replace('<script src="'+name+'?v=20261026"></script>','<script>'+(out/name).read_text()+'</script>')
        for name in ('index.html','recovery-report.html','annual-projects.html','sop.html','sop-offline.html'):
            page=page.replace('href="'+name,'href="https://aistar-psy.github.io/psych-tender-radar/'+name)
        (out/'sop-offline.html').write_text(page)
    lines=['# '+sop['title'],'',f"规范版本：{sop['version']}；当前词库：{config['version']}；更新：{config['updated']}。",'',
        'SOP是操作规范。浏览器中的人工复核不是机器执行回执；配置升级不表示历史数据已按新版回补。','',
        '## 范围与边界','']
    lines+=['- '+x['name']+'：'+x['range']+'。'+x['boundary'] for x in sop['scope']]
    for step in sop['steps']:
        lines+=['','## '+step['title'],'','输入：'+step['input'],'']+['- '+x for x in step['actions']]+['','产物：'+step['output'],'','完成条件：'+step['acceptance'],'','失败处理：'+step['failure']]
        if step['commands']:lines+=['','在项目根目录运行；“本轮独立批次”等占位值须替换。','', '```sh']+step['commands']+['```']
    lines+=['','## 项目字段','']+['- '+x for x in sop['fields']]
    (root/'docs/每周采集SOP.md').write_text('\n'.join(lines)+'\n')
    return payload

if __name__=='__main__':
    p=export();print(json.dumps({'version':p['configuration']['version'],'terms':p['configuration']['terms'],'atoms':p['configuration']['atoms'],'migration':p['migration']['status']},ensure_ascii=False))
