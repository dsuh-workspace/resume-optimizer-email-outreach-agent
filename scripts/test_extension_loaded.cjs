/* Real unpacked extension, isolated Chrome profile, intercepted synthetic portal.
   No production accounts, source data, model calls, or employer requests. */
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'applypilot-loaded-'));
const chrome=process.env.CHROME_BINARY||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let browser,backend,pending=new Map(),sequence=0,buffer='',events=[];
function call(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(new Error('Timeout: '+method));},20000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x);},reject:e=>{clearTimeout(timer);reject(e);}});browser.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');});}
async function evaluate(session,expression){const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true},session);if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function attach(id){return (await call('Target.attachToTarget',{targetId:id,flatten:true})).sessionId;}
async function until(fn,label,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){const v=await fn();if(v)return v;await pause(100);}throw new Error('Timed out: '+label);}
async function screenshot(session,file,width,height){await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false},session);const r=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},session);fs.writeFileSync(file,Buffer.from(r.data,'base64'));}
async function launch(){
  browser=spawn(chrome,['--headless=new','--remote-debugging-pipe','--enable-unsafe-extension-debugging','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--use-mock-keychain','--password-store=basic','--user-data-dir='+path.join(temporary,'profile'),'about:blank'],{stdio:['ignore','ignore','pipe','pipe','pipe']});
  browser.stderr.on('data',()=>{});
  browser.stdio[4].on('data',chunk=>{buffer+=chunk;let i;while((i=buffer.indexOf('\0'))>=0){const raw=buffer.slice(0,i);buffer=buffer.slice(i+1);if(!raw)continue;const message=JSON.parse(raw);if(message.id){const p=pending.get(message.id);pending.delete(message.id);if(p)message.error?p.reject(new Error(JSON.stringify(message.error))):p.resolve(message.result);}else events.forEach(fn=>fn(message));}});
  await call('Browser.getVersion');
}
(async()=>{
  await launch();
  const imageTarget=await call('Target.createTarget',{url:'about:blank'}),imageSession=await attach(imageTarget.targetId);
  if(!process.argv.includes('--skip-assets')){
  const svg=fs.readFileSync(path.join(root,'extension/icons/logo.svg'),'utf8');
  await call('Page.setDocumentContent',{frameId:(await call('Page.getFrameTree',{},imageSession)).frameTree.frame.id,html:'<style>html,body{margin:0;background:transparent}svg{width:100vw;height:100vh;display:block}</style>'+svg},imageSession);
  await call('Emulation.setDefaultBackgroundColorOverride',{color:{r:0,g:0,b:0,a:0}},imageSession);
  for(const n of [16,32,48,128,512])await screenshot(imageSession,path.join(root,'extension/icons/icon-'+n+'.png'),n,n);
  const sizes=[16,32,48,128];
  const cards=background=>'<div style="display:flex;align-items:center;justify-content:space-around;height:160px;background:'+background+'">'+sizes.map(n=>'<figure style="margin:0;text-align:center"><img width="'+n+'" height="'+n+'" src="data:image/png;base64,'+fs.readFileSync(path.join(root,'extension/icons/icon-'+n+'.png')).toString('base64')+'"><figcaption style="font:12px Arial;color:'+(background==='#202b27'?'white':'#174b3b')+'">'+n+'px</figcaption></figure>').join('')+'</div>';
  await call('Page.setDocumentContent',{frameId:(await call('Page.getFrameTree',{},imageSession)).frameTree.frame.id,html:'<body style="margin:0">'+cards('#f6f7f1')+cards('#202b27')+'</body>'},imageSession);
  await screenshot(imageSession,'/private/tmp/applypilot-logo-check.png',600,320);
  console.log('PASS: SVG rasterized at exact toolbar and launcher sizes.');
  }
  if(process.argv.includes('--assets-only'))return;
  await call('Page.setDocumentContent',{frameId:(await call('Page.getFrameTree',{},imageSession)).frameTree.frame.id,html:'<h1>Daniel Example</h1><h2>Experience</h2><p>Saved 50 hours per week using Python automation.</p>'},imageSession);
  fs.writeFileSync(path.join(temporary,'sample.pdf'),Buffer.from((await call('Page.printToPDF',{},imageSession)).data,'base64'));
  const installed=await call('Extensions.loadUnpacked',{path:path.join(root,'extension')});
  console.log('PASS: unpacked ApplyPilot installed in isolated Chrome.');
  backend=spawn(path.join(root,'Emails/.python/python/bin/python3'),[path.join(root,'scripts/extension_fixture_server.py'),'--native-profile',path.join(temporary,'profile'),'--state-root',path.join(temporary,'data'),'--pdf',path.join(temporary,'sample.pdf')],{cwd:root,stdio:['ignore','pipe','pipe']});let output='';backend.stdout.on('data',c=>output+=c);let errors='';backend.stderr.on('data',c=>errors+=c);
  const port=await until(()=>output.match(/^\d+$/m)?.[0]||(backend.exitCode!==null?Promise.reject(new Error(errors)):false),'fixture server');const server='http://127.0.0.1:'+port;
  const reviewTarget=await call('Target.createTarget',{url:server});let review=await attach(reviewTarget.targetId);
  await until(()=>evaluate(review,'!!document.getElementById("pair-code")?.onclick'),'review screen');
  backend.kill();await pause(500); // Native host must start the stopped fixture backend.
  const portal=await call('Target.createTarget',{url:'about:blank'}),portalSession=await attach(portal.targetId);
  events.push(m=>{if(m.method==='Fetch.requestPaused'&&m.sessionId===portalSession){const html='<h1>PM at Example</h1><div class="section-wrapper">Example PM role: build automation.</div><form><label>Full name<input id="name"></label><label>Name<input id="email"></label><label>Why this role?<textarea id="why"></textarea></label><div class="application-question"><label>Resume<input id="resume" type="file" accept=".pdf"></label><span id="receipt"></span></div><button type="submit">Submit</button></form><script>window.submits=0;document.querySelector("form").onsubmit=e=>{e.preventDefault();submits++};document.getElementById("resume").onchange=e=>document.getElementById("receipt").textContent=e.target.files[0]?.name||"";document.getElementById("email").oninput=e=>e.target.value="";</script>';call('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from(html).toString('base64')},portalSession).catch(console.error);}});
  await call('Fetch.enable',{patterns:[{urlPattern:'*'}]},portalSession);
  await call('Page.navigate',{url:'https://jobs.lever.co/example/test-posting/apply'},portalSession);
  await call('Target.activateTarget',{targetId:portal.targetId});
  const tabTarget=await until(async()=> (await call('Target.getTargets',{filter:[{type:'tab',exclude:false}]})).targetInfos.find(t=>t.url.includes('test-posting')),'portal tab loaded');
  await call('Extensions.triggerAction',{id:installed.id,targetId:tabTarget.targetId});
  const panelTarget=await until(async()=> (await call('Target.getTargets')).targetInfos.find(t=>t.url===`chrome-extension://${installed.id}/panel.html`),'actual side panel');
  let panel=await attach(panelTarget.targetId);
  await until(()=>evaluate(panel,"!!document.getElementById('pair')?.onclick"),'panel initialized');
  await until(()=>evaluate(panel,"document.getElementById('packet')?.options.length>1 && !document.body.hasAttribute('aria-busy')"),'automatic native connection and packet list');
  await evaluate(panel,"document.getElementById('packet').selectedIndex=1;document.getElementById('packet').dispatchEvent(new Event('change'))");
  await until(()=>evaluate(panel,"document.querySelectorAll('#fields .field').length===4"),'automatic scan');
  assert.equal(await evaluate(panel,"document.getElementById('resume-dialog').open"),false);
  await evaluate(panel,"document.getElementById('preview').click()");
  await until(()=>evaluate(panel,"document.getElementById('resume-dialog').open"),'optional resume preview opened');
  await until(async()=> (await call('Page.getFrameTree',{},panel)).frameTree.childFrames?.some(f=>f.frame.url.startsWith('blob:')),'inline PDF loaded');
  assert.ok(await evaluate(panel,"document.getElementById('resume-evidence').textContent.includes('50 hours')"),'Source evidence shown with PDF');
  await evaluate(panel,"document.getElementById('use-resume').click()");
  await until(()=>evaluate(panel,"document.getElementById('match').checked"),'resume explicitly approved');
  console.log('PASS: actual side panel connected through native host after cold backend start, activeTab granted, packet selected, automatic scan.');
  // Side-panel compositor capture does not support viewport emulation; render
  // the same markup in a normal test page for deterministic visual QA.
  let preview=fs.readFileSync(path.join(root,'extension/panel.html'),'utf8');
  preview=preview.replace('<script src="core.js"', '<script src="'+new URL('file://'+path.join(root,'extension/tests/panel-harness.js')).href+'"></script><script src="core.js"');
  for(const name of ['core.js','panel.js','panel.css','icons/logo.svg'])preview=preview.replaceAll('"'+name+'"','"'+new URL('file://'+path.join(root,'extension',name)).href+'"');
  const previewPath=path.join(temporary,'preview.html');fs.writeFileSync(previewPath,preview);
  const previewTarget=await call('Target.createTarget',{url:new URL('file://'+previewPath).href,background:true}),previewSession=await attach(previewTarget.targetId);
  await until(()=>evaluate(previewSession,"document.getElementById('packet')?.options.length>1"),'preview initialized');
  await evaluate(previewSession,"document.getElementById('packet').selectedIndex=1;document.getElementById('packet').onchange()");
  await evaluate(previewSession,"document.getElementById('preview-close').click()");
  await screenshot(previewSession,'/private/tmp/applypilot-panel.png',380,820);
  await call('Target.closeTarget',{targetId:previewTarget.targetId});
  await call('Target.activateTarget',{targetId:portal.targetId});
  // Start a deliberately slow job, reload panel while running, then resume it.
  await evaluate(panel,"[...document.querySelectorAll('#fields button')].find(b=>b.textContent==='Draft answer').click()");
  await until(()=>evaluate(panel,"!document.getElementById('cancel-job').hidden"),'job started');
  await call('Page.reload',{},panel);await until(()=>evaluate(panel,"!document.getElementById('resume-job')?.hidden && !document.getElementById('resume-job')?.disabled && !!document.getElementById('resume-job')?.onclick"),'persisted job after panel restart');
  await evaluate(panel,"document.getElementById('resume-job').click()");
  try{await until(()=>evaluate(panel,"[...document.querySelectorAll('#fields textarea')].some(t=>t.value.includes('50 hours'))"),'slow answer restored',45000);}catch(e){console.error(await evaluate(panel,"({status:document.getElementById('status').textContent,job:activeJob,posting:page?.postingKey,rows:rows.map(r=>({key:rowKey(r.field),answer:r.text?.value}))})"));throw e;}
  assert.equal(await evaluate(panel,"document.querySelector('#fields textarea').closest('article').querySelector('input').disabled"),false);
  console.log('PASS: 32-second background job survives panel reload; answer ready for automatic validation.');
  await until(()=>evaluate(panel,"!document.querySelector('#fields textarea').closest('article').querySelector('input').disabled"),'answer approved');
  await evaluate(panel,"document.getElementById('match').checked=true;document.getElementById('match').dispatchEvent(new Event('change'));document.getElementById('fill').click()");
  await until(()=>evaluate(panel,"document.getElementById('status').textContent.includes('filled')"),'fill results');
  assert.ok((await evaluate(panel,"document.getElementById('status').textContent")).includes('failed'),'Rejected value must be reported as failed');
  const result=await evaluate(portalSession,"({name:document.getElementById('name').value,why:document.getElementById('why').value,file:document.getElementById('resume').files[0]?.name,submits})");
  assert.ok(result.name);assert.ok(result.why.includes('50 hours'));assert.ok(result.file);assert.equal(result.submits,0);
  console.log('PASS: real messaging/injection, retained values, upload acknowledgement, partial rejection, zero submissions.');
  const fixtureHTML=await evaluate(portalSession,'document.documentElement.outerHTML');
  await pause(500);await call('Browser.close');await pause(700);events=[];buffer='';await launch();
  const extensions=(await call('Extensions.getExtensions')).extensions;
  if(!extensions.some(e=>e.id===installed.id))await call('Extensions.loadUnpacked',{path:path.join(root,'extension')});
  const newReview=await call('Target.createTarget',{url:server});review=await attach(newReview.targetId);
  await until(()=>evaluate(review,"!!document.getElementById('revoke-extension')?.onclick"),'review after restart');
  const freshPortal=await call('Target.createTarget',{url:'about:blank'}),freshSession=await attach(freshPortal.targetId);
  events.push(m=>{if(m.method==='Fetch.requestPaused'&&m.sessionId===freshSession)call('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from(fixtureHTML).toString('base64')},freshSession).catch(console.error);});
  await call('Fetch.enable',{patterns:[{urlPattern:'*'}]},freshSession);await call('Page.navigate',{url:'https://jobs.lever.co/example/test-posting/apply'},freshSession);
  await call('Target.activateTarget',{targetId:freshPortal.targetId});
  const freshTab=await until(async()=> (await call('Target.getTargets',{filter:[{type:'tab',exclude:false}]})).targetInfos.find(t=>t.url.includes('test-posting')),'fresh portal tab');
  await call('Extensions.triggerAction',{id:installed.id,targetId:freshTab.targetId});
  const restoredPanel=await until(async()=> (await call('Target.getTargets')).targetInfos.find(t=>t.url===`chrome-extension://${installed.id}/panel.html`),'panel after browser restart');
  panel=await attach(restoredPanel.targetId);
  await until(()=>evaluate(panel,"document.querySelector('#fields textarea')?.value.includes('50 hours')"),'saved answer after full browser restart');
  assert.equal(await evaluate(panel,"document.querySelector('#fields textarea').closest('article').querySelector('input').disabled"),false);
  console.log('PASS: full Chrome restart retains pairing and unfinished answer for automatic revalidation.');
  await evaluate(review,"document.getElementById('revoke-extension').click()");
  await until(()=>evaluate(review,"document.getElementById('pair-status').textContent.includes('revoked')"),'revocation');
  await evaluate(panel,"document.getElementById('refresh').click()");
  await until(()=>evaluate(panel,"document.getElementById('status').textContent.includes('not paired')"),'revoked token rejection');
  await call('Page.reload',{},panel);
  await until(()=>evaluate(panel,"document.getElementById('status')?.textContent.includes('not paired')"),'native reconnect remains revoked');
  assert.equal(JSON.parse(fs.readFileSync(path.join(temporary,'data/.extension_access.json'),'utf8'))._native,undefined);
  console.log('PASS: local revocation blocks the loaded extension and native reconnection.');
})().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{if(backend)backend.kill();const pidFile=path.join(temporary,'data/fixture-server.pid');if(fs.existsSync(pidFile)){try{process.kill(Number(fs.readFileSync(pidFile,'utf8')));}catch(_){}}if(browser){await Promise.race([call('Browser.close').catch(()=>{}),pause(1000)]);browser.kill();for(const stream of browser.stdio)stream?.destroy?.();browser.unref();}for(const p of pending.values())p.reject(new Error('Browser closed'));pending.clear();await pause(500);fs.rmSync(temporary,{recursive:true,force:true,maxRetries:10,retryDelay:200});backend?.stdout?.destroy();backend?.stderr?.destroy();backend?.unref();process.exit(process.exitCode||0);});
