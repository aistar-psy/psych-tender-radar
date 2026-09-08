"""Human-readable output generated from the exact saved run snapshot."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

def cell(value):
    if value is None or value=='':return '未披露'
    if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
    return str(value).replace('|','\\|').replace('\n',' ')

def table(records):
    if not records:return '未取得可提取条目。\n'
    keys=list(dict.fromkeys(k for r in records for k in r))
    return '\n'.join(['|'+'|'.join(keys)+'|','|'+'|'.join('---' for _ in keys)+'|']+
                     ['|'+'|'.join(cell(r.get(k)) for k in keys)+'|' for r in records])+'\n'

def temporal_bucket(analysis,start,end):
    published=analysis.get('published_at')
    if not published:return '发布时间待核验'
    # Date-only publication is deliberately not precise enough for boundary-day assertions.
    try:
        raw=str(published)
        if len(raw)==10:
            if raw==start[:10] or raw==end[:10]:return '窗口边界待核验'
            return '窗口内公告' if start[:10]<raw<end[:10] else '历史补录/窗口外'
        p=datetime.fromisoformat(raw)
        if p.tzinfo is None:return '发布时间待核验'
        return '窗口内公告' if datetime.fromisoformat(start)<=p<datetime.fromisoformat(end) else '历史补录/窗口外'
    except (ValueError,TypeError):return '发布时间待核验'

def opportunity_state(analysis,as_of):
    kind=analysis.get('notice_type') or ''
    if any(k in kind for k in ('成交','中标','终止','废标')):return '结果/历史研究'
    if '意向' in kind:return '采购意向；正式招采待核验'
    deadline=analysis.get('deadline')
    if not deadline:return '响应时间待核验'
    try:
        if len(deadline)==10:return '响应时刻不精确；待核验'
        due=datetime.fromisoformat(deadline)
        if due.tzinfo is None:return '响应时区待核验'
        return '原定响应截止已过；更正/结果待核验' if due<=datetime.fromisoformat(as_of) else '按原公告尚未截止；资格及更正待核验'
    except (ValueError,TypeError):return '响应时间待核验'

def render(run_dir,summary,documents,tasks,pending):
    run_dir=Path(run_dir);details=run_dir/'details';details.mkdir(exist_ok=True)
    for d in documents:
        a=d['analysis'];p=details/(d['project_id']+'-'+d['notice_id']+'.md')
        lines=[f"# {a.get('title') or d['url']}",'',f"- 原文：[来源]({d['url']})",f"- 项目ID：{d['project_id']}",
               f"- 分类：{a.get('category','待核验')}；依据：{cell(a.get('category_evidence'))}",
               f"- 详情：{d['detail_status']}；来源等级：{d['evidence_level']}；提取：规则候选，需业务复核",
               f"- 核验时间：{d['fetched_at']}",f"- 发布时间：{cell(a.get('published_at'))}；响应截止：{cell(a.get('deadline'))}",
               f"- 编号：{cell(a.get('project_number'))}；采购人：{cell(a.get('buyer'))}",
               '- 已过原定截止只表示原公告窗口已过，更正/结果尚需查证。','',
               '## 金额（不跨口径汇总）','',table(a.get('amounts',[])),
               '## 产品/服务候选行','',table(a.get('products',[])),
               '## 技术/商务参数候选行','',table(a.get('parameters',[])),
               '## 附件与缺口','',table(d.get('attachments',[])),
               '## 原始证据','',table(d['evidence']),
               '## 待复核','']+[f'- {x}' for x in d.get('warnings',[]) + a.get('warnings',[])]
        p.write_text('\n'.join(lines),encoding='utf-8');d['detail_path']=str(p)
    counts=Counter(d['analysis'].get('category','待核验') for d in documents)
    lines=['# 心理健康教育采购雷达周报','',f"- 窗口：{summary['window_start']} 至 {summary['window_end']}（左闭右开）",
           f"- 运行：{summary['run_id']}；状态：{summary['status']}",
           f"- 本轮读取公告：{len(documents)}；本地累计唯一项目：{summary['counts']['projects']}",
           f"- 本轮分类（按公告计，不作为去重市场规模）：{dict(counts)}",
           f"- 未完成事项：{len(pending)}；本轮检索只覆盖实际执行的查询/栏目，不代表全网。",
           '- 参数为可追溯的规则提取候选，并非已确认的完整技术规格；没有取得的文件不会补写参数。',
           '- 截止和变更未形成完整关联前，不自动推荐“立即投标”。','']
    for category in ['教育核心','教育相关','其他心理','待核验','排除']:
        lines.extend([f'## {category}',''])
        rows=[]
        for d in documents:
            a=d['analysis']
            if a.get('category','待核验')!=category:continue
            path='details/'+Path(d['detail_path']).name
            rows.append({'项目':f"[{a.get('title','未识别标题')}]({path})",'编号':a.get('project_number'),
                         '公告阶段':a.get('notice_type'),'时间分组':temporal_bucket(a,summary['window_start'],summary['window_end']),
                         '发布日期':a.get('published_at'),'响应截止':a.get('deadline'),'参与窗口':opportunity_state(a,summary.get('actual_started_at',summary['window_end'])),
                         '产品候选条数':len(a.get('products',[])),'参数候选条数':len(a.get('parameters',[])),
                         '详情':d['detail_status']})
        lines.extend([table(rows) if rows else '本轮未取得该类可展示公告。',''])
    lines.extend(['## 覆盖与后续','', '[逐项执行与失败](coverage.md)','', '[结构化提取](documents.json)',
                  '', '未获取附件、未执行任务、失败来源都在待补清单；没有独立样本，本轮召回率未验证。'])
    report=run_dir/'weekly.md';report.write_text('\n'.join(lines),encoding='utf-8')
    states=Counter(t['status'] for t in tasks)
    completed=sum(states.get(k,0) for k in ('ok','empty'))
    coverage=['# 覆盖与质量','',f"计划任务 {len(tasks)}；成功执行 {completed}；状态分布 {dict(states)}。",
              '', '成功指完成该次查询或单页读取，搜索索引及单页栏目均不是站点全量。来源登记未配置项不算成功。',
              '', '所有省份具有检索计划不等于已完成逐省抓取。首轮没有独立抽样，因此不提供全国召回率。',
              '', '## 执行明细','',table(tasks),'','## 待补队列','',table(pending)]
    (run_dir/'coverage.md').write_text('\n'.join(coverage),encoding='utf-8')
    return str(report)
