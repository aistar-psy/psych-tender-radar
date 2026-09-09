"""Budgeted weekly pipeline; every skipped/failed item remains visible."""
import fcntl
import hashlib
import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from .fetch import Fetcher,FetchError,canonical_url,save_evidence
from .store import Store,stamp,key
from .discovery import discover
from .search_recipes import build_region_plan
from .documents import parse_document
from .analysis import analyze_document
from .report import render

PACKAGE_ROOT=Path(__file__).resolve().parent.parent

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)

def load(path,default):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default

@contextmanager
def locked(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'run.lock').open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another radar run is already active')
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)

def attachment_usable(doc,content_type):
    if doc.get('status') not in ('ok','parsed'):return False
    text=doc.get('text','')
    if 'html' in content_type.lower() and re.search(r'请.*登录|登录后|用户名.*密码|访问权限|无权访问|验证码',text):return False
    return bool(text.strip())

def run(root=None,seeds=None,no_discovery=False,max_discovery=192,max_documents=40,
        max_attachments=8,interval=1.0,timeout=15,max_seconds=900,as_of=None,config_dir=None,window_days=7,fetcher=None):
    root=Path(root or PACKAGE_ROOT/'data'/'runtime').resolve()
    with locked(root):
        return _run(root,seeds,no_discovery,max_discovery,max_documents,max_attachments,
                    interval,timeout,max_seconds,as_of,config_dir,window_days,fetcher)

