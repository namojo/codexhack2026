'use strict';
// Independent regression: synthetic inputs, mocked network, actual production modules.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),checks=[],clone=x=>structuredClone(x),tick=()=>new Promise(r=>setImmediate(r));
const json=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
function empty(s){if(s.anyOf)return null;if(s.enum)return s.enum.includes(null)?null:s.enum[0];if(Array.isArray(s.type))return null;if(s.type==='object')return Object.fromEntries(Object.entries(s.properties).map(([k,v])=>[k,empty(v)]));return {array:[],string:'',integer:0,number:0,boolean:true}[s.type];}
async function check(name,fn){try{await fn();checks.push({name,status:'passed'});console.log('PASS',name);}catch(e){checks.push({name,status:'failed',evidence:e.stack});console.error('FAIL',name,e.stack);}}
(async()=>{
 const core=await import(pathToFileURL(path.join(root,'netlify/functions/ai-core.mjs'))),dto=()=>empty(core.schema);
 const env={OPENAI_API_KEY:'SYNTHETIC-SECRET-CANARY',OPENAI_MODEL:'mock-only',OPENAI_TRANSCRIBE_MODEL:'mock-asr'};
 const report=text=>({channel:'sms',kind:'initial',actor:'합성 QA',text,attachments:[]});
 const evidence=(id,type,quote)=>({field:'summary',source_id:id,type,quote,observation:null});
 for(const [name,separator]of [['LF','\n'],['CRLF','\r\n'],['TAB','\t'],['UNICODE-LINE','\u2028']])await check(name+' multiline input existing report ASR schemas retain exact source and reject invented quotes',()=>{
  const r=report('  합성 입력 하나'+separator+'합성 입력 둘  ');r.attachments=[{id:'A',media_type:'audio'},{id:'P',media_type:'image'}];
  const incidents=[{id:'I',reports:[{id:'R',text:'합성 기존 하나'+separator+'합성 기존 둘'}]}],ts=[{attachment_id:'A',text:'합성 음성 하나'+separator+'합성 음성 둘',model:'mock-asr'}],before=clone([r,incidents,ts]);
  const s=core.citationSchema(r,incidents,ts),branches=s.properties.evidence.items.anyOf;
  assert.deepEqual(branches.map(b=>b.properties.source_id.enum[0]),['input','R','A','P']);
  for(const [source,kind,text]of [['input','text',r.text],['R','text',incidents[0].reports[0].text],['A','audio_transcript',ts[0].text]]){
   const b=branches.find(b=>b.properties.source_id.enum[0]===source);assert.equal(b.properties.quote.enum.length,2);
   for(const q of b.properties.quote.enum){assert(text.includes(q));assert(!/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u.test(q));const a=dto();a.transcripts=clone(ts);a.evidence=[evidence(source,kind,q)];core.validateSchema(a,s);core.validateAnalysis(a,r,incidents,ts);
    for(const bad of [{quote:'허위 인용'},{source_id:source==='input'?'R':'input'},{type:'image_observation'}]){const forged=clone(a);Object.assign(forged.evidence[0],bad);assert.throws(()=>core.validateSchema(forged,s));assert.throws(()=>core.validateAnalysis(forged,r,incidents,ts));}
   }
  }
  assert.deepEqual([r,incidents,ts],before);const a=dto();a.transcripts=clone(ts);a.evidence=[{field:'hazards',source_id:'P',type:'image_observation',quote:null,observation:'합성 사진 물 관찰'}];core.validateSchema(a,s);core.validateAnalysis(a,r,incidents,ts);
 });
 await check('text-only actual analyze request is strict with original LF report unchanged',async()=>{
  const old=global.fetch,r=report('  합성 가상빌라\n두 명 고립\r\n도움 요청\t201호  '),before=clone(r);let calls=0;
  global.fetch=async(url,options)=>{calls++;assert.equal(String(url),'https://api.openai.com/v1/responses');const body=JSON.parse(options.body),packet=JSON.parse(body.input[0].content[0].text);assert.equal(packet.report.text,r.text);assert.equal(body.input[0].content.length,1);assert.equal(body.text.format.strict,true);assert.equal(body.store,false);const a=dto();a.evidence=[evidence('input','text','두 명 고립')];core.validateSchema(a,body.text.format.schema);return json({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(a)}]}]});};
  try{const out=await core.analyze({report:r,execution:{}},[],()=>{throw Error('text-only must not fetch media');},env);assert.equal(out.analysis.evidence[0].quote,'두 명 고립');assert.equal(calls,1);assert.deepEqual(r,before);}finally{global.fetch=old;}
 });
 await check('multimedia actual request uses bytes and multiline ASR tied to audio source',async()=>{
  const old=global.fetch,r=report('합성 문자\n현재 신고'),ts='합성 전사 하나\r\n합성 전사 둘\t호흡 확인 필요';r.attachments=[{id:'P',media_type:'image',filename:'qa.png'},{id:'A',media_type:'audio',filename:'qa.wav',transcript:'DO NOT TRUST'}];let calls=0;
  global.fetch=async(url,options)=>{calls++;if(String(url).endsWith('/audio/transcriptions'))return json({text:ts});const b=JSON.parse(options.body),p=JSON.parse(b.input[0].content[0].text);assert.equal(p.transcripts[0].text,ts);assert(!b.input[0].content[0].text.includes('DO NOT TRUST'));assert.equal(b.input[0].content[1].image_url,'data:image/png;base64,cGlj');const a=dto();a.transcripts=p.transcripts;a.evidence=[evidence('input','text','현재 신고'),evidence('A','audio_transcript','합성 전사 둘'),{field:'hazards',source_id:'P',type:'image_observation',quote:null,observation:'합성 사진 관찰'}];core.validateSchema(a,b.text.format.schema);return json({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(a)}]}]});};
  try{const before=clone(r),out=await core.analyze({report:r,execution:{}},[],async at=>({bytes:Buffer.from(at.id==='P'?'pic':'audio'),mime:at.id==='P'?'image/png':'audio/wav'}),env);assert.equal(out.analysis.transcripts[0].text,ts);assert.deepEqual(r,before);assert.equal(calls,2);}finally{global.fetch=old;}
 });
 await check('provider errors classify without leaking message key URL headers or malformed body',async()=>{
  const old=global.fetch,canary='SYNTHETIC-SECRET-CANARY',r=report('합성 원문\n보존');
  try{for(const [status,code,expected]of [[400,'invalid_json_schema','ai_schema_rejected'],[401,'invalid_api_key','ai_authentication'],[429,'rate_limit_exceeded','ai_rate_limit'],[503,'internal_error','ai_provider_unavailable']]){
    global.fetch=async()=>json({error:{code,message:canary+' https://private.test '+r.text,param:'text.format.schema',headers:{Authorization:canary}}},status);
    let error;try{await core.analyze({report:r,execution:{}},[],async()=>{},env);}catch(e){error=e;}assert(error);assert.equal(error.code,expected);assert(!JSON.stringify(error).includes(canary));assert(!error.message.includes(canary));assert(!JSON.stringify(error).includes('private.test'));assert.equal(error.execution.provider_error.http_status,status);
   }
   global.fetch=async()=>new Response(canary+' not json',{status:400});await assert.rejects(()=>core.analyze({report:r,execution:{}},[],async()=>{},env),e=>e.status===502&&!JSON.stringify(e).includes(canary)&&!e.message.includes(canary));
  }finally{global.fetch=old;}
 });
 const {createClient}=require('../web/cloud-client.js');
 function harness(){
  const nodes=new Map(),saved=new Map(),fields={},callbacks=[];let posts=[],confirms=0;
  function el(id){if(nodes.has(id))return nodes.get(id);const n={id,innerHTML:'',textContent:'',hidden:false,disabled:false,open:false,isConnected:true,listeners:{},addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);},async emit(type,event={}){for(const fn of this.listeners[type]||[])await fn(event);},querySelectorAll(){return [];},querySelector(){return el('control');},setAttribute(){},replaceChildren(){this.innerHTML='';},append(){},focus(){},showModal(){this.open=true;},close(){this.open=false;for(const fn of this.listeners.close||[])fn({});},reset(){}};nodes.set(id,n);return n;}
  const cloud={mode:'cloud',config:{ai:{configured:true}},remembered:()=>null,boot:async()=>({mode:'cloud'}),request:async p=>p==='/api/incidents'?{incidents:[],resources:[]}:{id:'I',revision:2},createAnalysis:async payload=>{posts.push(clone(payload));return {id:'JOB',status:'queued'};},startPolling:(_id,cb)=>{callbacks.push(cb);return ()=>{};},confirm:async()=>{confirms++;throw Object.assign(Error('conflict'),{status:409});}};
  const ctx=vm.createContext({console,Date,Intl,URL,AbortController,setTimeout:()=>1,clearTimeout(){},FormData:class{constructor(){return Object.entries(fields);}},sessionStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},document:{getElementById:el,querySelectorAll:()=>[],querySelector:()=>null,createElement:el,documentElement:{dataset:{serviceMode:'cloud'}},activeElement:el('focus')},window:{RescueCloud:cloud,addEventListener(){},scrollTo(){}},location:{hash:''},history:{pushState(){}}});
  vm.runInContext(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),ctx);
  return {ctx,el,cloud,fields,saved,callbacks,posts,get confirms(){return confirms;},run:s=>vm.runInContext(s,ctx)};
 }
 const source={channel:'sms',kind:'initial',actor:'합성 QA',text:'  합성 원문 <tag>\n두 명 고립\r\n\t  '},attachment={id:'UP-QA',filename:'synthetic.png',url:'/api/media/UP-QA',media_type:'image'};
 const start=async h=>{await tick();h.run('openAI()');Object.assign(h.fields,source);h.ctx.attach=clone(attachment);h.run('aiState.attachments=[attach]');await h.run('beginAI()');};
 for(const terminal of ['ready','failed'])await check('begin queued to '+terminal+' unlocks retry and preserves raw attachments without confirmation',async()=>{
  const h=harness();await start(h);assert.equal(h.el('ai-retry').disabled,true);assert.equal(h.run('aiState.busy'),true);const original=clone(h.posts[0]);
  const draft={id:'JOB',status:terminal,incident_id:null,expected_revision:null,report:original.report,analysis:terminal==='ready'?dto():null,execution:{},error:'합성 HTTP400'};h.callbacks[0].onUpdate(draft);
  assert.equal(h.el('ai-retry').disabled,false);assert.equal(h.run('aiState.busy'),false);assert.equal(h.confirms,0);assert.equal(h.posts.length,1);assert.equal(h.el('ai-submit').hidden,terminal==='failed');assert(!h.el('ai-fields').innerHTML.includes('분석 작업이 접수되었습니다'));assert(h.el('ai-fields').innerHTML.includes('&lt;tag&gt;'));
  assert.equal(h.run('aiState.draft.report.text'),source.text);assert.equal(h.run('aiState.attachments[0].id'),attachment.id);
  await h.el('ai-retry').emit('click');assert.equal(h.run('aiState.draft'),null);assert.equal(h.el('ai-submit').disabled,false);assert.equal(h.run('aiState.sourceValues.text'),source.text);
  h.fields.text='수정된 합성 원문\n세 명';await h.run('beginAI()');assert.equal(h.posts[1].report.text,h.fields.text);assert.deepEqual(h.posts[1].report.attachments,[attachment]);assert.equal(original.report.text,source.text);
 });
 await check('failed recovery takes server original attachment and enables editable retry',async()=>{const h=harness();await tick();h.cloud.getAnalysis=async()=>({id:'RECOVER',status:'failed',incident_id:null,expected_revision:null,report:{...source,attachments:[attachment]},error:'합성 실패'});await h.run("recoverAI('RECOVER')");assert.equal(h.el('ai-retry').disabled,false);assert.equal(h.run('aiState.sourceValues.text'),source.text);assert(h.el('ai-fields').innerHTML.includes(attachment.filename));await h.el('ai-retry').emit('click');assert.equal(h.run('aiState.attachments[0].id'),attachment.id);assert.equal(h.run('aiState.sourceValues.text'),source.text);assert.equal(h.confirms,0);});
 await check('create HTTP failure preserves editable values attachment and allows same form resubmission',async()=>{const h=harness();await tick();h.cloud.createAnalysis=async()=>{throw Error('합성 HTTP400');};await start(h);assert.equal(h.el('ai-submit').disabled,false);assert.equal(h.run('aiState.sourceValues.text'),source.text);assert.equal(h.run('aiState.attachments[0].id'),attachment.id);assert.match(h.el('ai-error').textContent,/400/);const saved=JSON.parse(h.saved.get('rescue-ai-input-v1'));assert.equal(saved.values.text,source.text);h.cloud.createAnalysis=async p=>{h.posts.push(clone(p));return {id:'RETRY',status:'queued'};};h.fields.text='편집 합성 원문';await h.run('beginAI()');assert.equal(h.posts[0].report.text,h.fields.text);});
 await check('stale recovered review blocks form confirm while retry remains available',async()=>{const h=harness();await tick();h.cloud.getAnalysis=async()=>({id:'STALE',status:'ready',incident_id:'I',expected_revision:1,report:{...source,attachments:[]},analysis:dto(),execution:{}});await h.run("recoverAI('STALE')");assert.equal(h.run('aiState.stale'),true);assert.equal(h.el('ai-submit').disabled,true);assert.equal(h.el('ai-retry').disabled,false);await h.el('ai-form').emit('submit',{preventDefault(){}});assert.equal(h.confirms,0);assert.equal(h.posts.length,0);});
 await check('cancel rejects late poll callbacks and late recovery cannot replace reopened input',async()=>{const h=harness();await start(h);h.run('stopAI()');h.callbacks[0].onUpdate({id:'LATE',status:'failed',report:{text:'must not show'}});assert.equal(h.el('ai-dialog').open,false);assert.equal(h.run('aiState.draft.id'),'JOB');assert(!h.el('ai-fields').innerHTML.includes('must not show'));let resolve;h.cloud.getAnalysis=()=>new Promise(r=>resolve=r);const recovering=h.run("recoverAI('OLD')");h.saved.clear();h.run('openAI()');resolve({id:'OLD',status:'failed',incident_id:null,report:{text:'must not show'}});await recovering;assert.equal(h.run('aiState.draft'),null);});
 await check('cancel while create pending ignores late job and preserves source',async()=>{const h=harness();await tick();let resolve;h.cloud.createAnalysis=()=>new Promise(r=>resolve=r);h.run('openAI()');Object.assign(h.fields,source);const pending=h.run('beginAI()');h.run('stopAI()');resolve({id:'LATE',status:'queued'});await pending;assert.equal(h.run('aiState.draft'),null);assert.equal(h.callbacks.length,0);assert.equal(h.el('ai-dialog').open,false);assert.equal(JSON.parse(h.saved.get('rescue-ai-input-v1')).values.text,source.text);});
 await check('poll deadline aborts hung fetch reports timeout once unlocks UI and ignores late ready',async()=>{
  const h=harness();await start(h);const timers=new Map();let serial=0,resolve,signal,errors=0;
  const c=createClient({setTimer:(fn,ms)=>{timers.set(++serial,{fn,ms});return serial;},clearTimer:id=>timers.delete(id),fetch:(_p,o)=>{signal=o.signal;return new Promise(r=>resolve=r);}});
  c.startPolling('JOB',{timeout:19,onUpdate:h.callbacks[0].onUpdate,onError:e=>{errors++;assert.equal(e.code,'analysis_timeout');h.callbacks[0].onError(e);}});const deadline=[...timers.values()].find(t=>t.ms===19);assert(deadline);deadline.fn();assert.equal(signal.aborted,true);assert.equal(timers.size,0);assert.equal(errors,1);assert.equal(h.el('ai-retry').disabled,false);assert.equal(h.el('ai-submit').hidden,true);assert.equal(h.run('aiState.sourceValues.text'),source.text);resolve(json({status:'ready',analysis:dto()}));await tick();deadline.fn();assert.equal(errors,1);assert.equal(h.run('aiState.draft.status'),'queued');
 });
 const result={mode:'mocked_transport_and_DOM_not_browser',live_calls:false,checks};
 if(process.env.AI_QA_RUN_ID){const dir=path.join(root,'_workspace/verification',process.env.AI_QA_RUN_ID,'qa');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'intake-checks.json'),JSON.stringify(result,null,2)+'\n');}
 console.log(JSON.stringify({passed:checks.filter(c=>c.status==='passed').length,failed:checks.filter(c=>c.status==='failed').length}));if(checks.some(c=>c.status==='failed'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
