'use strict';
importScripts('core.js');
const trustedStorage = Promise.all([
  chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'}),
  chrome.storage.session.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'})
]);
chrome.action.onClicked.addListener(tab => {
  chrome.sidePanel.open({tabId:tab.id}).then(()=>chrome.runtime.sendMessage({action:'invoked',tabId:tab.id})).catch(()=>{});
});
function serverURL(value) {
  const u=new URL(value || 'http://127.0.0.1:8765');
  if(u.protocol!=='http:' || u.hostname!=='127.0.0.1' || u.username || u.password || u.pathname!=='/' || u.search || u.hash) throw new Error('Use http://127.0.0.1:PORT for the local app.');
  return u.origin;
}
let connecting;
async function connectNative() {
  if (!connecting) connecting = (async()=>{
    const result=await chrome.runtime.sendNativeMessage('com.applypilot.companion',{action:'connect',version:1});
    if(result.error)throw new Error(result.error);
    if(result.version!==1||typeof result.token!=='string'||!result.token)throw new Error('Invalid local connector response. Repair ApplyPilot from the setup app.');
    const server=serverURL(result.server);
    await chrome.storage.local.set({server,token:result.token,disconnected:false});
  })().finally(()=>{connecting=null;});
  return connecting;
}
async function request(route, payload) {
  await trustedStorage;
  const config=await chrome.storage.local.get(['server','token']);
  if(!config.token) throw new Error('Pair with the local review app first.');
  let response;
  try {response=await fetch(serverURL(config.server)+'/extension/v1'+route,{method:payload?'POST':'GET',headers:{Authorization:'Bearer '+config.token,'X-Extension-Id':chrome.runtime.id,...(payload?{'Content-Type':'application/json'}:{})},body:payload?JSON.stringify({...payload,context_version:2}):undefined,signal:AbortSignal.timeout(15000)});}
  catch (_) {throw new Error('Local app is unavailable or the request timed out. Reopen ApplyPilot from the toolbar to reconnect, or open ApplyPilot.app to repair the connection.');}
  const data=await response.json(); if(!response.ok) throw new Error(data.error || 'Local request failed.'); return data;
}
async function active(tabId) {
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!tab || tab.id!==tabId) throw new Error('Active tab changed. Scan the current application again.');
  return tab;
}
async function run(message) {
  await trustedStorage;
  if(message.action==='settings'||message.action==='connect') {
    const before=await chrome.storage.local.get(['disconnected']);let connectionError='';
    if(message.action==='connect'||!before.disconnected){try{await connectNative();}catch(e){connectionError=e.message;}}
    const c=await chrome.storage.local.get(['server','token']);return {server:c.server||'http://127.0.0.1:8765',paired:!!c.token,id:chrome.runtime.id,connectionError};
  }
  if(message.action==='setup'||message.action==='manage') {await chrome.tabs.create({url:'http://127.0.0.1:8765/'+(message.action==='setup'?'setup':'')});return {}; }
  if(message.action==='pair') {
    const server=serverURL(message.server);
    const response=await fetch(server+'/extension/v1/pair',{method:'POST',headers:{'Content-Type':'application/json','X-Extension-Id':chrome.runtime.id},body:JSON.stringify({code:message.code}),signal:AbortSignal.timeout(10000)});
    const data=await response.json(); if(!response.ok) throw new Error(data.error);
    await chrome.storage.local.set({server,token:data.token,disconnected:false}); return {paired:true};
  }
  if(message.action==='disconnect') {await chrome.storage.local.remove('token');await chrome.storage.local.set({disconnected:true});await chrome.storage.session.clear();return {};}
  if(message.action==='api') {
    if(!['/packets','/packet','/preferences','/answer','/validate-answer','/health','/jobs','/session','/diagnostics','/resolve-fields'].includes(message.route)) throw new Error('Unknown endpoint.');
    return request(message.route,message.payload);
  }
  if(message.action==='pairing-page') {
    const config=await chrome.storage.local.get(['server']);
    await chrome.tabs.create({url:serverURL(message.server||config.server)+'/?extension_id='+chrome.runtime.id});return {};
  }
  if(message.action==='focus' || message.action==='undo' || message.action==='choices') {
    const tab=await active(message.tabId);
    if(tab.url!==message.url || !CopilotCore.platform(tab.url))throw new Error('Application changed. Scan again.');
    const [result]=await chrome.scripting.executeScript({target:{tabId:message.tabId},func:(action,id,version,query)=>{if(globalThis.ApplicationAutofill?.version!==version)throw new Error('ApplyPilot was updated. Preserve unsaved entries, refresh the application tab, and reopen ApplyPilot.');return globalThis.ApplicationAutofill[action](action==='choices'?{id,query}:id);},args:[message.action,message.id,chrome.runtime.getManifest().version,message.action==='choices'?String(message.query||'').slice(0,301):'']});return result.result;
  }
  if(message.action==='scan') {
    await active(message.tabId);
    const preferences=await request('/preferences');
    await chrome.scripting.executeScript({target:{tabId:message.tabId},files:['core.js','content.js']});
    const [result]=await chrome.scripting.executeScript({target:{tabId:message.tabId},func:(policy,version)=>{if(globalThis.ApplicationAutofill?.version!==version)throw new Error('ApplyPilot was updated. Preserve unsaved entries, refresh the application tab, and reopen ApplyPilot.');globalThis.CopilotCore.configure(policy);return globalThis.ApplicationAutofill.scan();},args:[preferences.policy,chrome.runtime.getManifest().version]});
    const page=result?.result;
    if(!page||typeof page.supported!=='boolean')throw new Error('Page scan did not complete. Preserve unsaved entries, reload ApplyPilot and refresh this application tab, then rescan.');
    if(page.supported){const resolved=await request('/resolve-fields',{url:page.url,company:page.company,fields:page.fields.map(CopilotCore.fieldContext)});for(const field of page.fields)if(resolved[field.id])field.resolution=resolved[field.id];}
    return page;
  }
  if(message.action==='fill') {
    const tab=await active(message.tabId);
    if(tab.url!==message.url || !CopilotCore.platform(tab.url)) throw new Error('Application changed or is unsupported. Scan again.');
    // Recheck source evidence and PDF bytes for every fill, including after worker restarts.
    const packet=await request('/packet',{packet_id:message.packetId,revision:message.revision,include_pdf:message.attach===true});
    const preferences=await request('/preferences');
    await active(message.tabId);
    CopilotCore.configure(preferences.policy);
    const [inspection]=await chrome.scripting.executeScript({target:{tabId:message.tabId},func:()=>globalThis.ApplicationAutofill.context()});
    const context=inspection.result;
    if(context.version!==chrome.runtime.getManifest().version)throw new Error('ApplyPilot was updated. Preserve unsaved entries, refresh the application tab, and reopen ApplyPilot.');
    if(context.url!==message.url||context.scanId!==message.scanId)throw new Error('Application changed. Scan again.');
    const company=context.company||packet.company||'';
    if(message.company&&CopilotCore.normalize(message.company)!==CopilotCore.normalize(company))throw new Error('Company context changed. Scan again.');
    const resolved=await request('/resolve-fields',{url:message.url,company,fields:context.fields.map(CopilotCore.fieldContext)});
    const changes=[],invalidated=[];
    for(const change of message.changes){
      const original=context.fields.find(f=>f.id===change.id);
      if(!original)throw new Error('Field context changed. Scan again.');
      const field={...original,resolution:resolved[original.id]};
      // Explicit entry mapping is accepted only for an originally unidentified entry.
      const mapped=message.fields?.find(f=>f.id===field.id);
      if(field.group&&!field.group.identity&&mapped?.group?.id===field.group.id)field.group=mapped.group;
      const proposal=CopilotCore.proposed(field,packet,preferences);
      if(CopilotCore.thirdParty(field)){invalidated.push({id:change.id,status:'invalidated',code:'manual'});continue;}
      if(!['written','once'].includes(change.source)&&(JSON.stringify(proposal.value)!==JSON.stringify(change.value)||!!proposal.checked!==!!change.checked)){
        invalidated.push({id:change.id,status:'invalidated',code:'invalidated'});continue;
      }
      changes.push({...change,alternatives:change.source==='once'?undefined:proposal.alternatives,matchRule:change.source==='once'?undefined:proposal.matchRule});
    }
    const attemptId=crypto.randomUUID(),extensionVersion=chrome.runtime.getManifest().version;
    const [result]=await chrome.scripting.executeScript({target:{tabId:message.tabId},func:async request=>globalThis.ApplicationAutofill.apply(request),args:[{
      scanId:message.scanId,url:message.url,discoverNew:true,settleMs:message.preparing===true?5000:300,changes,accounting:[...(message.accounting||[]),...invalidated],automation:preferences.application_profile?.automation||{},phoneCountry:['US','USA','United States','United States of America'].includes(preferences.facts?.country)?'US':undefined,
      pdf:message.attach?{name:packet.pdf_name,base64:packet.pdf_base64}:null
    }]});
    const outcomes=result.result;
    if(Array.isArray(outcomes)&&outcomes.some(r=>r.diagnostic)) {
      try {await request('/diagnostics',{action:'record',posting_key:CopilotCore.postingKey(message.url),results:outcomes.filter(r=>r.diagnostic).map(r=>({...r.diagnostic,attempt_id:attemptId,extension_version:extensionVersion,source:message.changes.find(c=>c.id===r.id)?.source||'unknown'}))});}
      catch (_) {outcomes.forEach(r=>r.diagnostic_unsaved=true);}
    }
    return result.result;
  }
  throw new Error('Unknown action.');
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id || sender.url!==chrome.runtime.getURL('panel.html') || sender.tab) return false;
  run(message).then(result=>reply({result}),error=>reply({error:error.message || 'Extension request failed.'})); return true;
});
