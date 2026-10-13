'use strict';
const $=id=>document.getElementById(id), C=CopilotCore;
const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let lastOncePosting=null;
let packet=null, page=null, tabId=null, prefs={facts:{},questions:[]}, rows=[], busy=false, epoch=0, packets=[], saved={}, saveTimer, activeJob=null, progressWrites=Promise.resolve(), server='http://127.0.0.1:8765', diagnosticHistory=[], onceAnswers=new Map();
function status(text='',error=false){$('status').textContent=text;$('status').className=(text?'visible':'')+(error?' error':'');}
async function send(message){const result=await chrome.runtime.sendMessage(message);if(!result)throw new Error('Extension worker unavailable. Reload the extension.');if(result.error){if(/paired|unavailable|timed out/i.test(result.error))$('connection-state').textContent=/paired/i.test(result.error)?'Pairing required':'Local app offline';throw new Error(result.error);}return result.result;}
const api=(route,payload)=>send({action:'api',route,payload});
function ready(){return !busy&&packet&&page?.supported&&$('match').checked&&rows.some(r=>r.select.checked&&!r.select.disabled);}
function controls(){ $('prepare').disabled=busy||!page?.supported||page.platform!=='greenhouse'||!!activeJob; $('resume-job').disabled=busy;const count=rows.filter(r=>r.select.checked&&!r.select.disabled&&r.approved).length;$('fill').textContent='Autofill this page'+(count?' · '+count:'');$('preview').disabled=busy||!packet;$('preview').textContent='Preview';$('generate').hidden=!!packet;$('generate').disabled=busy||!!activeJob;$('resume-title').textContent=packet?packet.company+' · '+packet.role:'A resume for this role';$('packet-info').textContent=packet?'✓ Ready for this application':'Prepare a tailored resume, or choose one you already have.'; $('fill').disabled=!ready();if(packet&&page?.supported)$('review-summary').textContent=count+' selected to fill · '+unresolvedSummary();$('download').disabled=busy||!packet; }
async function work(fn){if(busy){status('A task is running. Wait, cancel it, or reopen the panel to resume later.');return;}busy=true;controls();$('packet').disabled=true;document.body.setAttribute('aria-busy','true');try{await fn();}catch(error){status(error.message,true);}finally{busy=false;$('packet').disabled=false;document.body.removeAttribute('aria-busy');controls();}}
function invalidate(message){clearTimeout(saveTimer);closePreview();activeJob=null;$('resume-job').hidden=true;$('cancel-job').hidden=true;epoch++;page=null;rows=[];$('fields').replaceChildren();$('match').checked=false;$('page-info').textContent=message;controls();}
function currentContext(){return JSON.stringify([epoch,tabId,page?.url,page?.scanId,packet?.id,packet?.revision]);}
function requireContext(context){if(currentContext()!==context)throw new Error('Application or resume changed. Scan and review again.');}
function rowKey(field){return JSON.stringify([field.contextVersion,field.section,field.subject,field.label,field.helper,field.name,field.type,field.options,field.group?.identity,field.group?.role,...(field.group?[field.group.kind,field.group.index]:[]),...(field.occurrence?[field.occurrence]:[])]);}
const selectionKey=field=>JSON.stringify([field.label,field.name,field.type,field.options,field.group?.kind,field.group?.index,field.occurrence||0]);
async function saveProgress(){
  if(!page?.postingKey)return;
  const key=page.postingKey;
  const value={once_answers:Object.fromEntries(onceAnswers),selection_version:2,deferred:Object.fromEntries(rows.filter(r=>r.deferred).map(r=>[selectionKey(r.field),true])),selections:Object.fromEntries(rows.map(r=>[selectionKey(r.field),r.userSelection])),posting_details:{company:$('generate-company').value,role:$('generate-role').value,description:$('generate-description').value},packet_id:packet?.id,revision:packet?.revision,confirmed:$('match').checked,job:activeJob,rows:Object.fromEntries(rows.map(r=>[rowKey(r.field),{value:r.text?.value,result:r.draftResult,selected:r.select.checked||!!r.filled}]))};
  saved=value;const write=progressWrites.catch(()=>{}).then(()=>api('/session',{action:'save',key,value}));progressWrites=write;await write;
}
function scheduleSave(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveProgress().catch(e=>status('Progress could not be saved: '+e.message,true)),350);}
function renderPackets(){
  const old=$('packet').value, query=C.normalize($('packet-search').value);
  $('packet').replaceChildren(element('option','Choose a company and role…'));$('packet').firstChild.value='';
  const groups=new Map();
  for(const p of packets.filter(p=>p.eligible!==false).filter(p=>C.normalize(p.company+' '+p.role+' '+p.version).includes(query))){
    if(!groups.has(p.company)){const g=element('optgroup');g.label=p.company;groups.set(p.company,g);$('packet').append(g);}
    const o=element('option',`${p.role} · ${p.version}${p.eligible===false?' · View only':''}`);o.value=p.id;o.disabled=p.eligible===false;o.title=(p.problems||[]).join(' ');groups.get(p.company).append(o);
  }
  if([...$('packet').options].some(o=>o.value===old))$('packet').value=old;
  $('packet-count').textContent=packets.filter(p=>p.eligible!==false).length+' usable resumes. Older view-only versions are in Manage resumes.';
}
async function refresh(){packets=await api('/packets');renderPackets();}
function jobControls(){
  $('resume-job').hidden=!activeJob;
  $('cancel-job').hidden=!activeJob;$('cancel-job').textContent=activeJob?.status==='complete'?'Dismiss preparation':'Cancel preparation';
  $('resume-job').textContent=activeJob?.status==='complete'?(activeJob.kind==='resume'?'Review prepared resume':'Review prepared answer'):'Continue preparation';
  controls();
}
async function finishJob(context){
  requireContext(context);activeJob=null;jobControls();await saveProgress();
}
async function runJob(kind,input,context,row_key){
  if(activeJob)throw new Error('Continue or cancel the existing preparation first.');
  const request_id=crypto.randomUUID(),posting_key=page.postingKey;
  activeJob={request_id,kind,input,posting_key,row_key,question:input.question,packet_id:input.packet_id,revision:input.revision};
  jobControls();await saveProgress();requireContext(context);
  const job=await api('/jobs',{kind,input,request_id,posting_key});requireContext(context);
  activeJob.id=job.id;await saveProgress();requireContext(context);
  return await pollJob(job,context);
}
async function pollJob(job,context){
  while(['queued','running'].includes(job.status)){
    requireContext(context);status((job.kind==='resume'?'Preparing your resume':'Drafting your answer')+'… You can close and reopen the panel.');
    await new Promise(r=>setTimeout(r,900));requireContext(context);
    job=await api('/jobs',{action:'status',id:job.id});
  }
  requireContext(context);
  if(job.status!=='complete'){
    await finishJob(context);
    throw new Error(job.error||'Job '+job.status+'.');
  }
  // Keep the durable job reference until its result has been reviewed or saved.
  // Fetch/network failures also preserve it, so Retry cannot duplicate AI work.
  activeJob={...activeJob,id:job.id,status:'complete',result_packet_id:job.kind==='resume'?job.result.packet_id:undefined};jobControls();
  await saveProgress();requireContext(context);
  return job.result;
}
async function resolveFields(){
  if(!page?.supported)return;
  const context=currentContext(),result=await api('/resolve-fields',{url:page.url,company:page.company||packet?.company||'',fields:page.fields.map(C.fieldContext)});
  requireContext(context);for(const field of page.fields){delete field.resolution;if(result[field.id])field.resolution=result[field.id];}
}
async function scanPage(){
  await saveProgress();invalidate('Scanning visible fields…');const scanEpoch=epoch;
  const check=()=>{if(scanEpoch!==epoch)throw new Error('Tab changed while loading. Click ApplyPilot on the current application.');};
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});check();if(!tab)throw new Error('No active tab.');tabId=tab.id;
  const result=await send({action:'scan',tabId});check();if(lastOncePosting!==result.postingKey){onceAnswers.clear();lastOncePosting=result.postingKey;}
  result.postingKey=result.postingKey||C.postingKey(result.url);
  $('links').replaceChildren();
  if(!result.supported){$('job-title').textContent='Open a job application';$('job-company').textContent='APPLYPILOT';$('page-info').textContent='Open a hosted Greenhouse or Lever application.';for(const url of result.links||[]){const link=element('a','Open hosted application ↗');link.href=url;link.target='_blank';link.rel='noopener noreferrer';$('links').append(link);}return;}
  // Do not expose partially restored state to tab-change/pagehide saves.
  const restored=result.postingKey?await api('/session',{key:result.postingKey}):{};check();
  let selected=packet,notice='';
  if(restored.packet_id&&!selected){try{selected=await api('/packet',{packet_id:restored.packet_id,revision:restored.revision});}catch(e){notice='Saved resume needs review: '+e.message;}check();}
  if(!selected&&result.company){const candidates=packets.filter(p=>p.eligible!==false&&C.normalize(p.company)===C.normalize(result.company)&&C.normalize(p.role)===C.normalize(result.title));if(candidates.length===1){selected=await api('/packet',{packet_id:candidates[0].id});check();}}
  page=result;saved=restored;for(const [key,value] of Object.entries(restored.once_answers||{}))if(!onceAnswers.has(key))onceAnswers.set(key,value);packet=selected;$('packet').value=packet?.id||'';
  $('job-title').textContent=page.title||'Job application';$('job-company').textContent=page.company||'YOUR APPLICATION';$('page-info').textContent=(page.platform||'Supported')+' application';
  $('match').checked=!!packet;
  $('generate-company').value=saved.posting_details?.company||page.company||'';
  $('generate-role').value=saved.posting_details?.role||page.title||'';
  $('generate-description').value=saved.posting_details?.description||page.description||'';
  activeJob=saved.job||null;jobControls();await resolveFields();renderFields();await loadDiagnostics();
  status(notice||(activeJob?(activeJob.status==='complete'?'Your preparation is ready to review.':'Your preparation was saved. Click Continue preparation.'):$('match').checked?'Ready to autofill clear answers. Unresolved questions are listed below.':packet?'Ready to autofill clear answers.':'Prepare a resume for this role, or choose one with Change.'),!!notice);
}
function questionRow(question='',answer=''){
  const row=element('div',undefined,'question-row'), q=element('textarea'),a=element('textarea');q.value=question;a.value=answer;q.maxLength=1000;a.maxLength=2000;q.setAttribute('aria-label','Exact application question');a.setAttribute('aria-label','Your explicit answer');
  row.append(element('p','Question (exact wording)','hint'),q,element('p','Answer','hint'),a);const remove=element('button','Remove','secondary');remove.onclick=()=>row.remove();row.append(remove);$('saved-questions').append(row);
}
function renderApplicationProfile(){
  const host=$('application-profile');host.replaceChildren();const app=prefs.application_profile||{};
  const add=(path,title,value,options)=>{const label=element('label',title),input=element(options?'select':'input');input.dataset.profile=path;input.maxLength=300;if(options){input.append(element('option','Leave unanswered'));input.firstChild.value='';for(const [v,t] of options){const o=element('option',t);o.value=v;input.append(o);}}input.value=value===undefined?'':String(value);label.append(input);host.append(label);};
  add('work.country','Work eligibility country',app.work?.country,[['US','United States']]);
  for(const [key,title] of [['authorized','Authorized to work'],['sponsorship_now','Need sponsorship now'],['sponsorship_future','Need sponsorship in the future']])add('work.'+key,title,app.work?.[key],[['true','Yes'],['false','No']]);
  for(const key of ['race','hispanic','gender','disability','protected_veteran','veteran','lgbtq','gender_identity','ethnicity','military_history'])add('disclosures.'+key,key.replaceAll('_',' '),app.disclosures?.[key]);
  for(const [key,title] of [['relationships_no','Answer No to personal relationship questions across employers'],['exhaustive_employment','Use my full master experience list as exhaustive employment history'],['recruitment_consent','Allow recruitment data processing consent'],['demographic_consent','Allow demographic data processing consent']])add('automation.'+key,title,app.automation?.[key],[['true','Enabled'],['false','Disabled']]);
  host.append(element('h4','Company-specific exact answers'));
  (app.company_answers||[]).forEach((answer,i)=>{const group=element('div');group.dataset.companyAnswer=String(i);for(const key of ['company','question','answer']){const multiple=key==='answer'&&Array.isArray(answer[key]);const label=element('label',multiple?'Answers (one choice per line)':key),input=element(key==='question'||multiple?'textarea':'input');input.dataset.companyKey=key;if(multiple)input.dataset.multiple='true';input.value=multiple?answer[key].join('\n'):answer[key];input.maxLength=4000;label.append(input);group.append(label);}const remove=element('button','Remove company answer','secondary');remove.onclick=()=>group.remove();group.append(remove);host.append(group);});
  const schools=app.education?.length?app.education:[{}];
  schools.forEach((school,i)=>{host.append(element('h4','School '+(i+1)));for(const [key,title] of [['institution','School'],['degree','Degree'],['major','Major'],['start','Start (YYYY-MM)'],['end','Graduation (YYYY-MM)']])add('education.'+i+'.'+key,title,school[key]);add('education.'+i+'.status','Degree status',school.status,[['expected','Expected'],['completed','Completed']]);const remove=element('button','Remove school','secondary');remove.onclick=()=>{const app=readApplicationProfile();app.education.splice(i,1);prefs.application_profile=app;renderApplicationProfile();};host.append(remove);});const addSchool=element('button','Add school','secondary');addSchool.onclick=()=>{const app=readApplicationProfile();app.education.push({});prefs.application_profile=app;renderApplicationProfile();};host.append(addSchool);
}
function readApplicationProfile(){
  const app={...prefs.application_profile,work:{},disclosures:{},education:[],automation:{}};
  for(const el of document.querySelectorAll('[data-profile]')){if(!el.value.trim())continue;const [kind,key,sub]=el.dataset.profile.split('.');if(kind==='education'){app.education[key]||={aliases:prefs.application_profile?.education?.[key]?.aliases||[]};app.education[key][sub]=el.value.trim();}else app[kind][key]=(kind==='automation'||kind==='work'&&key!=='country')?el.value==='true':el.value.trim();}
  app.company_answers=[...document.querySelectorAll('[data-company-answer]')].map(group=>Object.fromEntries([...group.querySelectorAll('[data-company-key]')].map(el=>[el.dataset.companyKey,el.dataset.multiple==='true'?el.value.split('\n').map(v=>v.trim()).filter(Boolean):el.value.trim()])));
  app.education=app.education.filter(Boolean);return app;
}
const diagnosticKey=f=>JSON.stringify([f.label,f.name||'unnamed',f.type,f.section||(f.group?f.group.kind+':'+f.group.index:'application'),f.occurrence||0]);
const diagnosticMessages={explicit_detail_needed:'Explicit detail needed; choose an answer for this question',not_applicable:'Not applicable for the selected No answer',upload_error:'Portal reported an upload error',excluded:'Deliberately excluded',unanswered:'No selected answer',invalidated:'Answer or context changed',list_missing:'Associated dropdown list not found',option_ambiguous:'Multiple compatible options',option_timeout:'Dropdown results timed out',control_replaced:'Control replaced ambiguously',context_changed:'Application context changed',retained:'Value retained',preserved:'Existing value preserved',stale:'Field or page changed; rescan',manual:'Manual-only control',option_missing:'No unique compatible dropdown option',rejected:'Selection not retained; page rejected or cleared the value',upload_unconfirmed:'Upload acknowledgement missing',unsupported:'Unsupported control',fill_failed:'Fill failed; inspect this field'};
async function loadDiagnostics(){
  if(!page?.postingKey)return;const context=currentContext();
  try{const history=await api('/diagnostics',{posting_key:page.postingKey});requireContext(context);diagnosticHistory=history;const latest=new Map();for(const r of history)latest.set(diagnosticKey(r),r);$('diagnostic-results').replaceChildren();for(const r of latest.values())$('diagnostic-results').append(element('p',r.label+': '+(diagnosticMessages[r.code]||'Unknown outcome')+(r.stage&&r.stage!=='final'?' ('+r.stage.replaceAll('_',' ')+')':'')));for(const row of rows){const r=latest.get(diagnosticKey(row.field));if(r&&!row.validationError)row.result.textContent='Last attempt: '+diagnosticMessages[r.code];}}
  catch(error){$('diagnostic-results').textContent='Diagnostic history unavailable: '+error.message;}
}
$('missing-answers').onclick=()=>{for(const section of document.querySelectorAll('#fields details'))section.open=true;const row=rows.find(r=>r.proposal.value===undefined&&!r.field.excluded&&!r.proposal.written);row?.card.scrollIntoView({block:'center'});row?.card.querySelector('select,input:not([type=checkbox])')?.focus();};
$('retry-failed').onclick=()=>work(async()=>{const latest=new Map();for(const r of diagnosticHistory)latest.set(diagnosticKey(r),r);const failed=new Set([...latest].filter(([,r])=>['failed','needs review'].includes(r.status)).map(([key])=>key));await scanPage();for(const row of rows)row.select.checked=failed.has(diagnosticKey(row.field))&&!row.field.current&&!row.select.disabled&&row.userSelection!==false&&!row.deferred;controls();status('Failed empty fields selected after a fresh scan. Click Autofill to retry. Existing values are preserved.');});
$('copy-diagnostics').onclick=async()=>{const text=JSON.stringify(diagnosticHistory,null,2);$('diagnostic-copy').hidden=false;$('diagnostic-copy').value=text;$('diagnostic-copy').select();try{await navigator.clipboard.writeText(text);status('Diagnostic report copied. Answer values are excluded.');}catch(_){status('Select and copy the diagnostic report below.');}};
function renderPreferences(){ C.configure(prefs.policy); renderApplicationProfile(); $('facts').replaceChildren();for(const key of ['first_name','last_name','address','city','state','postal_code','country']){const label=element('label',key.replaceAll('_',' ')),input=element('input');input.dataset.fact=key;input.maxLength=300;input.value=prefs.facts[key]||'';label.append(input);$('facts').append(label);}$('saved-questions').replaceChildren();prefs.questions.filter(q=>!q.blocked).forEach(q=>questionRow(q.question,q.answer));}
function unresolvedSummary(){const unresolved=rows.filter(r=>!r.field.notApplicable&&!r.field.current&&(r.validationError||(r.value===undefined&&!r.text?.value))&&!r.filled);return unresolved.length?unresolved.length+' questions need your input; see Needs your input and written answers.':'No unanswered ambiguous fields detected.';}
function renderFields(){rows=[];$('fields').replaceChildren();if(!packet||!page?.supported)return;
  const postingText=C.normalize(page.title+' '+page.description);
  if(!postingText.includes(C.normalize(packet.company)) || !C.normalize(page.title).includes(C.normalize(packet.role)))
    $('page-info').textContent='Using your selected resume. Company or role could not be matched automatically.';
  $('history-note').textContent=packet.complete_history?'':'This resume selects part of your experience. Questions requesting complete history need manual review. Add any required repeat entries on the application, then scan again.';
  const categories={},clarifications=new Set();
  for(const name of ['Your details','Written answers and existing values','Needs your input']){const group=element('details');group.open=name!=='Your details';const summary=element('summary',name);group.append(summary);$('fields').append(group);categories[name]={group,summary,count:0};}
  for(const field of page.fields){
    const proposal=onceAnswers.get(rowKey(field))||C.proposed(field,packet,prefs),card=element('article',undefined,'field'),select=element('input');select.type='checkbox';select.checked=proposal.value!==undefined&&!field.current;select.disabled=proposal.value===undefined||field.excluded;
    const label=element('label',undefined,'check');label.append(select,element('strong',field.label+(field.required?' *':'')));card.append(label);if(field.section)card.append(element('p',field.section+' · '+field.subject.replace('_',' '),'hint'));
    const duplicateClarification=proposal.fact_key&&proposal.value===undefined&&clarifications.has(proposal.fact_key);if(proposal.fact_key&&proposal.value===undefined)clarifications.add(proposal.fact_key);
    const row={field,proposal,select,card,approved:!proposal.written,value:proposal.value,deferred:!!saved.deferred?.[selectionKey(field)],userSelection:saved.selection_version===2?(saved.selections?.[selectionKey(field)]??null):null};rows.push(row);
    // Legacy unchecked state did not distinguish a failure from an opt-out.
    if(row.userSelection===false||row.deferred)select.checked=false;
    if(field.current)card.append(element('p','Existing value: '+field.current+'\nSelect this field explicitly to replace it.','hint'));
    card.append(element('p',proposal.source||proposal.reason,'hint'));
    if(proposal.value!==undefined)card.append(element('div',proposal.value,'value'));
    select.onchange=()=>{row.deferred=false;row.userSelection=select.checked;row.filled=false;controls();scheduleSave();};
    if(proposal.written){
      const draft=element('button','Draft answer','secondary'),text=element('textarea'),evidence=element('pre');text.setAttribute('aria-label','Proposed answer to '+field.label);text.maxLength=field.limit||10000;
      let result=null,editRevision=0;row.text=text;text.hidden=true;
      const counter=element('p','0 / '+text.maxLength,'hint');counter.hidden=true;
      const payload=()=>({packet_id:packet.id,revision:packet.revision,url:page.url,question:C.questionText(field),field_context:C.fieldContext(field),description:page.description,limit:Math.min(field.limit||3000,10000),word_limit:field.wordLimit||undefined,evidence_scope:row.evidenceScope||'packet'});
      row.acceptDraft=next=>{row.validationError=null;text.hidden=false;counter.hidden=false;result=next;row.evidenceScope=next.evidence_scope||'packet';row.draftResult=next;text.value=next.answer;evidence.textContent=Object.entries(next.evidence||{}).map(([id,value])=>id+': '+value).join('\n\n');row.approved=true;select.checked=!field.current;select.disabled=false;counter.textContent=text.value.length+' / '+text.maxLength;scheduleSave();};
      row.draft=async()=>{const context=currentContext(),revision=editRevision;status('Drafting from verified evidence…');const next=await runJob('answer',payload(),context,rowKey(field));requireContext(context);if(revision!==editRevision)throw new Error('Answer edited while drafting. Your edits were preserved.');row.acceptDraft(next);await finishJob(context);status('Answer ready. Evidence will be checked automatically when filling.');};
      draft.onclick=()=>work(row.draft);
      text.oninput=()=>{editRevision++;row.validationError=null;row.value=undefined;row.approved=!!result;select.checked=!!result&&!field.current;select.disabled=!result;counter.textContent=text.value.length+' / '+text.maxLength;controls();scheduleSave();};
      row.validate=async()=>{if(!result)throw new Error('Draft an answer first.');const context=currentContext(),submitted=text.value,revision=editRevision;const checked=await api('/validate-answer',{...payload(),answer:submitted,citations:result.citations,source_revision:result.source_revision,answer_context:result.answer_context});requireContext(context);if(text.value!==submitted||revision!==editRevision)throw new Error('Answer changed during validation. Click Autofill again to check the current text.');row.value=checked.answer;row.validationError=null;};
      const previous=saved.packet_id===packet.id&&saved.revision===packet.revision?saved.rows?.[rowKey(field)]:null;
      if(previous?.result){row.acceptDraft(previous.result);if(previous.value!==undefined){text.value=previous.value;text.oninput();}if(row.userSelection===false||row.deferred)select.checked=false;}
      const sources=element('details',undefined,'sources');sources.append(element('summary','Sources & drafting details'),element('p','Drafting uses Gemini with this question, job description and selected resume evidence.','hint'),evidence);card.append(draft,text,counter,sources);
    } else if(!duplicateClarification&&(proposal.value===undefined||field.type==='combobox')&&!proposal.notApplicable&&!field.excluded&&!['file','password'].includes(field.type)){
      const answerHost=proposal.value!==undefined?element('details'):card;if(answerHost!==card){answerHost.append(element('summary','Choose a different answer'));card.append(answerHost);}
      const input=element(field.options?.length||field.type==='combobox'?'select':'input');input.setAttribute('aria-label','Your explicit answer to '+field.label);input.placeholder='Enter your answer';input.maxLength=field.limit||2000;if(field.multiple)input.multiple=true;
      const explicitValue=()=>field.multiple?[...input.selectedOptions].map(o=>o.value).filter(Boolean):input.value.trim();
      if(field.options?.length){input.append(element('option','Choose an answer…'));input.firstChild.value='';for(const o of field.options){const choice=element('option',o.label);choice.value=o.label;choice.disabled=o.disabled;input.append(choice);}}
      if(field.type==='combobox'&&!field.options?.length){
        input.append(element('option','Load the choices from this dropdown…'));input.firstChild.value='';
        const search=element('input');search.placeholder='Search options (optional)';search.maxLength=300;search.setAttribute('aria-label','Search choices for '+field.label);answerHost.append(search);
        const load=element('button','Load page choices','secondary');load.onclick=()=>work(async()=>{const context=currentContext();const options=await send({action:'choices',id:field.id,query:search.value,tabId,url:page.url});requireContext(context);input.replaceChildren(element('option','Choose an answer…'));input.firstChild.value='';for(const o of options){const option=element('option',o.label);option.value=o.label;option.disabled=o.disabled;input.append(option);}status('Choose an answer, then Use once or Save this answer. Search-only dropdowns may need completion on the page.');});answerHost.append(load);
      }
      const use=element('button','Use once','secondary');use.onclick=()=>{const value=explicitValue();if(!value.length){status('Enter your answer first.',true);return;}const targets=proposal.fact_key?page.fields.filter(f=>f.resolution?.fact_key===proposal.fact_key):[field];for(const target of targets.length?targets:[field])onceAnswers.set(rowKey(target),{value,source:'Explicit answer for this application'});renderFields();scheduleSave();};
      const scope=element('select');scope.setAttribute('aria-label','Reuse scope for '+field.label);scope.append(element('option','This company and exact question'));scope.firstChild.value='company';if(!C.enrollment(field)&&proposal.fact_key&&['current_city','first_name','last_name','full_name','email','phone','linkedin','github','address','state','postal_code','country','school','major','minor','gpa','graduation_month','graduation_year','gender_identity','ethnicity','military_history'].includes(proposal.fact_key)&&!field.multiple){const option=element('option','Reuse this fact across applications');option.value='global';scope.append(option);}
      const save=element('button','Save this answer','secondary');save.onclick=()=>work(async()=>{const value=explicitValue();if(!value.length)throw new Error('Enter your answer first.');if(scope.value==='global'){const knowledge=(prefs.knowledge||[]).filter(r=>!(r.key===proposal.fact_key&&r.scope==='global'));knowledge.push({key:proposal.fact_key,answer:value,scope:'global',question:C.questionText(field),confirmed_at:new Date().toISOString().slice(0,10)});prefs=await api('/preferences',{facts:prefs.facts,questions:prefs.questions.filter(q=>!q.blocked),application_profile:prefs.application_profile,knowledge});await resolveFields();renderPreferences();renderFields();status('Confirmed fact saved for equivalent questions across applications.');return;}const company=page.company||packet.company;if(!company)throw new Error('Identify the company before saving this answer.');const app=structuredClone(prefs.application_profile||{});app.company_answers=(app.company_answers||[]).filter(q=>!(C.normalize(q.company)===C.normalize(company)&&C.normalize(q.question)===C.normalize(C.questionText(field))));app.company_answers.push({company,question:C.questionText(field),answer:value});prefs=await api('/preferences',{facts:prefs.facts,questions:prefs.questions.filter(q=>!q.blocked),application_profile:app});field.resolution={value,source:'Explicit company answer (exact wording)'};renderPreferences();renderFields();status('Explicit answer saved for this company and exact wording.');});answerHost.append(input,scope,use,save);
    }
    if(field.group&&proposal.value===undefined&&!C.matchEntry(field.group,packet)){
      const mapping=element('select');mapping.setAttribute('aria-label','Match '+field.group.kind+' entry');mapping.append(element('option','Choose the matching resume entry…'));
      const entries=field.group.kind==='education'?packet.education:packet.experiences;
      entries.forEach((entry,i)=>{const option=element('option',(entry.company||entry.institution)+(entry.role?' · '+entry.role:''));option.value=String(i);mapping.append(option);});mapping.firstChild.value='';
      const mapButton=element('button','Use this entry','secondary');mapButton.onclick=()=>{if(mapping.value==='')return;const entry=entries[Number(mapping.value)],identity=entry.company||entry.institution;
        if(field.group.identity&&C.normalize(field.group.identity)!==C.normalize(identity)||field.group.role&&C.normalize(field.group.role)!==C.normalize(entry.role)){status('Existing employer or role differs. Correct the page and rescan before mapping.',true);return;}
        page.fields.filter(f=>f.group?.id===field.group.id).forEach(f=>f.group={...f.group,identity,role:entry.role||''});renderFields();};card.append(mapping,mapButton);
    }
    if(duplicateClarification)card.append(element('p','The answer to the earlier question about '+proposal.fact_key.replaceAll('_',' ')+' also applies here.','hint'));
    const focus=element('button','Show on page','secondary');focus.onclick=()=>work(()=>send({action:'focus',id:field.id,tabId,url:page.url}));card.append(focus);
    row.result=element('p','','field-result');card.append(row.result);const category=categories[proposal.written||field.current||proposal.notApplicable?'Written answers and existing values':proposal.value!==undefined?'Your details':'Needs your input'];category.group.append(card);category.count++;
  }for(const [name,category] of Object.entries(categories)){category.summary.textContent=name+' ('+category.count+')';category.group.classList.toggle('empty',!category.count);}const written=rows.filter(r=>r.draft).length;$('draft-all').hidden=written<1;$('review-summary').textContent=rows.filter(r=>r.proposal.value!==undefined&&!r.field.current).length+' ready to fill'+(written?' · '+written+' written question'+(written===1?'':'s'):'')+' · '+unresolvedSummary();controls();
}
$('pair').onclick=()=>work(async()=>{await send({action:'pair',server:$('server').value.trim(),code:$('code').value.trim()});server=$('server').value.trim();$('code').value='';prefs=await api('/preferences');renderPreferences();await refresh();$('connection').open=false;$('connection-state').textContent='Connected';await scanPage();$('welcome').hidden=true;status('Connected to ApplyPilot.');});
$('disconnect').onclick=()=>work(async()=>{await send({action:'disconnect'});packet=null;invalidate('Disconnected.');$('connection').open=true;$('welcome').hidden=false;status('Disconnected on this browser.');});
$('refresh').onclick=()=>work(async()=>{await refresh();if(packet){const context=currentContext(),selected=await api('/packet',{packet_id:packet.id});requireContext(context);packet=selected;invalidate('Packet refreshed. Scan again to review current facts.');}status('Packet list refreshed.');});
$('packet').onchange=()=>work(async()=>{packet=null;epoch++;$('match').checked=false;$('packet-info').textContent='';if(!$('packet').value){renderFields();return;}const context=currentContext(),selected=await api('/packet',{packet_id:$('packet').value});requireContext(context);packet=selected;$('match').checked=true;$('packet-info').textContent=`${packet.company} · ${packet.role}\n${packet.pdf_name}\nVersion: ${packet.folder}`;await resolveFields();renderFields();await saveProgress();controls();status('Resume selected. Clear answers are ready to autofill.');});
$('scan').onclick=()=>work(scanPage);
$('match').onchange=()=>{controls();scheduleSave();};
async function fillSelected(preparing=false){
  if(!packet||!page?.supported||!$('match').checked)throw new Error('Choose a resume and scan the application first.');
  const context=currentContext();const chosen=rows.filter(r=>r.select.checked&&!r.select.disabled&&r.approved);
  const blocked=[];
  for(const row of chosen.filter(r=>r.validate)){try{await row.validate();requireContext(context);}catch(error){requireContext(context);row.validationError=error.message;row.result.textContent='Not filled: '+error.message;row.select.checked=false;blocked.push(row);}}
  for(const row of chosen.filter(r=>r.validate&&!blocked.includes(r))){if(row.text.value!==row.value){row.validationError='Answer changed while other answers were being checked.';row.result.textContent='Not filled: '+row.validationError;row.select.checked=false;blocked.push(row);}}
  const changes=chosen.filter(r=>!blocked.includes(r)).map(r=>({id:r.field.id,value:r.value,checked:r.proposal.checked,alternatives:r.proposal.alternatives,source:r.proposal.source==='Explicit answer for this application'?'once':r.proposal.written?'written':r.proposal.file?'pdf':r.proposal.source?.startsWith('Explicit')?'explicit':'profile',replace:!!r.field.current}));
  status('Filling selected fields…');const results=await send({action:'fill',preparing,tabId,url:page.url,scanId:page.scanId,packetId:packet.id,revision:packet.revision,company:page.company||packet.company,fields:page.fields,accounting:rows.filter(r=>!changes.some(c=>c.id===r.field.id)).map(r=>({id:r.field.id,status:r.field.current?'skipped':r.userSelection===false?'excluded':r.validationError?'invalidated':r.field.excluded?'manual':'unanswered',code:r.field.current?'preserved':r.userSelection===false?'excluded':r.validationError?'invalidated':r.field.excluded?'manual':r.proposal.code||'unanswered'})),attach:chosen.filter(r=>!blocked.includes(r)).some(r=>r.proposal.file),changes});requireContext(context);
  for(const result of results){const row=rows.find(r=>r.field.id===result.id);if(!row)continue;row.field.notApplicable=result.status==='not applicable';row.result.textContent=row.validationError?'Not filled: '+row.validationError:result.status+': '+result.message;row.select.checked=result.status==='failed'&&!row.select.disabled&&row.userSelection!==false;row.filled=!row.proposal.written&&['filled','uploaded'].includes(result.status);}
  const counts={};results.forEach(r=>counts[r.status]=(counts[r.status]||0)+1);status(Object.entries(counts).map(([k,v])=>v+' '+k).join(' · ')+(results.length?'. ':'')+unresolvedSummary()+(blocked.length?' '+blocked.length+' written answer(s) failed validation; see the field explanations.':''));if(results.length)$('undo').disabled=false;await saveProgress();await loadDiagnostics();if(results.some(r=>r.newField)){const known=new Set(rows.map(r=>selectionKey(r.field)));await scanPage();for(const row of rows)if(!known.has(selectionKey(row.field))){row.select.checked=false;row.deferred=!preparing;}await saveProgress();status('New questions appeared and were rescanned. Select the additional fields you want to fill.');}if(page.fields.some(f=>f.condition)&&!results.some(r=>r.newField))await scanPage();if(results.some(r=>r.diagnostic_unsaved))status('Fill completed, but diagnostic history could not be saved. Keep this panel open.',true);
  return results;
}
$('fill').onclick=()=>work(()=>fillSelected());
function preparationSummary(){
  const missing=rows.filter(r=>r.field.required&&!r.field.current&&!r.field.notApplicable&&!r.proposal.notApplicable);
  const unsupported=page.unsupported||[];
  const uploads=page.fields.filter(f=>f.type==='file'&&f.current&&f.uploadAcknowledged===false);
  return (missing.length?missing.length+' required question(s) need your input. ':unsupported.length||uploads.length?'Preparation needs your attention. ':'Ready for your review. ')+
    (unsupported.length?unsupported.length+' unrecognized control(s) need inspection. ':'')+
    (uploads.length?uploads.length+' upload(s) lack portal acknowledgement. ':'')+
    'Review the values, resume and written answers on the page. Nothing has been submitted.';
}
async function prepareApplication(){
  const health=await api('/health');
  if(health.preparation_version!==2)throw new Error('Update and restart the ApplyPilot companion before preparing an application.');
  await scanPage();
  if(page?.platform!=='greenhouse')throw new Error('Prepare application currently supports hosted Greenhouse forms.');
  if(activeJob)throw new Error('Continue or cancel the saved preparation first.');
  if(!packet){
    const context=currentContext();
    const company=$('generate-company').value.trim(),role=$('generate-role').value.trim(),description=$('generate-description').value.trim();
    if(!company||!role||!description)throw new Error('Complete the company, role and description before preparing a resume.');
    const result=await runJob('resume',{url:page.url,company,role,description},context);
    await showGenerated(result,context);
  }
  if(C.normalize(packet.company)!==C.normalize(page.company)||C.normalize(packet.role)!==C.normalize(page.title))
    throw new Error('The selected resume does not exactly match this company and role. Choose the matching resume or correct the job details.');
  const failedKeys=new Set();
  const summary=()=>preparationSummary()+(failedKeys.size?' '+failedKeys.size+' field(s) failed verification; see Recent fill results and complete or retry those fields.':'');
  const eligible=row=>!row.field.current&&!row.field.excluded&&!row.field.notApplicable&&row.userSelection!==false&&!row.deferred&&!failedKeys.has(selectionKey(row.field));
  async function fillPrepared(){
    const keys=new Map(rows.map(row=>[row.field.id,selectionKey(row.field)]));
    const results=await fillSelected(true);
    const failures=results.filter(r=>['failed','needs review','invalidated'].includes(r.status));
    for(const result of failures)if(keys.has(result.id))failedKeys.add(keys.get(result.id));
    // A changed context requires a fresh user decision. Unavailable choices and
    // rejected uploads affect only that field; continue independent work once.
    if(failures.some(r=>r.status==='invalidated'||['stale','context_changed','control_replaced','invalidated'].includes(r.code))){
      status('Application context changed. Rescan and review before continuing. '+summary(),true);return false;
    }
    return true;
  }
  for(let cycle=0;cycle<5;cycle++){
    // Finish supported facts before asking questions or waiting for prose.
    for(const row of rows)row.select.checked=eligible(row)&&!row.proposal.written&&row.value!==undefined;
    if(rows.some(r=>r.select.checked)){
      if(!await fillPrepared())return;
      await scanPage();
    }
    const unknown=rows.filter(r=>eligible(r)&&r.value===undefined&&!r.proposal.written&&!r.field.resolution&&
      !C.personalQuestion.test(C.questionText(r.field))&&!C.manual.test(C.questionText(r.field))&&!C.disclosure.test(C.questionText(r.field))&&r.field.type!=='file');
    if(unknown.length){
      const context=currentContext();
      await runJob('interpret',{url:page.url,company:page.company,fields:unknown.slice(0,100).map(r=>C.fieldContext(r.field))},context);
      await finishJob(context);await resolveFields();renderFields();
    }
    for(const row of rows.filter(r=>eligible(r)&&r.field.required&&r.draft&&!r.text.value)){
      row.evidenceScope='profile';
      try{await row.draft();}catch(error){if(!page||activeJob)throw error;row.validationError=error.message;row.result.textContent='Needs your input: '+error.message;}
    }
    for(const row of rows)row.select.checked=eligible(row)&&!row.validationError&&
      (row.proposal.written?row.field.required&&!!row.text?.value:row.value!==undefined);
    if(!rows.some(r=>r.select.checked)){await saveProgress();status(summary(),!!page.unsupported?.length||failedKeys.size>0);return;}
    if(!await fillPrepared())return;
    const previous=JSON.stringify(page.fields.map(f=>[f.label,f.current]));
    await scanPage();
    if(JSON.stringify(page.fields.map(f=>[f.label,f.current]))===previous){status('No further progress detected. '+summary());return;}
  }
  status('Five preparation cycles completed. '+summary()+' Click Prepare application to continue if more questions appeared.');
}
$('prepare').onclick=()=>work(prepareApplication);
$('download').onclick=()=>work(async()=>{const current=packet;const data=await api('/packet',{packet_id:current.id,revision:current.revision,include_pdf:true});const bytes=Uint8Array.from(atob(data.pdf_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));const link=element('a');link.href=url;link.download=data.pdf_name;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);status('Selected PDF downloaded. You can attach it manually.');});
$('add-question').onclick=()=>questionRow();
$('save-preferences').onclick=()=>work(async()=>{const facts=Object.fromEntries([...document.querySelectorAll('[data-fact]')].map(e=>[e.dataset.fact,e.value.trim()]));const questions=[...document.querySelectorAll('.question-row')].map(row=>{const [q,a]=row.querySelectorAll('textarea');return {question:q.value,answer:a.value};});prefs=await api('/preferences',{facts,questions,application_profile:readApplicationProfile()});invalidate('Preferences changed. Scan again to review proposed answers.');status('Explicit answers saved locally.');});
chrome.tabs.onActivated.addListener(()=>{saveProgress().catch(()=>{});invalidate('Active tab changed. Click ApplyPilot on the application.');packet=null;$('packet').value='';controls();});
chrome.tabs.onUpdated.addListener((id,change)=>{if(id===tabId&&(change.url||change.status==='loading')){saveProgress().catch(()=>{});invalidate('Page changed. Scan and review again.');packet=null;$('packet').value='';controls();}});
async function initialize(action='settings'){try{const settings=await send({action});server=settings.server;$('server').value=settings.server;$('extension-id').textContent=settings.id;$('welcome').hidden=settings.paired;$('connection-state').textContent=settings.paired?'Connecting…':'Setup needed';if(settings.paired){prefs=await api('/preferences');renderPreferences();await api('/health');$('connection-state').textContent='Connected';await refresh();await work(scanPage);}else{renderPreferences();status(settings.connectionError?'Open ApplyPilot.app once to enable or repair the Chrome connection.':'Connect Chrome to get started.');}}catch(error){$('welcome').hidden=false;$('connection').open=true;status(error.message,true);}}
initialize();

