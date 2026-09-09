/* Read ordinary rendered public pages; stop at verification/login challenges. */
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),queue=JSON.parse(fs.readFileSync(process.argv[2])),out=path.resolve(process.argv[3]);fs.mkdirSync(path.join(out,'bodies'),{recursive:true});
const file=path.join(out,'manifest.json');const records=new Map((fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[]).map(r=>[r.url,r]));
function allowed(value){try{const u=new URL(value);return /^https?:$/.test(u.protocol)&&!u.username&&!u.password&&!u.port&&!/^(localhost|127\.|10\.|192\.168\.|0\.|169\.254\.|\[)/i.test(u.hostname)}catch{return false}}
const save=()=>fs.writeFileSync(file,JSON.stringify([...records.values()],null,2));
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage();let n=0;
for(const seed of queue){const url=seed.url;if(!allowed(url)||records.get(url)?.status==='ok')continue;const row={url,kind:seed.kind||'document',provider:'public_browser',read_at:new Date().toISOString()};
 try{const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:18000});await page.waitForTimeout(1200);const text=await page.locator('body').innerText({timeout:5000});
 if(/人机验证|访问验证|安全验证|HumanMachineVerification|Access Denied|验证码/.test(text)&&text.length<1500)throw Error('access_challenge');if(response?.status()>=400)throw Error('HTTP_'+response.status());if(!allowed(page.url()))throw Error('non_public_redirect');
 const content=await page.content(),hash=crypto.createHash('sha256').update(content).digest('hex'),p='bodies/'+hash+'.bin';fs.writeFileSync(path.join(out,p),content);
 const links=await page.locator('a[href]').evaluateAll(xs=>xs.map(a=>({url:a.href,text:a.innerText.trim()})));
 const origins=links.filter(a=>/原文|原始公告|来源网站|信息来源|查看来源|原公告链接/.test(a.text)&&/^https?:/.test(a.url));
 Object.assign(row,{status:'ok',status_code:response?.status()||200,sha256:hash,path:p,content_type:'text/html; charset=utf-8',final_url:page.url(),visible_characters:text.length,origin_links:origins});
 }catch(e){Object.assign(row,{status:'failed',error_type:'browser_read_failed',error:String(e).slice(0,220)})}
 records.set(url,row);save();console.log(++n,row.status,row.visible_characters||0,new URL(url).hostname);await page.waitForTimeout(350);
}await browser.close()})().catch(e=>{save();console.error(String(e));process.exitCode=1});
