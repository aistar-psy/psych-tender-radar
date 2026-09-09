"""Convert executed search responses to unconfirmed, deduplicated notice leads."""
import json,re,sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from radar.search_recipes import vocabulary_match,load_recipes
from radar.pipeline import write_json,PACKAGE_ROOT
rows=json.loads((PACKAGE_ROOT/'data/diagnostics/20260909/v15_complete_results.json').read_text());found={};queries=[]
for row in rows:
 queries.append({'query':row['q'],'status':'empty' if row['raw'].startswith('Empty') else 'ok','executed_at':datetime.now().astimezone().isoformat(),'provider':'web_search','recipe_version':load_recipes()['version'],'recipe_sha256':load_recipes()['source_sha256'],'field_verified':False,'pagination_complete':False})
 for block in row['raw'].split('-'*80):
  m=re.search(r'^([^\n]*?)\s*\((https?://[^\n]+)\)\s*\n',block.strip())
  if not m:continue
  title,url=m.groups();body=block[m.end():]
  if not vocabulary_match(title+' '+body) or not re.search(r'招标|采购|成交|中标|磋商|询比',title+' '+body[:1000]):continue
  if re.search(r'/enterprise/|/zbkeyw-|/hot\d|/gjxx/|/history-|/areanew_|/s_01_|/list[./?]|/index(?:_\d+)?\.|/px/',url):continue
  if not re.search(r'公告|招标|采购|成交|意向|询价|谈判|中标|公示|公共资源交易',title):continue
  if re.search(r'qixin\.com|qichacha\.com|zhengxin-pub|finance\.sina|cj\.sina|k\.sina|instrument\.com|ibook\.antpedia',url):continue
  date=None;d=re.search(r'(?:/t|/|content-)(20\d{2})(\d{2})(\d{2})(?:_|/)',url)
  if d:date='-'.join(d.groups())
  if not date:
   d=re.search(r'(?:发布时间|发布日期|公告时间)[：:|\s]*(20\d{2})[年.-](\d{1,2})[月.-](\d{1,2})',body)
   if d:date=f'{d[1]}-{int(d[2]):02}-{int(d[3]):02}'
  if date and not '2025-09-10'<=date<='2026-09-09':continue
  found[url]={'url':url,'title':title or '公告标题待核验','published_at':date,'search_note':re.sub(r'\ue200.*?\ue201|\[wordlim[^]]*\]','',body[:600]),'provider':'web_search_v15','query':row['q'],'source_status':'unconfirmed','recipe_version':load_recipes()['version']}
write_json(PACKAGE_ROOT/'data/external-discovery/v15_combined.json',list(found.values()));write_json(PACKAGE_ROOT/'data/external-discovery/v15_queries.json',{'executed_queries':queries});write_json(PACKAGE_ROOT/'data/v15_fetch_queue.json',list(found.values()));print(len(queries),'queries',len(found),'candidate URLs')
