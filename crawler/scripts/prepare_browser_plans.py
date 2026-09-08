import sys
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import build_recipe_plan,seed_plan,load_recipes
from radar.source_scan import load_catalog
from radar.pipeline import write_json,PACKAGE_ROOT
now=datetime.now(ZoneInfo('Asia/Shanghai'));start=(now-timedelta(days=364)).date().isoformat();end=now.date().isoformat()
for id,file in [('ggzy-chongqing','browser_plan.json'),('aggregator_jianyu360','jianyu_plan.json')]:
 source=next(s for s in load_catalog() if s['id']==id);plan=seed_plan(build_recipe_plan([source],start,end))
 for q in plan:q['recipe_sha256']=load_recipes()['source_sha256']
 write_json(PACKAGE_ROOT/'data/native-search'/file,plan)
print('已生成重庆和剑鱼原式种子计划；待执行不计完成。')