$('packet-search').oninput=renderPackets;
$('open-pairing').onclick=()=>work(()=>send({action:'pairing-page',server:$('server').value.trim()}));
$('undo').onclick=()=>work(async()=>{const results=await send({action:'undo',tabId,url:page.url});status(results.filter(r=>r.status==='restored').length+' values restored. Uploads and custom dropdowns need manual removal.');$('undo').disabled=true;});
$('draft-all').onclick=()=>work(async()=>{for(const row of rows.filter(r=>r.draft&&!r.text.value)){await row.draft();}status('Written answers ready. Click Autofill; evidence checks run automatically.');});
$('clear-progress').onclick=()=>work(async()=>{if(!page?.postingKey)return;clearTimeout(saveTimer);await progressWrites.catch(()=>{});await api('/session',{action:'clear',key:page.postingKey});activeJob=null;jobControls();saved={};$('match').checked=!!packet;renderFields();status('Progress cleared for this application. PDFs and tracker history preserved.');});
$('clear-all-progress').onclick=()=>work(async()=>{clearTimeout(saveTimer);await progressWrites.catch(()=>{});await api('/session',{action:'clear-all',key:'all'});activeJob=null;jobControls();saved={};$('match').checked=!!packet;renderFields();status('All saved application progress cleared.');});
$('cancel-job').onclick=async()=>{try{
  if(!activeJob)return;const context=currentContext(),pending={...activeJob};
  if(pending.status!=='complete')await api('/jobs',{action:'cancel',id:pending.id,request_id:pending.request_id});
  requireContext(context);epoch++;activeJob=null;jobControls();await saveProgress();status('Preparation dismissed. Any completed resume remains in Change.');
}catch(e){status(e.message,true);}};
$('generate').onclick=()=>work(async()=>{if(!page?.supported)throw new Error('Scan a supported posting first.');if(!$('generate-company').value.trim()||!$('generate-role').value.trim()||!$('generate-description').value.trim()){$('generate-options').open=true;$('generate-company').focus();throw new Error('Check the job details above, then click Prepare my resume.');}const context=currentContext();const result=await runJob('resume',{url:page.url,company:$('generate-company').value,role:$('generate-role').value,description:$('generate-description').value},context);await showGenerated(result,context);});
async function showGenerated(result,context=currentContext()){await refresh();requireContext(context);const selected=await api('/packet',{packet_id:result.packet_id});requireContext(context);packet=selected;activeJob=null;epoch++;$('packet').value=packet.id;$('match').checked=true;jobControls();await resolveFields();renderFields();await saveProgress();status('Prepared resume selected. Clear answers are ready to autofill.');}
$('resume-job').onclick=()=>work(async()=>{
  if(!activeJob)return;
  const pending={...activeJob},context=currentContext();
  if(pending.posting_key!==page?.postingKey)throw new Error('Preparation belongs to another application.');
  if(pending.kind==='answer'&&(pending.packet_id!==packet?.id||pending.revision!==packet?.revision))throw new Error('Pending answer belongs to another resume version. Select that version or cancel the pending preparation.');
  const job=pending.id?await api('/jobs',{action:'status',id:pending.id}):await api('/jobs',{kind:pending.kind,input:pending.input,request_id:pending.request_id,posting_key:pending.posting_key});requireContext(context);
  const result=await pollJob(job,context);
  if(pending.kind==='resume')await showGenerated(result,context);
  else if(pending.kind==='interpret'){await finishJob(context);await resolveFields();renderFields();status('Questions interpreted. Click Prepare application to continue.');}
  else{
    const candidates=rows.filter(r=>pending.row_key?rowKey(r.field)===pending.row_key:r.field.label===pending.question);
    const row=candidates.length===1?candidates[0]:null;
    if(!row?.acceptDraft||row.text.value)throw new Error('Existing answer preserved, or the question changed. Cancel this preparation before drafting again.');
    row.acceptDraft(result);await finishJob(context);status('Answer restored. Evidence will be checked automatically when filling.');
  }
});

