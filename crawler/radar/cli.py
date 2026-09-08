"""python -m radar.cli --help"""
import argparse
import json
import re
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .pipeline import run,PACKAGE_ROOT,write_json,load
from .search_recipes import build_region_plan
from .store import Store

def main():
    parser=argparse.ArgumentParser(description='心理健康教育公开采购雷达（独立运行）')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan',help='生成可核验全国计划，不发网络请求')
    p.add_argument('--out',default=str(PACKAGE_ROOT/'data'/'plan.json'))
    p.add_argument('--as-of')
    p=sub.add_parser('run',help='执行发现、正文附件、分类与报告')
    p.add_argument('--data-dir',default=str(PACKAGE_ROOT/'data'/'runtime'))
    p.add_argument('--seed-file',default=str(PACKAGE_ROOT/'config'/'seeds.json'))
    p.add_argument('--url',action='append',default=[])
    p.add_argument('--no-discovery',action='store_true')
    p.add_argument('--max-discovery',type=int,default=192)
    p.add_argument('--max-documents',type=int,default=40)
    p.add_argument('--max-attachments',type=int,default=8)
    p.add_argument('--max-seconds',type=int,default=900)
    p.add_argument('--timeout',type=float,default=15)
    p.add_argument('--interval',type=float,default=1)
    p.add_argument('--as-of',help='含时区的ISO窗口截止时间')
    p.add_argument('--days',type=int,default=7,help='回溯窗口天数，年度为365')
    p.add_argument('--weekly',action='store_true',help='窗口截止按最近的周一09:00计算')
    p=sub.add_parser('import-legacy',help='只导入旧周报URL作为待核验线索')
    p.add_argument('path');p.add_argument('--out',default=str(PACKAGE_ROOT/'config'/'legacy_seeds.json'))
    p=sub.add_parser('status',help='显示最近一次运行与数据库计数')
    p.add_argument('--data-dir',default=str(PACKAGE_ROOT/'data'/'runtime'))
    args=parser.parse_args()
    if args.command=='plan':
        end=datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(ZoneInfo('Asia/Shanghai'))
        plan=build_region_plan(load(PACKAGE_ROOT/'config/regions.json',[]),
                        (end-timedelta(days=14)).date().isoformat(),end.date().isoformat())
        write_json(args.out,plan);print(json.dumps({'path':args.out,'tasks':len(plan),'executed':0},ensure_ascii=False));return
    if args.command=='import-legacy':
        root=Path(args.path);files=list(root.rglob('*.md')) if root.is_dir() else [root]
        urls={}
        for f in files:
            for title,url in re.findall(r'\[([^\]]*)\]\((https?://[^\s)]+)\)',f.read_text(encoding='utf-8')):
                urls.setdefault(url,{'url':url,'legacy_title':title,'imported_from':str(f),'status':'unverified_legacy'})
        write_json(args.out,list(urls.values()));print(json.dumps({'urls':len(urls),'path':args.out},ensure_ascii=False));return
    if args.command=='status':
        print(json.dumps(load(Path(args.data_dir)/'latest.json',{'status':'never_run'}),ensure_ascii=False,indent=2));return
    seeds=load(args.seed_file,[])+args.url
    as_of=args.as_of
    if args.weekly and not as_of:
        now=datetime.now(ZoneInfo('Asia/Shanghai'))
        end=(now-timedelta(days=now.weekday())).replace(hour=9,minute=0,second=0,microsecond=0)
        if end>now:end-=timedelta(days=7)
        as_of=end.isoformat()
    result=run(root=Path(args.data_dir),seeds=seeds,no_discovery=args.no_discovery,
               max_discovery=args.max_discovery,max_documents=args.max_documents,
               max_attachments=args.max_attachments,max_seconds=args.max_seconds,
               interval=args.interval,timeout=args.timeout,as_of=as_of,window_days=args.days)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
