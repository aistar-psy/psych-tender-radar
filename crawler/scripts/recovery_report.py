"""Generate the public recovery/weekly report from the exported snapshot."""
import argparse,collections,html,json,sys
from pathlib import Path
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
    failures=collections.Counter(p.get('acquisition',{}).get('label','待抓取正文') for p in annual if p.get('sourceQuality')!='正文已取得')
    batches=[]
    for f in (ROOT/'data/public-downloads').glob(batch+'*/manifest.json'):
        a=json.loads(f.read_text());batches.append({'batch':f.parent.name,'attempted':len(a),'responses':sum(r['status']=='ok' for r in a)})
    bm,am,wm=metrics(old),metrics(annual),metrics(week)
    week_amounts={}
    for kind in ('预算','限价','成交','合同'):
        total=0;count=0
        for project in week:
            if project.get('sourceQuality')!='正文已取得' or project.get('amountEligible') is False:continue
            values={float(a['value']) for a in project.get('amounts',[]) if a.get('type')==kind and a.get('value') is not None}
            if len(values)==1:total+=values.pop();count+=1
        week_amounts[kind]={'yuan':total,'records':count}
    result={'builtAt':after['builtAt'],'yearRange':after['yearRange'],'weekRange':after['weekRange'],'before':bm,'after':am,'week':wm,'pendingReasons':dict(failures),'downloadBatches':batches,'weekAmounts':week_amounts}
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
            out=['<a href="'+h(p['sourceUrl'])+'" target="_blank" rel="noopener">'+h(p['title'])+'</a>',h('分类待确认' if p.get('category')=='待核验' else p.get('category')),h(p.get('buyer')),h(' / '.join(dict.fromkeys(values)) or '未取得'),h(p.get('procurementTime',{}).get('value')),h(p.get('procurementTime',{}).get('label')),h('；'.join(suppliers)),h('、'.join(p.get('sourceNames',[]))),h('、'.join(p.get('matchedTerms',[]))),h(p.get('acquisition',{}).get('label',p.get('sourceQuality')))]
            output.append('<tr>'+''.join('<td>'+x+'</td>' for x in out)+'</tr>')
        header=''.join('<th>'+x+'</th>' for x in ['项目名称 / 来源链接','分类','采购单位','金额','采购时间','时间口径','中标单位 / 合同供应商','数据来源','命中词','正文状态'])
        return '<div class="scroll"><table><thead><tr>'+header+'</tr></thead><tbody>'+''.join(output)+'</tbody></table></div>'
    money_table='<table><tr><th>金额口径</th><th>可汇总样本金额</th><th>记录数</th></tr>'+''.join('<tr><td>'+h(k)+'</td><td>'+format(v['yuan']/10000,',.2f')+' 万元</td><td>'+str(v['records'])+'</td></tr>' for k,v in week_amounts.items())+'</table><p>金额仅汇总已取得正文、口径明确且未被更正或批次意向排除的记录。各口径不可相加，不代表本周市场总额。</p>'
    css='body{margin:0;background:#f5f4ef;color:#222c27;font:16px/1.7 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:40px 24px}h1{font-size:34px}h2{margin-top:40px}a{color:#246446}p,li{max-width:95ch}.scroll{overflow:auto;background:white;border:1px solid #d8ddd8}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{background:#e5ebe5}.scroll td{min-width:90px}.scroll td:first-child{min-width:220px}.muted{color:#646c65}input{padding:12px;width:min(440px,80%);margin:12px 0;border:1px solid #88998d;border-radius:6px}.badge{padding:4px 12px;background:#deebe0;border-radius:20px}summary{cursor:pointer;font-weight:600}details{margin:20px 0}@media(max-width:600px){main{padding:24px 14px}h1{font-size:26px}}'
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>正文补抓与市场周报 · 心育采购观察</title><style>'+css+'</style><main><a href="index.html">← 返回情报工作台</a><h1>正文补抓与市场周报</h1><p class="muted">生成时间：'+h(after['builtAt'])+'<br>年度窗口：'+h(after['yearRange']['start'])+' — '+h(after['yearRange']['end'])+'</p><h2>补抓前后</h2><table><tr><th>指标</th><th>修复前</th><th>修复后</th></tr>'+rows+'</table><p>以上为当前窗口内项目和线索记录。项目编号归并、非公告排除与正文日期校正会改变条数；不把待补减少量全部当作新增独立项目。</p><h2>本周市场概况</h2><p>'+h(after['weekRange']['start'])+' — '+h(after['weekRange']['end'])+'，共 '+str(wm['records'])+' 条记录，正文已取得 '+str(wm['body_obtained'])+' 条，教育类 '+str(wm['education'])+' 条，已取得正文涉及 '+str(wm['buyers'])+' 家采购单位。</p>'+money_table+table(week)+'<h2>实际执行批次</h2><table><tr><th>批次</th><th>已尝试 URL</th><th>取得响应</th></tr>'+batch_table+'</table><p>同一 URL 可能先后经过 HTTP、浏览器和附件补抓；各批次不能相加当作独立项目。取得响应须继续通过正文解析，才纳入正文已取得。</p><h2>仍需补充的正文</h2><ul>'+reasons+'</ul><p>普通浏览器中仍无法完成的验证、会员可见字段、无法取得的文件以及未识别扫描件都保留缺口，不据此推断网站无相关信息。</p><h2>修复内容</h2><ul><li>HTTPS 使用系统证书库，保留证书校验；访问错误与动态页面自动进入浏览器补抓。</li><li>修复陕西正文容器、重庆项目号、嵌入正文入口及无关下载链接；保留原始响应和真实读取时间。</li><li>合同金额单独标注，中标单位与合同供应商区分；公告发布、预计采购月份、合同签订日期分别标注。</li><li>具体失败原因进入项目列表筛选和详情；公开附件与公告关联，新闻、政策和企业名录排除。</li></ul><p class="muted">系统证书库实现依据 <a href="https://truststore.readthedocs.io/en/latest/">Truststore 官方文档</a>。金额为可追溯的规则提取候选；预算、限价、成交和合同金额分别查看，更正生效关系未确认时不计入汇总。当前仍不代表全网全量。</p><h2>近一年项目与线索明细</h2><p>支持文字搜索。更细的命中词、对位点和状态组合筛选，以及完整正文阅读，请进入主工作台。</p><input id="search" aria-label="搜索年度明细" placeholder="输入项目、单位或命中词"><div id="annual">'+table(annual)+'</div></main><script>document.querySelector("#search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#annual tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))})</script></html>'
    (public_dir(ROOT)/'recovery-report.html').write_text(page)
    lines=['# 正文补抓与市场周报','',f"生成时间：{after['builtAt']}",'',f"年度窗口：{after['yearRange']['start']} — {after['yearRange']['end']}",'','|指标|修复前|修复后|','|---|---:|---:|']
    for label,key in [('项目及线索记录','records'),('正文已取得','body_obtained'),('正文待补','body_pending'),('教育类','education'),('采购单位','buyers'),('有供应商记录','with_supplier')]:lines.append(f'|{label}|{bm[key]}|{am[key]}|')
    lines+=['','条数包含归并、排除和日期校正；不等于新增独立项目数。','',f"本周共 {wm['records']} 条记录，正文已取得 {wm['body_obtained']} 条，教育类 {wm['education']} 条，涉及 {wm['buyers']} 家采购单位。",'','待补原因：'+'；'.join(f'{label} {count} 条' for label,count in failures.items())+'。','','仍无法读取的验证页和公开发布源保留具体失败原因，后续补抓从队列继续。','', '[HTML 报告](https://aistar-psy.github.io/psych-tender-radar/recovery-report.html)','', '详细字段、参数与正文在主工作台逐条查看。公开来源尚未完整穷举，正文已取得不等于每一份附件或扫描件都已完整解析。']
    (ROOT/'docs'/f"{after['builtAt'][:10]}正文补抓修复报告.md").write_text('\n'.join(lines)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',required=True);p.add_argument('--batch',required=True);a=p.parse_args();build(a.before,a.batch)
