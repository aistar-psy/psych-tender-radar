"""Export an allowlisted public snapshot, separate from crawler internals."""
import argparse
import json
import re
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from .report import opportunity_state
from .fetch import canonical_url
from .search_recipes import vocabulary_match
from .paths import public_dir

ROOT=Path(__file__).resolve().parent.parent

def clean(value):
    if value is None:return None
    value=str(value)
    value=re.sub(r'(?:/Users/|/private/|/home/)[^\s|<>]*','[本地记录]',value)
    value=re.sub(r'\ue200[^\ue201]*\ue201|\[wordlim:\s*\d+\]','',value)
    return value

def link(value):
    if not isinstance(value,str):return ''
    try:
        p=urlsplit(value)
        if p.scheme in ('http','https') and p.hostname and not p.username and not p.password:return value
    except ValueError:pass
    return ''

def public_rows(rows,keys):
    output=[];seen=set();contexts={};names={}
    for row in rows or []:
        item={k:link(row.get(k)) if k=='url' else clean(row.get(k)) for k in keys}
        marker=json.dumps(item,sort_keys=True,ensure_ascii=False)
        if marker in seen:continue
        seen.add(marker)
        if 'name' in keys:
            context=json.dumps({k:v for k,v in item.items() if k!='name'},sort_keys=True,ensure_ascii=False)
            if context in contexts:
                if item.get('name') and item['name'] not in names[context]:
                    names[context].append(item['name']);contexts[context]['name']='、'.join(names[context])
                continue
            contexts[context]=item;names[context]=[item['name']] if item.get('name') else []
        output.append(item)
    return output

def public_run(summary,documents,tasks):
    by_region=defaultdict(lambda:{'planned':0,'executed':0,'failed':0,'unexecuted':0})
    coverage={'planned':0,'executed':0,'failed':0,'unexecuted':0,'registered':0,'byRegion':[]}
    for task in tasks:
        if task.get('kind')=='source_registry':coverage['registered']+=1;continue
        if task.get('kind') not in ('search','listing'):continue
        state=task.get('status','not_executed');region=task.get('region') or '全国'
        counts=by_region[region]
        for bucket in (coverage,counts):
            bucket['planned']+=1
            if state in ('not_executed','not_configured','running'):bucket['unexecuted']+=1
            else:
                bucket['executed']+=1
                if state not in ('ok','empty'):bucket['failed']+=1
    coverage['byRegion']=[{'region':clean(k),**v} for k,v in by_region.items()]
    grouped=defaultdict(list)
    for d in documents:grouped[d['project_id']].append(d)
    projects=[]
    for pid,items in grouped.items():
        # Latest publication drives metadata; all notices retain their own parameter evidence.
        primary=max(items,key=lambda d:(d['analysis'].get('published_at') or '',d.get('fetched_at') or ''))
        a=primary['analysis'];gaps=[];events=[]
        for d in items:
            da=d['analysis'];events.append({'title':clean(da.get('title')),'type':clean(da.get('notice_type')),
                'url':link(d.get('url')),'publishedAt':clean(da.get('published_at')),'deadline':clean(da.get('deadline'))})
            if d.get('main_content_status')=='unavailable':
                gaps.append({'name':'公告正文','status':'未取得','reason':'公告页正文不可用，当前采购内容取自其公开附件；需回到各附件核验。','url':link(d.get('url'))})
            if not d.get('attachments'):
                gaps.append({'name':'完整采购文件','status':'未取得','reason':'公告未发现公开附件；细化技术参数可能需另行获取。','url':link(d.get('url'))})
            for att in d.get('attachments',[]):
                if att.get('status') not in ('ok','parsed'):
                    reasons={'blocked':'访问受限','network_error':'网络请求未成功','deferred':'本轮预算未处理','needs_ocr':'扫描件需OCR','access_page':'只取得登录或权限页面'}
                    gaps.append({'name':clean(att.get('name') or '采购附件'),'status':clean(att.get('status')),
                                 'reason':reasons.get(att.get('status'),'文件尚未完成读取或解析'),'url':link(att.get('url'))})
        amounts=[]
        for m in a.get('amounts',[]):
            amounts.append({'type':clean(m.get('type')),'value':m.get('value') if isinstance(m.get('value'),(int,float)) else None,
                            'currency':clean(m.get('currency')),'raw':clean(m.get('raw'))})
        as_of=summary.get('actual_started_at') or summary.get('window_end') or datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        projects.append({'id':str(pid),'title':clean(a.get('title') or '标题待核验'),'category':clean(a.get('category') or '待核验'),
            'buyer':clean(a.get('buyer')),'number':clean(a.get('project_number')),'publishedAt':clean(a.get('published_at')),
            'deadline':clean(a.get('deadline')),'status':opportunity_state(a,as_of),'detailStatus':clean(primary.get('detail_status') or '待核验'),
            'sourceUrl':link(primary.get('url')),'amounts':amounts,
            'province':clean(a.get('province')),'buyerType':clean(a.get('buyer_type')),
            'openingAt':clean(a.get('opening_at')),'bidAt':clean(a.get('bid_at')),
            'sourceQuality':'正文已取得','fetchMode':'普通浏览器渲染' if any(e.get('provider')=='public_browser' for e in primary.get('evidence',[])) else ('云端公开HTTP' if any(e.get('provider')=='github_public_fetch' for e in primary.get('evidence',[])) else '本机公开HTTP'),'amountEligible':a.get('category') in ('教育核心','教育相关','其他心理') and a.get('notice_type')!='采购意向',
            'amountScope':'金额为规则提取候选；同类多值或批次意向不计入合计',
            'products':public_rows([p for d in items for p in d['analysis'].get('products',[])],('name','text','locator','url')),
            'parameters':public_rows([p for d in items for p in d['analysis'].get('parameters',[])],('text','locator','url')),
            'events':events,'gaps':gaps})
        if any('更正' in (e.get('type') or '') or '更正' in (e.get('title') or '') for e in events):
            projects[-1].update(amountEligible=False,amountScope='存在更正公告，字段生效关系待复核，不计入合计')
    rank={'教育核心':0,'教育相关':1,'其他心理':2,'待核验':3,'排除':4}
    projects.sort(key=lambda p:(rank.get(p['category'],5),p['title']))
    return {'id':summary['run_id'],'label':('综合试跑' if coverage['planned'] else '详情补抓')+' · '+summary.get('window_end','')[:10],
            'start':summary.get('window_start'),'end':summary.get('window_end'),
            'executedAt':summary.get('actual_started_at'),'status':summary.get('status','partial'),'coverage':coverage,'projects':projects}

