/* Normal public page navigation; no direct API retries or verification bypass. */
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const runtime=process.env.PLAYWRIGHT_MODULE||'playwright';const {chromium}=require(runtime);
const root=path.resolve(__dirname,'..'),out=path.join(root,'data/native-search'),plan=JSON.parse(fs.readFileSync(path.join(out,'browser_plan.json')));
const file=path.join(out,'queries-browser-cq.json');let logs=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[];
const save=()=>fs.writeFileSync(file,JSON.stringify(logs,null,2));
(async()=>{const b=await chromium.launch({headless:true,channel:'chrome'});const p=await b.newPage();p.setDefaultTimeout(4000);
for(const seed of plan){const id=crypto.createHash('sha256').update('browser:'+JSON.stringify(seed)).digest('hex').slice(0,24);if(logs.some(x=>x.id===id&&['exhausted','date_boundary_observed'].includes(x.stop_reason)))continue;
 const q={...seed,id,provider:'native_public_browser',checked_at:new Date().toISOString(),records:[],pages:[],field_verified:false,date_verified:false,pagination_complete:false,fulltext_status:'search_snippets_only',complete:false};let url='https://www.cqggzy.com/search?keyword='+encodeURIComponent(seed.keyword),seen=new Set();
 for(let n=1;n<=30;n++){
 try{await p.goto(url,{waitUntil:'commit',timeout:18000});let text='';for(let wait=0;wait<12;wait++){text=await p.locator('body').innerText().catch(()=>'');if(/为您找到\s*[\d,]+\s*个相关内容/.test(text))break;if(/人机验证|访问验证|Access Denied/.test(text))throw Error('access_challenge');await p.waitForTimeout(1000)}
 const m=text.match(/为您找到\s*([\d,]+)\s*个相关内容/);if(!m)throw Error('result_area_not_loaded');q.reported_total=Number(m[1].replaceAll(',',''));
 const rows=await p.locator('li').evaluateAll(xs=>xs.flatMap(x=>{let a=x.querySelector('a[href*="/searchDetail/"]'),d=x.innerText.match(/发布时间：[\s]*(\d{4}-\d{2}-\d{2})/);return a?[{url:a.href,title:a.innerText,published_at:d?.[1]||'',snippet:''}]:[]}));
 if(!rows.length&&q.reported_total>0)throw Error('result_parser_missing_rows');let hash=crypto.createHash('sha256').update(JSON.stringify(rows.map(x=>x.url))).digest('hex');if(seen.has(hash))throw Error('repeated_page');seen.add(hash);
 const html=await p.content(),ev='data/native-search/evidence/cq-'+crypto.createHash('sha256').update(html).digest('hex')+'.html';fs.writeFileSync(path.join(root,ev),html);q.pages.push({offset:(n-1)*10,status:'ok',rows:rows.length,total:q.reported_total,evidence:ev});q.records.push(...rows);
 const dates=q.records.map(x=>x.published_at);const descending=dates.every((d,i)=>d&&(!i||d<=dates[i-1]));
 if(rows.length&&rows.every(x=>x.published_at&&x.published_at<seed.start)&&descending){q.stop_reason='date_boundary_observed';break}
 if(q.records.length>=q.reported_total){q.stop_reason='exhausted';q.pagination_complete=true;break}
 const next=await p.locator('a[href*="pageNum="]').evaluateAll((xs,n)=>xs.map(x=>x.href).find(u=>new URL(u).searchParams.get('pageNum')===String(n+1)),n);
 if(!next)throw Error('next_page_missing');url=next;q.stop_reason='page_budget';q.next_url=url;
 await p.waitForTimeout(500);
 }catch(e){q.pages.push({offset:(n-1)*10,status:'fetch_error',error:String(e).slice(0,220)});q.stop_reason='fetch_error';break}
 }
 q.status=q.stop_reason==='fetch_error'?'partial_error':'ok';q.native_result_url_count=new Set(q.records.map(x=>x.url)).size;logs=logs.filter(x=>x.id!==id);logs.push(q);save();console.log(seed.keyword,q.records.length,q.pages.length,q.stop_reason);
 if(q.stop_reason==='fetch_error'&&!q.records.length)break;
}await b.close()})();