def _run(root,seeds,no_discovery,max_discovery,max_documents,max_attachments,interval,timeout,max_seconds,as_of,config_dir,window_days,fetcher):
    for value in (max_discovery,max_documents,max_attachments,max_seconds):
        if value<0:raise ValueError('Budgets must not be negative')
    start_clock=time.monotonic()
    actual_started_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    end=datetime.fromisoformat(as_of) if as_of else datetime.now(ZoneInfo('Asia/Shanghai'))
    if end.tzinfo is None:raise ValueError('as_of must include timezone')
    if window_days < 1: raise ValueError("window_days must be positive")
    start=end-timedelta(days=window_days)
    run_id=end.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
    directory=root/'runs'/run_id;directory.mkdir(parents=True)
    store=Store(root/'radar.sqlite3');fetch=fetcher or Fetcher(interval=interval,timeout=timeout,retries=0)
    config=Path(config_dir or PACKAGE_ROOT/'config')
    tasks=[];documents=[];queue=[];seen=set()
    def remaining():return time.monotonic()-start_clock<max_seconds
    def add(url):
        if not isinstance(url,str) or urlsplit(url).scheme not in ('http','https'):return
        url=canonical_url(url)
        if url not in seen:seen.add(url);queue.append(url)
    def snapshot():
        write_json(directory/'execution.json',tasks)
        write_json(directory/'documents.json',documents)
    def obtain(url):
        response=fetch(url);evidence=save_evidence(response,root/'evidence')
        evidence['fetched_at']=response.get('fetched_at') or stamp()
        evidence['provider']=response.get('provider','local_http')
        doc=parse_document(response['body'],response['url'],response['content_type'])
        write_json(root/'evidence'/(evidence['sha256']+'.json'),{'evidence':evidence,'parsed':doc})
        return doc,evidence
    try:
        write_json(directory/'seed_inputs.json',seeds or [])
        for seed in seeds or []:add(seed.get('url') if isinstance(seed,dict) else seed)
        for old in store.pending():
            if old['kind'] in ('document','deferred_document','detail_gap'):add(old['id'])
        # Periodically revisit persisted notices to detect changed bodies; budget remains explicit.
        for url in store.known_urls():add(url)
        if not no_discovery:
            regions=load(config/'regions.json',[])
            channels=load(config/'channels.json',{})
            plan=build_region_plan(regions,(start-timedelta(days=7)).date().isoformat(),end.date().isoformat())
            primary=[p for p in plan if p.get('group_index',0)==0]
            extra=[p for p in plan if p.get('group_index',0)>0]
            cursor=store.get('discovery_cursor',0)%max(1,len(extra))
            primary_cursor=store.get('primary_cursor',0)%max(1,len(primary))
            ordered=primary[primary_cursor:]+primary[:primary_cursor]+extra[cursor:]+extra[:cursor]
            retry_queries=[p for p in store.pending() if p['kind']=='search'][:8]
            for retry in retry_queries:
                tasks.append({'id':key(retry['id']),'query':retry['id'],'kind':'search','status':'not_executed','region':'原窗口重试','error':''})
            for task in ordered:
                tasks.append({**task,'kind':'search','status':'not_executed','error':''})
            sources=load(config/'sources.json',[])
            for source in sources:
                tasks.append({'id':source['id'],'region':source.get('region',''),'kind':'listing' if source.get('kind')=='listing' else 'source_registry',
                              'url':source.get('url',''),'status':'not_executed' if source.get('kind')=='listing' else 'not_configured',
                              'error':'' if source.get('kind')=='listing' else '来源登记；尚未配置可执行栏目连接器'})
            write_json(directory/'plan.json',tasks)
            executed=0;consecutive_failures=0;primary_executed=0
            for task in tasks:
                if task['kind']!='search':continue
                if executed>=max_discovery or not remaining() or time.monotonic()-start_clock>max_seconds*0.4 or consecutive_failures>=3:
                    task['error']='检索预算/阶段时间耗尽或连续3次失败熔断；保留公告读取时间并后续轮转';continue
                result=discover(task['query'],fetch);task.update(status=result['status'],error=result.get('error',''),hits=len(result['links']),executed_at=stamp(),attempts=result.get('attempts',[]),pagination=result.get('pagination',{}))
                for link in result['links']:add(link['url'])
                if result['status'] in ('ok','empty'):store.resolve(task['query']);consecutive_failures=0
                else:consecutive_failures+=1;store.backlog(task['query'],'search',task['error'])
                executed+=1
                if task.get('primary'):primary_executed+=1
                snapshot()
            if primary:store.set('primary_cursor',(primary_cursor+primary_executed)%len(primary))
            if extra:store.set('discovery_cursor',(cursor+max(0,executed-len(primary)-len(retry_queries)))%len(extra))
            for task in tasks:
                if task['kind']!='listing':continue
                if not remaining():task['error']='时间预算未执行';continue
                try:
                    doc,ev=obtain(task['url'])
                    selected=[x for x in doc['links'] if x.get('kind')=='page' and
                              any(w in x.get('text','') for w in ('心理','心育','学生','校园','健康','采购意向'))]
                    for link in selected:add(link['url'])
                    task.update(status='ok',hits=len(selected),scope='single_listing_page',evidence=ev['path'])
                except Exception as exc:task.update(status=getattr(exc,'kind','failed'),error=str(exc)[:500])
                snapshot()
        else:write_json(directory/'plan.json',[])
        write_json(directory/'candidates.json',queue)
        for index,url in enumerate(queue):
            if index>=max_documents or not remaining():
                store.backlog(url,'deferred_document','本轮公告读取预算或时间耗尽')
                continue
            task={'id':key(url),'kind':'document','url':url,'status':'running'};tasks.append(task)
            try:
                doc,ev=obtain(url)
                if doc.get('page_kind')=='non_notice':
                    task.update(status='not_procurement',error='已确认页面为新闻、政策或企业名录，不是项目公告')
                    store.resolve(url);snapshot();continue
                main_unavailable=doc.get('content_status')=='unavailable'
                if main_unavailable:task['main_content_status']='unavailable'
                links=list({l['url']:l for l in doc.get('links',[]) if l.get('kind')=='attachment'}.values())
                if doc.get('status') not in ('ok','parsed','partial') or (not doc.get('text','').strip() and not main_unavailable):
                    raise FetchError('parse_error',str(doc.get('warnings') or doc.get('status')),url)
                initial_analysis=analyze_document(doc,url,end.isoformat())
                if not (main_unavailable and links) and (initial_analysis.get('is_procurement') is not True or main_unavailable):
                    task.update(status='content_unconfirmed',error='尚未识别有效采购正文，可能是动态壳或未适配版式，保留线索复查')
                    store.backlog(url,'document',task['error']);snapshot();continue
                combined={**doc,'blocks':list(doc['blocks'])}
                if main_unavailable:
                    # Shell widgets are not notice text; only explicit metadata and title survive.
                    combined['blocks']=[b for b in doc['blocks'] if b.get('kind')=='metadata']
                    combined['text']='\n'.join(b['text'] for b in combined['blocks'])
                attachments=[];evidences=[ev];warnings=list(doc.get('warnings',[]));usable_attachments=0
                pending_urls={p['id'] for p in store.pending() if p['kind']=='attachment'}
                links.sort(key=lambda l: (l['url'] not in pending_urls, store.get('attachment_checked:'+key(l['url']),'')))
                for j,link in enumerate(links):
                    attach={'url':link['url'],'name':link.get('text',''),'status':'deferred'}
                    attachments.append(attach)
                    if j>=max_attachments or not remaining():
                        cached=store.get('attachment_cache:'+key(link['url']))
                        if cached and attachment_usable(cached['parsed'],cached['evidence']['content_type']):
                            parsed=cached['parsed'];evidences.append(cached['evidence']);attach.update(status='ok',freshness='cached',checked_at=cached['evidence']['fetched_at'])
                            for block in parsed['blocks']:combined['blocks'].append({**block,'locator':link.get('text','附件')+' / '+block['locator'],'source_url':link['url']})
                            combined['text']+='\n'+parsed.get('text','')
                            usable_attachments+=1
                            continue
                        attach['error']='附件/时间预算耗尽';store.backlog(link['url'],'attachment',attach['error']);continue
                    try:
                        parsed,aev=obtain(link['url']);evidences.append(aev)
                        attach['status']=parsed.get('status','parse_error')
                        attach['warnings']=parsed.get('warnings',[])
                        if not attachment_usable(parsed,aev['content_type']):
                            if attach['status'] in ('ok','parsed'):attach['status']='access_page';attach['warnings'].append('仅取得登录/权限页，未取得采购文件')
                            store.backlog(link['url'],'attachment',str(attach['warnings']));continue
                        for block in parsed['blocks']:
                            combined['blocks'].append({**block,'locator':link.get('text','附件')+' / '+block['locator'],'source_url':link['url']})
                        combined['text']+='\n'+parsed.get('text','')
                        usable_attachments+=1
                        store.resolve(link['url'])
                        store.set('attachment_checked:'+key(link['url']),stamp())
                        store.set('attachment_cache:'+key(link['url']),{'parsed':parsed,'evidence':aev})
                    except Exception as exc:
                        attach.update(status=getattr(exc,'kind','failed'),error=str(exc)[:500]);store.backlog(link['url'],'attachment',attach['error'])
                    finally:
                        store.set('attachment_checked:'+key(link['url']),stamp())
                if main_unavailable:
                    if not usable_attachments:
                        task.update(status='content_unconfirmed',error='公告正文未取得，公开附件尚无可用内容；保留父公告复查',attachments=attachments,evidence=evidences)
                        store.backlog(url,'document',task['error']);snapshot();continue
                    combined['content_status']='attachment_only'
                analysis=analyze_document(combined,url,end.isoformat())
                if main_unavailable and analysis.get('is_procurement') is not True:
                    task.update(status='content_unconfirmed',error='公告正文未取得，公开附件及元数据仍不能确认采购内容；保留线索复查',attachments=attachments,evidence=evidences)
                    store.backlog(url,'document',task['error']);snapshot();continue
                if not links:warnings.append('未发现可下载附件；无法确认采购文件完整性，可能需另行获取。')
                if main_unavailable:warnings.append('公告正文未取得；当前分析仅依据标题、公开元数据及已取得附件，父公告待补。')
                incomplete=main_unavailable or not links or any(a['status'] not in ('ok','parsed') for a in attachments)
                warnings.append('分类、品目和参数是规则提取候选；更正/结果需按项目号复核。')
                detail_status='部分完成' if incomplete else '已解析公开附件，待业务复核'
                if not analysis.get('parameters'):detail_status='部分完成';warnings.append('未取得可识别参数行。')
                level='E2' if urlsplit(url).hostname and urlsplit(url).hostname.endswith(('.gov.cn','.edu.cn')) else 'E1/发布方待核验'
                bundle_hash=hashlib.sha256(json.dumps(sorted((e['url'],e['sha256']) for e in evidences)).encode()).hexdigest()
                pid=store.save_document(url,analysis,bundle_hash,run_id)
                record={'project_id':pid,'notice_id':key(url),'url':url,'analysis':analysis,'attachments':attachments,
                        'main_content_status':'unavailable' if main_unavailable else 'available',
                        'evidence':evidences,'detail_status':detail_status,'evidence_level':level,'fetched_at':stamp(),'warnings':warnings}
                documents.append(record);task.update(status='partial' if main_unavailable else 'ok',project_id=pid);store.resolve(url)
                if incomplete:store.backlog(url,'detail_gap','公告正文尚未取得；已取得附件不能代替父公告，下轮重查' if main_unavailable else '公开附件尚未完整取得；保留父公告以便下轮重查')
            except Exception as exc:
                task.update(status=getattr(exc,'kind','failed'),error=str(exc)[:600]);store.backlog(url,'document',str(exc))
            snapshot()
        pending=store.pending()
        for t in tasks:
            if t.get('status') in ('not_executed','not_configured'):
                pending.append({'id':t['id'],'kind':t['kind'],'error':t.get('error',''),'status':t['status']})
        failures=any(t.get('status') not in ('ok','empty','not_procurement') for t in tasks)
        summary={'run_id':run_id,'actual_started_at':actual_started_at,'window_start':start.isoformat(),'window_end':end.isoformat(),
                 'run_dir':str(directory),'counts':store.counts(),'processed_documents':len(documents),
                 'pending_count':len(pending),'status':'partial' if failures or pending or any(d['detail_status']=='部分完成' for d in documents) else 'completed',
                 'duration_seconds':round(time.monotonic()-start_clock,2)}
        summary['report']=render(directory,summary,documents,tasks,pending)
        snapshot();write_json(directory/'backlog.json',pending);write_json(directory/'summary.json',summary)
        write_json(root/'latest.json',summary);store.save_run(run_id,summary)
        return summary
    finally:store.close()
