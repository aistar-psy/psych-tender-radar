/* Audit public entry controls with one fresh page per source; never infer absence. */
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),day=process.argv[3]||new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'}).replaceAll('-',''),out=path.join(root,'data/source-audit/browser-checks-'+day);
fs.mkdirSync(out,{recursive:true});
const plan=JSON.parse(fs.readFileSync(process.argv[2]||path.join(root,'data/weekly',day,'browser_audit_plan.json')));
const logfile=path.join(root,'data/source-audit/native_checks.json');
const old=fs.existsSync(logfile)?JSON.parse(fs.readFileSync(logfile)):[],results=[];let cursor=0;
function save(){fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));fs.writeFileSync(logfile,JSON.stringify([...old.filter(x=>!results.some(r=>r.source_id===x.source_id)),...results],null,2));}
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true,args:process.env.RADAR_BROWSER_DIRECT==='1'?['--no-proxy-server']:[]});
async function worker(){const context=await browser.newContext();
 while(cursor<plan.length){const page=await context.newPage();page.setDefaultTimeout(4000);const s=plan[cursor++],q={source_id:s.id,checked_at:new Date().toISOString(),entry_url:s.url,complete:false,positive_control_reference:s.positive_control_reference};
 try{const response=await page.goto(s.url,{waitUntil:'domcontentloaded',timeout:25000});q.http_status=response?.status();q.title=await page.title();q.final_url=page.url();let text=await page.locator('body').innerText({timeout:4000});
  const challenge=/人机验证|访问验证|安全验证|请输入验证码以继续|Access Denied|verify you are human/i;
  if(challenge.test(text)&&text.length<8000){q.status='verification_required';q.reason='公开入口显示验证要求；停止交互，未判断无公告。';}
  else if(s.id.startsWith('aggregator_')){q.status=/注册|登录|会员/.test(text)?'login_or_membership_prompt':'search_ui_unadapted';q.reason='公开聚合入口已读取；高级检索、会员权限及年度分页未完成核验。';q.visible_restrictions=text.split('\n').filter(l=>/注册|登录|会员|高级检索|高级搜索/.test(l)).slice(0,12);}
  else {q.status='search_ui_unadapted';q.reason='入口加载后，标题/全文范围、全年日期和分页尚未核实，不能判定无信息。';
   const inputs=page.locator('input[placeholder*="搜"],input[placeholder*="关键"],input[placeholder*="检索"],input[type="search"],input[id*="keyword"],input[name*="keyword"],input[id*="search"]');
   for(let i=0;i<await inputs.count();i++){const input=inputs.nth(i);if(!await input.isVisible()||!await input.isEditable())continue;
    await input.fill('心理健康');await input.press('Enter');await page.waitForTimeout(2200);text=await page.locator('body').innerText({timeout:4000});q.query='心理健康';q.atom_id='A.001';q.recipe_id='A';q.requested_field='title';q.field_verified=false;q.pagination_complete=false;
    q.status=challenge.test(text)&&text.length<8000?'verification_required':'search_ui_unverified';q.reason=q.status==='verification_required'?'检索后出现验证要求；停止交互，保留公开发布源补查。':'已在公开搜索框提交 A.001；返回区域、字段、日期及后续分页需继续核验，不推断整站无信息。';break;
   }
  }
  q.search_links=await page.locator('a[href]').evaluateAll(xs=>xs.filter(x=>/搜索|检索/.test(x.innerText)).slice(0,8).map(x=>({title:x.innerText,url:x.href})));
  q.evidence='data/source-audit/browser-checks-'+day+'/'+s.id+'.html';fs.writeFileSync(path.join(root,q.evidence),await page.content());
 }catch(e){q.status=q.http_status?'render_failed':'connection_failed';q.reason=q.http_status?'入口已响应，但结果区域或检索控件未完整加载。':'普通浏览器入口读取未完成，不能判断有无公告。';q.error=String(e).slice(0,400);}
 await page.close();results.push(q);save();console.log(s.id,q.status);
 }await context.close();}
await Promise.all(Array.from({length:4},worker));await browser.close();})().catch(e=>{console.error(e);process.exitCode=1});
