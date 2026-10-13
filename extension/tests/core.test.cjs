const assert=require('node:assert/strict');
const C=require('../core.js');
let count=0;
function test(name,fn){fn();count++;console.log('PASS '+name);}
const packet={pdf_name:'Daniel_Example.pdf',complete_history:false,personal_info:{full_name:'Daniel Suh',email:'sample@example.org',linkedin:'linkedin.com/in/sample'},experiences:[{company:'Example',role:'Analyst',date_range:'May 2025 – Present',bullets:['Saved 50 hours weekly.']}],education:[{institution:'Example University',degree:'Bachelor of Science',graduation_date:'May 2028'}]};
const field=(label,type='text',extra={})=>({label,type,...extra});
const propose=(f,p={facts:{},questions:[]})=>C.proposed(f,packet,p);
test('Only explicit supported HTTPS hosts',()=>{assert.equal(C.platform('https://jobs.lever.co/example/123/apply'),'lever');assert.equal(C.platform('https://job-boards.greenhouse.io/example/jobs/1'),'greenhouse');assert.equal(C.platform('https://jobs.lever.co.evil.test/a'),null);assert.equal(C.platform('http://jobs.lever.co/a'),null);});
test('Name components are not guessed',()=>{assert.equal(propose(field('Full name')).value,'Daniel Suh');assert.equal(propose(field('First name')).value,undefined);assert.equal(propose(field('First name'),{facts:{first_name:'Daniel'},questions:[]}).value,'Daniel');});
test('Profile URLs gain HTTPS',()=>assert.equal(propose(field('LinkedIn')).value,'https://linkedin.com/in/sample'));
test('Unconfigured clients stay restrictive, even with saved answers',()=>{for(const label of ['Gender','Veteran status','I agree to processing','Disability','Social Security Number','Citizenship'])assert.equal(propose(field(label),{facts:{},questions:[{question:label,answer:'Yes'}]}).value,undefined);});
test('Exact explicit answers only; sponsorship is never inferred',()=>{const prefs={facts:{},questions:[{question:'Do you require sponsorship in the US?',answer:'Yes'}]};assert.equal(propose(field('Do you require sponsorship in the US?'),prefs).value,'Yes');assert.equal(propose(field('Do you require sponsorship in Canada?'),prefs).value,undefined);});
test('Selected experience descriptions retain their exact bullets',()=>assert.equal(propose(field('Description','textarea',{group:{kind:'employment',identity:'Example',role:'Analyst'}})).value,'Saved 50 hours weekly.'));
test('Repeated entries beyond selected experience remain manual',()=>assert.equal(propose(field('Company','text',{group:{kind:'employment',index:1}})).value,undefined));
test('Complete history requires manual review if entries omitted',()=>assert.equal(propose(field('Describe your complete work history','textarea')).written,undefined));
test('PDF only for resume field',()=>{assert.equal(propose(field('Resume','file')).file,true);assert.equal(propose(field('Transcript','file')).file,undefined);});
test('Open-ended answers require an explicit draft request; personal facts not drafted',()=>{assert.equal(propose(field('Why this role?','textarea')).written,true);assert.equal(propose(field('Describe your salary expectations','textarea')).written,undefined);});
test('Exact dropdown option or manual',()=>{const f=field('Country','select',{options:[{label:'United States',value:'US'}]});assert.equal(propose(f,{facts:{country:'United States'}}).value,'United States');assert.equal(propose(f,{facts:{country:'US'}}).value,undefined);assert.equal(C.exactOption([{label:'Yes',value:'a'},{label:'Yes',value:'b'}],'Yes'),null);});
test('Never silently truncate',()=>assert.equal(propose(field('Full name','text',{limit:3})).value,undefined));
test('Month known does not invent a day',()=>{const group={kind:'education',identity:'Example University'};assert.equal(propose(field('Graduation date','date',{group})).value,undefined);assert.equal(propose(field('Graduation date','month',{group})).value,'2028-05');});

test('Empty and conflicting history rows never use ordinal position',()=>{assert.equal(propose(field('Description','textarea',{group:{kind:'employment',index:0}})).value,undefined);assert.equal(propose(field('Description','textarea',{group:{kind:'employment',identity:'Other'}})).value,undefined);});
test('Written preferences cannot bypass per-posting evidence validation',()=>{const q='What interests you about this position?';assert.equal(propose(field(q,'textarea'),{questions:[{question:q,answer:'Old company essay'}]}).written,true);});
test('Posting identity ignores tracking and apply step',()=>{assert.equal(C.postingKey('https://jobs.lever.co/example/123/apply?utm_source=x'),C.postingKey('https://jobs.lever.co/example/123'));assert.notEqual(C.postingKey('https://jobs.lever.co/example/123'),C.postingKey('https://jobs.lever.co/other/123'));});
for(const fixture of require('./question-fixtures.json'))test('Shared written-question rule: '+fixture.question,()=>assert.equal(C.writtenQuestion(fixture.question),fixture.written));

test('Established conditional No is not an unanswered fact',()=>{const result=propose(field('If you answered "Yes" to the above question, provide details','textarea',{notApplicable:true}));assert.equal(result.notApplicable,true);assert.equal(result.value,undefined);assert.equal(result.written,undefined);});
console.log(`${count} mapping tests passed`);
