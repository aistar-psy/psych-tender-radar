"""Generate the public recovery/weekly report from the exported snapshot."""
import argparse,collections,html,json,sys
from pathlib import Path
from datetime import date,timedelta
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.fetch import canonical_url
from radar.paths import public_dir
ROOT=Path(__file__).resolve().parents[1]

def read_snapshot(path):
    text=Path(path).read_text();return json.loads(text[text.index('{'):text.rfind(';')]) if text.startswith('window.') else json.loads(text)

def selected(data,period):
    start,end=period['start'],period['end']
    return [p for p in data.get('archiveProjects',[]) if any(start<=str(d)[:10]<=end for d in [p.get('publishedAt')]+[e.get('publishedAt') for e in p.get('events',[])] if d)]

def metrics(rows):
    bodies=[p for p in rows if p.get('sourceQuality')=='正文已取得']
    return {'records':len(rows),'body_obtained':len(bodies),'body_pending':len(rows)-len(bodies),'education':sum(p.get('category') in ('教育核心','教育相关') for p in rows),
            'buyers':len({p['buyer'] for p in bodies if p.get('buyer')}),'with_supplier':sum(bool(p.get('winners')) for p in bodies),
            'body_and_attachment_texts':len({f['path'] for p in bodies for f in p.get('fullTexts',[])})}

