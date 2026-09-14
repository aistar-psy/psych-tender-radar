/* Public Epoint search through a normally loaded browser; keep TLS verification. */
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),id=process.argv[2]||'ggzy-jiangxi',limit=Number(process.argv[3]||80);
const cfg=JSON.parse(fs.readFileSync(path.join(root,'config/native_search.json'))).find(c=>c.source_id===id);
if(!cfg||cfg.adapter==='chongqing')throw Error('unsupported_public_adapter');
const out=path.join(root,'data/native-search'),file=path.join(out,'queries-browser-'+id+'.json');
const plan=JSON.parse(fs.readFileSync(path.join(out,'epoint-'+id+'-plan.json')));
let logs=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[];
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const save=()=>fs.writeFileSync(file,JSON.stringify(logs,null,2));
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage();
try {
 await page.goto(cfg.base,{waitUntil:'domcontentloaded',timeout:20000});
 for(const seed of plan){
  const key=hash('epoint-browser:'+JSON.stringify([seed,cfg])).slice(0,24),old=logs.find(x=>x.id===key);
  if(old?.pagination_complete)continue;
  const q={...seed,id:key,provider:'native_public_browser_json',checked_at:new Date().toISOString(),records:old?.records||[],pages:old?.pages||[],field_verified:true,date_verified:false,pagination_complete:false,fulltext_status:'search_snippets_only',complete:false};
  let offset=old?.next_offset||0;const seen=new Set(q.pages.filter(p=>p.sha256).map(p=>p.sha256));
  for(let n=0;n<limit;n++){
   try{
    const payload={...cfg.payload,wd:seed.keyword,pn:offset,rn:10,sdt:seed.start+' 00:00:00',edt:seed.end+' 23:59:59'};
    const response=await page.evaluate(async ({url,payload})=>{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(18000)});return {status:r.status,text:await r.text()}},{url:cfg.endpoint,payload});
    if(response.status!==200)throw Error('HTTP '+response.status);
    let data=JSON.parse(response.text);if(typeof data.content==='string')data=JSON.parse(data.content);const result=data.result;
    if(!Array.isArray(result?.records)||!Number.isFinite(Number(result.totalcount)))throw Error('unrecognized_search_response');
    const records=await page.evaluate(({items,base})=>{const text=x=>new DOMParser().parseFromString(String(x||''),'text/html').body.textContent;return items.map(x=>{if(!x.linkurl)throw Error('missing_linkurl');return {url:new URL(x.linkurl,base).href,title:text(x.title),snippet:text(x.content),published_at:String(x.webdate||'').slice(0,10)}})},{items:result.records,base:cfg.base});
    q.reported_total=Number(result.totalcount);const fingerprint=hash(JSON.stringify(records.map(r=>r.url)));
    if(records.length&&seen.has(fingerprint))throw Error('repeated_page');if(!records.length&&offset<q.reported_total)throw Error('empty_page_before_total');seen.add(fingerprint);
    const evidence='data/native-search/evidence/'+hash(response.text)+'.json';fs.mkdirSync(path.dirname(path.join(root,evidence)),{recursive:true});fs.writeFileSync(path.join(root,evidence),JSON.stringify({url:cfg.endpoint,payload,response:data,read_at:new Date().toISOString()}));
    q.pages.push({offset,status:'ok',rows:records.length,total:q.reported_total,sha256:fingerprint,evidence});q.records=[...new Map([...q.records,...records].map(r=>[r.url,r])).values()];offset+=10;q.next_offset=offset;q.stop_reason='page_budget';
    if(offset>=q.reported_total){q.pagination_complete=q.records.length>=q.reported_total;q.stop_reason=q.pagination_complete?'exhausted':'count_mismatch';q.next_offset=q.pagination_complete?null:offset;break;}
    await page.waitForTimeout(650);
   }catch(e){q.pages.push({offset,status:'fetch_error',error:String(e).slice(0,300)});q.stop_reason='fetch_error';q.next_offset=offset;break;}
  }
  q.date_verified=q.records.length>0&&q.records.every(r=>r.published_at>=seed.start&&r.published_at<=seed.end);q.status=q.stop_reason==='fetch_error'?'partial_error':'ok';q.native_result_url_count=q.records.length;
  logs=logs.filter(x=>x.id!==key);logs.push(q);save();console.log(id,seed.keyword,q.records.length,q.stop_reason);
  if(q.stop_reason==='fetch_error'&&!q.records.length)break;
 }
}finally{await browser.close()}})().catch(e=>{console.error(String(e));process.exitCode=1});
