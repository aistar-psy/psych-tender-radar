from .search_recipes import keyword_text
"""Conservative rule extraction: every candidate retains its source evidence."""
import re
from datetime import datetime
from decimal import Decimal

PSYCH = r'心理|心育|情绪|精神卫生|精神健康|抑郁|焦虑'
EDU = r'学校|校园|学生|中小学|中学|小学|幼儿园|教育局|教育厅|教育委员会|教委|大学|高校|学院'
MEDICAL = r'医院|诊疗|病房|医疗|临床'
PRODUCT = re.compile(r'[^，。；：:|\n]{0,25}(?:系统|平台|设备|软件|量表|仪器|机器人|训练仪|测评工具|咨询室|课程|培训|服务|终端)')
DATE = r'(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?(?:[ T\s]*(\d{1,2})[:：点时](\d{1,2})分?(?:(?:[:：]|分)(\d{2})秒?)?)?'
BUYER_LABEL = r'(?:采购人(?:名称)?(?:[（(]甲方[）)])?|采购单位(?:名称)?)'


def _buyer(blocks,url):
    headers={}
    def valid(value):
        return len(value)>=2 and bool(re.search(r'[\u4e00-\u9fffA-Za-z]',value)) and not re.fullmatch(r'(?:采购项目名称|采购需求概况|名称|采购人信息)',value) and not re.search(r'QQ|服务群|联系电话',value,re.I)
    for index,block in enumerate(blocks):
        line=block['text']; candidates=[]; evidence_text=line
        if block.get('kind')=='table_row':
            key=(block.get('source_url',url),block.get('locator','').rsplit('/row:',1)[0])
            cells=[c.strip() for c in line.split('|')]
            named=[i for i,c in enumerate(cells) if re.fullmatch(BUYER_LABEL,c)]
            # Multiple column labels indicate a header, not a label/value row.
            if named and any(re.fullmatch(r'采购项目名称|项目名称|采购需求概况',c) for c in cells): headers[key]=named
            elif key in headers:
                candidates.extend(cells[i] for i in headers[key] if i<len(cells))
        candidates.extend(m.group(1).strip() for m in re.finditer(BUYER_LABEL+r'\s*[:：|]\s*([^\n|；;]{2,100})',line))
        if re.search(r'采购人信息',line):
            section=line
            for following in blocks[index+1:index+4]:
                if following.get('source_url',url)!=block.get('source_url',url) or re.search(r'采购代理',following['text']): break
                section+='\n'+following['text']
            match=re.search(r'采购人信息\s*名\s*称\s*[:：|]\s*([^\n|；;]{2,100})',section)
            if match:
                candidates.append(match.group(1).strip())
                evidence_text=section
        for name in candidates:
            if valid(name):
                return name,{'text':evidence_text,'locator':block.get('locator','document'),'url':block.get('source_url',url)}
    return None,None


def _dated(text,label,tz,warnings):
    match=re.search(label+r'\s*[:：|]?\s*'+DATE,text)
    if not match: return None
    try:
        parts=match.groups()
        dt=datetime(int(parts[0]),int(parts[1]),int(parts[2]),int(parts[3] or 0),int(parts[4] or 0),int(parts[5] or 0),tzinfo=tz)
        return dt.isoformat() if parts[3] is not None else dt.date().isoformat()
    except ValueError:
        warnings.append('invalid labeled date ignored'); return None


