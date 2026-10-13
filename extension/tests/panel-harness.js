/* Test-only Chrome APIs; the real side panel is exercised against synthetic data. */
(() => {
  const fixture={id:'packet',revision:'v1',company:'Example',role:'Analyst',folder:'Example_Analyst_v1',pdf_name:'Sample.pdf',complete_history:true,
    personal_info:{full_name:'Daniel Example',email:'example@example.test'},education:[],experiences:[]};
  globalThis.panelTest={fills:[],activated:null,currentName:'',jobs:new Map(),jobCreates:0};
  const sessions=new Map();
  const api=async message=>{
    if(message.action==='choices')return [{label:'Yes',value:'yes'},{label:'No',value:'no'}];
    if(message.action==='settings')return {id:'a'.repeat(32),server:'http://127.0.0.1:8765',paired:true};
    if(message.action==='disconnect')return {};
    if(message.action==='scan'&&panelTest.prepare)return {supported:true,platform:'greenhouse',company:'Example',title:'Analyst',url:'https://job-boards.greenhouse.io/example/jobs/123',scanId:'scan',description:'Example analytics role',unsupported:[],fields:[
      ...(panelTest.failSchool?[{id:'school',name:'school',label:'School',type:'combobox',required:true,current:''}]:[]),
      {id:'name',label:'Full name',type:'text',required:true,current:panelTest.currentName},
      {id:'why',label:'Why this role?',type:'textarea',required:true,current:panelTest.currentWhy||'',limit:300},
      {id:'email',label:'Email',type:'text',required:true,current:panelTest.currentEmail||''},
      {id:'optional',label:'Additional information',type:'textarea',required:false,current:''}]};
    if(message.action==='scan')return {supported:true,title:'Analyst at Example',url:'https://jobs.lever.co/example/123/apply',scanId:'scan',description:'Example analytics role',fields:[
      {id:'name',label:'Full name',type:'text',current:panelTest.currentName},{id:'why',name:panelTest.questionName||'why',label:'Why this role?',type:'textarea',current:'',limit:300}]};
    if(message.action==='fill'){panelTest.fills.push(message);if(panelTest.prepare&&!panelTest.failFill)for(const c of message.changes){if(c.id==='name')panelTest.currentName=c.value;if(c.id==='why')panelTest.currentWhy=c.value;if(c.id==='email')panelTest.currentEmail=c.value;}return message.changes.map(c=>({id:c.id,status:panelTest.failFill||c.id==='school'?'failed':'filled',code:c.id==='school'?'option_missing':'retained',message:c.id==='school'?'No unique compatible dropdown option':'Verified'}));}
    if(message.route==='/resolve-fields')return panelTest.failSchool?{school:{value:'Example School',source:'Explicit education'}}:{};
    if(message.route==='/health')return {api_version:1,preparation_version:2};
    if(message.route==='/session'){const p=message.payload;if(!p.action&&panelTest.beforeSessionRead){const hook=panelTest.beforeSessionRead;panelTest.beforeSessionRead=null;hook();}if(p.action==='save')sessions.set(p.key,p.value);if(p.action==='clear')sessions.delete(p.key);if(p.action==='clear-all')sessions.clear();return sessions.get(p.key)||{};}
    if(message.route==='/jobs'){
      const p=message.payload;
      if(p.action==='cancel'){const job=panelTest.jobs.get(p.id||p.request_id);if(job&&job.status!=='complete')job.status='cancelled';return job;}
      if(p.action==='status'){if(panelTest.failJobStatus){panelTest.failJobStatus=false;throw new Error('Temporary connection failure');}const job=panelTest.jobs.get(p.id);if(job.status==='running')job.status='complete';return job;}
      if(!panelTest.jobs.has(p.request_id)){
        panelTest.jobCreates++;
        panelTest.jobs.set(p.request_id,{id:p.request_id,kind:p.kind,status:panelTest.failJobStatus?'running':'complete',result:p.kind==='resume'?{packet_id:'packet'}:{answer:'My Python automation experience is relevant.',citations:['experience:0:0'],evidence:{'experience:0:0':'Built Python automation.'}}});
      }
      if(panelTest.loseCreateResponse){panelTest.loseCreateResponse=false;throw new Error('Connection lost after accepting job');}
      return panelTest.jobs.get(p.request_id);
    }
    if(message.route==='/packets')return [{...fixture,version:'v1'}];
    if(message.route==='/preferences')return {facts:{},questions:[]};
    if(message.route==='/packet')return fixture;
    if(message.route==='/answer')return {answer:'My Python automation experience is relevant.',citations:['experience:0:0'],evidence:{'experience:0:0':'Built Python automation.'}};
    if(message.route==='/validate-answer'){if(panelTest.beforeValidation)panelTest.beforeValidation();return {...message.payload,evidence:{'experience:0:0':'Built Python automation.'}};}
    throw new Error('Unexpected test action');
  };
  globalThis.chrome={runtime:{sendMessage:async m=>{try{return {result:await api(m)};}catch(e){return {error:e.message};}}},tabs:{query:async()=>[{id:7}],onActivated:{addListener:f=>panelTest.activated=f},onUpdated:{addListener:()=>{}}}};
})();
