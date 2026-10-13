/* Synthetic reproductions of observed Greenhouse flyout, phone and upload behavior. */
(async()=>{
 const check=(v,m)=>{if(!v)throw Error(m);},form=document.querySelector('form');let submits=0,scan;
 CopilotCore.platform=()=> 'greenhouse';form.onsubmit=e=>{e.preventDefault();submits++;};
 const field=id=>scan.fields.find(f=>f.name===id);
 const run=changes=>ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,changes,pdf:{name:'Fixture.pdf',base64:btoa('%PDF fixture')}});
 const reset=html=>{form.innerHTML=html;document.querySelectorAll('.portal-menu').forEach(e=>e.remove());};
 function combo(id,labels,{delay=100,edit=false}={}){
   const box=document.createElement('div');box.className='select-shell';box.innerHTML=`<label for="${id}">${id}</label><div class="select__control"><span class="select__single-value"></span><input id="${id}" role="combobox" aria-expanded="false"><button type="button" aria-label="Toggle flyout">Open</button></div>`;form.append(box);
   const el=box.querySelector('input'),display=box.querySelector('span');let opened=false;
   const close=()=>{el.setAttribute('aria-expanded','false');document.getElementById(id+'-list')?.remove();};
   const open=()=>{if(opened)return;opened=true;el.focus();el.setAttribute('aria-expanded','true');setTimeout(()=>{
     if(edit){el.value='User search';return;}
     const list=document.createElement('div');list.id=id+'-list';list.className='portal-menu';list.setAttribute('role','listbox');el.setAttribute('aria-controls',list.id);
     for(const label of labels){const option=document.createElement('div');option.setAttribute('role','option');option.textContent=label;option.onclick=()=>{display.textContent=label;el.value='';close();};list.append(option);}document.body.append(list);
   },delay);};
   box.querySelector('.select__control').onmousedown=open;
   el.onkeydown=e=>{if(e.key==='Escape')close();};
   return el;
 }
 try{
   reset('<fieldset><legend>Applicant information</legend><label>Email<input id="app-email"></label></fieldset><fieldset><legend>References</legend><label>Email<input id="ref-email"></label></fieldset><section><h3>Emergency contact</h3><label>Full name<input id="emergency-name"></label></section>');
   scan=ApplicationAutofill.scan();
   check(field('app-email').subject==='applicant'&&!field('app-email').excluded,'Clearly identified applicant stays eligible');
   check(field('ref-email').subject==='third_party'&&field('emergency-name').excluded,'References and emergency contacts stay manual');
   let subjectResults=await run([{id:field('app-email').id,value:'applicant@example.test'},{id:field('ref-email').id,value:'wrong@example.test'}]);
   check(document.getElementById('app-email').value==='applicant@example.test'&&!document.getElementById('ref-email').value,'Applicant fills without leaking into reference');
   reset('<section><h3>Applicant information</h3><label>Email<input id="section-change"></label></section>');scan=ApplicationAutofill.scan();form.querySelector('h3').textContent='Emergency contact';
   subjectResults=await run([{id:field('section-change').id,value:'wrong@example.test'}]);check(!document.getElementById('section-change').value,'Changed section blocks stale fill');
   reset('<label>Email<input id="repeat-a"></label><label>Email<input id="repeat-b"></label>');scan=ApplicationAutofill.scan();check(scan.fields.every(f=>f.subject==='uncertain'&&f.excluded),'Ambiguous repeated identity stays unresolved');
   reset('');let el=combo('Degree',["Bachelor's Degree",'Masters']);scan=ApplicationAutofill.scan();
   let result=await run([{id:field('Degree').id,value:'Bachelor of Science',alternatives:["Bachelor's Degree"]}]);
   check(result[0].status==='filled','Mousedown flyout with external menu must commit: '+JSON.stringify(result));
   check(el.value===''&&el.previousElementSibling.textContent==="Bachelor's Degree",'Selection is committed separately from search text');
   // IEX React Select describes the input with a placeholder that disappears
   // during search. It is presentation, while adjacent instructions are stable.
   reset('');el=combo('School',[]);
   const placeholder=document.createElement('div');placeholder.id='react-select-School-placeholder';placeholder.className='select__placeholder';placeholder.textContent='Select...';el.before(placeholder);
   const schoolHelp=document.createElement('p');schoolHelp.id='school-help';schoolHelp.textContent='Choose your university';el.after(schoolHelp);el.setAttribute('aria-describedby',placeholder.id+' '+schoolHelp.id);
   el.oninput=()=>{placeholder.remove();const list=document.getElementById('School-list');if(!list)return;list.replaceChildren();if(el.value==='Example University'){const option=document.createElement('div');option.setAttribute('role','option');option.textContent='Example University';option.onclick=()=>{el.closest('.select-shell').querySelector('.select__single-value').textContent=option.textContent;el.value='';el.setAttribute('aria-expanded','false');list.remove();};list.append(option);}else list.textContent='No options';};
   scan=ApplicationAutofill.scan();
   result=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,discoverNew:true,changes:[{id:field('School').id,value:'University of Example',alternatives:['Example University']}]});
   check(result.length===1&&result[0].status==='filled','Transient described placeholder must not stale search or duplicate diagnostics: '+JSON.stringify(result));
   scan=ApplicationAutofill.scan();check(field('School').helper==='Choose your university','Actual instructions remain in the scanned question');
   schoolHelp.textContent='Choose only an accredited university';
   result=await run([{id:field('School').id,value:'Example University'}]);check(result[0].status==='failed','Changed select instructions still invalidate a fill');
   reset('');el=combo('School',['Berkeley College','University of California - Berkeley','University of California - Los Angeles']);scan=ApplicationAutofill.scan();
   result=await run([{id:field('School').id,value:'University of California, Berkeley',matchRule:{kind:'institution'}}]);
   check(result[0].status==='filled'&&el.previousElementSibling.textContent==='University of California - Berkeley','Portal school punctuation is matched and committed, not left as a search');
   // The real catalog does not find comma-form names. It also retains old
   // results briefly while a new query loads, without aria-busy.
   reset('');el=combo('School',['Berkeley College']);const schoolInput=el;let queryGeneration=0;const schoolQueries=[];
   el.oninput=()=>{const query=schoolInput.value,ticket=++queryGeneration;schoolQueries.push(query);setTimeout(()=>{
     if(ticket!==queryGeneration)return;const list=document.getElementById('School-list');if(!list)return;list.replaceChildren();
     if(query!=='University of California - Berkeley'){list.textContent='No options';return;}
     const option=document.createElement('div');option.setAttribute('role','option');option.textContent='University of California - Berkeley';
     option.onclick=()=>{schoolInput.previousElementSibling.textContent=option.textContent;schoolInput.value='';schoolInput.setAttribute('aria-expanded','false');list.remove();};list.append(option);
   },500);};
   scan=ApplicationAutofill.scan();
   result=await run([{id:field('School').id,value:'University of California, Berkeley',alternatives:['UC Berkeley','University of California Berkeley'],matchRule:{kind:'institution'}}]);
   check(result[0].status==='filled'&&schoolInput.previousElementSibling.textContent==='University of California - Berkeley','Search typography and delayed replacement results must work together: '+JSON.stringify(result));
   check(schoolQueries.includes('University of California - Berkeley')&&!schoolQueries.includes('Berkeley'),'Full school name search only; a campus fragment is not an authorized alternative');
   reset('');el=combo('School',['UC Berkeley'],{delay:1800});scan=ApplicationAutofill.scan();
   result=await run([{id:field('School').id,value:'UC Berkeley'}]);check(result[0].status==='filled','Delayed results beyond old 1.5s timeout');
   reset('');el=combo('School',['UC Berkeley','UC Berkeley']);scan=ApplicationAutofill.scan();
   result=await run([{id:field('School').id,value:'UC Berkeley'}]);check(result[0].code==='option_ambiguous','Duplicate compatible choices stay unresolved');
   reset('');el=combo('School',['UC Berkeley'],{edit:true});scan=ApplicationAutofill.scan();
   result=await run([{id:field('School').id,value:'UC Berkeley'}]);check(result[0].status==='failed'&&el.value==='User search','Concurrent user search preserved');
   reset('');el=combo('Choice',['Yes','No']);scan=ApplicationAutofill.scan();
   const choices=await ApplicationAutofill.choices(field('Choice').id);
   check(choices.map(o=>o.label).join(',')==='Yes,No'&&el.previousElementSibling.textContent==='','Inspect real choices without selecting');
   check(el.getAttribute('aria-expanded')==='false','Choice inspection closes menu');
   reset('');el=combo('School',['UC Berkeley']);scan=ApplicationAutofill.scan();
   const searched=await ApplicationAutofill.choices({id:field('School').id,query:'Berkeley'});
   check(searched[0].label==='UC Berkeley'&&el.value===''&&el.previousElementSibling.textContent==='','Panel search returns choices and restores its temporary input');
   // Loaded and already-open menus must not be toggled or searched first.
   reset('');el=combo('Degree',["Bachelors","Bachelor's Degree"]);let toggles=0,typed=0;
   const opener=el.parentElement.onmousedown;el.parentElement.onmousedown=()=>{toggles++;opener();};el.oninput=()=>typed++;
   el.parentElement.onmousedown();await new Promise(r=>setTimeout(r,150));scan=ApplicationAutofill.scan();
   result=await run([{id:field('Degree').id,value:'Bachelor of Science',alternatives:["Bachelor's Degree",'Bachelors'],matchRule:{kind:'degree'}}]);
   check(result[0].status==='filled'&&el.previousElementSibling.textContent==="Bachelor's Degree"&&toggles===1&&typed===0,'Open menu inspected without toggling or searching; ranked degree wins');
   reset('');el=combo('Degree',["Bachelor's Degree","Bachelor's Degree"]);scan=ApplicationAutofill.scan();
   result=await run([{id:field('Degree').id,value:'Bachelor of Science',alternatives:["Bachelor's Degree"],matchRule:{kind:'degree'}}]);check(result[0].code==='option_ambiguous','Duplicate best bachelor choices unresolved');
   reset('');el=combo('Degree',['Bachelor of Science',"Bachelor's Degree"]);el.parentElement.onmousedown();await new Promise(r=>setTimeout(r,150));document.querySelector('[role="option"]').setAttribute('aria-disabled','true');scan=ApplicationAutofill.scan();
   result=await run([{id:field('Degree').id,value:'Bachelor of Science',alternatives:["Bachelor's Degree"],matchRule:{kind:'degree'}}]);check(result[0].status==='filled'&&el.previousElementSibling.textContent==="Bachelor's Degree",'Disabled exact degree is never selected');
   // An inert option must not turn typed query text into a selection.
   reset('<div class="field"><label for="inert">Choice</label><input id="inert" role="combobox" aria-controls="inert-menu"><div id="inert-menu" role="listbox" hidden></div></div>');
   el=document.getElementById('inert');el.oninput=()=>{const list=document.getElementById('inert-menu');list.hidden=false;list.innerHTML='<div role="option" aria-selected="true">Yes</div>';list.firstChild.onclick=()=>{list.hidden=true;el.setAttribute('aria-expanded','false');};};scan=ApplicationAutofill.scan();
   result=await run([{id:field('inert').id,value:'Yes'}]);check(result[0].code==='rejected'&&el.value==='','Typed text, highlight and a click without a selection event/token are rejected');
   // Country phone controls compress the selected label to flag + dial code.
   // +1 alone is ambiguous; the explicit US flag must remain present.
   for(const flag of ['us','ca','missing']){
     reset('');const country=combo('country',['United States +1']);
     // Observe the portal's post-selection display change.
     const display=country.previousElementSibling;
     const observer=new MutationObserver(()=>{if(display.textContent==='United States +1')display.innerHTML=(flag==='missing'?'':'<div class="iti__flag iti__'+flag+'"></div>')+'<span>+1</span>';});
     observer.observe(display,{childList:true});scan=ApplicationAutofill.scan();
     result=await run([{id:field('country').id,value:'United States +1'}]);observer.disconnect();
     check(result[0].status===(flag==='us'?'filled':'failed'),'Compressed country identity requires US flag: '+flag);
     if(flag==='us'){
       scan=ApplicationAutofill.scan();check(field('country').current==='United States +1','Country scan keeps exact retained identity');
       const later=document.createElement('input');later.id='later';later.setAttribute('aria-label','Later field');form.append(later);
       later.oninput=()=>display.querySelector('.iti__flag').className='iti__flag iti__ca';scan=ApplicationAutofill.scan();
       result=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,changes:[{id:field('later').id,value:'Example'}],accounting:[{id:field('country').id,status:'skipped',code:'preserved'}]});
       check(result.find(r=>r.id===field('country').id).code==='context_changed','Later country flag change is not preserved as US');
     }
   }
   // Live Greenhouse uses an outside aria label and an unnamed required input
   // directly under select-shell. It must not create a second education entry.
   reset('<section><h2>Education</h2><label id="school-label">School</label><div class="select-shell"><span class="select__single-value">Example University</span><input id="school" role="combobox" aria-labelledby="school-label"><input required tabindex="-1" aria-hidden="true"></div><label id="degree-label">Degree</label><div class="select-shell"><input id="degree" role="combobox" aria-labelledby="degree-label"><input required tabindex="-1" aria-hidden="true"></div><label>End date year<input id="year"></label></section>');
   scan=ApplicationAutofill.scan();
   check(scan.fields.length===3,'Outside labels: validation helpers are not application questions');
   check(field('school').group.id===field('degree').group.id&&field('degree').group.id===field('year').group.id,'Outside labels: education remains one entry');
   check(field('year').group.identity==='Example University','Outside labels: dependent date retains school identity');
   const helpers=[...form.querySelectorAll('[aria-hidden="true"]')];helpers.forEach(e=>e.remove());
   result=await run([{id:field('year').id,value:'2028'}]);
   check(result[0].status==='filled'&&document.getElementById('year').value==='2028','Validation helper removal does not stale graduation date');
   reset('<div class="select-shell"><input role="combobox" aria-label="Choice one"><input role="combobox" aria-label="Choice two"><input aria-hidden="true" tabindex="-1"></div><div class="select-shell"><input role="combobox" aria-label="Choice"><input aria-label="Separate answer" aria-hidden="true" tabindex="-1"></div>');
   scan=ApplicationAutofill.scan();check(scan.fields.length===5,'Ambiguous or separately labelled controls remain distinct');
   // Separate and repeated schools: never use ordinal matching or accept reordering.
   const education=()=>'<section data-education><div class="field"><label for="s1">School</label><input id="s1" role="combobox" value="One"><input type="text" aria-hidden="true"></div><label>Degree<input id="d1"></label></section><section data-education><label>School<input id="s2" value="Two"></label><label>Degree<input id="d2"></label></section>';
   reset(education());scan=ApplicationAutofill.scan();check(field('d1').group.identity==='One'&&field('d2').group.identity==='Two','Two schools have distinct identity');
   document.querySelector('[aria-hidden]').remove();result=await run([{id:field('d1').id,value:'First degree'},{id:field('d2').id,value:'Second degree'}]);check(result.every(r=>r.status==='filled'),'Helper removal leaves group identity stable');
   reset(education());document.getElementById('s2').value='One';scan=ApplicationAutofill.scan();const before=field('d1').group.id;form.prepend(form.lastElementChild);
   result=await run([{id:field('d1').id,value:'Wrong'}]);check(result[0].status==='failed'&&!document.getElementById('d1').value,'Repeated school reordering is stale even with identical names');
   reset(education());scan=ApplicationAutofill.scan();document.getElementById('s1').value='Changed';result=await run([{id:field('d1').id,value:'Wrong'}]);check(result[0].status==='failed','Changed school blocks dependents');
   reset(education());scan=ApplicationAutofill.scan();form.append(form.firstElementChild.cloneNode(true));result=await run([{id:field('d1').id,value:'Wrong'}]);check(result[0].status==='failed','Added duplicate entry blocks stale fill');
   // A verified owned school change can rebuild dependent controls, but cannot
   // authorize concurrent edits or ambiguous replacements.
   for(const mode of ['rebuild','duplicate','edit']){
     reset('<section data-education><div class="field"><label for="owned-school">School</label><select id="owned-school"><option value="">Choose</option><option value="one">One</option></select></div><label>Degree<input id="owned-degree"></label></section>');
     document.getElementById('owned-school').onchange=()=>{const old=document.getElementById('owned-degree'),clone=old.cloneNode(true);old.replaceWith(clone);if(mode==='duplicate')clone.parentElement.parentElement.append(clone.parentElement.cloneNode(true));if(mode==='edit')clone.value='User degree';};
     scan=ApplicationAutofill.scan();result=await run([{id:field('owned-degree').id,value:'Bachelor of Science'},{id:field('owned-school').id,value:'One'}]);
     check(result[0].id===field('owned-school').id&&result[0].status==='filled','School fills before dependent field');
     check(result[1].status===(mode==='rebuild'?'filled':'failed'),'Rebuilt dependent: '+mode+JSON.stringify(result));
   }
   reset('<div class="field"><label for="phone">Phone</label><input id="phone" type="tel"></div>');
   const phone=document.getElementById('phone');phone.oninput=()=>phone.value=phone.value.replace(/\D/g,'');scan=ApplicationAutofill.scan();
   result=await run([{id:field('phone').id,value:'202-555-0100'}]);check(result[0].status==='filled'&&phone.value==='2025550100','Formatting-only phone change is retained');
   phone.value='';phone.oninput=()=>phone.value='2025550199';scan=ApplicationAutofill.scan();result=await run([{id:field('phone').id,value:'202-555-0100'}]);check(result[0].status==='failed','Changed phone digits rejected');
   reset('<label>Phone<input type="tel" id="phone"></label><label>Country<select id="phone-country"><option value="">Choose</option><option value="US">United States</option></select></label>');
   const national=document.getElementById('phone');national.oninput=()=>national.value=national.value.replace(/^\+1/, '').replace(/\D/g,'');
   document.getElementById('phone-country').onchange=()=>national.value='';scan=ApplicationAutofill.scan();
   result=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,phoneCountry:'US',changes:[{id:field('phone').id,value:'+1 202-555-0100'},{id:field('phone-country').id,value:'United States'}]});
   check(result.every(r=>r.status==='filled')&&national.value==='2025550100','Known country selection precedes phone and allows country-code formatting');
   national.value='';scan=ApplicationAutofill.scan();result=await run([{id:field('phone').id,value:'+1 202-555-0100'}]);check(result[0].status==='failed','Country-code equivalence requires explicitly known country');
   national.value='2025550199';document.getElementById('phone-country').value='';scan=ApplicationAutofill.scan();
   result=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,changes:[{id:field('phone-country').id,value:'United States'}],accounting:[{id:field('phone').id,status:'skipped',code:'preserved'}]});
   check(result.find(r=>r.id===field('phone').id).status==='invalidated'&&national.value==='','Portal clearing an unselected existing phone is reported, never silently refilled');
   reset('<label>Choice<input id="orphan" role="combobox"></label><div role="listbox"><div role="option">Yes</div></div>');
   let wrongClicks=0;form.querySelector('[role="option"]').onclick=()=>wrongClicks++;scan=ApplicationAutofill.scan();result=await run([{id:field('orphan').id,value:'Yes'}]);
   check(result[0].status==='failed'&&wrongClicks===0,'Unassociated global menu never used');
   for(const mode of ['receipt','error','missing','late-error']){
     reset('<div class="field-wrapper"><div class="file-upload" id="upload"><label for="resume">Resume/CV</label><input id="resume" type="file" accept=".pdf"></div></div>');
     const upload=document.getElementById('upload');document.getElementById('resume').onchange=()=>{
       if(mode==='missing'){document.getElementById('resume').remove();return;}
       upload.innerHTML='<span>Fixture.pdf</span><button type="button" aria-label="Remove file">Remove file</button>'+(mode==='error'?'<div role="alert">Upload failed</div>':'');
       if(mode==='late-error')setTimeout(()=>upload.insertAdjacentHTML('beforeend','<div role="alert">Upload failed</div>'),150);
     };scan=ApplicationAutofill.scan();result=await run([{id:field('resume').id,value:'Fixture.pdf'}]);
     check(result[0].status===(mode==='receipt'?'filled':mode==='missing'?'needs review':'failed'),'Replaced upload '+mode+': '+JSON.stringify(result));
   }
   reset('<div class="field"><label for="parent">Do you have a conflict?</label><select id="parent"><option value="no">No</option><option value="yes">Yes</option></select></div><div class="field"><label for="explanation">If you answered "Yes" to the above question, please provide additional information here:</label><textarea id="explanation"></textarea></div>');
   scan=ApplicationAutofill.scan();check(field('explanation').notApplicable,'Committed No establishes non-applicable explanation');
   document.getElementById('parent').value='yes';scan=ApplicationAutofill.scan();check(!field('explanation').notApplicable,'Yes requires explanation');
   document.getElementById('parent').value='no';
   result=await run([{id:field('explanation').id,value:'Must not be inserted'}]);check(result[0].status==='not applicable'&&!document.getElementById('explanation').value,'Recheck committed parent immediately before filling explanation');
   reset('<fieldset><legend>Select skills</legend><label><input id="python" type="checkbox" value="p">Python</label><label><input id="sql" type="checkbox" value="s">SQL</label><label><input id="java" type="checkbox" value="j">Java</label></fieldset>');
   scan=ApplicationAutofill.scan();check(scan.fields.length===1&&field('python').multiple,'Checkbox set is one multiselect field');
   result=await run([{id:field('python').id,value:['Python','SQL']}]);
   check(result[0].status==='filled'&&document.getElementById('python').checked&&document.getElementById('sql').checked&&!document.getElementById('java').checked,'Both selected answers remain checked');
   scan=ApplicationAutofill.scan();result=await run([{id:field('python').id,value:['Java']}]);
   check(result[0].status==='skipped'&&document.getElementById('python').checked&&document.getElementById('sql').checked,'Existing checkbox selections are preserved');
   reset('<div class="field"><label for="essay">What drew you to this role?</label><p id="hint" class="helper-text">Maximum 150 words</p><textarea id="essay" aria-describedby="hint"></textarea></div><div role="textbox" contenteditable="true" aria-label="Unrecognized answer"></div>');
   scan=ApplicationAutofill.scan();check(field('essay').wordLimit===150&&scan.unsupported.length===1,'Text limits and an unmapped editable control are visible in the inventory');
   document.getElementById('hint').textContent='Maximum 20 words';result=await run([{id:field('essay').id,value:'Short answer'}]);
   check(result[0].status==='failed'&&!document.getElementById('essay').value,'Changed helper instructions invalidate a fill');
   reset('<div class="field"><label for="late">First Name</label><input id="late"></div>');
   document.getElementById('late').oninput=()=>setTimeout(()=>document.getElementById('late').value='',2500);
   scan=ApplicationAutofill.scan();result=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,settleMs:5000,changes:[{id:field('late').id,value:'Example'}]});
   check(result[0].code==='rejected','Preparation detects a value cleared after the immediate batch');
   reset('<label>Referral source<select id="source"><option>Job board</option><option>Other</option></select></label><label>If you selected Other, specify<input id="other"></label>');
   scan=ApplicationAutofill.scan();check(field('other').notApplicable,'Other explanation is inapplicable for an explicit different selection');
   reset('<label>Have you had a conflict?<select id="source"><option>No</option><option>Yes</option></select></label><label>If yes, explain. If no, enter N/A<textarea id="explain" required></textarea></label>');
   scan=ApplicationAutofill.scan();check(!field('explain').notApplicable&&field('explain').conditionalValue==='N/A','Explicit No instructions require N/A rather than a blank');
   result=await run([{id:field('explain').id,value:'N/A'}]);check(result[0].status==='filled','Explicit N/A is retained');
   CopilotCore.platform=()=> 'lever';
   reset('<div><div class="application-label full-width multiple-choice">Are you authorized to work?</div><div class="application-field"><ul><li><label><input id="lever-yes" type="radio" name="authorization" value="yes">Yes</label></li><li><label><input type="radio" name="authorization" value="no">No</label></li></ul></div></div><label><div class="application-label">Current location</div><div class="application-field"><input class="location-input" name="location" id="location-input"><input type="hidden" name="selectedLocation"></div></label>');
   scan=ApplicationAutofill.scan();check(field('authorization').label==='Are you authorized to work?','Lever sibling question is distinct from its Yes option');
   check(field('location').excluded&&field('location').manualReason.includes('suggestion'),'Lever uncommitted location widget is explicitly manual');
   result=await run([{id:field('authorization').id,value:'Yes'},{id:field('location').id,value:'Berkeley'}]);
   check(result[0].status==='filled'&&result[1].status==='failed'&&!document.getElementById('location-input').value,'Native Lever radio fills; unsupported location cannot report typed text as success');
   reset('<div class="application-field"><input id="resume" name="resume" type="file"><span class="filename"></span><span class="resume-upload-working" style="display:none">Analyzing resume...</span><span class="resume-upload-failure" style="display:none">Could not read resume</span></div>');
   const leverUpload=document.getElementById('resume');leverUpload.onchange=()=>{form.querySelector('.filename').textContent='Fixture.pdf';form.querySelector('.resume-upload-failure').style.display='inline';};
   scan=ApplicationAutofill.scan();result=await run([{id:field('resume').id,value:'Fixture.pdf'}]);check(result[0].code==='upload_error','Lever visible upload failure defeats filename receipt');
   check(submits===0,'No submissions');document.getElementById('results').textContent='PASS: realistic dropdown events, external menus, delayed choices, phone normalization, upload receipts, conditional questions; zero submissions';
 }catch(e){document.getElementById('results').textContent='FAIL: '+e.stack;}
})();
