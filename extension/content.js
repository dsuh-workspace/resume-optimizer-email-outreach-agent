/* Runs in Chrome's isolated world. No runtime message listener or page-controlled fetch. */
(function () {
  'use strict';
  const version='0.9.2';
  if(globalThis.ApplicationAutofill) {
    if(globalThis.ApplicationAutofill.version!==version)throw new Error('ApplyPilot was updated. Preserve any unsaved entries, refresh this application tab, and reopen ApplyPilot.');
    return;
  }
  const C = globalThis.CopilotCore;
  let mapping = new Map(), scanId = '', snapshotURL = '', snapshotCompany='', undoLog = [];
  const searches=new WeakMap();
  let userRevision=0,ownedInteraction=0;
  function interact(action){ownedInteraction++;try{return action();}finally{ownedInteraction--;}}
  for(const event of ['input','change','keydown','pointerdown'])document.addEventListener(event,e=>{if(e.isTrusted&&!ownedInteraction)userRevision++;},true);
  const identities=new WeakMap(); let identityCounter=0;
  const nodeId=node=>{if(!node)return '';if(!identities.has(node))identities.set(node,++identityCounter);return identities.get(node);};
  const actionControl=el=>['submit','reset','image'].includes(el.type)||(el.tagName==='BUTTON'&&/^(?:next|submit|continue|send|finish|apply(?: now)?)$/i.test(el.textContent.trim()));
  const visible = el => !!el && !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  const adapters = {
    greenhouse: {container:'.field, .input-wrapper, .select, .select-shell, .file-upload, .field-wrapper, fieldset', title:'.app-title, h1', description:'#content, .job__description, .job-post-description', groups:'.education, .education-entry, .education--entry, .employment, [data-education], [data-employment]', uploadError:'.file-upload__error', uploadBusy:'.file-upload__loading'},
    lever: {container:'.application-question, .application-field, fieldset', title:'.posting-headline h2, h1', description:'.posting-page .content, .section-wrapper', groups:'[data-education], [data-employment], .education, .employment', uploadError:'.resume-upload-failure', uploadBusy:'.resume-upload-working'}
  };
  // React-style selects open on mousedown, not HTMLElement.click(). Dispatch only
  // to a validated non-action control; never a global menu or navigation button.
  function activate(el) {
    if(actionControl(el)||el.disabled)throw failure('unsupported','Unsafe or disabled control.');
    el.focus();
    el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:0}));
    el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true,button:0}));
    interact(()=>el.click());
  }
  function committed(el) {
    if(el.tagName==='SELECT')return el.value?el.selectedOptions[0]?.textContent.trim()||'':'';
    if(el.type==='radio'){const selected=radios(el).find(o=>o.checked);return selected?label(selected,adapters[C.platform(location.href)]):'';}
    return current(el);
  }
  function notApplicable(record) {
    const parent=mapping.get(record.field.condition?.parentId);
    if(!parent||!parent.el.isConnected||parent.el.form!==record.el.form||fingerprint(parent.el,adapters[C.platform(location.href)])!==parent.fingerprint)return false;
    const value=C.normalize(committed(parent.el)),condition=record.field.condition;
    return !!value&&!condition.noValue&&(condition.when==='other'?!/^other\b/.test(value):value==='no');
  }
  function conditionalValue(record){const condition=record.field.condition,parent=mapping.get(condition?.parentId);return condition?.noValue&&parent?.el.isConnected&&fingerprint(parent.el,adapters[C.platform(location.href)])===parent.fingerprint&&C.normalize(committed(parent.el))==='no'?condition.noValue:undefined;}
  function label(el, adapter) {
    const labelText=node=>{if(!node.querySelector('select,textarea,[role="listbox"]'))return node.innerText.trim();const copy=node.cloneNode(true);copy.querySelectorAll('input,select,textarea,button,[role="listbox"]').forEach(e=>e.remove());return copy.textContent.trim();};
    const labels = [...(el.labels || [])].map(labelText).filter(Boolean);
    if(labels.length) return labels.join(' ').slice(0,2000);
    const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ').trim();
    if(labelled) return labelled.slice(0,2000);
    const wrapper = el.closest(adapter.container);
    return (el.getAttribute('aria-label') || wrapperLabel(wrapper) || wrapper?.querySelector('label, .application-label, legend')?.innerText || el.getAttribute('placeholder') || el.name || el.id || 'Unlabeled field').trim().slice(0,2000);
  }
  function helperText(el,adapter){
    const nodes=(el.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean).map(id=>document.getElementById(id));
    const wrapper=el.closest(adapter.container);
    if(wrapper)nodes.push(...wrapper.querySelectorAll('.helper-text,.description,.field-description,.helper,.help-text,[data-description]'));
    // React Select includes its transient placeholder in aria-describedby.
    // Typing/selection removes it; that is not a change to the question.
    // Ignore only the associated widget placeholder, retaining all instructions.
    const placeholder=n=>el.getAttribute('role')==='combobox'&&n.matches('.select__placeholder,[class$="-placeholder"]')&&n.closest('.select-shell,.select')===el.closest('.select-shell,.select');
    return [...new Set(nodes.filter(n=>n&&visible(n)&&!placeholder(n)).map(n=>n.innerText.trim()).filter(Boolean))].join('\n').slice(0,4000);
  }
  function wrapperLabel(wrapper){return wrapper?.matches('.application-field')?wrapper.parentElement?.querySelector(':scope > .application-label')?.innerText||'':'';}
  function radios(el) {return [...document.querySelectorAll('input[type="radio"]')].filter(o=>o.name===el.name && o.form===el.form);}
  function checks(el) {if(C.privacyConsent(label(el,adapters[C.platform(location.href)])))return [el];const group=el.closest('fieldset,[role="group"]');return group?[...group.querySelectorAll('input[type="checkbox"]')]:[el];}
  function question(el,adapter) {if(el.type==='checkbox'&&C.privacyConsent(label(el,adapter)))return label(el,adapter);const group=el.closest('fieldset,[role="radiogroup"],[role="group"]');return ['radio','checkbox'].includes(el.type) ? group?.querySelector('legend')?.innerText || group?.getAttribute('aria-label') || (group?.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText||'').join(' ').trim() || wrapperLabel(el.closest(adapter.container)) || el.closest(adapter.container)?.querySelector('.application-label, label')?.innerText || label(el,adapter) : label(el,adapter);}
  function displayValue(el,display) {
    const text=display.textContent.trim();
    // Greenhouse collapses the phone country to a flag and dial code after
    // selection. Never infer US from +1 alone (Canada shares that code).
    if(C.platform(location.href)==='greenhouse'&&el.id==='country'&&
       C.normalize(label(el,adapters.greenhouse))==='country'&&/^\+\s*1$/.test(text)&&
       display.querySelectorAll('.iti__flag').length===1&&display.querySelector('.iti__flag.iti__us'))return 'United States +1';
    return text;
  }
  function current(el) {
    if(el.getAttribute?.('role')==='combobox'){
      const pending=searches.get(el);
      if(pending&&el.value===pending.query)return pending.previous;
      const selected=el.closest('.field,.application-question,.application-field,.input-wrapper,.select,.select-shell,.field-wrapper')?.querySelectorAll('.select__single-value,[class$="-singleValue"],[data-selected-value]');
      if(selected?.length===1&&selected[0].textContent.trim())return displayValue(el,selected[0]);
      if(el.value&&el.getAttribute('aria-expanded')!=='true')return el.value;
      const text=el.tagName==='BUTTON'?el.innerText.trim():'';
      return /^(?:select|choose)(?: an? option)?(?:\.{3}|…)?$/i.test(text)?'':text;
    }
    if(el.type==='file'){
      const selected=[...el.files].map(f=>f.name).join(', ');if(selected)return selected;
      const wrapper=el.closest(adapters[C.platform(location.href)]?.container||'.file-upload');
      if(wrapper&&[...wrapper.querySelectorAll('button,[role="button"]')].some(e=>visible(e)&&/^(?:remove|delete)(?: file| attachment| resume)?$/i.test(e.getAttribute('aria-label')||e.textContent.trim()))){
        const names=[...wrapper.querySelectorAll('span,a,p,div')].filter(e=>visible(e)&&!e.childElementCount&&/^[^\n]+\.(?:pdf|docx?|txt|rtf)$/i.test(e.textContent.trim())).map(e=>e.textContent.trim());
        if(new Set(names).size===1)return names[0];
      }
      return '';
    }
    return el.tagName==='SELECT'&&el.multiple?[...el.selectedOptions].map(o=>o.value).join(', '):el.type === 'checkbox' ? checks(el).filter(o=>o.checked).map(o=>o.value).join(', ') : el.type === 'radio' ? (radios(el).find(o=>o.checked)?.value || '') : el.value||'';
  }
  function options(el,adapter) {return el.tagName==='SELECT'?[...el.options].filter(o=>o.value).map(o=>({label:o.textContent.trim(),value:o.value,disabled:o.disabled||o.parentElement?.tagName==='OPTGROUP'&&o.parentElement.disabled})):['radio','checkbox'].includes(el.type)?(el.type==='radio'?radios(el):checks(el)).map(o=>({label:label(o,adapter),value:o.value,disabled:o.disabled||o.parentElement?.tagName==='OPTGROUP'&&o.parentElement.disabled})):[];}
  function subjectContext(el, adapter) {
    const sections=[];
    for(let parent=el.parentElement;parent&&parent.tagName!=='BODY';parent=parent.parentElement){
      const heading=parent.querySelector(':scope > legend,:scope > h2,:scope > h3,:scope > h4,:scope > [role="heading"]');
      if(heading&&!heading.contains(el)&&heading.textContent.trim())sections.push(heading.textContent.trim().replace(/\s+/g,' ').slice(0,300));
      const aria=parent.getAttribute('aria-labelledby');
      if(aria&&['group','region'].includes(parent.getAttribute('role')))for(const id of aria.split(/\s+/)){const title=document.getElementById(id);if(title)sections.push(title.textContent.trim().slice(0,300));}
      // Older layouts delimit sections with a heading followed by sibling fields.
      for(let previous=parent.previousElementSibling;previous;previous=previous.previousElementSibling){
        if(previous.matches('h2,h3,h4,legend,[role="heading"]')){sections.push(previous.textContent.trim().slice(0,300));break;}
      }
      if(parent.tagName==='FORM')break;
    }
    const section=[...new Set(sections)].reverse().join(' / ');
    const explicitApplicant=/\b(applicant|your (?:details|information)|personal (?:details|information)|contact information)\b/i.test(section);
    let subject=C.thirdParty({section,label:question(el,adapter)})?'third_party':'applicant';
    const identity=/^(?:first name|last name|full name|name|email(?: address)?|phone(?: number)?)$/i;
    const own=C.normalize(question(el,adapter));
    if(subject==='applicant'&&!explicitApplicant&&identity.test(own)){
      const peers=[...(el.form||document).querySelectorAll('input')].filter(o=>logicalControl(o,adapter)===o&&visible(o)&&C.normalize(question(o,adapter))===own);
      if(peers.length>1)subject='uncertain';
    }
    return {contextVersion:2,section,subject};
  }
  function fingerprint(el, adapter) {return JSON.stringify([subjectContext(el,adapter),el.tagName,el.type,el.name,question(el,adapter),helperText(el,adapter),el.multiple,el.getAttribute('role'),options(el,adapter),nodeId(el.form),nodeId(el.closest('fieldset,[role="radiogroup"]')),el.readOnly,el.required,el.getAttribute('aria-required'),el.maxLength,el.accept]);}
  function assertFresh(record,adapter,ownValue) {
    const {el,field}=record;
    if(record.uncertain)throw failure('context_changed','School or employer identity is uncertain after a concurrent change. Scan again.');
    if(companyName()!==snapshotCompany)throw failure('context_changed','Company context changed. Scan again.');
    const pending=searches.get(el);if(pending&&(el.value!==pending.query||pending.revision!==userRevision))throw failure('context_changed','Search changed while waiting. Your edit was preserved.');
    if(actionControl(el)||location.href!==snapshotURL || !el.isConnected || (el.type==='file'?!visible(el.closest(adapter.container)||el):!visible(el)) || el.disabled || el.readOnly || fingerprint(el,adapter)!==record.fingerprint) throw new Error('Field changed. Scan again.');
    if(C.thirdParty({...field,...subjectContext(el,adapter)}) || field.excluded || C.manual.test(question(el,adapter))&&!C.privacyConsent(question(el,adapter)) || el.type==='password' || (el.type==='checkbox'&&!el.closest('fieldset,[role="group"]')&&!C.privacyConsent(question(el,adapter)))) throw new Error('Manual-only field.');
    if(current(el)!==(ownValue===undefined?field.current:ownValue)) throw new Error('Value changed since preview. Scan again before replacing it.');
    if(field.group && (!sameGroup(record,adapter)||groupIdentity(el,adapter,ownValue!==undefined?field.current:undefined)!==record.groupIdentity)) throw new Error('Employment or education entry changed. Scan again.');
  }
  const controlSelector='input,select,button[role="combobox"]';
  const schoolLabel=/^(school|school name|university|institution|college)$/;
  const employerLabel=/^(company|company name|employer|employer name)$/;
  function logicalControl(el,adapter) {
    if(el.getAttribute('role')==='combobox')return el;
    // Composite dropdowns often expose an unnamed dummy text input beside the real control.
    if(el.tagName!=='INPUT'||el.type!=='text'||el.name||el.id||el.labels?.length||el.hasAttribute('aria-label')||el.hasAttribute('aria-labelledby'))return el;
    if(el.getAttribute('aria-hidden')!=='true'&&!(el.tabIndex===-1&&el.closest('.select,.select-shell,[data-select]')))return el;
    const wrapper=el.closest('.select,.select-shell,.input-wrapper,.field,.application-question,.application-field,[data-select]');
    const combos=wrapper?[...wrapper.querySelectorAll('input[role="combobox"],button[role="combobox"]')]:[];
    // Required-input shims have no label of their own. Greenhouse may place
    // the real question label outside select-shell, referenced only by the
    // combobox. A unique control in this local wrapper establishes ownership.
    return combos.length===1?combos[0]:el;
  }
  function entryGroup(el,adapter) {
    const explicit=el.closest(adapter.groups);
    if(explicit)return {el:explicit,kind:/education/.test(explicit.className)||explicit.hasAttribute('data-education')?'education':'employment'};
    for(let parent=el.parentElement;parent&&parent.tagName!=='FORM'&&parent.tagName!=='BODY';parent=parent.parentElement){
      const controls=[...parent.querySelectorAll(controlSelector)].filter(o=>logicalControl(o,adapter)===o&&o.type!=='hidden');
      const schools=controls.filter(o=>schoolLabel.test(C.normalize(label(o,adapter))));
      const employers=controls.filter(o=>employerLabel.test(C.normalize(label(o,adapter))));
      if(schools.length===1&&!employers.length&&controls.length>1)return {el:parent,kind:'education'};
      if(employers.length===1&&!schools.length&&controls.length>1)return {el:parent,kind:'employment'};
      if(schools.length>1||employers.length>1)return null;
      const heading=parent.querySelector(':scope > legend,:scope > h2,:scope > h3,:scope > h4');
      if(heading&&controls.length>1&&/^(education|employment|work experience)(?: \d+)?$/i.test(heading.textContent.trim()))return {el:parent,kind:/education/i.test(heading.textContent)?'education':'employment'};
    }
    return null;
  }
  function groupIdentity(el,adapter,ownOriginal) {
    const group=entryGroup(el,adapter)?.el; if(!group)return '';
    return JSON.stringify([...group.querySelectorAll('input,select,button[role="combobox"]')].filter(o=>logicalControl(o,adapter)===o&&/^(company|company name|employer|employer name|title|job title|role|position|school|school name|university|institution|college)$/.test(C.normalize(label(o,adapter)))).map(o=>[label(o,adapter),o===el&&ownOriginal!==undefined?ownOriginal:current(o)]));
  }
  function companyName(heading=document.querySelector(adapters[C.platform(location.href)]?.title||'h1')?.innerText||document.title){
    let company=document.querySelector('[itemprop="hiringOrganization"] [itemprop="name"], .company-name')?.textContent.trim()||'';
    for(const script of document.querySelectorAll('script[type="application/ld+json"]')){try{
      const raw=JSON.parse(script.textContent),records=Array.isArray(raw)?raw:raw['@graph']||[raw];
      const job=records.find(r=>r['@type']==='JobPosting'&&C.normalize(r.title)===C.normalize(heading));
      if(job&&typeof job.hiringOrganization?.name==='string')company=job.hiringOrganization.name;
    }catch(_){/* Incomplete site metadata remains editable by the user. */}}

    // Modern hosted Greenhouse pages can omit hiringOrganization entirely.
    // Require the entire visible role prefix so another page's metadata cannot
    // silently choose the employer used for scoped personal answers.
    if(!company&&C.platform(location.href)==='greenhouse'){
      const prefix='Job Application for '+heading.trim()+' at ';
      if(document.title.startsWith(prefix))company=document.title.slice(prefix.length).trim();
    }
    return company;
  }
  function scan() {
    const platform = C.platform(location.href);
    if(!platform) {
      const links = [...document.querySelectorAll('iframe[src], a[href]')].map(el => el.src || el.href).filter(C.platform);
      return {supported:false, links:[...new Set(links)].slice(0,10)};
    }
    const adapter = adapters[platform]; mapping = new Map(); scanId = crypto.randomUUID(); snapshotURL = location.href;
    const fields = [], radioNames = new Set(),occurrences=new Map();
    const groups = [];
    for(const el of document.querySelectorAll('input, select, textarea, button[role="combobox"]')) {
      if(logicalControl(el,adapter)!==el)continue;
      if(actionControl(el)||el.disabled || el.readOnly || ['hidden','button'].includes(el.type) && el.getAttribute('role') !== 'combobox') continue;
      if(el.type !== 'file' && !visible(el)) continue;
      if(el.type === 'file' && !visible(el) && !visible(el.closest(adapter.container) || el)) continue;
      if(el.type === 'radio' && (!el.name || radioNames.has(radios(el)[0]))) continue;
      if(el.type === 'radio') radioNames.add(radios(el)[0]);
      if(el.type==='checkbox'){const first=checks(el)[0];if(radioNames.has(first))continue;radioNames.add(first);}
      let text = label(el, adapter), type = el.getAttribute('role') === 'combobox' ? 'combobox' : el.tagName === 'TEXTAREA' ? 'textarea' : el.tagName === 'SELECT' ? 'select' : el.type;
      text=question(el,adapter);
      const choices=options(el,adapter);
      const entry=entryGroup(el,adapter),groupEl=entry?.el,kind=entry?.kind;
      if(groupEl&&!groups.includes(groupEl))groups.push(groupEl);
      const group=groupEl?{kind,index:groups.indexOf(groupEl)}:null;
      if(group) {
        const controls=[...groupEl.querySelectorAll(controlSelector)].filter(o=>logicalControl(o,adapter)===o);
        group.id=String(nodeId(groupEl));
        group.identity=current(controls.find(o=>/^(company|company name|employer|employer name|school|school name|university|institution|college)$/.test(C.normalize(label(o,adapter))))||{value:''});
        group.role=current(controls.find(o=>/^(title|job title|role|position)$/.test(C.normalize(label(o,adapter))))||{value:''});
      }
      const id = 'field-' + fields.length;
      const consent=type==='checkbox'&&choices.length===1&&C.privacyConsent(text);
      const excluded = C.manual.test(text)&&!consent || type==='password' || (type==='checkbox'&&!el.closest('fieldset,[role="group"]')&&!consent) || (type==='radio' && new Set(radios(el).map(o=>o.closest('fieldset,[role="radiogroup"]'))).size>1);
      const helper=helperText(el,adapter),constraintText=text+' '+helper;
      const wordMatch=constraintText.match(/(?:max(?:imum)?(?: of)?|up to|no more than|limit(?: of)?)\s*(\d+)\s*words|\b(\d+)\s*words?\s*(?:max(?:imum)?|limit)/i);
      const field = {...subjectContext(el,adapter),id,label:text,helper,name:el.name||el.id,type,options:choices,group,current:current(el),excluded,required:el.required||el.getAttribute('aria-required')==='true'||/[*✱]\s*$/.test(text),limit:el.maxLength>0 ? el.maxLength:null,
        multiple:el.tagName==='SELECT'?el.multiple:type==='checkbox'&&choices.length>1,wordLimit:wordMatch?Number(wordMatch[1]||wordMatch[2]):null};
      if(field.subject!=='applicant'){field.excluded=true;field.manualReason='Third-party or uncertain subject: complete this field manually.';}
      if(type==='file'&&field.current)field.uploadAcknowledged=uploadState({el,uploadWrapper:el.closest(adapter.container)},adapter,field.current)==='accepted';
      // Lever's location widget has a separate committed location token. Plain
      // text retention cannot establish a selected place for this widget.
      if(platform==='lever'&&el.matches('input.location-input')&&el.closest('.application-field')?.querySelector('input[name="selectedLocation"]')){
        field.excluded=true;field.manualReason='Choose a location suggestion on the page. This widget requires a committed place, not just typed text.';
      }
      const key=JSON.stringify([field.label,field.name,field.type,group?.kind,group?.index]);field.occurrence=occurrences.get(key)||0;occurrences.set(key,field.occurrence+1);
      fields.push(field); mapping.set(id,{el,field,fingerprint:fingerprint(el,adapter),groupIdentity:groupIdentity(el,adapter),groupEl});
      const prior=fields[fields.length-2],priorRecord=mapping.get(prior?.id);
      const yesFollowup=/^if (?:you (?:have )?answered )?["“']?yes\b/i.test(text),otherFollowup=/^if you selected ["“']?other\b/i.test(text);
      if((yesFollowup||otherFollowup)&&priorRecord&&priorRecord.el.form===el.form&&['select','radio','combobox'].includes(prior.type)){
        field.condition={parentId:prior.id,when:otherFollowup?'other':'yes',...(/if\s+(?:you (?:have )?answered\s+)?["“']?no["”']?[, ]+(?:please )?(?:enter|write|type|list)\s+["“']?n\/?a\b/i.test(text)?{noValue:'N/A'}:{})};field.notApplicable=notApplicable(mapping.get(id));field.conditionalValue=conditionalValue(mapping.get(id));
      }
    }
    for(const record of mapping.values())if(record.groupEl)record.groupOrder=groupOrder(adapter);
    const heading = document.querySelector(adapter.title)?.innerText || document.title;
    const company=companyName(heading);snapshotCompany=company;

    const description = document.querySelector(adapter.description)?.innerText || '';
    const mapped=new Set([...mapping.values()].flatMap(r=>[r.el,...(r.el.type==='radio'?radios(r.el):r.el.type==='checkbox'?checks(r.el):[])]));
    const unsupported=[...document.querySelectorAll('[contenteditable="true"],[role="textbox"],[role="combobox"],[role="checkbox"],[role="radio"],select,input,textarea')]
      .filter(el=>visible(el)&&!el.disabled&&!el.readOnly&&!actionControl(el)&&!['hidden','button'].includes(el.type)&&!mapped.has(logicalControl(el,adapter)))
      .map(el=>({label:label(el,adapter)||el.getAttribute('aria-label')||'Unrecognized visible control',type:el.getAttribute('role')||el.type||el.tagName}));
    return {version,supported:true,platform,postingKey:C.postingKey(location.href),url:location.href,scanId,title:heading,company:company.slice(0,300),description:description.slice(0,30000),fields,unsupported};
  }
  const pause = ms => new Promise(resolve => setTimeout(resolve,ms));
  function setValue(el, value) {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);
    el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true}));
  }
  function failure(code,message){return Object.assign(new Error(message),{code});}
  async function waitFor(check,timeout=4000) {
    const deadline=Date.now()+timeout;
    do {if(check())return true;await pause(100);}while(Date.now()<deadline);
    return false;
  }
  function groupOrder(adapter) {
    const groups=[];
    for(const el of document.querySelectorAll(controlSelector)){
      if(logicalControl(el,adapter)!==el||el.type==='hidden'||!visible(el))continue;
      const group=entryGroup(el,adapter)?.el;
      if(group&&!groups.includes(group))groups.push(group);
    }
    return groups.map(nodeId).join(',');
  }
  function sameGroup(record,adapter) {
    return record.groupEl?.isConnected&&entryGroup(record.el,adapter)?.el===record.groupEl&&groupOrder(adapter)===record.groupOrder;
  }
  function rebind(record,adapter) {
    if(record.el.isConnected)return record.el;
    const matches=[...document.querySelectorAll('input,select,textarea,button[role="combobox"]')].filter(o=>visible(o)&&fingerprint(o,adapter)===record.fingerprint&&(!record.groupEl||entryGroup(o,adapter)?.el===record.groupEl&&groupOrder(adapter)===record.groupOrder)&&groupIdentity(o,adapter,record.field.current)===record.groupIdentity&&(current(o)===record.field.current||searches.get(record.el)?.query===o.value));
    if(matches.length!==1)throw failure('control_replaced','Control replaced without a unique unchanged match. Scan again.');
    const previous=searches.get(record.el);record.el=matches[0];if(previous)searches.set(record.el,previous);
    return record.el;
  }
  function optionList(el,adapter) {
    const ids=(el.getAttribute('aria-controls')||el.getAttribute('aria-owns')||'').split(/\s+/).filter(Boolean);
    let lists=ids.map(id=>document.getElementById(id)).filter(Boolean);
    if(!lists.length){const active=document.getElementById(el.getAttribute('aria-activedescendant'));const list=active?.closest('[role="listbox"]');if(list)lists=[list];}
    if(!lists.length&&el.id){lists=[...document.querySelectorAll('[role="listbox"]')].filter(list=>(list.getAttribute('aria-labelledby')||'').split(/\s+/).includes(el.id));}
    if(!lists.length){const wrapper=el.closest(adapter.container);lists=wrapper&&wrapper.querySelectorAll('[role="combobox"]').length===1?[...wrapper.querySelectorAll('[role="listbox"]')].filter(visible):[];}
    return lists.length===1?lists[0]:null;
  }
  function menuOptions(list){return [...list.querySelectorAll('[role="option"]')].filter(visible);}
  function menuChoices(list){return menuOptions(list).map(o=>({label:o.innerText.trim(),value:o.innerText.trim(),disabled:o.getAttribute('aria-disabled')==='true'||o.disabled===true,node:o}));}
  function openMenu(el,adapter){if(el.getAttribute('aria-expanded')!=='true'&&!visible(optionList(el,adapter)))activate(el);}
  function searchText(el,query,previous){searches.set(el,{query,previous,revision:userRevision});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,query);el.dispatchEvent(new Event('input',{bubbles:true}));}
  function closeMenu(el){el.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));el.blur();}
  async function choices(input) {
    const id=typeof input==='string'?input:input.id,query=typeof input==='string'?'':String(input.query||'').trim();
    if(query.length>300)throw new Error('Search text is too long.');
    const record=mapping.get(id),adapter=adapters[C.platform(location.href)];
    if(!record||record.field.type!=='combobox')throw new Error('Scan this dropdown again.');
    assertFresh(record,adapter);record.stage='opening';
    const previousInput=record.el.value,revision=userRevision;
    try{
      openMenu(record.el,adapter);
      if(query){if(record.el.tagName!=='INPUT')throw new Error('This dropdown does not support text search.');searchText(record.el,query,record.field.current);}
      let list;
      const loaded=await waitFor(()=>{rebind(record,adapter);assertFresh(record,adapter);if(userRevision!==revision||!query&&record.el.value!==previousInput)throw failure('context_changed','Page changed while loading choices. Your edit was preserved.');list=optionList(record.el,adapter);return list&&visible(list)&&list.getAttribute('aria-busy')!=='true'&&menuOptions(list).length;});
      if(!loaded)throw failure('option_timeout','No choices loaded. Use the dropdown on the page to search, then rescan.');
      return menuChoices(list).map(({node,...choice})=>choice);
    }finally{
      const el=record.el,pending=searches.get(el);
      if(pending){
        const safe=el.isConnected&&el.value===query&&pending.revision===userRevision&&location.href===snapshotURL&&companyName()===snapshotCompany&&fingerprint(el,adapter)===record.fingerprint&&groupIdentity(el,adapter)===record.groupIdentity;
        searches.delete(el);
        if(safe){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,previousInput);el.dispatchEvent(new Event('input',{bubbles:true}));}
        else if(record.field.group)for(const other of mapping.values())if(other.field.group?.id===record.field.group.id)other.uncertain=true;
      }
      if(userRevision===revision&&(!el.value||el.value===previousInput))closeMenu(el);
    }
  }
  async function dropdown(record,change,adapter) {
    let el=record.el;const previous=current(el),previousInput=el.value,revision=userRevision;
    const queries=C.dropdownQueries(change);
    let last={code:'list_missing',reason:'Associated dropdown list not found.'},clicked=false;
    try {
      record.stage='opening';openMenu(el,adapter);el=rebind(record,adapter);
      // Inspect loaded choices first. Searching a non-searchable select can hide
      // good choices and must never be used as evidence of a committed selection.
      for(const query of [null,...(el.tagName==='INPUT'?queries:[])]) {
        assertFresh(record,adapter);
        if(query!==null)searchText(el,query,previous);
        const raw=el.value;record.stage='option_loading';const deadline=Date.now()+4000;
        while(Date.now()<deadline){
          await pause(100);el=rebind(record,adapter);assertFresh(record,adapter);
          if(userRevision!==revision||el.value!==raw)throw failure('context_changed','Page changed while waiting. Your edit was preserved.');
          const list=optionList(el,adapter);
          if(!list||!visible(list))continue;
          if(list.getAttribute('aria-busy')==='true'){last={code:'option_timeout',reason:'Dropdown results timed out.'};continue;}
          const choices=menuChoices(list),matched=C.matchChoice({...record.field,options:choices},change);
          if(matched.code==='option_ambiguous')throw failure(matched.code,matched.reason);
          last=matched;
          if(matched.option){
            const chosen=matched.option.label;record.stage='selection';clicked=true;
            // An input value is sufficient only with a selection event from the
            // option interaction. A query, highlight or inert click is not one.
            let selectionEvent=false;
            const changed=e=>{if(e.target===record.el)selectionEvent=true;};
            document.addEventListener('change',changed,true);
            record.stopSelectionWatch=()=>document.removeEventListener('change',changed,true);
            searches.delete(el);
            activate(matched.option.node);
            if(!el.isConnected)el=rebind(record,adapter);
            const selectedToken=()=>{
              const control=record.el,display=control.closest(adapter.container)?.querySelectorAll('.select__single-value,[class$="-singleValue"],[data-selected-value]');
              return display?.length===1?displayValue(control,display[0]):control.tagName==='BUTTON'?control.innerText.trim():selectionEvent?control.value:'';
            };
            record.restoreSearch=()=>{
              const control=record.el;
              if(query!==null&&!selectionEvent&&(!selectedToken()||selectedToken()===previous)&&control.isConnected&&control.value===query&&userRevision===revision&&location.href===snapshotURL&&companyName()===snapshotCompany&&fingerprint(control,adapter)===record.fingerprint&&groupIdentity(control,adapter,previous)===record.groupIdentity){
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(control,previousInput);
                control.dispatchEvent(new Event('input',{bubbles:true}));closeMenu(control);
              }
            };
            return ()=>{
              const control=record.el;
              return userRevision===revision&&control.isConnected&&C.normalize(selectedToken())===C.normalize(chosen)&&control.getAttribute('aria-expanded')!=='true'&&!visible(optionList(control,adapter));
            };
          }
          // Async school catalogs can show an old empty/unrelated result while
          // the next search loads, without exposing aria-busy. Give each search
          // its bounded window; matching still requires the full institution.
          if((query===null||change.matchRule?.kind!=='institution')&&
             (choices.length||/no (?:options|results)|not found/i.test(list.textContent)))break;
        }
      }
      throw failure(last.code||'option_missing',last.reason||'Matching choice unavailable.');
    } finally {
      const pending=searches.get(el);
      const safe=el.isConnected&&pending&&el.value===pending.query&&pending.revision===userRevision&&location.href===snapshotURL&&companyName()===snapshotCompany&&fingerprint(el,adapter)===record.fingerprint&&groupIdentity(el,adapter)===record.groupIdentity;
      if(!clicked&&pending&&!safe&&record.field.group)for(const other of mapping.values())if(other.field.group?.id===record.field.group.id)other.uncertain=true;
      if(!clicked&&safe){
        searches.delete(el);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,previousInput);
        el.dispatchEvent(new Event('input',{bubbles:true}));closeMenu(el);
      }
      searches.delete(el);
    }
  }
  function uploadState(record,adapter,name) {
    const wrapper=record.uploadWrapper;
    if(location.href!==snapshotURL||companyName()!==snapshotCompany||!wrapper?.isConnected)return 'unknown';
    const errors=[...wrapper.querySelectorAll('[role="alert"],.error,.field-error,[aria-invalid="true"],'+adapter.uploadError)].filter(visible);
    if(errors.some(e=>e.textContent.trim()||e.getAttribute('aria-invalid')==='true'))return 'error';
    if([...wrapper.querySelectorAll('[aria-busy="true"],[role="progressbar"],'+adapter.uploadBusy)].some(visible))return 'pending';
    const receipt=[...wrapper.querySelectorAll('span,a,p,div')].some(e=>visible(e)&&e.childElementCount===0&&e.textContent.trim()===name);
    const input=record.el;
    const selected=input.isConnected&&input.files?.length===1&&input.files[0].name===name;
    const remove=[...wrapper.querySelectorAll('button,[role="button"]')].some(e=>visible(e)&&/^(?:remove|delete)(?: file| attachment| resume)?$/i.test(e.getAttribute('aria-label')||e.textContent.trim()));
    return receipt&&(selected||remove)?'accepted':selected?'selected':'unknown';
  }
  function samePhone(actual,expected,country) {
    if(!/^[+\d\s().-]+$/.test(actual)||!/^[+\d\s().-]+$/.test(expected))return false;
    let a=actual.replace(/\D/g,''),b=expected.replace(/\D/g,'');
    if(a===b)return !!a;
    if(country==='US'){if(a.length===11&&a[0]==='1')a=a.slice(1);if(b.length===11&&b[0]==='1')b=b.slice(1);return a.length===10&&a===b;}
    return false;
  }
  async function apply(request) {
    if(request.scanId !== scanId || request.url !== location.href || snapshotURL !== location.href) throw new Error('Application changed. Scan and review again.');
    const adapter = adapters[C.platform(location.href)];
    if(!adapter) throw new Error('Unsupported application page.');
    const results = [],retained=[],initialUserRevision=userRevision;
    // Country selections may reset phone controls. Complete them first.
    const isCountry=id=>{const field=mapping.get(id)?.field;return field&&(field.name==='country'||C.normalize(field.label)==='country');};
    const priority=id=>isCountry(id)?2:schoolLabel.test(C.normalize(mapping.get(id)?.field.label))?1:0;
    const ordered=[...request.changes].sort((a,b)=>priority(b.id)-priority(a.id));
    for(const change of ordered) {
      const record = mapping.get(change.id);
      try {
        if(!record) throw new Error('Field no longer exists. Scan again.');
        if(userRevision!==initialUserRevision)throw failure('context_changed','User activity detected. Preparation paused; review before continuing.');
        record.stage='discovery';let {el,field} = record;
        assertFresh(record,adapter);
        if(field.condition?.noValue&&change.value===field.condition.noValue&&conditionalValue(record)!==change.value)throw failure('context_changed','Conditional parent answer changed. Rescan before filling.');
        if(notApplicable(record)){results.push({id:change.id,status:'not applicable',code:'not_applicable',message:'Explanation is not required for the selected No answer.'});continue;}
        if(current(el) && !change.replace) {results.push({id:change.id,status:'skipped',message:'Existing value preserved.'});continue;}
        const previous=current(el);
        if(field.limit && change.value.length>field.limit) throw new Error('Answer exceeds the character limit.');
        let expected = change.value, verify = () => current(record.el)===expected, acknowledgement = true;
        record.stage='selection';
        if(field.type==='checkbox'&&C.privacyConsent(field.label)) {
          const consent=C.privacyConsent(question(el,adapter));
          if(!consent||!request.automation?.[consent]||change.checked!==true)throw new Error('Privacy consent is not authorized or wording changed.');
          if(!el.checked)interact(()=>el.click());
          expected=el.value;verify=()=>record.el.checked&&C.privacyConsent(question(record.el,adapter))===consent&&fingerprint(record.el,adapter)===record.fingerprint;
        } else if(field.type === 'file') {
          if(!request.pdf || !/resume|résumé|\bcv\b/i.test(field.label+' '+field.name)) throw new Error('Manual upload required.');
          if(el.accept && !/pdf|application\/\*|\.\*/i.test(el.accept)) throw new Error('This field does not advertise PDF support. Upload manually.');
          record.uploadWrapper=el.closest(adapter.container);record.stage='upload_acknowledgement';
          const bytes = Uint8Array.from(atob(request.pdf.base64), c=>c.charCodeAt(0));
          const transfer = new DataTransfer(); transfer.items.add(new File([bytes],request.pdf.name,{type:'application/pdf'})); el.files=transfer.files;
          el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('input',{bubbles:true}));
          expected=request.pdf.name;
          await waitFor(()=>['accepted','error'].includes(uploadState(record,adapter,expected)),6000);
          if(uploadState(record,adapter,expected)==='error')throw failure('upload_error','The portal reported an upload error. Attach the resume manually.');
          acknowledgement=uploadState(record,adapter,expected)==='accepted';
          verify=()=>uploadState(record,adapter,expected)==='accepted';
          if(!acknowledgement){results.push({id:change.id,status:'needs review',code:'upload_unconfirmed',message:'Upload acknowledgement missing. Check the attachment or upload manually.'});continue;}
        } else if(field.multiple) {
          const matched=C.matchChoice(field,change);if(!matched.options)throw failure(matched.code||'unsupported',matched.reason||'An explicit set of answers is required.');
          const wanted=new Set(matched.options.map(o=>o.value));
          if(field.type==='checkbox'){for(const box of checks(el)){if(box.checked!==wanted.has(box.value))interact(()=>box.click());}}
          else if(field.type==='select'){for(const option of el.options)option.selected=wanted.has(option.value);el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('input',{bubbles:true}));}
          else throw failure('unsupported','This multiselect control needs manual handling.');
          verify=()=>{const actual=field.type==='checkbox'?checks(record.el).filter(o=>o.checked).map(o=>o.value):[...record.el.selectedOptions].map(o=>o.value);return actual.length===wanted.size&&actual.every(v=>wanted.has(v));};
        } else if(field.type === 'select' || field.type === 'radio' || field.type==='checkbox') {
          const matched=C.matchChoice(field,change);if(!matched.option)throw failure(matched.code,matched.reason);const selected=matched.option;expected=selected.value;
          if(field.type === 'select') setValue(el,expected);
          else if(field.type==='checkbox'){for(const box of checks(el)){const wanted=box.value===expected;if(box.checked!==wanted)interact(()=>box.click());}}
          else {const radio=radios(el).find(e=>e.value===expected); if(!radio || radio.disabled) throw new Error('Option changed.'); interact(()=>radio.click());}
        } else if(field.type === 'combobox') {
          verify=await dropdown(record,change,adapter);el=record.el;
        } else {setValue(el,change.value);if(field.type==='tel'||/^(phone|phone number|mobile phone)$/.test(C.normalize(field.label)))verify=()=>samePhone(current(record.el),expected,request.phoneCountry);}
        record.stage=field.type==='file'?'upload_acknowledgement':'retention';
        if(!await waitFor(()=>{if(field.type!=='file'&&!record.el.isConnected)el=rebind(record,adapter);return verify();}))throw failure('rejected','The page did not retain the value. Review manually.');
        for(let stable=0;stable<3;stable++){await pause(150);if(field.type!=='file'&&!record.el.isConnected)el=rebind(record,adapter);if(!verify())throw failure('rejected','The page changed the value. Review manually; no automatic retry.');}
        if(field.type!=='file'&&(!el.isConnected || el.getAttribute('aria-invalid')==='true' || (el.validity && !el.validity.valid))) throw failure('rejected','The page did not retain or accept the value. Review manually.');
        if(field.type!=='file')assertFresh(record,adapter,current(el));
        undoLog.push({el,previous,written:current(el),fingerprint:record.fingerprint,adapter,type:field.type});
        field.current=current(el);
        const previousGroup=record.groupIdentity;
        for(const other of mapping.values()){
          if(field.group&&other.field.group?.id===field.group.id&&other.groupIdentity===previousGroup){other.groupIdentity=groupIdentity(el,adapter);if(schoolLabel.test(C.normalize(field.label)))other.field.group.identity=current(el);}
          if(!other.el.isConnected){try{rebind(other,adapter);}catch(_){/* Ambiguous replacements remain stale. */}}
        }
        retained.push({record,verify,expected:current(el)});
        results.push({id:change.id,status:acknowledgement?'filled':'needs review',message:acknowledgement?'Value retained; review before submitting.':'File selected, but portal acknowledgement was not detected. Check the upload or attach manually.'});
      } catch(error) {record?.restoreSearch?.();results.push({id:change.id,status:'failed',message:error.message,code:error.code,stage:record?.stage||'discovery'});}
      finally {if(record){record.stopSelectionWatch?.();delete record.stopSelectionWatch;delete record.restoreSearch;}}
    }
    await pause(request.settleMs===5000?5000:300);
    for(const {record,verify,expected} of retained){
      const result=results.find(r=>r.id===record.field.id);
      try {if(record.field.type!=='file')assertFresh(record,adapter,expected);if(!verify()||record.el.getAttribute('aria-invalid')==='true'||record.el.validity&&!record.el.validity.valid)throw new Error('Value not retained');}
      catch(_){result.status='failed';result.code='rejected';result.stage='retention';result.message='Value was changed or rejected later in this attempt. Review and rescan.';}
    }
    // Discover conditional additions without invalidating the caller's scan or
    // expanding its selection. A subsequent panel scan makes them reviewable.
    if(request.discoverNew){
      const previousMapping=mapping,previousScan=scanId,previousURL=snapshotURL,previousCompany=snapshotCompany;
      const knownElements=new Map([...mapping.values()].map(r=>[r.el,r.fingerprint]));
      const known=new Map();for(const r of mapping.values())known.set(r.fingerprint,(known.get(r.fingerprint)||0)+1);
      try{scan();for(const record of mapping.values()){if(knownElements.has(record.el)){const old=knownElements.get(record.el);known.set(old,Math.max(0,(known.get(old)||0)-1));continue;}const remaining=known.get(record.fingerprint)||0;if(remaining){known.set(record.fingerprint,remaining-1);continue;}
        const field=record.field;results.push({id:'new-'+field.id,status:'unanswered',newField:true,message:'Newly revealed field; review before selecting.',diagnostic:{label:field.label,name:field.name||'unnamed',type:field.type,section:field.section||(field.group?field.group.kind+':'+field.group.index:'application'),status:'unanswered',code:'unanswered',stage:'final',occurrence:field.occurrence||0}});
      }}finally{mapping=previousMapping;scanId=previousScan;snapshotURL=previousURL;snapshotCompany=previousCompany;}
    }
    for(const item of request.accounting||[])if(mapping.has(item.id)&&!results.some(r=>r.id===item.id)){
      const record=mapping.get(item.id),na=notApplicable(record);
      const changed=item.status==='skipped'&&(!record.el.isConnected||current(record.el)!==record.field.current);
      results.push({...item,...(changed?{status:'invalidated',code:'context_changed',stage:'retention'}:na?{status:'not applicable',code:'not_applicable'}:{}),message:changed?'The page changed an existing value during this attempt. Review this field; it was not refilled.':na?'Explanation is not required for the selected No answer.':item.status==='invalidated'?'Saved answer changed; scan again before filling.':'Not selected for this attempt.'});
    }
    for(const result of results){
      const field=mapping.get(result.id)?.field;
      if(!field)continue;
      const code=result.code||(result.status==='filled'?'retained':result.status==='skipped'?'preserved':result.status==='needs review'?'upload_unconfirmed':/page changed the value|retain|accept/i.test(result.message)?'rejected':/changed|exists|scan again/i.test(result.message)?'stale':/Manual-only/i.test(result.message)?'manual':/option|dropdown/i.test(result.message)?'option_missing':/retain|accept|value/i.test(result.message)?'rejected':'fill_failed');
      result.diagnostic={label:field.label,name:field.name||'unnamed',type:field.type,section:field.section||(field.group?field.group.kind+':'+field.group.index:'application'),status:result.status,code,stage:result.stage||'final',control_family:field.type==='combobox'?'custom_select':field.type==='file'?'upload':field.type==='tel'?'phone':'native',occurrence:field.occurrence||0};
    }
    return results;
  }
  function focus(id) {const el=mapping.get(id)?.el;if(!el?.isConnected)throw new Error('Scan the page again.');el.scrollIntoView({block:'center',behavior:'smooth'});el.focus();return true;}
  async function undo() {
    const results=[];
    for(const entry of undoLog.splice(0).reverse()) {
      const {el,previous,written,adapter,type}=entry;
      if(type==='file'||type==='combobox'||type==='checkbox'){results.push({status:'manual',message:'Remove uploads or restore custom dropdowns manually.'});continue;}
      if(!el.isConnected || current(el)!==written || fingerprint(el,adapter)!==entry.fingerprint || el.disabled || el.readOnly){results.push({status:'skipped',message:'Field changed after filling; preserved.'});continue;}
      if(type==='radio'){radios(el).forEach(o=>{o.checked=o.value===previous;o.dispatchEvent(new Event('change',{bubbles:true}));});}else setValue(el,previous);
      results.push({status:'restored'});
    }
    return results;
  }
  globalThis.ApplicationAutofill={version,scan,apply,focus,undo,choices,context:()=>({version,url:location.href,company:companyName(),scanId,fields:[...mapping.values()].map(r=>({...r.field,...subjectContext(r.el,adapters[C.platform(location.href)]),notApplicable:notApplicable(r),conditionalValue:conditionalValue(r)}))})};
})();