def build(before_path,batch):
    after=read_snapshot(public_dir(ROOT)/'data.js');before=read_snapshot(before_path)
    annual=selected(after,after['yearRange']);week=selected(after,after['weekRange']);old=selected(before,before['yearRange'])
    monday=date.fromisoformat(after['weekRange']['start'][:10]);previous_range={'start':str(monday-timedelta(days=7)),'end':str(monday-timedelta(days=1))}
    previous=selected(after,previous_range);previous_metrics=metrics(previous)
    old_pending={canonical_url(p['sourceUrl']) for p in old if p.get('sourceQuality')!='正文已取得'}
    current_by_url={canonical_url(u):p for p in annual for u in [p['sourceUrl']]+[e['url'] for e in p.get('events',[])]}
    backfill={'previousPending':len(old_pending),'recovered':sum(u in current_by_url and current_by_url[u].get('sourceQuality')=='正文已取得' for u in old_pending),'stillPending':sum(u in current_by_url and current_by_url[u].get('sourceQuality')!='正文已取得' for u in old_pending),'outsideCurrentList':sum(u not in current_by_url for u in old_pending),'newPending':sum(p.get('sourceQuality')!='正文已取得' and not (old_pending & {canonical_url(u) for u in [p['sourceUrl']]+[e['url'] for e in p.get('events',[])]}) for p in annual)}
    failures=collections.Counter(p.get('acquisition',{}).get('label','待抓取正文') for p in annual if p.get('sourceQuality')!='正文已取得')
    batches=[]
    for f in (ROOT/'data/public-downloads').glob(batch+'*/manifest.json'):
        a=json.loads(f.read_text());batches.append({'batch':f.parent.name,'attempted':len(a),'responses':sum(r['status']=='ok' for r in a)})
    for f in (ROOT/'data/cloud-downloads').glob(batch+'*/manifest.json'):
        a=json.loads(f.read_text());a=a.get('results',[]) if isinstance(a,dict) else a
        batches.append({'batch':f.parent.name+'（云端）','attempted':len(a),'responses':sum(r['status']=='ok' for r in a)})
    bm,am,wm=metrics(old),metrics(annual),metrics(week)
    week_amounts={}
    for kind in ('预算','限价','成交','合同'):
        total=0;count=0
        for project in week:
            if project.get('sourceQuality')!='正文已取得' or project.get('amountEligible') is False:continue
            values={float(a['value']) for a in project.get('amounts',[]) if a.get('type')==kind and a.get('value') is not None}
            if len(values)==1:total+=values.pop();count+=1
        week_amounts[kind]={'yuan':total,'records':count}
    result={'backfillProgress':backfill,'builtAt':after['builtAt'],'yearRange':after['yearRange'],'weekRange':after['weekRange'],'before':bm,'after':am,'week':wm,'pendingReasons':dict(failures),'downloadBatches':batches,'weekAmounts':week_amounts,'previousWeekRange':previous_range,'previousWeek':previous_metrics,'beforeYearRange':before['yearRange']}
    directory=ROOT/'data/recovery'/batch;directory.mkdir(parents=True,exist_ok=True);(directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    h=lambda x:html.escape(str(x if x not in (None,'') else '未取得'))
    rows=''.join('<tr><td>'+h(k)+'</td><td>'+str(bm[key])+'</td><td>'+str(am[key])+'</td></tr>' for k,key in [('项目及搜索线索记录','records'),('正文已取得','body_obtained'),('正文待补','body_pending'),('教育类记录','education'),('已取得正文中的采购单位数','buyers'),('有中标单位或合同供应商的记录','with_supplier')])
    batch_table=''.join('<tr><td>'+h(x['batch'])+'</td><td>'+str(x['attempted'])+'</td><td>'+str(x['responses'])+'</td></tr>' for x in batches)
    reasons=''.join('<li>'+h(k)+'：'+str(v)+' 条</li>' for k,v in failures.items()) or '<li>当前年度记录无正文待补项。</li>'
    def table(projects):
        output=[]
        for p in sorted(projects,key=lambda x:x.get('publishedAt') or '',reverse=True):
            values=[a.get('type','')+' '+format(float(a['value'])/10000,',.2f')+' 万元' for a in p.get('amounts',[]) if a.get('value') is not None]
            suppliers=[w['name']+('（合同供应商）' if w.get('role')=='合同供应商' else '') for w in p.get('winners',[])]
            out=['<a href="'+h(p['sourceUrl'])+'" target="_blank" rel="noopener">'+h(p['title'])+'</a>',h('分类待确认' if p.get('category')=='待核验' else p.get('category')),h(p.get('buyer')),h(' / '.join(dict.fromkeys(values)) or '未取得'),h(p.get('procurementTime',{}).get('value')),h(p.get('procurementTime',{}).get('label')),h('；'.join(suppliers)),h('、'.join(p.get('sourceNames',[]))),h('、'.join(p.get('matchedTerms',[]))),h('、'.join(p.get('matchPoints',[]))),h(p.get('publishedAt')),h(p.get('deadline')),h(p.get('openingAt')),h(p.get('acquisition',{}).get('label',p.get('sourceQuality')))]
            output.append('<tr>'+''.join('<td>'+x+'</td>' for x in out)+'</tr>')
        header=''.join('<th>'+x+'</th>' for x in ['项目名称 / 来源链接','分类','采购单位','金额','采购时间','时间口径','中标单位 / 合同供应商','数据来源','命中词','对位点','公告发布','响应截止','开标时间','正文状态'])
        return '<div class="scroll"><table><thead><tr>'+header+'</tr></thead><tbody>'+''.join(output)+'</tbody></table></div>'
    money_table='<table><tr><th>金额口径</th><th>可汇总样本金额</th><th>记录数</th></tr>'+''.join('<tr><td>'+h(k)+'</td><td>'+format(v['yuan']/10000,',.2f')+' 万元</td><td>'+str(v['records'])+'</td></tr>' for k,v in week_amounts.items())+'</table><p>金额仅汇总已取得正文、口径明确且未被更正或批次意向排除的记录。各口径不可相加，不代表本周市场总额。</p>'
    css='body{margin:0;background:#f5f4ef;color:#222c27;font:16px/1.7 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:40px 24px}h1{font-size:34px}h2{margin-top:40px}a{color:#246446}p,li{max-width:95ch}.scroll{overflow:auto;background:white;border:1px solid #d8ddd8}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{background:#e5ebe5}.scroll td{min-width:90px}.scroll td:first-child{min-width:220px}.muted{color:#646c65}input{padding:12px;width:min(440px,80%);margin:12px 0;border:1px solid #88998d;border-radius:6px}.badge{padding:4px 12px;background:#deebe0;border-radius:20px}summary{cursor:pointer;font-weight:600}details{margin:20px 0}@media(max-width:600px){main{padding:24px 14px}h1{font-size:26px}}'
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>正文补抓与市场周报 · 心育采购观察</title><style>'+css+'</style><main><a href="index.html">← 返回情报工作台</a><h1>正文补抓与市场周报</h1><p class="muted">生成时间：'+h(after['builtAt'])+'<br>年度窗口：'+h(after['yearRange']['start'])+' — '+h(after['yearRange']['end'])+'</p><h2>补抓前后</h2><table><tr><th>指标</th><th>修复前</th><th>修复后</th></tr>'+rows+'</table><p>以上为当前窗口内项目和线索记录。项目编号归并、非公告排除与正文日期校正会改变条数；不把待补减少量全部当作新增独立项目。</p><h2>本周市场概况</h2><p>'+h(after['weekRange']['start'])+' — '+h(after['weekRange']['end'])+'，共 '+str(wm['records'])+' 条记录，正文已取得 '+str(wm['body_obtained'])+' 条，教育类 '+str(wm['education'])+' 条，已取得正文涉及 '+str(wm['buyers'])+' 家采购单位。</p>'+money_table+table(week)+'<h2>实际执行批次</h2><table><tr><th>批次</th><th>已尝试 URL</th><th>取得响应</th></tr>'+batch_table+'</table><p>同一 URL 可能先后经过 HTTP、浏览器和附件补抓；各批次不能相加当作独立项目。取得响应须继续通过正文解析，才纳入正文已取得。</p><h2>仍需补充的正文</h2><ul>'+reasons+'</ul><p>普通浏览器中仍无法完成的验证、会员可见字段、无法取得的文件以及未识别扫描件都保留缺口，不据此推断网站无相关信息。</p><h2>修复内容</h2><ul><li>HTTPS 使用系统证书库，保留证书校验；访问错误与动态页面自动进入浏览器补抓。</li><li>修复陕西正文容器、重庆项目号、嵌入正文入口及无关下载链接；保留原始响应和真实读取时间。</li><li>合同金额单独标注，中标单位与合同供应商区分；公告发布、预计采购月份、合同签订日期分别标注。</li><li>具体失败原因进入项目列表筛选和详情；公开附件与公告关联，新闻、政策和企业名录排除。</li></ul><p class="muted">系统证书库实现依据 <a href="https://truststore.readthedocs.io/en/latest/">Truststore 官方文档</a>。金额为可追溯的规则提取候选；预算、限价、成交和合同金额分别查看，更正生效关系未确认时不计入汇总。当前仍不代表全网全量。</p></main></html>'
    progress_text=f"上期 {backfill['previousPending']} 条待补中，本次 {backfill['recovered']} 条已取得正文、{backfill['stillPending']} 条仍待补、{backfill['outsideCurrentList']} 条不再位于当前年度列表；本次检索另有 {backfill['newPending']} 条新增待补线索。待补总数同时受新增线索、项目归并和年度窗口变化影响。"
    page=page.replace('<h2>仍需补充的正文</h2>','<h2>仍需补充的正文</h2><p>'+h(progress_text)+'</p>')
    previous_section='<h2>最近一个完整周</h2><p>'+h(previous_range['start'])+' — '+h(previous_range['end'])+'，共 '+str(previous_metrics['records'])+' 条记录，其中正文已取得 '+str(previous_metrics['body_obtained'])+' 条，教育类 '+str(previous_metrics['education'])+' 条，已取得正文涉及 '+str(previous_metrics['buyers'])+' 家采购单位。</p>'+table(previous)
    page=page.replace('<h2>实际执行批次</h2>',previous_section+'<h2>实际执行批次</h2>')
    audit_path=ROOT/'data/weekly'/after['builtAt'][:10].replace('-','')/'execution_summary.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text());page=page.replace('<h2>修复内容</h2>','<h2>本轮检索与缺口</h2><ul>'+''.join('<li>'+h(t)+'</li>' for t in audit.get('notes',[]))+'</ul><h2>修复内容</h2>')
        result['weeklyExecution']=audit
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    page=page.replace('以上为当前窗口内项目和线索记录。','上期快照窗口为 '+h(before['yearRange']['start'])+' — '+h(before['yearRange']['end'])+'；本期窗口为 '+h(after['yearRange']['start'])+' — '+h(after['yearRange']['end'])+'。以上为各自窗口内项目和线索记录。')
    module_css="""
.report-nav{position:sticky;top:0;z-index:10;background:#f5f4ef;border-bottom:1px solid #d6ded7}
.report-nav-inner{max-width:1250px;margin:auto;display:flex;align-items:center;gap:32px;padding:0 24px;min-height:70px}
.report-brand{font-weight:650;text-decoration:none;margin-right:auto;font-size:17px;white-space:nowrap}
.report-links{display:flex;align-items:stretch;gap:26px;align-self:stretch}
.report-links a{display:flex;align-items:center;border-bottom:3px solid transparent;text-decoration:none;color:#647269;padding:4px 0 0;font-size:15px;font-weight:600;white-space:nowrap}
.report-links a[aria-current=page]{color:#245f43;border-bottom-color:#245f43}
.report-links a:hover{color:#245f43}.report-nav a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #246446;outline-offset:4px}
.annual-intro h1{font-family:Georgia,"Songti SC",serif;font-size:36px;letter-spacing:.02em;line-height:1.35;margin:10px 0 14px}
.annual-intro .eyebrow{font:600 11px/1.5 Georgia,serif;letter-spacing:.17em;color:#246446}
.annual-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:26px 0;border-block:1px solid #cdd8cf;padding:18px 0}
.annual-summary div{padding:0 22px;border-right:1px solid #d8dfd8}.annual-summary div:first-child{padding-left:0}.annual-summary div:last-child{border:0}
.annual-summary span{display:block;color:#646c65;font-size:13px}.annual-summary strong{font-family:Georgia,"Songti SC",serif;font-size:31px;font-weight:500;line-height:1.5}
.annual-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:24px 0 8px}.annual-tools input{flex:1 1 260px;width:auto;margin:0;min-width:0;background:white;font:inherit}
.annual-tools select,.annual-tools button{font:inherit;font-size:14px;padding:12px;background:#fff;border:1px solid #bdcabe;border-radius:6px;color:#244b35}.annual-tools select{max-width:240px}.annual-tools button{cursor:pointer;background:transparent}
.annual-caption{display:flex;justify-content:space-between;gap:16px;color:#647269;font-size:13px;margin:12px 0}.annual-caption p{margin:0}
.annual-table .scroll{max-height:68vh}.annual-table th{position:sticky;top:0;z-index:1;white-space:nowrap}.annual-table td:first-child{min-width:290px;max-width:400px}.annual-table tr[hidden]{display:none}.no-results{padding:32px;text-align:center;border:1px solid #d8ddd8;background:white}
@media(max-width:600px){.report-nav-inner{padding:0 14px;gap:12px;min-height:60px}.report-brand{font-size:14px}.report-links{gap:16px}.report-links a{font-size:14px}.annual-intro h1{font-size:28px}.annual-summary{grid-template-columns:repeat(2,1fr);row-gap:18px;padding:18px 0}.annual-summary div{padding:0 16px}.annual-summary div:nth-child(3){padding-left:0}.annual-summary div:nth-child(2){border:0}.annual-summary strong{font-size:27px}.annual-tools select{flex:1 1 130px;min-width:0;max-width:none}.annual-tools button{flex:0 0 auto}.annual-caption{flex-direction:column;gap:4px}}
"""
    def navigation(active):
        links=[('report','recovery-report.html','市场周报'),('annual','annual-projects.html','近一年明细')]
        return '<header class="report-nav"><nav class="report-nav-inner" aria-label="报告模块"><a class="report-brand" href="index.html">心育采购观察 ↗</a><div class="report-links">'+''.join('<a href="'+url+'"'+(' aria-current="page"' if key==active else '')+'>'+label+'</a>' for key,url,label in links)+'</div></nav></header>'
    page=page.replace('</style>','</style><style>'+module_css+'</style>')
    page=page.replace('<main><a href="index.html">← 返回情报工作台</a>',navigation('report')+'<main>')
    (public_dir(ROOT)/'recovery-report.html').write_text(page)
    def options(field):
        values=sorted({value for project in annual for value in project.get(field,[])})
        return ''.join('<option value="'+h(value)+'">'+h(value)+'</option>' for value in values)
    annual_table=table(annual)
    summary=''.join('<div><span>'+label+'</span><strong>'+format(am[key],',')+'</strong></div>' for label,key in [('项目及线索','records'),('正文已取得','body_obtained'),('教育类','education'),('正文待补','body_pending')])
    annual_script="""const rows=Array.from(document.querySelectorAll('#annual tbody tr'));
const search=document.querySelector('#search'),keyword=document.querySelector('#annual-keyword'),point=document.querySelector('#annual-point');
function filter(){const query=search.value.trim().toLocaleLowerCase();let shown=0;rows.forEach(row=>{const matches=(!query||row.textContent.toLocaleLowerCase().includes(query))&&(!keyword.value||row.cells[8].textContent.split('、').includes(keyword.value))&&(!point.value||row.cells[9].textContent.split('、').includes(point.value));row.hidden=!matches;if(matches)shown++});document.querySelector('#result-count').textContent='显示 '+shown.toLocaleString()+' / '+rows.length.toLocaleString()+' 条';document.querySelector('#no-results').hidden=shown!==0}
search.addEventListener('input',filter);keyword.addEventListener('change',filter);point.addEventListener('change',filter);document.querySelector('#reset-filters').addEventListener('click',()=>{search.value='';keyword.value='';point.value='';filter();search.focus()});filter();"""
    annual_page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>近一年项目与线索明细 · 心育采购观察</title><style>'+css+module_css+'</style>'+navigation('annual')+'<main><div class="annual-intro"><div class="eyebrow">ANNUAL PROJECTS / 年度项目库</div><h1>近一年项目与线索明细</h1><p class="muted">'+h(after['yearRange']['start'])+' — '+h(after['yearRange']['end'])+' · 数据更新 '+h(after['builtAt'])+'</p></div><div class="annual-summary">'+summary+'</div><div class="annual-tools" role="search" aria-label="年度项目筛选"><input id="search" type="search" aria-label="搜索年度明细" placeholder="搜索项目名称、采购单位、中标单位或命中词"><select id="annual-keyword" aria-label="命中词"><option value="">全部命中词</option>'+options('matchedTerms')+'</select><select id="annual-point" aria-label="对位点"><option value="">全部对位点</option>'+options('matchPoints')+'</select><button type="button" id="reset-filters">重置筛选</button></div><div class="annual-caption"><p id="result-count" role="status" aria-live="polite">共 '+str(len(annual))+' 条记录</p><p>按公告发布日期排序 · 左右滑动查看完整字段</p></div><div id="annual" class="annual-table">'+annual_table+'</div><p id="no-results" class="no-results" hidden>未找到符合条件的项目，请调整或重置筛选。</p><p class="muted">记录包括已取得正文的项目和待补线索；金额、时间及供应商以各自来源公告为准。完整正文和附件可在<a href="index.html">情报工作台的项目库</a>查阅。</p></main><script>'+annual_script+'</script></html>'
    (public_dir(ROOT)/'annual-projects.html').write_text(annual_page)
    lines=['# 正文补抓与市场周报','',f"生成时间：{after['builtAt']}",'',f"年度窗口：{after['yearRange']['start']} — {after['yearRange']['end']}",'','|指标|修复前|修复后|','|---|---:|---:|']
    for label,key in [('项目及线索记录','records'),('正文已取得','body_obtained'),('正文待补','body_pending'),('教育类','education'),('采购单位','buyers'),('有供应商记录','with_supplier')]:lines.append(f'|{label}|{bm[key]}|{am[key]}|')
    lines+=['','条数包含归并、排除和日期校正；不等于新增独立项目数。','',f"本周共 {wm['records']} 条记录，正文已取得 {wm['body_obtained']} 条，教育类 {wm['education']} 条，涉及 {wm['buyers']} 家采购单位。",'','待补原因：'+'；'.join(f'{label} {count} 条' for label,count in failures.items())+'。','','仍无法读取的验证页和公开发布源保留具体失败原因，后续补抓从队列继续。','', '[HTML 报告](https://aistar-psy.github.io/psych-tender-radar/recovery-report.html)','', '详细字段、参数与正文在主工作台逐条查看。公开来源尚未完整穷举，正文已取得不等于每一份附件或扫描件都已完整解析。']
    lines+=['',progress_text]
    lines+=['',f"最近完整周：{previous_range['start']} — {previous_range['end']}，共 {previous_metrics['records']} 条，正文已取得 {previous_metrics['body_obtained']} 条，教育类 {previous_metrics['education']} 条。"]
    if audit_path.exists():lines+=['']+['- '+t for t in audit.get('notes',[])]
    (ROOT/'docs'/f"{after['builtAt'][:10]}正文补抓修复报告.md").write_text('\n'.join(lines)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',required=True);p.add_argument('--batch',required=True);a=p.parse_args();build(a.before,a.batch)
