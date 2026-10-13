const assert=require('node:assert/strict'), C=require('../core.js');
const prefs=require('./application-profile.json'), matrix=require('./acceptance-matrix.json');
C.configure(require('../field-policy.json'));
const packet={personal_info:{email:'new@example.test'},education:[],experiences:[],complete_history:true};
for(const item of matrix){
 const field={...item,current:item.initial||'',options:item.options?.map(label=>({label,value:label})),group:item.education?{kind:'education',index:0,identity:''}:null};
 if(item.resolved)field.resolution={value:item.expected,source:'Synthetic server resolution'};
 const proposal=C.proposed(field,packet,prefs);
 if(item.manual)assert.equal(proposal.value,undefined,item.id);
 else if(item.written)assert.equal(proposal.written,true,item.id);
 else if(item.single)assert.equal(proposal.checked,true);
 else if(!item.initial)assert.ok([proposal.value,...(proposal.alternatives||[])].includes(item.expected),item.id+': '+JSON.stringify(proposal));
}
for(const label of ['Are you authorized to work in Germany?','Are you NOT authorized to work in the US?','Will you need sponsorship in Canada?','What are your salary expectations?'])assert.equal(C.proposed({label,type:'text'},packet,prefs).value,undefined,label);
for(const [key,value] of [['race','White'],['gender','Female']]){
 const p=structuredClone(prefs);p.application_profile.disclosures[key]=value;
 const f=matrix.find(f=>f.id===key);assert.notEqual(C.proposed({...f,options:f.options.map(label=>({label,value:label}))},packet,p).value,f.expected);
}
const ambiguous={label:'School',type:'select',options:['UC Berkeley','University of California, Berkeley'].map(label=>({label,value:label})),group:{kind:'education',identity:''}};
assert.equal(C.proposed(ambiguous,packet,prefs).value,undefined);
const multiple=structuredClone(prefs);multiple.application_profile.education.push({...multiple.application_profile.education[0],institution:'Other School',aliases:[]});assert.equal(C.proposed({label:'School',type:'text',group:{kind:'education',identity:''}},packet,multiple).value,undefined);
for(const label of ['Gender','Race','Veteran Status','Disability Status'])assert.equal(C.proposed({label,type:'text'},packet,{application_profile:{}}).value,undefined);
console.log('PASS: fixed 40-field acceptance mapping, country/wording distinctions, ambiguous options and missing facts');

const questions=require('./robinhood-questions.json');
const enabled=structuredClone(prefs);enabled.application_profile.automation={recruitment_consent:true,demographic_consent:true};enabled.application_profile.disclosures.lgbtq='No';
assert.equal(C.proposed({label:questions.lgbtq,type:'select',options:[{label:'No',value:'n'}]},packet,enabled).value,'No');
assert.equal(C.proposed({label:questions.consent,type:'checkbox'},packet,enabled).checked,true);
assert.equal(C.proposed({label:questions.consent,type:'checkbox'},packet,{...prefs,application_profile:{}}).value,undefined);
assert.equal(C.privacyConsent('I consent to processing my personal data for recruitment purposes'),'recruitment_consent');
for(const extra of [' I certify that this is accurate.',' and marketing',' and permit a background check',' and agree to all policies'])assert.equal(C.privacyConsent(questions.consent+extra),null);
assert.equal(C.proposed({label:'End date year',type:'number'},packet,enabled).value,undefined);
for(const [label,value] of [['End date month','May'],['End date year','2028']])assert.equal(C.proposed({label,type:'text',group:{kind:'education',identity:'UC Berkeley'}},packet,enabled).value,value);
const employment={...packet,experiences:[{company:'One',role:'Analyst',date_range:'Jan 2020 – March 2021'},{company:'Two',role:'Intern',date_range:'June 2022 – August 2023'}]};
for(const [company,year] of [['One','2021'],['Two','2023']])assert.equal(C.proposed({label:'End date year',type:'number',group:{kind:'employment',identity:company}},employment,enabled).value,year);
assert.match(C.proposed({label:'End date month',type:'text',group:{kind:'employment',identity:''}},employment,enabled).reason,/which experience/);
console.log('PASS: consent boundaries, LGBTQ explicit answer, contextual dates and distinct experience dates');