def analyze_document(doc: dict, url: str, now: str) -> dict:
    warnings=list(doc.get('warnings',[]))
    try:
        current=datetime.fromisoformat(now.replace('Z','+00:00'))
        if current.tzinfo is None: raise ValueError('now must include timezone')
    except ValueError as exc:
        raise ValueError('now must be an ISO timestamp with timezone') from exc
    blocks=doc.get('blocks') or [{'text':doc.get('text',''),'locator':'document','kind':'text'}]
    text=doc.get('text','') or '\n'.join(b['text'] for b in blocks)
    corpus=keyword_text(doc.get('title','')+'\n'+text)
    psych=bool(re.search(PSYCH,corpus)); edu=bool(re.search(EDU,corpus))
    medical=bool(re.search(MEDICAL,corpus))
    ordinary=bool(re.search(r'普通椅|轮椅|病床|办公家具|保洁|物业|空调',corpus))
    specific=bool(re.search(r'心理(?:测评|评估|咨询|辅导|干预|健康教育)|心育|情绪(?:调节|识别|训练)|抑郁(?:评估|筛查)',corpus))
    title=doc.get('title','')
    title_psych=bool(re.search(PSYCH,keyword_text(title)))
    if title_psych and re.search(MEDICAL,title):
        category='其他心理'
    elif title_psych and re.search(EDU,title) and re.search(r'平台|系统|心理健康|心育|心理测评',title):
        category='教育核心'
    elif medical and ordinary and not specific:
        category='排除'
    elif psych and edu and not (medical and re.search(r'诊疗|临床',corpus)):
        category='教育相关' if re.search(r'教师.*(?:培训|咨询)|家长.*(?:培训|咨询)',corpus) and not re.search(r'校园|学生|心育',corpus) else '教育核心'
    elif psych and re.search(r'未成年人|未保|青少年|家庭教育|家长教育',corpus) and not medical:
        category='教育相关'
    elif psych:
        category='其他心理'
    else:
        category='待核验'
    evidence=[{'text':b['text'],'locator':b.get('locator','document'),'url':b.get('source_url',url)} for b in blocks if re.search(PSYCH+'|'+EDU+'|健康画像',b['text'])][:8]
    result={'title':doc.get('title',''),'project_number':None,'published_at':None,'deadline':None,'category':category,'category_evidence':evidence,'products':[],'parameters':[],'amounts':[],'warnings':warnings}
    result['buyer'],result['buyer_evidence']=_buyer(blocks,url)
    notice_types=('更正公告','终止公告','废标公告','中标（成交）结果公告','成交结果公告','中标结果公告','成交公告','中标公告','中标公示','中标通知书','合同公告','采购意向','招标计划','竞争性磋商公告','竞争性谈判公告','询价公告','招标公告','采购信息公告','采购公告','采购公示')
    result['notice_type']=next((kind for source in (title,corpus) for kind in notice_types if kind in source),None)
    result['is_procurement']=bool(re.search(r'采购(?:信息)?公告|采购公示|招标公告|磋商公告|谈判公告|询价公告|采购意向|(?:成交|中标)(?:[（(]成交[）)])?(?:结果)?(?:公告|公示|明细)|中标通知书|合同公告|招标计划|采购项目|采购需求|采购预算|预算金额|项目编号|采购编号|招标编号',corpus))
    if re.search(r'更正公告|终止公告|废标公告',corpus) and re.search(r'响应|投标|采购|招标|供应商|成交|中标|磋商',corpus):
        result['is_procurement']=True
    if re.search(r'比选公告|遴选公告',corpus) and re.search(r'供应商|报价文件|采购|招标',corpus):
        result['is_procurement']=True
    result['procurement_hint']=result['is_procurement']
    result['content_status']=doc.get('content_status','available')
    if result['content_status']=='unavailable': result['is_procurement']=None
    number=re.search(r'(?:项目编号|项目号|采购编号|招标编号|采购计划编号)\s*[:：|]\s*([A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff_.()（）\[\]〔〕/—-]{2,79})',text)
    if number: result['project_number']=number.group(1)
    date_label=r'(?:发布日期|发布时间|公告日期|公告发布时间|信息提供日期|信息时间)'
    primary_blocks=[b for b in blocks if b.get('source_url',url)==url]
    for selected in ([b for b in primary_blocks if b.get('kind')=='metadata'], [b for b in primary_blocks if b.get('kind')!='table_row'], primary_blocks):
        date_text='\n'.join(b['text'] for b in selected)
        result['published_at']=_dated(date_text,date_label,current.tzinfo,warnings)
        if not result['published_at'] and selected and all(b.get('kind')=='metadata' for b in selected):
            result['published_at']=_dated(date_text,r'(?:时间|日期)',current.tzinfo,warnings)
        if result['published_at']: break
    if not result['published_at']:
        for block in blocks:
            if block.get('kind')=='metadata':
                result['published_at']=_dated(block['text'],r'(?:时间|日期)',current.tzinfo,warnings)
                if result['published_at']: break
    result['bid_at']=result['published_at']
    result['bid_at_semantics']='公开发布日期'
    result['opening_at']=_dated(text,r'(?:(?:开标|开启)\s*(?:时间|日期)|(?:开标|开启)\s*[:：]?\s*时间)',current.tzinfo,warnings)
    buyer_name=result['buyer'] or ''
    result['buyer_type']='B/企业' if re.search(r'公司|集团|企业',buyer_name) else ('G/事业单位' if re.search(r'大学|学院|学校|小学|中学|幼儿园|教育局|教育厅|委员会|政府|管理局|管理中心|事业单位',buyer_name) else '未知')
    result['buyer_type_evidence']={'method':'根据采购人名称规则推断，待核验','text':buyer_name,'url':url} if buyer_name else {'method':'采购人未识别，未知'}
    primary_text=re.split(r'采购代理(?:机构)?(?:信息)?',text,maxsplit=1)[0]
    candidates=[]
    buyer_section=re.search(r'采购人(?:信息|名称)?[\s\S]{0,600}',primary_text)
    if buyer_section:
        address=re.search(r'地\s*址\s*[:：|]\s*([^\n|]{2,150})',buyer_section.group(0))
        if address: candidates.append(address.group(1))
    candidates.extend(m.group(1) for m in re.finditer(r'(?:项目实施地点|项目所在地|所属地区|项目地点|采购人地址)\s*[:：|]\s*([^\n|]{2,150})',primary_text))
    if buyer_name: candidates.append(buyer_name)
    provinces='北京市 天津市 上海市 重庆市 河北省 山西省 辽宁省 吉林省 黑龙江省 江苏省 浙江省 安徽省 福建省 江西省 山东省 河南省 湖北省 湖南省 广东省 海南省 四川省 贵州省 云南省 陕西省 甘肃省 青海省 台湾省 内蒙古自治区 广西壮族自治区 西藏自治区 宁夏回族自治区 新疆维吾尔自治区 香港特别行政区 澳门特别行政区'.split()
    matched={province for candidate in candidates for province in provinces if province in candidate}
    result['province']=next(iter(matched)) if len(matched)==1 else None
    if len(matched)>1: warnings.append('采购方地区证据冲突，省份待核验')
    result['deadline']=_dated(text,r'(?:(?:响应|投标)\s*(?:截止时间|截止日期)|(?:提交|递交)(?:响应|投标)文件\s*[:：]?\s*(?:截止时间|截止日期)|(?:响应|投标)文件(?:提交|递交)\s*(?:截止时间|截止日期))',current.tzinfo,warnings)
    amount_re=re.compile(r'(?P<label>预算金额(?:（亦是最高限价）)?|采购预算|项目预算|最高限价|最高投标限价|成交金额|中标金额|中标价格|合同金额|预算)\s*(?:为)?\s*[:：|]?\s*(?:人民币)?\s*(?P<symbol>[¥￥]?)\s*(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>亿元|万元|元)?')
    seen=set()
    table_headers={}
    amount_headers={}
    for bi,b in enumerate(blocks):
        line=b['text']; loc=b.get('locator','document')
        ev={'text':line,'locator':loc,'url':b.get('source_url',url)}
        amount_line=line
        amount_blocks=[b]
        valid=lambda m: bool(m['unit'] or m['symbol'])
        matches=[m for m in amount_re.finditer(amount_line) if valid(m)]
        if not matches and re.search(r'预算|限价|成交金额|中标金额|中标价格|合同金额',line) and b.get('kind')!='table_row':
            for following in blocks[bi+1:bi+4]:
                if following.get('source_url',url)!=b.get('source_url',url) or following.get('kind')=='table_row': break
                amount_blocks.append(following)
                amount_line+=' '+following['text']
                matches=[m for m in amount_re.finditer(amount_line) if valid(m) and m.start()<len(line)]
                if matches: break
        for m in matches:
            kind='合同' if '合同' in m['label'] else ('预算' if '预算' in m['label'] else ('限价' if '限价' in m['label'] else '成交'))
            value=Decimal(m['value'].replace(',',''))*{'亿元':Decimal(100000000),'万元':Decimal(10000),'元':Decimal(1)}[m['unit'] or '元']
            kinds=[kind,'限价'] if '亦是最高限价' in m['label'] else [kind]
            for kind in kinds:
                key=(kind,str(value),loc)
                if key not in seen:
                    result['amounts'].append(dict(ev,text=amount_line,type=kind,value=float(value),currency='CNY',raw=m.group(0),source_locators=[item.get('locator','document') for item in amount_blocks])); seen.add(key)
        if re.search(r'预算金额|采购预算|最高限价|成交金额|中标金额',line) and re.search(r'¥|￥|人民币',line) and not amount_re.search(line):
            warnings.append('金额待核验：'+loc+' '+line[:180])
        tabular_product=False
        if b.get('kind')=='table_row':
            table_key=(b.get('source_url',url),loc.rsplit('/row:',1)[0])
            cells=[c.strip() for c in line.split('|')]
            monetary=[(i,c) for i,c in enumerate(cells) if re.search(r'预算(?:金额)?|最高限价|成交金额|中标金额',c) and not re.search(r'\d',c)]
            if monetary:
                amount_headers[table_key]=monetary
            elif table_key in amount_headers:
                for index,header in amount_headers[table_key]:
                    if index>=len(cells): continue
                    unit=re.search(r'亿元|万元|元',header)
                    number_cell=re.fullmatch(r'[¥￥]?\s*(\d[\d,]*(?:\.\d+)?)\s*(亿元|万元|元)?(?:人民币)?',cells[index])
                    if not number_cell or not (number_cell.group(2) or unit): continue
                    unit_name=number_cell.group(2) or unit.group(0)
                    kind='预算' if '预算' in header else ('限价' if '限价' in header else '成交')
                    value=Decimal(number_cell.group(1).replace(',',''))*{'亿元':Decimal(100000000),'万元':Decimal(10000),'元':Decimal(1)}[unit_name]
                    result['amounts'].append(dict(ev,type=kind,value=float(value),currency='CNY',raw=header+'：'+cells[index]))
            if any(re.search(r'标的名称|产品名称|货物名称|设备名称|服务名称',c) for c in cells):
                table_headers[table_key]=cells
            elif psych and table_key in table_headers:
                headers=table_headers[table_key]
                for index,header in enumerate(headers):
                    if re.search(r'标的名称|产品名称|货物名称|设备名称|服务名称',header) and index<len(cells) and cells[index]:
                        result['products'].append(dict(ev,name=cells[index],review_status='候选，待业务复核'))
                        tabular_product=True
                quantity_indices=[i for i,h in enumerate(headers) if '数量' in h]
                if tabular_product and any(i<len(cells) and re.search(r'\d',cells[i]) for i in quantity_indices):
                    result['parameters'].append(dict(ev,review_status='候选，待业务复核'))
        if re.search(PSYCH,line) and not tabular_product:
            for match in PRODUCT.finditer(line):
                result['products'].append(dict(ev,name=match.group(0).strip(),review_status='候选，待业务复核'))
        fulfillment = psych and re.search(r'部署|交付|实施周期|服务期|云服务|软件服务|质保|维保|技术支持|履约|验收|系统配置|存储容量',line) and re.search(r'\d+\s*(?:个)?(?:工作日|日|天|月|年|GB|TB)|≥|≤|不少于|不低于|不超过',line,re.I)
        if not tabular_product and (fulfillment or (re.search(PSYCH,line) or b.get('kind')=='table_row') and re.search(r'≥|≤|不少于|不低于|不超过|支持|规格|参数|并发|数量\s*[:：]?\s*\d|\d+\s*(?:套|台|个|人|秒|寸|GB|TB)',line,re.I)):
            result['parameters'].append(dict(ev,review_status='候选，待业务复核'))
    warnings.append('规则提取，待业务复核；仅保留原文候选，不代表完整参数清单')
    return result
