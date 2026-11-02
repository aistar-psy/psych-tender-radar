"""Separate broad search recall from evidence of a psychology purchase.

A vocabulary hit is a discovery clue. This gate uses retained notice/attachment
text, never search snippets, to decide whether it belongs in the project list.
Missing evidence is quarantined for review; it does not prove market absence.
"""
import re
from .search_recipes import keyword_text

VERSION = '2026-11-02.2'
TARGET = re.compile(
    r'心理|心育|精神卫生|精神健康|精神障碍|精神测评|抑郁|焦虑|孤独症|自闭症|多动症|'
    r'情绪(?:调节|识别|训练|管理|疏导|宣泄|问题|监测)|无感式情感分析|压力管理|危机干预|'
    r'心灵驿站|舒心小屋|苏康驿站|心灵灯塔|阳光心灵|宣泄室|沙盘(?:游戏|治疗|咨询|辅导)|沙具|'
    r'生物反馈|正念|音乐放松|放松训练|减压(?:室|舱|训练|服务)|'
    r'团体辅导|认知神经|认知(?:训练|评估)|注意力(?:训练|测评|评估)|'
    r'自杀|自伤|校园欺凌|防欺凌|防霸凌|12355|12356'
)

def purchase_context(text):
    """Remove observed non-purchase senses without erasing actual training."""
    text = keyword_text(text)
    text = re.sub(r'核\s*心\s*理\s*念', '核心 理念', text)
    text = re.sub(r'(?:急切|急躁|消费|从众|投机|侥幸)心理(?!\s*(?:测评|测试|评估|实验|研究|课程|教学|培训|咨询|辅导|学))|心理(?:价位|预期|准备)(?!\s*(?:测评|测试|评估|实验|研究|课程|教学|培训|咨询|辅导))', '', text)
    text = re.sub(r'(?:具备|具有|应有|拥有|强大|良好|较强|较好)(?:良好|强大|较强|较好)?的?(?:心理素质|情绪管理能力)(?!\s*(?:培训|课程|训练|提升))', '', text)
    # Supplier identity alone says nothing about the purchased goods/services.
    text = re.sub(r'(?:供应商(?:名称)?(?:\s*[（(]乙方[）)])?|中标单位|成交供应商)\s*[:：|]\s*[^\n|；;。，,:：]+', '', text)
    return text

def assess_relevance(title, blocks, *, body_available):
    sources = [{'text': title or '', 'locator': 'title', 'field': '标题'}]
    if body_available:
        sources += [dict(b, field='正文/公开附件') for b in blocks]
    evidence = []
    supplier_next = False
    previous_url = None
    for block in sources:
        raw = block.get('text', '')
        source_url = block.get('source_url') or block.get('url') or ''
        name_only = supplier_next and source_url == previous_url and re.fullmatch(r'[^:：|\n]{2,100}(?:公司|学会|协会|学校|中心|研究院|工作室)', raw.strip())
        normalized = '' if name_only else purchase_context(raw)
        supplier_next = bool(re.fullmatch(r'(?:供应商(?:名称)?(?:[（(]乙方[）)])?|中标单位|成交供应商)\s*[:：|]?\s*', raw))
        previous_url = source_url
        match = TARGET.search(normalized)
        if match:
            evidence.append({'term': match[0], 'field': block['field'],
                             'locator': block.get('locator', 'document'),
                             'url': block.get('source_url') or block.get('url') or '',
                             'text': normalized[max(0, match.start()-80):match.end()+160]})
    if evidence:
        status = 'related' if body_available else 'unconfirmed'
        reason = '标题或已取得采购正文/附件含心理用途证据' if body_available else '标题有心理线索，正文用途尚待核验'
    elif body_available:
        status, reason = 'review_required', '已取得文本未发现心理采购用途；宽泛母包、文化口号及服务礼仪用语不能作为入库依据'
    else:
        status, reason = 'unconfirmed', '正文尚未取得，不能确认或排除心理子包'
    return {'version': VERSION, 'status': status, 'reason': reason, 'evidence': evidence[:8]}


def attach_relevance_audit(data, quarantined, audit_dir, public):
    """Persist the same review receipt for normal exports and saved-text refreshes."""
    import collections
    import json
    import shutil
    from pathlib import Path
    audit_dir, public = Path(audit_dir), Path(public)
    audit_dir.mkdir(parents=True, exist_ok=True)
    records = [q for q in quarantined if q['reason']=='psychology_evidence_missing']
    removed = [q['project'] for q in records if q['scope']=='archive']
    annual = lambda p: any(data['yearRange']['start']<=str(d)[:10]<=data['yearRange']['end'] for d in [p.get('publishedAt')]+[e.get('publishedAt') for e in p.get('events', [])] if d)
    reasons = {scope:dict(collections.Counter(q['reason'] for q in records if q['scope']==scope)) for scope in ('archive','historicalRunRows')}
    receipt = {'builtAt':data['builtAt'], 'ruleVersion':VERSION,
               'archiveBefore':len(data['archiveProjects'])+len(removed),
               'archiveAfter':len(data['archiveProjects']), 'archiveRemoved':len(removed),
               'annualRemoved':sum(annual(p) for p in removed),
               'historicalRowsRemoved':sum(q['scope']=='historicalRunRows' for q in records),
               'reasons':reasons,
               'method':'基于已保存公告/附件文本核验心理用途；相关性复核不等于新增正文抓取',
               'limitation':'缺少心理用途证据的记录移出项目列表并保留待复核，不据此断言原项目绝无心理子包；正文未取得的线索仍待核验。'}
    data['relevanceAudit'] = {**receipt, 'reviewRows':[{'title':p['title'], 'sourceUrl':p['sourceUrl'], 'reason':p['relevance']['reason']} for p in removed]}
    (audit_dir/'quarantined.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
    (audit_dir/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    for q in records:
        for ref in q['project'].get('fullTexts', []):
            path = ref['path']
            if not path.startswith('bodies/') or '..' in Path(path).parts:
                raise ValueError('Invalid public body path')
            dest = audit_dir/path; dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():shutil.copy2(public/path, dest)
    return receipt