chrome.runtime.onMessage?.addListener((message,sender)=>{if(sender.id===chrome.runtime.id&&message.action==='invoked'&&!busy)work(scanPage);});

window.addEventListener("pagehide",()=>{clearTimeout(saveTimer);saveProgress().catch(()=>{});});

let previewData=null,previewContext=null,previewURL=null;
function closePreview(){ $('resume-dialog').close();if(previewURL)URL.revokeObjectURL(previewURL);previewURL=null;previewData=null; }
async function previewResume(id){
  const context=currentContext(),data=await api('/packet',{packet_id:id,revision:id===packet?.id?packet.revision:undefined,include_pdf:true});requireContext(context);
  previewData=data;previewContext=context;
  if(previewURL)URL.revokeObjectURL(previewURL);
  previewURL=URL.createObjectURL(new Blob([Uint8Array.from(atob(data.pdf_base64||''),c=>c.charCodeAt(0))],{type:'application/pdf'}));
  $('pdf-preview').src=previewURL;$('preview-label').textContent=data.company+' · '+data.role;
  $('resume-evidence').replaceChildren();
  for(const bullet of data.review_bullets||[]){const card=element('article');card.append(element('strong',bullet.company+' · '+bullet.role),element('p','Resume: '+bullet.text),element('p','Original: '+(Array.isArray(bullet.original)?bullet.original.join('\n'):bullet.original)));$('resume-evidence').append(card);}
  $('resume-dialog').showModal();
}
$('preview').onclick=()=>work(()=>previewResume(packet.id));
$('preview-close').onclick=closePreview;
$('resume-dialog').addEventListener('cancel',closePreview);
$('preview-download').onclick=()=>{if(!previewData)return;const link=element('a');link.href=previewURL;link.download=previewData.pdf_name;link.click();};
$('use-resume').onclick=()=>work(async()=>{if(!previewData)throw new Error('Preview a resume first.');requireContext(previewContext);if(!page?.supported)throw new Error('Open a supported application first.');const selected=await api('/packet',{packet_id:previewData.id,revision:previewData.revision});requireContext(previewContext);packet=selected;if(activeJob?.kind==='resume'&&activeJob.result_packet_id===selected.id)activeJob=null;jobControls();epoch++;$('packet').value=packet.id;$('match').checked=true;closePreview();$('resume-library').open=false;await resolveFields();renderFields();await saveProgress();status('Resume ready. Autofill your details, then review the remaining questions.');});
$('settings-open').onclick=()=>$('settings-dialog').showModal();$('settings-close').onclick=()=>$('settings-dialog').close();
$('change-resume').onclick=()=>{$('resume-library').open=!$('resume-library').open;};
$('edit-job').onclick=()=>{$('generate-options').open=!$('generate-options').open;};
$('manage').onclick=()=>work(()=>send({action:'manage'}));$('setup').onclick=()=>work(()=>send({action:'setup'}));
$('reconnect').onclick=()=>initialize('connect');

for(const id of ['generate-company','generate-role','generate-description'])$(id).addEventListener('input',scheduleSave);
