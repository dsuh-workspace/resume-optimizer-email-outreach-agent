'use strict';
const $=id=>document.getElementById(id);
async function request(path,payload){const r=await fetch(path,{method:payload?'POST':'GET',headers:payload?{'Content-Type':'application/json','X-Review-Token':document.querySelector('meta[name=review-token]').content}:{},body:payload?JSON.stringify(payload):undefined});const data=await r.json();if(!r.ok)throw new Error(data.error);return data;}
function show(s){$('path').textContent=s.extension_path;$('identity').textContent=s.extension_id;$('connection').textContent=s.enabled?'✓ Chrome connection enabled.':s.relocated?'Project location changed. Enable the connection to repair it.':'Connection not enabled yet.';$('install').textContent=s.enabled?'Repair Chrome connection':'Enable Chrome connection';$('connected').textContent=s.last_connected?'✓ Chrome connected successfully. You can close this setup page.':'';}
async function run(fn){try{$('error').textContent='';await fn();}catch(e){$('error').textContent=e.message;}}
$('install').onclick=()=>run(async()=>show(await request('/api/setup/install',{})));
$('copy').onclick=()=>run(async()=>{await navigator.clipboard.writeText($('path').textContent);$('copy').textContent='Copied';});
$('revoke').onclick=()=>run(async()=>{await request('/api/extension/revoke',{});show(await request('/api/setup/status'));});
run(async()=>show(await request('/api/setup/status')));
setInterval(()=>request('/api/setup/status').then(show).catch(()=>{}),3000);
