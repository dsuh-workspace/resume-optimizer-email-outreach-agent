/* Synthetic local pages only. Override host classification in the test harness, not production. */
(async()=>{
  const results=document.getElementById('results'), check=(value,message)=>{if(!value)throw new Error(message);};
  try {
    CopilotCore.platform=()=>location.pathname.includes('lever')?'lever':'greenhouse';
    let submitted=0;document.querySelector('form').onsubmit=e=>{e.preventDefault();submitted++;};
    document.getElementById('resume').onchange=()=>document.getElementById('receipt').textContent=document.getElementById('resume').files[0]?.name||'';
    const custom=document.getElementById('custom');custom.onclick=()=>document.getElementById('places').hidden=false;document.querySelector('[role="option"]').onclick=e=>{custom.value=e.target.textContent;document.getElementById('places').hidden=true;custom.dispatchEvent(new Event('change',{bubbles:true}));};
    let scan=ApplicationAutofill.scan();
    if(CopilotCore.platform()==='greenhouse'){
      const originalTitle=document.title,heading=document.querySelector('h1').innerText;
      document.title='Job Application for '+heading+' at Example University Recruiting';
      check(ApplicationAutofill.scan().company==='Example University Recruiting','Hosted Greenhouse title identifies employer without structured metadata');
      document.title='Job Application for A different role at Wrong Company';
      check(!ApplicationAutofill.scan().company,'Mismatched title cannot supply employer');
      document.title=originalTitle;scan=ApplicationAutofill.scan();
    }
    const id=label=>scan.fields.find(f=>f.label===label).id;
    const apply=changes=>ApplicationAutofill.apply({scanId:scan.scanId,url:scan.url,changes,pdf:{name:'Sample.pdf',base64:btoa('%PDF synthetic fixture')}});
    check(scan.fields.length===9,'Visible field count');
    const response=await apply([{id:id('First name'),value:'Daniel'},{id:id('Email'),value:'new@example.org'}, {id:id('Country'),value:'United States'},{id:id('Description'),value:'Saved 50 hours weekly.'},{id:id('Gender'),value:'No'},{id:id('Resume'),value:'Sample.pdf'},{id:id('Current location'),value:'Berkeley'}]);
    check(response.filter(r=>r.status==='filled').length===5,JSON.stringify(response));
    check(document.getElementById('email').value==='existing@example.org','Existing value preserved');
    check(!document.getElementById('gender').value,'Disclosure untouched');
    check(document.getElementById('country').value==='US','Exact dropdown match');
    check(document.getElementById('resume').files[0].name==='Sample.pdf','PDF attached');
    check(custom.value==='Berkeley','Custom dropdown retained');
    check(submitted===0,'No submission');
    check(document.querySelectorAll('.employment,[data-employment]').length===1,'No duplicated experience entries');
    const again=await apply([{id:id('First name'),value:'Other'}]);check(again[0].status==='skipped','Repeated fill preserves value');
    scan=ApplicationAutofill.scan();document.getElementById('first').value='User edit';
    const stale=await apply([{id:id('First name'),value:'Changed',replace:true}]);check(stale[0].status==='failed','Changed values cannot be overwritten');
    const unknown=await apply([{id:id('Country'),value:'Canada',replace:true}]);check(unknown[0].status==='failed','Unknown dropdown option');
    const long=await apply([{id:id('Why this role?'),value:'x'.repeat(251)}]);check(long[0].status==='failed','Length limit');
    const old=scan.scanId;scan=ApplicationAutofill.scan();let rejected=false;try{await ApplicationAutofill.apply({scanId:old,url:scan.url,changes:[]});}catch(_){rejected=true;}check(rejected,'Stale scan rejected');
    const input=document.getElementById('why');input.oninput=()=>input.value='';
    const reverted=await apply([{id:id('Why this role?'),value:'A reviewed answer'}]);check(reverted[0].status==='failed','React-style rejection surfaced');
    const dynamic=document.createElement('input');dynamic.setAttribute('aria-label','New question');document.querySelector('form').append(dynamic);
    check(ApplicationAutofill.scan().fields.some(f=>f.label==='New question'),'Dynamic fields detected on rescan');
    const form=document.querySelector('form');
    const group=document.createElement('fieldset');group.innerHTML='<legend>Are you authorized to work?</legend><label><input type="radio" name="authorization" value="yes">Yes</label><label><input type="radio" name="authorization" value="no">No</label>';form.append(group);
    scan=ApplicationAutofill.scan();const radioId=scan.fields.find(f=>f.type==='radio').id;
    group.querySelector('legend').textContent='I certify that all information is correct';
    const unsafe=await apply([{id:radioId,value:'Yes'}]);check(unsafe[0].status==='failed'&&!group.querySelector('input').checked,'Changed radio question never clicks attestation');
    group.querySelector('legend').textContent='Are you authorized to work?';scan=ApplicationAutofill.scan();group.querySelectorAll('label')[1].lastChild.textContent='Definitely';
    check((await apply([{id:scan.fields.find(f=>f.type==='radio').id,value:'Yes'}]))[0].status==='failed','Changed radio options rejected');
    scan=ApplicationAutofill.scan();const originalFirst=document.getElementById('first');originalFirst.hidden=true;
    check((await apply([{id:id('First name'),value:'Other',replace:true}]))[0].status==='failed','Hidden-after-preview field rejected');
    originalFirst.hidden=false;scan=ApplicationAutofill.scan();const firstParent=originalFirst.parentElement;originalFirst.remove();
    check((await apply([{id:id('First name'),value:'Other',replace:true}]))[0].status==='failed','Removed-after-preview field rejected');
    firstParent.append(originalFirst);
    scan=ApplicationAutofill.scan();document.getElementById('first').readOnly=true;
    check((await apply([{id:id('First name'),value:'Other',replace:true}]))[0].status==='failed','Readonly changed after scan rejected');
    const undone=await ApplicationAutofill.undo();check(document.getElementById('first').value==='User edit','Undo preserves later user edits');check(undone.some(r=>r.status==='manual'),'Uploads require manual removal');
    // No expected CSS classes: structural education and two separate employment entries.
    CopilotCore.configure({version:1,manual:'\\b(consent|agree|certify|signature)\\b',disclosure:'lgbtq',personal:'sponsor',written:'describe',education:'^(School|Degree)$',options:{}});
    const extra=document.createElement('div');extra.innerHTML='<section><h2>Education</h2><div class="field"><label for="school2">School</label><input id="school2" value="UC Berkeley" role="combobox"><input type="text" aria-hidden="true"></div><div class="field"><label for="edu-end">End date year</label><input id="edu-end"></div></section><section><h2>Employment</h2><label>Company<input value="One"></label><label>End date year<input id="job-one"></label></section><section><h2>Employment</h2><label>Company<input value="Two"></label><label>End date year<input id="job-two"></label></section><label>End date year<input id="orphan-date"></label><label id="privacy-label"><input type="checkbox" id="privacy-box">I consent to processing my personal data for recruitment purposes</label>';
    form.append(extra);scan=ApplicationAutofill.scan();
    check(scan.fields.filter(f=>f.label==='School').length===1,'Composite dropdown is one field');
    const named=name=>scan.fields.find(f=>f.name===name);
    check(named('edu-end').group.kind==='education','Structural school date recognized');
    check(named('job-one').group.identity==='One'&&named('job-two').group.identity==='Two','Repeated employment dates retain separate identity');
    check(!named('orphan-date').group,'Unidentified date not guessed');
    const datePacket={experiences:[{company:'One',date_range:'Jan 2020 – March 2021'},{company:'Two',date_range:'June 2022 – August 2023'}]},datePrefs={application_profile:{education:[{institution:'UC Berkeley',end:'2028-05'}]}};
    const dateChanges=['edu-end','job-one','job-two'].map(name=>({id:named(name).id,value:CopilotCore.proposed(named(name),datePacket,datePrefs).value}));
    check((await apply(dateChanges)).every(r=>r.status==='filled'),'Contextual dates fill successfully');
    check(document.getElementById('edu-end').value==='2028'&&document.getElementById('job-one').value==='2021'&&document.getElementById('job-two').value==='2023','Independent retained school and experience dates');
    const consentId=named('privacy-box').id;
    let consentResult=await apply([{id:consentId,value:'Yes',checked:true}]);check(consentResult[0].status==='failed'&&!document.getElementById('privacy-box').checked,'Unauthorized consent not clicked');
    const consentApply=()=>ApplicationAutofill.apply({scanId:scan.scanId,url:scan.url,automation:{recruitment_consent:true},changes:[{id:named('privacy-box').id,value:'Yes',checked:true}]});
    consentResult=await consentApply();check(consentResult[0].status==='filled'&&document.getElementById('privacy-box').checked,'Authorized consent retained');
    scan=ApplicationAutofill.scan();let clicks=0;document.getElementById('privacy-box').onclick=()=>clicks++;await consentApply();check(clicks===0,'Already checked consent preserved');
    document.getElementById('privacy-box').checked=false;scan=ApplicationAutofill.scan();document.getElementById('privacy-label').append(' and I certify all answers are accurate');
    consentResult=await consentApply();check(consentResult[0].status==='failed'&&!document.getElementById('privacy-box').checked,'Changed mixed consent cannot be clicked');
    // Search input is temporary, aliases are bounded and only exact options commit.
    const retryGroup=document.createElement('section');retryGroup.className='education';
    retryGroup.innerHTML='<div class="field application-question"><label for="alias-school">School</label><input id="alias-school" role="combobox" aria-controls="alias-list"><div role="listbox" id="alias-list" hidden></div></div><label>Degree<input id="alias-degree"></label><label>End date year<input id="alias-year"></label>';
    form.append(retryGroup);let school=document.getElementById('alias-school'),list=document.getElementById('alias-list');
    let searches=[],mode='alias';
    school.oninput=()=>{const query=school.value;searches.push(query);school.setAttribute('aria-expanded','true');list.hidden=false;list.replaceChildren();
      if(mode==='edit'){school.value='User edit';return;}
      if(mode==='missing')return;
      if(query==='UC Berkeley'){const option=document.createElement('div');option.setAttribute('role','option');option.textContent='UC Berkeley';option.onclick=()=>{school.value='UC Berkeley';school.setAttribute('aria-expanded','false');list.hidden=true;school.dispatchEvent(new Event('change',{bubbles:true}));};list.append(option);if(mode==='ambiguous')list.append(option.cloneNode(true));}
    };
    const schoolFill=()=>apply([{id:named('alias-school').id,value:'University of California, Berkeley',alternatives:['University of California, Berkeley','UC Berkeley']},{id:named('alias-degree').id,value:'Bachelor of Science'},{id:named('alias-year').id,value:'2028'}]);
    scan=ApplicationAutofill.scan();let aliasResults=await schoolFill();
    check(aliasResults.every(r=>r.status==='filled')&&school.value==='UC Berkeley','Alias-only search commits correct school');
    check(searches.includes('University of California, Berkeley')&&searches.includes('UC Berkeley'),'Searches approved aliases');
    for(const testMode of ['missing','ambiguous','edit']){
      school.value='';school.setAttribute('aria-expanded','false');document.getElementById('alias-degree').value='';document.getElementById('alias-year').value='';mode=testMode;scan=ApplicationAutofill.scan();aliasResults=await schoolFill();
      check(aliasResults[0].status==='failed','School failure reported: '+testMode);
      if(testMode==='edit'){check(school.value==='User edit','Intervening user search is preserved');check(aliasResults.slice(1).every(r=>r.status==='failed'),'Uncertain school identity blocks dependent fields');}
      else {check(school.value==='','Only temporary search restored: '+testMode);check(aliasResults.slice(1).every(r=>r.status==='filled'),'Independent degree/year continue after failed school: '+testMode);}
    }
    // Later controls may invalidate an earlier apparently successful fill.
    school.removeAttribute('role');school.value='';school.oninput=null;document.getElementById('alias-degree').value='';document.getElementById('alias-year').value='';
    document.getElementById('alias-year').oninput=()=>document.getElementById('alias-degree').value='';scan=ApplicationAutofill.scan();
    const late=await apply([{id:named('alias-degree').id,value:'Bachelor of Science'},{id:named('alias-year').id,value:'2028'}]);
    check(late[0].status==='failed'&&late[0].diagnostic.code==='rejected','Final pass catches later clearing of a prior field');
    const anonymous=document.createElement('label');anonymous.innerHTML='Postal code<input>';form.append(anonymous);scan=ApplicationAutofill.scan();form.append(anonymous.cloneNode(true));
    const duplicates=await ApplicationAutofill.apply({url:scan.url,scanId:scan.scanId,changes:[],discoverNew:true});
    check(duplicates.length===1&&duplicates[0].newField&&duplicates[0].diagnostic.occurrence===1,'New duplicate unnamed component is counted separately');
    const misleadingActions=document.createElement('div');misleadingActions.innerHTML='<button id="role-submit" type="submit" role="combobox" aria-label="School">Select school</button><button id="role-next" type="button" role="combobox" aria-label="School">Next</button>';form.append(misleadingActions);
    scan=ApplicationAutofill.scan();check(!scan.fields.some(f=>['role-submit','role-next'].includes(f.name)),'Submission/navigation buttons cannot masquerade as dropdowns');
    check(submitted===0,'Still zero submissions');
    results.textContent='PASS: browser mapping, structural dates, duplicate controls, consent authorization and retained state; zero submissions';document.title='PASS';
  }catch(error){results.textContent='FAIL: '+error.stack;document.title='FAIL';}
})();