def merge_project(newer,older):
    primary,secondary=(newer,older) if (newer.get('publishedAt') or '') >= (older.get('publishedAt') or '') else (older,newer)
    result=dict(primary)
    for field in ('events','parameters','products','gaps'):
        seen=set();values=[]
        for item in primary.get(field,[])+secondary.get(field,[]):
            k=json.dumps(item,ensure_ascii=False,sort_keys=True)
            if k not in seen:seen.add(k);values.append(item)
        result[field]=values
    if any('更正' in (e.get('type') or '') or '更正' in (e.get('title') or '') for e in result['events']):
        result.update(amountEligible=False,amountScope='含更正与历史公告，字段生效待复核，不计入合计')
    result['detailStatus']='含多份公告/历史参数证据，按各自来源核验有效性'
    return result

def cloud_attempts(directory):
    latest={}
    for path in Path(directory).glob('*/manifest.json'):
        rows=json.loads(path.read_text());rows=rows.get('results',[]) if isinstance(rows,dict) else rows
        for row in rows:
            if not link(row.get('url')):continue
            url=canonical_url(row['url'])
            if url not in latest or (row.get('read_at') or '') > (latest[url].get('read_at') or ''):latest[url]=row
    failed={u:'cloud_'+(r.get('error_type') or 'failed') for u,r in latest.items() if r.get('status')!='ok'}
    return {'attempted':len(latest),'downloaded':sum(r.get('status')=='ok' for r in latest.values()),'failed':len(failed),
        'scope':'公开HTTP正文下载；取得响应不等于已取得有效采购公告，仍须经过正文解析与采购属性检查'},failed

def latest_document_versions(documents):
    latest={}
    for document in documents:
        url=canonical_url(document['url'])
        if url not in latest or timestamp(document.get('fetched_at')) > timestamp(latest[url].get('fetched_at')):latest[url]=document
    return list(latest.values())

def timestamp(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError):return 0

