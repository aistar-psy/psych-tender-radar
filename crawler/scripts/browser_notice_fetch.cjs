/* Ordinary Chrome rendering, resumable receipts and bounded per-site traffic. */
const fs=require('fs'),path=require('path'),crypto=require('crypto'),net=require('net');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
function allowed(value){
  try {const u=new URL(value),h=u.hostname.toLowerCase();
    return /^https?:$/.test(u.protocol)&&!u.username&&!u.password&&!u.port&&
      !net.isIP(h)&&!h.startsWith('[')&&!/(^|\.)(localhost|local|internal)$/.test(h)&&h.includes('.');
  } catch{return false}
}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function run(queueFile,outDir,workers=3){
  const queue=JSON.parse(fs.readFileSync(queueFile)),out=path.resolve(outDir);
  fs.mkdirSync(path.join(out,'bodies'),{recursive:true});fs.mkdirSync(path.join(out,'diagnostics'),{recursive:true});
  const file=path.join(out,'manifest.json');
  const records=new Map((fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[]).map(r=>[r.url,r]));
  const save=()=>{const tmp=file+'.tmp';fs.writeFileSync(tmp,JSON.stringify([...records.values()],null,2));fs.renameSync(tmp,file)};
  const todo=queue.filter(r=>allowed(r.url)&&records.get(r.url)?.status!=='ok');
  const hosts=new Set(),lastHost=new Map(),diagnosticHosts=new Set();let finished=0;
  const browser=await chromium.launch({headless:process.env.RADAR_HEADFUL!=='1',channel:process.env.CHROME_CHANNEL||'chrome'});
  async function worker(){
    const context=await browser.newContext({locale:'zh-CN'});
    while(todo.length){
      const i=todo.findIndex(r=>!hosts.has(new URL(r.url).hostname));
      if(i<0){await sleep(100);continue}
      const seed=todo.splice(i,1)[0],url=seed.url,host=new URL(url).hostname;hosts.add(host);
      await sleep(Math.max(0,650-(Date.now()-(lastHost.get(host)||0))));
      const page=await context.newPage();
      const row={url,kind:seed.kind||'document',provider:'public_browser',read_at:new Date().toISOString()};
      try{
        const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:22000});
        row.status_code=response?.status();row.final_url=page.url();
        await page.waitForTimeout(750);
        try{await page.waitForFunction(()=>document.body?.innerText.length>250,{},{timeout:3500})}catch{}
        const text=await page.locator('body').innerText({timeout:4000});
        const challenged=/人机验证|访问验证|安全验证|HumanMachineVerification|Access Denied|验证码|cf-chl-/.test(text)&&text.length<2200;
        if(challenged)throw Error('access_challenge');
        if(response?.status()>=400)throw Error('HTTP_'+response.status());
        if(!allowed(page.url()))throw Error('non_public_redirect');
        const content=await page.content();if(Buffer.byteLength(content)>6*1024*1024)throw Error('body_limit');
        const hash=crypto.createHash('sha256').update(content).digest('hex'),p='bodies/'+hash+'.bin';fs.writeFileSync(path.join(out,p),content);
        const links=await page.locator('a[href]').evaluateAll(xs=>xs.map(a=>({url:a.href,text:a.innerText.trim()})));
        const origins=links.filter(a=>/原文|原始公告|来源网站|信息来源|查看来源|原公告链接/.test(a.text)&&allowed(a.url));
        const frames=page.frames().filter(f=>f!==page.mainFrame()&&allowed(f.url())).map(f=>({url:f.url(),text:'iframe 公告正文入口'}));
        Object.assign(row,{status:'ok',sha256:hash,path:p,content_type:'text/html; charset=utf-8',visible_characters:text.length,origin_links:origins,frame_links:frames});
      }catch(e){
        const message=String(e);Object.assign(row,{status:'failed',error_type:message.includes('access_challenge')?'access_challenge':'browser_read_failed',error:message.slice(0,1200)});
        if(!diagnosticHosts.has(host)){
          diagnosticHosts.add(host);
          try{const stem=crypto.createHash('sha256').update(url).digest('hex');
            fs.writeFileSync(path.join(out,'diagnostics',stem+'.txt'),(await page.locator('body').innerText({timeout:1500})).slice(0,15000));
            await page.screenshot({path:path.join(out,'diagnostics',stem+'.png'),timeout:3000});row.diagnostic='diagnostics/'+stem;
          }catch{}
        }
      }finally{
        records.set(url,row);save();await page.close();lastHost.set(host,Date.now());hosts.delete(host);
        finished++;if(finished%10===0)console.log(JSON.stringify({finished,total:queue.length,downloaded:[...records.values()].filter(r=>r.status==='ok').length,last:row.status,host}));
      }
    }
    await context.close();
  }
  try{await Promise.all(Array.from({length:Math.max(1,Math.min(workers,4))},worker))}finally{save();await browser.close()}
  console.log(JSON.stringify({total:records.size,downloaded:[...records.values()].filter(r=>r.status==='ok').length}));
}
module.exports={allowed,run};
if(require.main===module)run(process.argv[2],process.argv[3],Number(process.argv[4]||3)).catch(e=>{console.error(String(e));process.exitCode=1});