assert.equal(C.proposed({label:'If you answered Yes to the above question, please provide additional information here:',type:'text'},packet,enabled).written,undefined);

assert.equal(C.proposed({label:'Start date month',type:'text',group:{kind:'employment',identity:'One'}},employment,enabled).value,'January');

for(const label of ['If yes, describe your relationship','If Yes, provide additional information'])assert.equal(C.proposed({label,type:'textarea'},packet,enabled).written,undefined,'Conditional No follow-ups never generate irrelevant prose');

const menuField=(item,type='select')=>({label:item.label,type,options:item.options.map(label=>({label,value:label})),...(item.id==='degree'?{group:{kind:'education',identity:'UC Berkeley'}}:{})});
for(const item of require('./robinhood-menus.json')){
  const field=menuField(item);
  if(item.id==='robinhood_history')field.resolution={value:'No',alternatives:['I have never worked at Robinhood']};
  const answer=C.proposed(field,packet,prefs);
  assert.equal(answer.value,item.expected,item.id+': '+JSON.stringify(answer));
  if(item.explicit){assert.equal(answer.code,'explicit_detail_needed');field.resolution={value:item.explicit,source:'Explicit company answer (exact wording)'};assert.equal(C.proposed(field,packet,prefs).value,item.explicit);}
}
for(const [label,options] of [
 ['Gender',['Cisgender man']],['Ethnicity',['East Asian']],
 ['Veteran Status',['I have never served in the military','I am a protected veteran']],
 ['Disability Status',['No, I do not have a disability and have not had one in the past']],
 ['Disability Status',['I do not have a disability or would not like to be considered under the affirmative action program']]
])assert.equal(C.proposed(menuField({label,options}),packet,prefs).value,undefined,label);
const degrees=options=>C.proposed(menuField({id:'degree',label:'Degree',options}),packet,prefs);
assert.equal(degrees(['Bachelors',"Bachelor's Degree",'Bachelor of Science','BS']).value,'Bachelor of Science');
assert.equal(degrees(['Bachelors',"Bachelor's Degree",'B.S.']).value,'B.S.');
assert.equal(degrees(['Bachelors',"Bachelor's Degree"]).value,"Bachelor's Degree");
assert.equal(degrees(["Bachelor's Degree","Bachelor's Degree"]).value,undefined);
assert.equal(degrees(["Bachelor's Degree","Bachelor’s Degree"]).value,undefined);
assert.equal(degrees(['Bachelor of Arts']).value,undefined);
assert.equal(degrees(['BS','B.S.']).value,undefined,'Equivalent qualifications cannot distinguish duplicate choices');
const disabled=menuField({id:'degree',label:'Degree',options:['Bachelor of Science',"Bachelor's Degree"]});disabled.options[0].disabled=true;
assert.equal(C.proposed(disabled,packet,prefs).value,"Bachelor's Degree");
const ended=menuField({label:'Do you currently work at Robinhood?',options:['I have never worked at Robinhood']});ended.resolution={value:'No'};
assert.equal(C.proposed(ended,packet,prefs).value,undefined);
ended.resolution={value:'Yes'};ended.options=[{label:'I am a former employee',value:'former'}];assert.equal(C.proposed(ended,packet,prefs).value,undefined);
const removed=menuField({label:'Gender',options:['Cisgender woman']});removed.resolution={value:'Cisgender man'};assert.equal(C.proposed(removed,packet,prefs).value,undefined);
console.log('PASS: six Robinhood menu contracts, disclosure boundaries, degree ranking, duplicate/disabled/removed choices and employment distinctions');
const completedField=menuField({label:'Highest degree completed',options:["Bachelor's Degree"]});
assert.equal(C.proposed(completedField,packet,prefs).value,undefined,'Expected is not completed');
const awarded=structuredClone(prefs);awarded.application_profile.education[0].status='completed';
assert.equal(C.proposed(completedField,packet,awarded).value,"Bachelor's Degree",'Explicitly completed qualification');
const abbreviated=structuredClone(prefs);abbreviated.application_profile.education[0].degree='B.S.';
assert.equal(C.proposed(menuField({id:'degree',label:'Degree',options:['Bachelor of Science','Bachelors']}),packet,abbreviated).value,'Bachelor of Science');
assert.equal(C.proposed(menuField({label:'Have you ever had a disability?',options:['Yes','No']}),packet,prefs).value,undefined);
const twoSchools=structuredClone(prefs);twoSchools.application_profile.education.push({institution:'Other School',degree:'Bachelor of Arts',major:'History',status:'completed'});
assert.equal(C.proposed({label:'Degree',type:'text',group:{kind:'education',identity:'Other School'}},packet,twoSchools).value,'Bachelor of Arts');
assert.equal(C.proposed({label:'Degree',type:'text',group:{kind:'education',identity:'UC Berkeley'}},packet,twoSchools).value,'Bachelor of Science');
twoSchools.application_profile.education.push(structuredClone(twoSchools.application_profile.education[0]));
assert.equal(C.proposed({label:'Degree',type:'text',group:{kind:'education',identity:'UC Berkeley'}},packet,twoSchools).value,undefined,'Repeated indistinguishable schools need explicit mapping');
assert.equal(C.proposed(menuField({label:'Disability Status',options:['No, I don’t have a disability.']}),packet,prefs).value,'No, I don’t have a disability.');
assert.equal(C.proposed(removed,packet,prefs).code,'option_missing','A removed explicit detail is an unavailable choice, not missing personal information');
const facets=structuredClone(prefs);
Object.assign(facets.application_profile.disclosures,{gender_identity:'Cisgender man',ethnicity:'East Asian',military_history:'I have never served in the military'});
for(const [label,choices,expected] of [
 ['What is your gender identity?',['Cisgender man','Transgender man'],'Cisgender man'],
 ['Race and ethnicity',['East Asian','South Asian'],'East Asian'],
 ['Military status',['I have never served in the military','Currently serving'],'I have never served in the military']
])assert.equal(C.proposed(menuField({label,options:choices}),packet,facets).value,expected);
const multi={label:'Select relevant skills',type:'checkbox',multiple:true,options:[{label:'Python',value:'p'},{label:'SQL',value:'s'},{label:'Java',value:'j'}],resolution:{value:['Python','SQL'],source:'Explicit answer'}};
assert.deepEqual(C.proposed(multi,packet,prefs).value,['Python','SQL']);
assert.deepEqual(C.matchChoice(multi,multi.resolution).options.map(o=>o.value),['p','s']);
assert.equal(C.matchChoice({...multi,multiple:false},multi.resolution).code,'unsupported');
assert.equal(C.matchChoice(multi,{value:['Python','Unavailable']}).code,'option_missing');
const gpa={label:'What is your cumulative GPA?',options:['4.0 or higher','3.5 - 3.99','3.49 - 3.0','2.99 or below'].map(label=>({label,value:label}))};
assert.equal(C.matchChoice(gpa,{value:'3.52',matchRule:{kind:'numeric_interval'}}).option.label,'3.5 - 3.99');
assert.equal(C.matchChoice(gpa,{value:'3.49',matchRule:{kind:'numeric_interval'}}).option.label,'3.49 - 3.0');
assert.equal(C.matchChoice({...gpa,options:[{label:'3.0 - 4.0'},{label:'3.5 - 4.0'}]},{value:'3.52',matchRule:{kind:'numeric_interval'}}).code,'option_ambiguous');

for(const subject of ['third_party','uncertain']){
  const f={label:'Email',type:'email',subject,section:'References',contextVersion:2};
  assert.equal(C.proposed(f,packet,{questions:[{question:'Email',answer:'wrong@example.test'}]}).value,undefined);
  assert.equal(C.proposed({...f,resolution:{value:'wrong@example.test'}},packet,prefs).value,undefined);
}
for(const end of ['2020-05','2030-05','', 'uncertain']){
  const education={application_profile:{education:[{institution:'Example',end}]}};
  for(const label of ['Current school','Which university are you currently attending?','Are you currently enrolled?'])assert.equal(C.proposed({label,type:'text'},packet,education).value,undefined);
}
assert.notDeepEqual(C.fieldContext({label:'Name',section:'Applicant',subject:'applicant'}),C.fieldContext({label:'Name',section:'References',subject:'third_party'}));
console.log('PASS: subject isolation and no current-enrollment inference');

assert.equal(!!C.thirdParty({label:'Why this role? Please reference one part of the role description.'}),false);