def export(out=None,run_dirs=None):
    out=Path(out or public_dir(ROOT));out.mkdir(parents=True,exist_ok=True)
    if run_dirs is None:
        snapshots=list((ROOT/'data/reprocessed/runs').glob('*/summary.json'))+list((ROOT/'data/cloud_replay/runs').glob('*/summary.json'))+list((ROOT/'data/site_backfill/runs').glob('*/summary.json'))+list((ROOT/'data/expanded/runs').glob('*/summary.json'))+list((ROOT/'data/annual/runs').glob('*/summary.json'))+list((ROOT/'data/runtime/runs').glob('*/summary.json'))+list((ROOT/'data/validated/runs').glob('*/summary.json'))
        run_dirs=[p.parent for p in sorted(snapshots,key=lambda p:p.stat().st_mtime,reverse=True)]
    rejected_path=ROOT/'data/external-discovery/v15_rejected.json'
    rejected_urls={canonical_url(r['url']) for r in json.loads(rejected_path.read_text())} if rejected_path.exists() else set()
    run_documents={};runs=[];read_urls=set();task_status={};task_times={};task_details={};all_documents=[]
    for directory in run_dirs:
        directory=Path(directory)
        read=lambda name:json.loads((directory/name).read_text(encoding='utf-8'))
        documents=[d for d in read('documents.json') if canonical_url(d['url']) not in rejected_urls];tasks=read('execution.json');summary=read('summary.json')
        all_documents.extend(documents)
        read_urls.update(canonical_url(d['url']) for d in documents)
        for t in tasks:
            if t.get('kind')=='document' and t.get('url'):
                if t.get('status') in ('not_in_cloud_batch','not_executed','deferred_document'):continue
                u=canonical_url(t['url']);when=timestamp(t.get('executed_at') or summary.get('actual_started_at'))
                if u not in task_times or when>task_times[u]:task_times[u]=when;task_status[u]=t['status'];task_details[u]=t
        runs.append(public_run(summary,documents,tasks));run_documents[summary['run_id']]=documents
    runs.sort(key=lambda r:r.get('executedAt') or '',reverse=True)
    latest_documents=[d for d in latest_document_versions(all_documents) if task_status.get(canonical_url(d['url'])) not in ('content_unconfirmed','not_procurement')]
    read_urls={canonical_url(d['url']) for d in latest_documents}
    preferred=next((r for r in runs if r['coverage']['planned']),runs[0] if runs else None)
    data={'title':'心育采购观察','builtAt':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
          'defaultRunId':preferred['id'] if preferred else None,'runs':runs}
    # Archive all successful snapshots; enrich only with explicit discovery provenance.
    candidates={}
    for f in (ROOT/'data/external-discovery').glob('*combined.json'):
        candidates.update({canonical_url(r['url']):r for r in json.loads(f.read_text()) if r.get('url')})
    archive={};seen_urls=set();url_project={};excluded_urls=set()
    # Corrected parsers supersede older interpretations of the same URL. Distinct
    # procurement/correction/result URLs still contribute their own evidence.
    archive_run=public_run({'run_id':'archive','actual_started_at':data['builtAt']},latest_documents,[])
    for r in [archive_run]:
        for project in r['projects']:
            urls={canonical_url(e['url']) for e in project['events'] if e.get('url')};seed=next((candidates[u] for u in urls if u in candidates),{})
            project['province']=project.get('province') or (seed.get('province') or seed.get('region'))
            if project['province']:
                project['province']=re.sub(r'壮族自治区|回族自治区|维吾尔自治区|自治区|省|市','',project['province'])
            if project['title'] in ('新闻网','通知公告','招标公告','标题待核验','公告内容文档') and seed.get('title'):project['title']=clean(seed['title'])
            project['discoveryDate']=seed.get('published_at')
            project['dateEvidence']='正文' if project.get('publishedAt') else '搜索索引日期，待核验'
            project['publishedAt']=project.get('publishedAt') or seed.get('published_at')
            project['buyer']=project.get('buyer') or seed.get('buyer')
            if 'axhu.edu.cn' in project['sourceUrl']:project['buyerType']='B端·企业采购（教育）'
            if project['category']=='排除':excluded_urls.update(urls);continue
            if project['category']=='待核验' and not vocabulary_match(project['title']+' '.join(x.get('text') or '' for x in project['parameters'])):excluded_urls.update(urls);continue
            # Cross-run project ids are derived from source identity; URLs catch alternate ids.
            existing=project['id'] if project['id'] in archive else next((url_project[u] for u in urls if u in url_project),None)
            if existing:archive[existing]=merge_project(archive[existing],project)
            else:existing=project['id'];archive[existing]=project
            for u in urls:url_project[u]=existing
            seen_urls.update(urls)
    import hashlib
    for url,seed in candidates.items():
        if url in seen_urls or url in excluded_urls or url in rejected_urls or task_status.get(url)=='not_procurement':continue
        pid='lead-'+hashlib.sha256(url.encode()).hexdigest()[:12]
        archive[pid]={'id':pid,'title':clean(seed['title']),'sourceUrl':link(url),'category':clean(seed.get('category') or '待核验'),
            'buyer':clean(seed.get('buyer')),'province':clean(seed.get('province') or seed.get('region')),'buyerType':None,
            'publishedAt':seed.get('published_at'),'dateEvidence':'搜索索引日期，待核验','sourceQuality':'搜索线索待核验',
            'amountEligible':False,'amounts':seed.get('amounts',[]),'amountScope':'搜索索引金额待复核，不计入汇总',
            'openingAt':seed.get('opening_at'),'deadline':seed.get('deadline'),'number':seed.get('number'),
            'products':[],'parameters':[{'text':clean(seed['search_note']),'locator':'搜索摘要，非本地正文','url':link(url)}] if seed.get('search_note') else [],'events':[],
            'detailStatus':'正文待获取或采购属性待核验','status':'待核验',
            'gaps':[{'name':'公告正文','status':'待核验','reason':'尚未完成正文核验，不计入已核验金额','url':link(url)}]}
    from .enrichment import enrich
    enrich(list(archive.values()),latest_documents,out)
    for r in runs:enrich(r['projects'],run_documents[r['id']],out)
    from .recovery import latest_receipts,acquisition_state
    receipts=latest_receipts(ROOT)
    for project in list(archive.values())+[p for r in runs for p in r['projects']]:
        u=canonical_url(project['sourceUrl'])
        state=acquisition_state(receipts.get(u,{}),task_details.get(u,{}),project.get('sourceQuality')=='正文已取得')
        project['acquisition']=state
        if project.get('sourceQuality')!='正文已取得':
            project['detailStatus']=state['label']+'：'+state['reason']
            project['gaps']=[g for g in project.get('gaps',[]) if g.get('name')!='公告正文']+[{'name':'公告正文','status':state['label'],'reason':state['reason'],'url':project['sourceUrl']}]

    cloud,cloud_failed=cloud_attempts(ROOT/'data/cloud-downloads')
    for url,status in cloud_failed.items():
        if url not in read_urls and task_status.get(url)!='not_procurement':task_status[url]=status
    data['cloudFallback']=cloud
    now=datetime.now(ZoneInfo('Asia/Shanghai'));week=now-timedelta(days=now.weekday())
    data.update(yearRange={'start':(now-timedelta(days=364)).date().isoformat(),'end':now.date().isoformat()},
        weekRange={'start':week.date().isoformat(),'end':now.date().isoformat()},archiveProjects=list(archive.values()))
    logs=ROOT/'data/external-discovery/annual_education_queries.json'
    count=len(json.loads(logs.read_text()).get('executed_queries',[])) if logs.exists() else 0
    fetched=sum(1 for u in candidates if u in read_urls)
    data['archiveCoverage']={'queries':count+len(json.loads((ROOT/'data/external-discovery/annual_recent_queries.json').read_text()).get('executed_queries',[])) if (ROOT/'data/external-discovery/annual_recent_queries.json').exists() else count,'candidates':len(candidates),'fetched':fetched,'failed':sum(u not in read_urls and task_status.get(u) not in (None,'ok','running','not_procurement','deferred','not_executed') for u in candidates),
        'pending':sum(u not in read_urls and task_status.get(u) in (None,'running','deferred','not_executed') for u in candidates),
        'excluded':sum(task_status.get(u)=='not_procurement' for u in candidates),
        'excluded_after_read':len(set(candidates)&excluded_urls),
        'monthsCovered':sorted({str(p.get('publishedAt'))[:7] for p in archive.values() if data['yearRange']['start'] <= str(p.get('publishedAt') or '')[:10] <= data['yearRange']['end']}),
        'limitation':'近一年已发现线索的回溯归档，并非全网全量库；未对各省平台逐页穷举。索引日期、采购主体性质为待复核线索；访问受限、付费文件和扫描件保留缺口。月份仅表示已有线索，不代表该月完整覆盖。'}
    from .source_matrix import matrix,query_logs
    data['sourceCoverage']=matrix(list(archive.values()),candidates)
    data['archiveCoverage']['queries']=len(query_logs())
    referenced={ref['path'] for p in data['archiveProjects']+[p for r in runs for p in r['projects']] for ref in p.get('fullTexts',[])}
    for old in (out/'bodies').glob('*.json'):
        if re.fullmatch(r'[a-f0-9]{64}\.json',old.name) and 'bodies/'+old.name not in referenced:old.unlink()
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e')
    (out/'data.js').write_text('window.RADAR_DATA = '+encoded+';\n',encoding='utf-8')
    return {'out':str(out),'runs':len(runs),'projects_in_default_run':len(preferred['projects']) if preferred else 0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out');parser.add_argument('--run-dir',action='append')
    args=parser.parse_args();print(json.dumps(export(args.out,args.run_dir),ensure_ascii=False))
