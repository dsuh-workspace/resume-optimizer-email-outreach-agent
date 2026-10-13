/* Pure mapping rules shared by the panel, worker, content script, and tests. */
(function (root) {
  'use strict';
  const normalize = value => String(value || '').toLowerCase().replace(/\s+/g, ' ').trim().replace(/[ *:?!✱]+$/g, '').trim();
  // School campus separators vary between portal catalogs; preserve every word.
  const institutionKey=value=>normalize(value).replace(/,\s*|\s+[-–—]\s+/g,' ').replace(/\s+/g,' ').trim();
  function dropdownQueries(answer) {
    const values=[answer.value,...(answer.alternatives||[])],queries=[];
    for(const value of values){
      if(typeof value!=='string'||!value.trim())continue;
      queries.push(value);
      if(answer.matchRule?.kind==='institution')
        for(const separator of [' - ',', ',' – ',' — ',' '])
          queries.push(value.replace(/,\s*|\s+[-–—]\s+/g,separator));
    }
    return [...new Set(queries)].slice(0,12);
  }
  let policy=null;
  let manual = /\b(gender|sex|race|ethnic\w*|disab\w*|veteran\w*|military|consent|agree\w*|certif\w*|attest\w*|signature|criminal|convict\w*|ssn|social security|password|birth\w*|citizenship|nationality|pronouns|captcha)\b/i;
  let personalQuestion = /\b(sponsor\w*|authoriz\w*|eligible|eligibility|salary|compensation|relocat\w*|availab\w*|notice period|start date|visa|permit)\b/i;
  let disclosure = /\b(gender|sex|race|racial|ethnic\w*|hispanic|latino|disab\w*|veteran\w*|military)\b/i;
  let written = /\b(why|describe|tell us|experience|interests?|anything else|additional information|cover letter)\b/i;
  const writtenQuestion = value => written.test(value);
  const fieldContext=field=>Object.fromEntries(['id','label','helper','type','options','required','limit','wordLimit','group','condition','occurrence','multiple','section','subject','contextVersion'].filter(k=>field[k]!==undefined).map(k=>[k,field[k]]));
  const questionText=field=>(field.section?'['+field.section+' | '+(field.subject||'applicant')+']\n':'')+field.label+(field.helper?'\n'+field.helper:'');
  const thirdParty=field=>field.subject&&field.subject!=='applicant'||/\b(references?|referees?|emergency|next of kin|third.party|parent|guardian|spouse)\b/i.test(field.section||'')||/\b(emergency contact|next of kin|third.party|parent|guardian|spouse|referee)\b|\breference(?:['’]s|\s+(?:name|email|phone|contact|relationship))\b|\b(?:of|for) (?:your |a |the )?reference\b|^\s*references?\s*[*:]*$/i.test(field.label||'');
  const enrollment=field=>/\b(enroll\w*|attend\w*|pursu\w*)\b|\b(current|currently|present)\b.*\b(school|university|college|student|degree|education)\b|\b(school|university|college|degree|education)\b.*\b(current|currently|present)\b/i.test(field.label+' '+(field.helper||''));
  function configure(value) {if(value?.version!==1) return; policy=value;manual=new RegExp(value.manual,'i');personalQuestion=new RegExp(value.personal,'i');disclosure=new RegExp(value.disclosure,'i');written=new RegExp(value.written,'i');Object.assign(root.CopilotCore,{manual,personalQuestion,disclosure});}
  function privacyConsent(text) {
    const q=normalize(text).replace(/[.,]$/,'');
    if(/certif|attest|accura|background|marketing|signature|terms|criminal|credit check|truth|contact me|waiv|releas|arbitrat|binding|acknowledg|agreement|agree to all/i.test(q))return null;
    // Closed wording families: arbitrary additional clauses cannot ride along with data consent.
    const prefix=/^(?:by checking this box,? )?i (?:consent|agree) to (?:[a-z0-9 &'’().-]+? )?(?:collecting,? storing,? and processing|collecting and processing|processing|the processing of) my /;
    if(!prefix.test(q))return null;
    const tail=q.replace(prefix,'');
    if(/^(?:responses to the )?demographic (?:data surveys above|data|survey responses)(?: for (?:recruitment|equal opportunity monitoring|diversity monitoring))?$/.test(tail))return 'demographic_consent';
    if(/^(?:personal|application|recruitment) data for (?:recruitment|recruiting|hiring|recruitment purposes|recruiting purposes|the recruitment process)(?: in accordance with (?:the |your |[a-z0-9 ’'-]+ )?privacy (?:policy|notice))?$/.test(tail))return 'recruitment_consent';
    return null;
  }
  const dateField=label=>/^(?:(?:start|end)(?: date)?(?: month| year)?|(?:graduation|expected graduation)(?: date| month| year)?)$/.test(normalize(label));
  function dateValue(date,field) {
    const label=normalize(field.label);let year,month;
    let m=/^(\d{4})-(\d{2})$/.exec(date||'');
    if(m){year=m[1];month=Number(m[2]);}
    else {m=/^([a-z]+) (\d{4})$/i.exec(date||'');if(m){year=m[2];const matches=months.filter(v=>m[1].length>=3&&v.toLowerCase().startsWith(m[1].toLowerCase()));month=matches.length===1?months.indexOf(matches[0])+1:0;}}
    if(!year||!month)return {reason:'Month and year are not recorded for this entry.'};
    if(field.type==='date')return {reason:'Exact calendar day is not recorded. Enter it manually.'};
    const value=field.type==='month'?year+'-'+String(month).padStart(2,'0'):/month/.test(label)?months[month-1]:/year/.test(label)?year:months[month-1]+' '+year;
    return {value,alternatives:/month/.test(label)&&field.type!=='month'?[value,String(month),String(month).padStart(2,'0')]:[value]};
  }
  function classify(field) {const text=field.label||'';if(manual.test(text)||field.type==='password')return 'manual';if(disclosure.test(text))return 'disclosure';if(field.group?.kind==='education'||policy&&new RegExp(policy.education,'i').test(normalize(text)))return 'education';if(personalQuestion.test(text))return 'personal';if(writtenQuestion(text))return 'written';return 'fact';}
  const months=['January','February','March','April','May','June','July','August','September','October','November','December'];
  function militaryAnswer(label, options, d) {
    const substantive=options.filter(o=>!/(decline|wish|prefer|select|choose)/i.test(o.label));
    const protectedQuestion=/protected/.test(label)||(!/military|served/.test(label)&&substantive.length>0&&substantive.every(o=>/protected veteran/i.test(o.label)));
    if(/military|served/.test(label)&&!protectedQuestion)return d.military_history?{value:d.military_history,alternatives:[]}:{code:'explicit_detail_needed',reason:'Explicit detail needed: military service history is different from veteran status. Choose your answer.'};
    const value=d[protectedQuestion?'protected_veteran':'veteran'];
    return {value,alternatives:normalize(value)==='no'?(policy.options[protectedQuestion?'protected_veteran_no':'veteran_no']||[]):normalize(value)==='decline to answer'?policy.options.decline:[]};
  }
  // One matcher for preview, native controls and loaded custom menus. Only degree
  // qualifications have ranked aliases; indistinguishable best choices are unsafe.
  function matchChoice(field, answer) {
    let {value,alternatives=[]}=answer;
    if(field.multiple&&!Array.isArray(value)&&value!==undefined)value=[value];
    if(Array.isArray(value)){
      if(!field.multiple||!value.length||new Set(value.map(normalize)).size!==value.length)return {code:'unsupported',reason:'This control does not accept this answer set.'};
      const options=[];
      for(const item of value){const matched=matchChoice({...field,multiple:false},{value:item});if(!matched.option)return matched;options.push(matched.option);}
      return {options};
    }
    if(answer.matchRule?.kind==='military'){
      const military=militaryAnswer(normalize(field.label),field.options||[],answer.matchRule.disclosures);
      if(military.reason)return military;
      value=military.value;alternatives=military.alternatives;
    }
    const key=answer.matchRule?.kind==='institution'?institutionKey:normalize;
    const candidates=[value,...alternatives].filter(v=>v!==undefined).map(key);
    let matches=(field.options||[]).filter(o=>!o.disabled&&candidates.includes(key(o.label)));
    if(answer.matchRule?.kind==='numeric_interval'&&/^\d+(?:\.\d+)?$/.test(String(value))&&!matches.length){
      const number=Number(value);
      matches=(field.options||[]).filter(o=>{if(o.disabled)return false;const label=normalize(o.label);let m=/^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$/.exec(label);if(m)return number>=Math.min(Number(m[1]),Number(m[2]))&&number<=Math.max(Number(m[1]),Number(m[2]));m=/^(\d+(?:\.\d+)?) or (higher|above|lower|below)$/.exec(label);return !!m&&(m[2]==='higher'||m[2]==='above'?number>=Number(m[1]):number<=Number(m[1]));});
    }
    if(answer.matchRule?.kind==='degree'&&matches.length){
      const rank=o=>normalize(o.label)===normalize(value)?0:/^bachelor['’]s degree$/i.test(o.label)?2:normalize(o.label)==='bachelors'?3:1;
      const best=Math.min(...matches.map(rank));matches=matches.filter(o=>rank(o)===best);
    }
    if(matches.length===1)return {option:matches[0]};
    const broad=['yes','no','male','female','man','woman','asian'].includes(normalize(value));
    const detail=disclosure.test(field.label)&&broad||!alternatives.length&&['yes','no'].includes(normalize(value))&&(!!field.resolution||/worked|employed|employee|contractor/i.test(field.label));
    return {code:matches.length?'option_ambiguous':detail?'explicit_detail_needed':'option_missing',reason:matches.length?'Multiple indistinguishable compatible choices. Choose on the page.':detail?'Explicit detail needed: the saved answer does not establish one of these choices. Choose your answer.':'Matching choice unavailable. Load the choices or complete this field on the page.'};
  }
  function applicationProposal(field, packet, preferences) {
    if(!policy)return null;
    const label=normalize(field.label), app=preferences.application_profile||{}, category=classify(field);
    let value, alternatives=[], matchRule, source='Explicit application profile';
    const aliases=key=>policy.options[key]||[];
    if(category==='disclosure') {
      const d=app.disclosures||{};
      if(/lgbtq/.test(label))value=d.lgbtq;
      else if(/hispanic|latino/.test(label)&&!/race|ethnic/.test(label))value=d.hispanic;
      else if(/race|racial|ethnic/.test(label)){value=d.race;if(value==='Asian'&&d.hispanic==='No')alternatives=['Asian (Not Hispanic or Latino)'];if(d.ethnicity&&(field.options||[]).some(o=>normalize(o.label)===normalize(d.ethnicity)))value=d.ethnicity;else if(d.ethnicity&&!field.options?.length&&/ethnic/.test(label))value=d.ethnicity;}
      else if(/gender|sex/.test(label)){value=d.gender;alternatives=aliases(normalize(value));if(d.gender_identity&&/identity/.test(label)){value=d.gender_identity;alternatives=[];}}
      else if(/disab/.test(label)){value=d.disability;if(value==='No'){if(/ever|past|previous|history/.test(label))return {code:'explicit_detail_needed',reason:'Explicit detail needed: current disability status does not establish past disability status.'};alternatives=aliases('disability_no');}}
      else if(/veteran|military/.test(label)) {
        const answer=militaryAnswer(label,field.options||[],d);
        if(answer.reason)return answer;
        ({value,alternatives}=answer);matchRule={kind:'military',disclosures:{veteran:d.veteran,protected_veteran:d.protected_veteran,military_history:d.military_history}};
      }
      if(normalize(value)==='decline to answer')alternatives=aliases('decline');
    } else if(category==='education') {
      let entries=app.education||[], identity=institutionKey(field.group?.identity);
      if(identity)entries=entries.filter(e=>[e.institution,...(e.aliases||[])].some(a=>institutionKey(a)===identity));
      if(entries.length!==1)return {reason:'Cannot identify which school this education field belongs to.'};
      const e=entries[0];
      const completion=/completed|highest|earned|awarded/.test(label);
      if(completion&&(e.status!=='completed'||/highest/.test(label)&&(app.education||[]).length!==1))return {code:'explicit_detail_needed',reason:'Confirm completed qualifications separately; an expected degree is not completed.'};
      if(/^(school|school name|university|institution|college)$/.test(label)){value=e.institution;alternatives=e.aliases||[];matchRule={kind:'institution'};}
      else if(/^degree(?: type)?$/.test(label)||completion&&/degree/.test(label)){
        value=e.degree;
        if(['bachelor of science','bs','b.s.',"bachelor's degree (bs)",'bachelor of science (b.s.)'].includes(normalize(value)))alternatives=aliases('degree');
        matchRule={kind:'degree'};
      }
      else if(/^(major|discipline|field of study)$/.test(label))value=e.major;
      else if(dateField(label)){
        const result=dateValue(/start|from/.test(label)?e.start:e.end,field);
        if(result.reason)return result;value=result.value;alternatives=result.alternatives;
      }
    } else if(category==='personal') {
      const w=app.work||{};
      // Explicit foreign country/context or qualified conditions require a reviewed exact answer.
      const us=/\bunited states(?: of america)?\b|\bu\.?s\.?a?\.?\b/i;
      const countryClause=label.match(/\b(?:work|working|employment|employed|position|role) (?:in|within) (?:the )?([a-z .]+?)(?:[?,]|\b(?:now|without|with|and|or|on|at|will|do|have|currently)\b|$)/);
      if(w.country!=='US'||/canada|united kingdom|australia|germany|india|europe|relocat|salary|compensation/.test(label)||countryClause&&!us.test(countryClause[1]))return null;
      let answer;
      if(/sponsor/.test(label)&&/without|not require|no sponsorship/.test(label)) {
        if(/work/.test(label)&&w.authorized===true&&w.sponsorship_now===false&&w.sponsorship_future===false)answer=true;
      } else if(/sponsor/.test(label)) {
        if(/future|any (?:time|point)|now or|now and/.test(label)){
          if(typeof w.sponsorship_now==='boolean'&&typeof w.sponsorship_future==='boolean')answer=w.sponsorship_now||w.sponsorship_future;
        } else answer=w.sponsorship_now;
      } else if(/authoriz|eligible.*work/.test(label)&&!/not |unauthoriz|restriction|condition|visa/.test(label))answer=w.authorized;
      if(typeof answer==='boolean')value=answer?'Yes':'No';
    } else if(label==='country'&&aliases('country').some(a=>normalize(a)===normalize(preferences.facts?.country||app.work?.country))) {value='United States';alternatives=aliases('country');}
    if(value===undefined)return null;
    if(field.type==='date'&&!/^\d{4}-\d{2}-\d{2}$/.test(value))return {reason:'Exact calendar day is not recorded. Enter it manually.'};
    if(field.limit&&String(value).length>field.limit)return {reason:'Recorded answer exceeds the character limit.'};
    const candidates=[String(value),...alternatives];
    if(field.options?.length){const matched=matchChoice(field,{value,alternatives,matchRule});if(matched.options)return {value:matched.options.map(o=>o.label),source,category};if(!matched.option)return matched;value=matched.option.label;}
    const fact_key=/gender.*identity/.test(label)?'gender_identity':/ethnic/.test(label)&&value===app.disclosures?.ethnicity?'ethnicity':/military|served/.test(label)&&value===app.disclosures?.military_history?'military_history':undefined;
    return {value:String(value),alternatives:candidates,matchRule,source,category,fact_key};
  }
  function postingKey(value) {
    if(!platform(value)) return null;
    const u=new URL(value), parts=u.pathname.split('/').filter(Boolean);
    const job=u.searchParams.get('gh_jid') || (platform(value)==='lever'?parts[1]:(parts.includes('jobs')?parts[parts.indexOf('jobs')+1]:null));
    return job && parts[0] ? [platform(value),u.hostname,parts[0],job].join(':') : null;
  }
  function matchEntry(group, packet) {
    const entries=(group.kind==='education'?packet.education:packet.experiences)||[];
    const identity=normalize(group.identity), role=normalize(group.role);
    if(!identity) return null;
    const matches=entries.filter(e=>normalize(group.kind==='education'?e.institution:e.company)===identity && (!role || normalize(e.role)===role));
    return matches.length===1?matches[0]:null;
  }
  function platform(value) {
    try {const url = new URL(value); if(url.protocol !== 'https:') return null;
      if(['boards.greenhouse.io','job-boards.greenhouse.io','boards.eu.greenhouse.io','job-boards.eu.greenhouse.io'].includes(url.hostname)) return 'greenhouse';
      if(['jobs.lever.co','jobs.eu.lever.co'].includes(url.hostname)) return 'lever';
    } catch (_) {} return null;
  }
  function exactOption(options, answer) {
    const matches = options.filter(o => !o.disabled && normalize(o.label) === normalize(answer));
    return matches.length === 1 ? matches[0] : null;
  }
  function proposed(field, packet, preferences) {
    const label = normalize(field.label), name = normalize(field.name);
    if(thirdParty(field))return {reason:'Third-party or uncertain subject: complete this field manually.'};
    if(field.notApplicable)return {notApplicable:true,reason:'Not applicable: the preceding question is answered No.'};
    if(field.conditionalValue)return {value:field.conditionalValue,source:'Explicit conditional instructions for the selected parent answer'};
    if(field.manualReason)return {reason:field.manualReason};
    const consent=!field.excluded&&field.type==='checkbox'&&(!field.options||field.options.length<=1)&&privacyConsent(field.label);
    if(consent){if(preferences.application_profile?.automation?.[consent])return {value:'Yes',checked:true,source:'Explicit application privacy consent authorization'};return {reason:'Application privacy consent automation is not authorized in Settings.'};}
    if(field.excluded || manual.test(label)) return {reason:'Complete this disclosure or attestation manually.'};
    if(/^if (?:yes\b|you (?:have )?answered.*["“”]?yes)/.test(label))return {reason:'Complete this follow-up only if your preceding answer is Yes.'};
    if(field.resolution){const result=field.resolution;if(result.value!==undefined&&field.options?.length){const matched=matchChoice(field,result);return matched.options?{...result,value:matched.options.map(o=>o.label)}:matched.option?{...result,value:matched.option.label}:matched;}return result;}
    if(field.helper&&/\b(?:summer|future|during|since|between|subsidiar\w*|affiliat\w*|certif\w*|attest\w*|agree\w*|consent|require\w*|must|only|at least|at most)\b/i.test(field.helper))return {reason:'Additional instructions qualify this question. An explicit answer is needed.'};
    if(/\b(?:relationship|related to|relatives?|familial|worked (?:for|with|at)|employed by|previous employee)\b/.test(label))return {reason:'This question needs an authorized relationship answer or full master profile check.'};
    if(dateField(label)&&!field.group&&!/graduation/.test(label))return {reason:'Cannot identify whether this date belongs to education or a particular experience.'};
    if(/complete (?:work|employment|history)|all (?:previous |prior )?(?:employment|work)|entire.*history/.test(label) && !packet.complete_history) return {reason:'This resume does not contain your complete work history. Review manually.'};
    const saved = (preferences.questions || []).filter(q => !q.blocked && normalize(q.question) === normalize(questionText(field)) && !writtenQuestion(label) && (!q.options || JSON.stringify(q.options)===JSON.stringify((field.options||[]).map(o=>o.label))));
    if(saved.length === 1) {const value=saved[0].answer; if(field.limit && value.length>field.limit) return {reason:'Saved answer exceeds the character limit.'}; if(field.options?.length && !exactOption(field.options,value)) return {reason:'Saved answer does not match a unique option.'}; return {value, source:'Explicit saved answer'};}
    if(enrollment(field))return {reason:'Current enrollment requires your explicit answer to this exact question.'};
    const application=applicationProposal(field,packet,preferences);if(application)return application;
    if(personalQuestion.test(label)&&!(field.group?.kind==='employment'&&dateField(label))) return {reason:'Save your explicit answer to this exact question in Preferences.'};
    if(disclosure.test(label))return {code:'explicit_detail_needed',reason:'Explicit detail needed: choose your disclosure answer below. Nothing is inferred.'};
    if(field.type === 'file') return /resume|résumé|\bcv\b/.test(label + ' ' + name) ? {value:packet.pdf_name, source:'Selected PDF', file:true} : {reason:'Upload this document manually.'};
    const personal = packet.personal_info || {}, facts = preferences.facts || {};
    const aliases = {
      'full name':'full_name', 'name':'full_name', 'first name':'first_name', 'last name':'last_name',
      'email':'email', 'email address':'email', 'phone':'phone', 'phone number':'phone', 'mobile phone':'phone',
      'linkedin profile url':'linkedin', 'linkedin profile url (please provide a direct link to your profile)':'linkedin',
      'linkedin':'linkedin', 'linkedin profile':'linkedin', 'linkedin url':'linkedin', 'github':'github', 'github url':'github',
      'portfolio':'portfolio', 'portfolio url':'portfolio', 'website':'portfolio', 'personal website':'portfolio',
      'current location':'location', 'location city':'location', 'location (city)':'location', 'location':'location', 'address':'address', 'street address':'address',
      'city':'city', 'state':'state', 'province':'state', 'zip code':'postal_code', 'postal code':'postal_code', 'country':'country'
    };
    let value, source;
    if(field.group && ['education','employment'].includes(field.group.kind)) {
      const item = matchEntry(field.group,packet);
      if(!item) return {reason:field.group.kind==='employment'?'Cannot identify which experience this date or field belongs to.':'Cannot identify which school this field belongs to.'};
      if(field.group.kind === 'education') {
        if(/^(school|school name|university|institution|college)$/.test(label)) value = item.institution;
        else if(label === 'degree') value = item.degree;
        else if(label === 'gpa') value = item.gpa;
        else if(/^(end date|graduation date)$/.test(label)) value = item.graduation_date;
      } else {
        if(/^(company|company name|employer|employer name)$/.test(label)) value = item.company;
        else if(/^(title|job title|role|position)$/.test(label)) value = item.role;
        else if(/^(description|responsibilities|job description)$/.test(label)) value = item.bullets.map(b => typeof b === 'string' ? b : b.text).join('\n');
        else if(label === 'location') value = item.location;
        else if(dateField(label)) {
          const dates=String(item.date_range||'').split(/\s+[–—-]\s+/);
          const result=dateValue(dates.length===2?dates[/start/.test(label)?0:1]:null,field);
          if(result.reason)return result;
          if(field.options?.length){const matches=field.options.filter(o=>!o.disabled&&result.alternatives.some(a=>normalize(a)===normalize(o.label)));if(matches.length!==1)return {reason:'No unique compatible date option.'};result.value=matches[0].label;}
          return {...result,source:'Selected resume matching experience'};
        }
      }
      source = 'Selected resume ' + field.group.kind;
    } else if(aliases[label]) {
      const key = aliases[label]; value = facts[key] || (key==='location'?facts.city:undefined) || personal[key]; source = facts[key]||key==='location'&&facts.city ? 'Explicit profile fact' : 'Verified profile';
      if(['linkedin','github','portfolio'].includes(key) && value && !/^https?:\/\//i.test(value)) value = 'https://' + value;
    } else if(label === 'current company' && /present|current/i.test(packet.experiences?.[0]?.date_range || '')) {
      value = packet.experiences[0].company; source = 'Selected resume';
    }
    if(value !== undefined && value !== null && String(value).trim()) {
      value = String(value);
      if(field.type === 'date') {if(!/^\d{4}-\d{2}-\d{2}$/.test(value)) return {reason:'Exact calendar date is not recorded. Enter it manually.'};}
      if(field.type === 'month') {
        const match = /^(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})$/i.exec(value);
        if(match) value = match[2] + '-' + String(['january','february','march','april','may','june','july','august','september','october','november','december'].indexOf(match[1].toLowerCase())+1).padStart(2,'0');
        if(!/^\d{4}-\d{2}$/.test(value)) return {reason:'Month and year are not recorded in a recognized format.'};
      }
      if(field.limit && value.length > field.limit) return {reason:'The proposed value exceeds this field’s character limit.'};
      if(field.options?.length && !exactOption(field.options, value)) return {reason:'No unique exact dropdown option matches: ' + value};
      return {value, source, fact_key:aliases[label]==='location'||aliases[label]==='city'?'current_city':aliases[label]};
    }
    const isWritten = ['textarea','text','search'].includes(field.type) && writtenQuestion(label);
    return isWritten ? {reason:'No recorded answer. Request a draft from resume evidence, or answer on the page.', written:true} : {reason:'No unambiguous recorded answer. Complete manually or save an exact answer.'};
  }
  root.CopilotCore = {normalize, manual, personalQuestion, disclosure, writtenQuestion, postingKey, matchEntry, platform, exactOption, matchChoice, proposed,configure,classify,privacyConsent,dateField,fieldContext,questionText,thirdParty,enrollment,dropdownQueries};
  if(typeof module !== 'undefined') module.exports = root.CopilotCore;
})(globalThis);
