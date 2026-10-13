/* Real unpacked extension, isolated Chrome profile, intercepted synthetic portal.
   No production accounts, source data, model calls, or employer requests. */
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'applypilot-coverage-'));
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
const {html,matrixFor}=require('./autofill_fixture.cjs');
const platform=process.argv[2]||'greenhouse',variant=process.argv[3]||'immediate',matrix=matrixFor(variant);
const forcedFailures=['first','last',...(variant==='missing-school'?['school']:[]),...(variant==='late'?['country']:[])].sort();
(async()=>{
 await launch();
 const pdfTarget=await call('Target.createTarget',{url:'about:blank'}),pdfSession=await attach(pdfTarget.targetId);
 await call('Page.setDocumentContent',{frameId:(await call('Page.getFrameTree',{},pdfSession)).frameTree.frame.id,html:'<h1>Sample Applicant</h1><p>Saved 50 hours weekly using Python automation.</p>'},pdfSession);
 fs.writeFileSync(path.join(temporary,'sample.pdf'),Buffer.from((await call('Page.printToPDF',{},pdfSession)).data,'base64'));
 const installed=await call('Extensions.loadUnpacked',{path:path.join(root,'extension')});
 backend=spawn(path.join(root,'Emails/.python/python/bin/python3'),[path.join(root,'scripts/extension_fixture_server.py'),'--expanded',...(['workflow','modern','robinhood'].includes(variant)?['--workflow']:[]),'--native-profile',path.join(temporary,'profile'),'--state-root',path.join(temporary,'data'),'--pdf',path.join(temporary,'sample.pdf')],{cwd:root,stdio:['ignore','pipe','pipe']});
 let output='',errors='';backend.stdout.on('data',c=>output+=c);backend.stderr.on('data',c=>errors+=c);
 await until(()=>output.match(/^\d+$/m)?.[0]||(backend.exitCode!==null?Promise.reject(new Error(errors)):false),'fixture server');
 const portal=await call('Target.createTarget',{url:'about:blank'}),portalSession=await attach(portal.targetId);
 const url=platform==='lever'?'https://jobs.lever.co/example/coverage/apply':'https://job-boards.greenhouse.io/example/jobs/12345';
 events.push(m=>{if(m.method==='Fetch.requestPaused'&&m.sessionId===portalSession)call('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from(html(platform,variant)).toString('base64')},portalSession).catch(console.error);});
 await call('Fetch.enable',{patterns:[{urlPattern:'*'}]},portalSession);await call('Page.navigate',{url},portalSession);
 await call('Target.activateTarget',{targetId:portal.targetId});
 const tab=await until(async()=> (await call('Target.getTargets',{filter:[{type:'tab',exclude:false}]})).targetInfos.find(t=>t.url===url),'portal tab');
 await call('Extensions.triggerAction',{id:installed.id,targetId:tab.targetId});
 const panelTarget=await until(async()=> (await call('Target.getTargets')).targetInfos.find(t=>t.url===`chrome-extension://${installed.id}/panel.html`),'panel');
 let panel=await attach(panelTarget.targetId);
 const debug=()=>evaluate(panel,"({status:document.getElementById('status')?.textContent,fields:typeof rows!=='undefined'?rows.map(r=>({name:r.field.name,result:r.result?.textContent,checked:r.select.checked})):[]})");
 try {
  await until(()=>evaluate(panel,"document.getElementById('packet')?.options.length>1 && !document.body.hasAttribute('aria-busy')"),'connected');
  await evaluate(panel,"document.getElementById('packet').selectedIndex=1;document.getElementById('packet').dispatchEvent(new Event('change'))");
  await until(()=>evaluate(panel,"document.getElementById('match').checked && !document.body.hasAttribute('aria-busy')"),'selected');
  if(variant==='robinhood'){
    // Save only deliberately selected detailed answers through the actual panel.
    for(const menu of require('../extension/tests/robinhood-menus.json').filter(m=>m.explicit)){
      assert.equal(await evaluate(portalSession,`document.getElementById(${JSON.stringify(menu.id)}).value`),'','No disclosure inferred on the page');
      await evaluate(panel,`{const r=rows.find(r=>r.field.name===${JSON.stringify(menu.id)});[...r.card.querySelectorAll('button')].find(b=>b.textContent==='Load page choices').click();}`);
      await until(()=>evaluate(panel,"!document.body.hasAttribute('aria-busy')"),'load real disclosure menu');
      assert.deepEqual(await evaluate(panel,`[...rows.find(r=>r.field.name===${JSON.stringify(menu.id)}).card.querySelector('select').options].slice(1).map(o=>o.textContent)`),menu.options);
      await evaluate(panel,`{const r=rows.find(r=>r.field.name===${JSON.stringify(menu.id)});r.card.querySelector('select').value=${JSON.stringify(menu.explicit)};[...r.card.querySelectorAll('button')].find(b=>b.textContent==='Save this answer').click();}`);
      await until(()=>evaluate(panel,"!document.body.hasAttribute('aria-busy') && document.getElementById('status').textContent.startsWith('Explicit answer saved')"),'save scoped disclosure');
      matrix.find(f=>f.id===menu.id).expected=menu.explicit;
    }
    await evaluate(panel,"(async()=>{await saveProgress();window.savedDisclosureMarker=true;})()");
    await call('Page.reload',{},panel);
    await until(()=>evaluate(panel,"!window.savedDisclosureMarker && typeof rows!=='undefined' && rows.length>0 && !document.body.hasAttribute('aria-busy')"),'restore saved disclosures');
    for(const menu of require('../extension/tests/robinhood-menus.json').filter(m=>m.explicit))assert.equal(await evaluate(panel,`rows.find(r=>r.field.name===${JSON.stringify(menu.id)}).value`),menu.explicit,'Restored company-specific detail');
  }
  // Persist a real legacy session, then restore it in a fresh panel document.
  if(variant==='legacy'){
    await evaluate(panel,"(async()=>{await saveProgress();const old=structuredClone(saved);delete old.selection_version;delete old.selections;Object.values(old.rows).forEach(r=>r.selected=false);await api('/session',{action:'save',key:page.postingKey,value:old});page=null;rows=[];window.oldDocumentMarker=true;})()");
    await call('Page.reload',{},panel);
    await until(()=>evaluate(panel,"!window.oldDocumentMarker && typeof rows!=='undefined' && rows.length>0 && !document.body.hasAttribute('aria-busy')"),'legacy restore');
    assert.ok(await evaluate(panel,"rows.filter(r=>r.proposal.value!==undefined&&!r.field.current).every(r=>r.select.checked)"),'Legacy empty eligible rows selected');
  }
  await evaluate(panel,"{const r=rows.find(r=>r.field.name==='country');r.select.checked=false;r.select.onchange();document.getElementById('scan').click()}");
  await until(()=>evaluate(panel,"!document.body.hasAttribute('aria-busy')"),'deliberate opt-out rescan');
  assert.equal(await evaluate(panel,"rows.find(r=>r.field.name==='country').select.checked"),false,'Opt-out survives rescan');
  await evaluate(panel,"{const r=rows.find(r=>r.field.name==='country');r.select.checked=true;r.select.onchange()}");
  assert.equal(await evaluate(panel,"document.getElementById('resume-dialog').open"),false,'No mandatory resume review');
  assert.ok(await evaluate(panel,"document.getElementById('review-summary').textContent.includes('questions need your input')"),'Ambiguous fields reported');
  assert.equal(await evaluate(panel,"document.querySelectorAll('#fields article.field').length"),matrix.length,'Every fixture field must be discovered');
  assert.equal(await evaluate(panel,"[...document.querySelectorAll('#fields button')].filter(b=>b.textContent==='Draft answer').length"),2,'Both text input and textarea must support drafting');
  await evaluate(panel,"document.getElementById('draft-all').click()");
  await until(()=>evaluate(panel,"[...document.querySelectorAll('#fields textarea')].filter(t=>t.value).length===2 && !document.body.hasAttribute('aria-busy')"),'draft all',20000);
  assert.equal(await evaluate(panel,"[...document.querySelectorAll('#fields button')].some(b=>b.textContent.includes('Approve'))"),false,'No answer approval buttons');
  await evaluate(panel,"document.getElementById('fill').click()");
  await until(()=>evaluate(panel,"(document.getElementById('status').textContent.includes('questions need your input')||document.getElementById('status').textContent.includes('New questions appeared')) && !document.body.hasAttribute('aria-busy')"),'first fill',60000);
  console.log('PASS: initial actual fill completed');
  let actual=await evaluate(portalSession,'window.inspectFields()');
  for(const field of matrix)assert.equal(actual[field.id],forcedFailures.includes(field.id)?'':field.expected,'Actual portal value: '+field.id);
  if(variant==='robinhood')assert.equal(await evaluate(portalSession,"document.getElementById('country').closest('.select-shell').querySelector('.select__single-value .iti__flag').className"),'iti__flag iti__us','Compressed dial code retains actual US identity');
  let history=JSON.parse(fs.readFileSync(path.join(temporary,'data/.applypilot_diagnostics.json'),'utf8'));
  assert.deepEqual(history.filter(r=>r.status==='failed').map(r=>r.name).sort(),forcedFailures);
  assert.equal(history.length,matrix.length+(variant==='conditional'?1:0),'Every discovered field accounted independently of mapper eligibility');assert.ok(history.every(r=>r.attempt_id&&r.extension_version===require('../extension/manifest.json').version&&['final','retention','option_loading'].includes(r.stage)));
  if(variant==='conditional'){
    assert.equal(await evaluate(portalSession,"document.getElementById('conditional-first').value"),'','New known field not filled implicitly');
    assert.equal(await evaluate(panel,"rows.find(r=>r.field.name==='conditional-first').select.checked"),false,'New known field not automatically selected');
  }
  const serialized=JSON.stringify(history.map(({attempt_id,time,...metadata})=>metadata));for(const secret of ['Sample','Applicant','Business Administration','2024','2028','50 hours','keep@example.test'])assert.ok(!serialized.includes(secret),'Diagnostic answer leak: '+secret);
  await evaluate(panel,"window.oldDocumentMarker=true");
  if(variant==='extension-reload'){
    const oldWorkers=new Set((await call('Target.getTargets')).targetInfos.filter(t=>t.type==='service_worker').map(t=>t.targetId));
    const reloaded=await call('Extensions.loadUnpacked',{path:path.join(root,'extension')});
    assert.equal(reloaded.id,installed.id,'Reload preserves extension identity');
    const workerTarget=await until(async()=>(await call('Target.getTargets')).targetInfos.find(t=>t.type==='service_worker'&&!oldWorkers.has(t.targetId)&&t.url===`chrome-extension://${installed.id}/background.js`),'reloaded service worker');
    const workerSession=await attach(workerTarget.targetId);await until(()=>evaluate(workerSession,"typeof run==='function'"),'worker initialized');
    await call('Target.activateTarget',{targetId:portal.targetId});
    const reloadedTab=await until(async()=>(await call('Target.getTargets',{filter:[{type:'tab',exclude:false}]})).targetInfos.find(t=>t.url===url),'current tab after extension reload');
    await call('Extensions.triggerAction',{id:installed.id,targetId:reloadedTab.targetId});
    const reopened=await until(async()=>(await call('Target.getTargets')).targetInfos.find(t=>t.url===`chrome-extension://${installed.id}/panel.html`),'reopened extension panel');
    panel=await attach(reopened.targetId);
  }else await call('Page.reload',{},panel);
  await until(()=>evaluate(panel,"!window.oldDocumentMarker && document.readyState==='complete' && !!document.getElementById('retry-failed')?.onclick && document.getElementById('diagnostic-results')?.textContent.includes('First Name') && !document.body.hasAttribute('aria-busy')"),'persistent failures');
  if(variant==='conditional')assert.equal(await evaluate(panel,"rows.find(r=>r.field.name==='conditional-first').select.checked"),false,'New field remains deferred after panel reopen');
  assert.equal(await evaluate(panel,"[...document.querySelectorAll('#fields article.field')].filter(a=>a.querySelector('textarea')&&!a.querySelector('input[type=checkbox]').disabled).length"),2,'Restored written answers ready for automatic validation');
  await evaluate(portalSession,"window.repairFailures=true;document.getElementById('prefilled').value='later-edit@example.test'");
  await evaluate(panel,"document.getElementById('retry-failed').click()");
  await until(()=>evaluate(panel,"document.getElementById('status').textContent.startsWith('Failed empty fields selected') && !document.body.hasAttribute('aria-busy')"),'fresh retry scan');
  assert.deepEqual(await evaluate(panel,"[...document.querySelectorAll('#fields article.field')].filter(a=>a.querySelector('input[type=checkbox]').checked).map(a=>a.querySelector('strong').textContent).sort()"),matrix.filter(f=>forcedFailures.includes(f.id)).map(f=>f.label).sort());
  await evaluate(panel,"document.getElementById('fill').click()");
  await until(()=>evaluate(panel,"document.getElementById('status').textContent.includes('questions need your input') && !document.body.hasAttribute('aria-busy')"),'retry fill',20000);
  actual=await evaluate(portalSession,'window.inspectFields()');
  for(const field of matrix)assert.equal(actual[field.id],field.id==='prefilled'?'later-edit@example.test':field.expected,'Retained value after recovery: '+field.id);
  assert.deepEqual(await evaluate(portalSession,'[window.submits,window.nextClicks]'),[0,0]);
  history=JSON.parse(fs.readFileSync(path.join(temporary,'data/.applypilot_diagnostics.json'),'utf8'));
  const latest=history.filter(r=>r.attempt_id===history.at(-1).attempt_id);assert.deepEqual(latest.filter(r=>r.status==='filled').map(r=>r.name).sort(),forcedFailures);
  console.log(`PASS: ${platform}/${variant}: ${matrix.length} independent field assertions before and after diagnostic recovery; real extension/worker/companion; zero Next or Submit.`);
 }catch(error){console.error(JSON.stringify(await debug().catch(e=>({diagnosticError:e.message})),null,2));throw error;}
})().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{if(backend)backend.kill();const pidFile=path.join(temporary,'data/fixture-server.pid');if(fs.existsSync(pidFile)){try{process.kill(Number(fs.readFileSync(pidFile,'utf8')));}catch(_){}}if(browser){await Promise.race([call('Browser.close').catch(()=>{}),pause(1000)]);browser.kill();for(const stream of browser.stdio)stream?.destroy?.();browser.unref();}for(const p of pending.values())p.reject(new Error('Browser closed'));pending.clear();await pause(500);fs.rmSync(temporary,{recursive:true,force:true,maxRetries:10,retryDelay:200});backend?.stdout?.destroy();backend?.stderr?.destroy();backend?.unref();process.exit(process.exitCode||0);});
