/* Read visible public search results and ordinary popup links only. */
const fs=require('fs'),path=require('path'),crypto=require('crypto');const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'data/native-search'),plan=JSON.parse(fs.readFileSync(path.join(out,'jianyu_plan.json')));const file=path.join(out,'queries-browser-jianyu.json');let logs=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[];
(async()=>{const b=await chromium.launch({headless:true,channel:'chrome'}),p=await b.newPage();p.setDefaultTimeout(5000);
for(const seed of plan){let q={...seed,id:crypto.createHash('sha256').update('jy-public:'+JSON.stringify(seed)).digest('hex').slice(0,24),provider:'native_public_browser',checked_at:new Date().toISOString(),pages:[],records:[],listings:[],pagination_complete:false,field_verified:false,date_verified:false,fulltext_status:'search_snippets_only',complete:false};
try{await p.goto('https://www.jianyu360.cn/jylab/supsearch/index.html?keywords='+encodeURIComponent(seed.keyword)+'&selectType=title&searchGroup=1',{waitUntil:'commit',timeout:20000});await p.getByText(/搜索到\s*[\d,]+\s*条信息/).first().waitFor({timeout:40000});
for(let n=1;n<=Number(process.env.MAX_PUBLIC_PAGES||10);n++){
 await p.waitForTimeout(700);let text=await p.locator('body').innerText();q.reported_total=Number(text.match(/搜索到\s*([\d,]+)\s*条信息/)?.[1].replaceAll(',',''));q.selected_filters=await p.locator('.j-button-item.active').allTextContents();
 const titles=await p.locator('.a-i-left').allTextContents();if(!titles.length&&q.reported_total>0)throw Error('result_rows_missing');const fingerprint=crypto.createHash('sha256').update(JSON.stringify(titles)).digest('hex');if(q.pages.some(x=>x.sha256===fingerprint))throw Error('repeated_page');
 const ev='data/native-search/evidence/jy-'+q.id+'-'+n+'.html';fs.writeFileSync(path.join(root,ev),await p.content());q.pages.push({offset:(n-1)*50,status:'ok',rows:titles.length,total:q.reported_total,sha256:fingerprint,evidence:ev});
 for(let i=0;i<titles.length;i++){let item={title:titles[i].replace(/^\s*\d+\.\s*/,''),query:seed.keyword,page:n};if(!/^\s*\d+\./.test(titles[i]))continue;q.listings.push(item);
 // Only procurement-like titles enter the slower original-link resolution queue.
 if(process.env.RESOLVE_PUBLIC_LINKS!=='1'||!/采购|招标|中标|成交|询价|磋商|合同|竞价|公告|比选|意向/.test(item.title))continue;
 let popup=p.waitForEvent('popup',{timeout:3000}).catch(()=>null);await p.locator('.a-i-left').nth(i).click({timeout:4000});let page=await popup;
 if(!page){q.link_limitation='标题点击未提供公开链接，保留待回链标题';continue}
 await page.waitForURL(u=>u.protocol==='https:'||u.protocol==='http:',{timeout:4000}).catch(()=>{});let url=page.url();if(/^https?:/.test(url)){item.url=url;q.records.push({...item,url,published_at:null,snippet:'',link_verified:false})}await page.close();
 }
 q.stop_reason='page_budget';logs=logs.filter(x=>x.id!==q.id);logs.push(q);fs.writeFileSync(file,JSON.stringify(logs,null,2));console.log(seed.keyword,'page',n,'rows',titles.length,'linked',q.records.length);
 const next=p.locator('.el-pagination .btn-next');if(await next.isDisabled()){q.stop_reason=q.listings.length>=q.reported_total?'exhausted':'visible_page_limit';q.pagination_complete=q.stop_reason==='exhausted';break}
 await p.bringToFront();const numbered=p.locator('li.number').filter({hasText:new RegExp('^'+(n+1)+'$')});if(await numbered.count())await numbered.first().click({timeout:4000});else await next.click({timeout:4000});await p.waitForFunction(n=>document.querySelector('.el-pager .number.active')?.textContent.trim()===String(n+1),n,{timeout:12000,polling:250});await p.waitForTimeout(1000);
}
q.status='ok';
}catch(e){fs.writeFileSync(path.join(out,'jianyu-last-error.html'),await p.content().catch(()=>''));q.status='partial_error';q.stop_reason='fetch_error';q.pages.push({status:'fetch_error',error:String(e).slice(0,220)});}
const previous=logs.find(x=>x.id===q.id);if(previous&&previous.records.length>q.records.length){q.previous_attempt_error=q.pages.at(-1);q.records=previous.records;q.listings=previous.listings;q.pages=previous.pages.concat(q.pages.filter(x=>x.status!=='ok'));}logs=logs.filter(x=>x.id!==q.id);logs.push(q);fs.writeFileSync(file,JSON.stringify(logs,null,2));console.log(seed.keyword,q.stop_reason,q.records.length);if(q.status==='partial_error')break;
}await b.close()})();
