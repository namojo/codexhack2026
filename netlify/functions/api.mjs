import Pages from '../../web/pages-store.js';
import seedData from '../../data/seed.json' with {type:'json'};
import {randomUUID} from 'node:crypto';
import {database} from './supabase.mjs';
import {APIError,hash,signedPayload,schema,validateSchema} from './ai-core.mjs';
const safeID=/^[A-Za-z0-9_-]{1,100}$/;
const output=(statusCode,value)=>({statusCode,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'},body:JSON.stringify(value)});
export function optionalDailyLimit(env=process.env){
 const raw=env.AI_DAILY_LIMIT;
 if(raw===undefined||raw===null||raw==='')return null;
 if(!['string','number'].includes(typeof raw)||typeof raw==='string'&&!raw.trim())throw new APIError(503,'AI 일일 제한 설정이 잘못되었습니다.');
 const limit=Number(raw);
 if(!Number.isSafeInteger(limit)||limit<0||limit>1000)throw new APIError(503,'AI 일일 제한 설정이 잘못되었습니다.');
 return limit===0?null:limit;
}
// rawUrl is supplied by Netlify; client Host / forwarded headers never select dispatch.
export function backgroundOrigin(event,env=process.env){
 function secureURL(value,status){
  let url;
  try{
   if(typeof value!=='string'||/[\s\\]/.test(value)||!value.startsWith('https://'))throw new Error();
   url=new URL(value);
   const authority=/^https:\/\/([^/?#]+)/.exec(value)?.[1];
   // Compare the original authority too: URL normalizes an explicit :443 port away.
   if(url.protocol!=='https:'||url.username||url.password||url.port||authority!==url.hostname)throw new Error();
  }catch{throw new APIError(status,'background 호출 출처가 안전한 HTTPS 주소가 아닙니다.','background_origin_invalid');}
  return url;
 }
 const production=secureURL(env.URL,503);
 if(production.pathname!=='/'||production.search||production.hash)throw new APIError(503,'운영 사이트 주소 설정을 확인하세요.','background_origin_invalid');
 function sameSite(value,status){
  const url=secureURL(value,status),hostname=url.hostname;
  const suffix='--'+production.hostname;
  const preview=production.hostname.endsWith('.netlify.app')&&hostname.endsWith(suffix)&&/^[a-f0-9]{24}$/.test(hostname.slice(0,-suffix.length));
  if(hostname!==production.hostname&&!preview)throw new APIError(status,'같은 사이트의 운영 또는 지정 미리보기 출처만 허용됩니다.','background_origin_invalid');
  return url.origin;
 }
 if(event.rawUrl!==undefined&&event.rawUrl!==null&&event.rawUrl!=='')return sameSite(event.rawUrl,400);
 // Legacy/test events may omit rawUrl. Every server environment fallback is validated.
 for(const name of ['DEPLOY_URL','DEPLOY_PRIME_URL','URL'])if(env[name])return sameSite(env[name],503);
 throw new APIError(503,'background 배포 주소가 설정되지 않았습니다.','background_origin_invalid');
}
export function engine(document){const key='rescue-pages:v1:/',memory=new Map([[key,JSON.stringify(document)]]);const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v)};const store=Pages.createStore({storage,cloud:true});return {store,snapshot:()=>JSON.parse(memory.get(key))};}
function body(event){try{const b=JSON.parse(event.isBase64Encoded?Buffer.from(event.body||'','base64').toString():event.body||'{}');if(!b||typeof b!=='object'||Array.isArray(b))throw 0;return b;}catch{throw new APIError(400,'JSON 객체가 필요합니다.');}}
function keys(b,allowed,required=allowed){if(!b||typeof b!=='object'||Array.isArray(b))throw new APIError(400,'JSON 객체가 필요합니다.');if(Object.keys(b).some(k=>!allowed.includes(k))||required.some(k=>!Object.hasOwn(b,k)))throw new APIError(400,'알 수 없는 필드 또는 필수 입력 누락입니다.');}
function text(v,label){if(typeof v!=='string'||!v.trim()||v.length>20000)throw new APIError(400,`${label}을 입력하세요.`);}
export function validateIntake(v){
 function partial(value,shape){if(shape.type==='object'){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!Object.hasOwn(shape.properties,k)))throw new Error();for(const [k,x] of Object.entries(value))partial(x,shape.properties[k]);}else validateSchema(value,shape);}
 try{partial(v,schema.properties.intake119);}catch{throw new APIError(400,'119 접수 정보의 필드/값을 확인하세요.');}
}
async function workspace(db){try{return await db.workspace();}catch(e){if(!e.message.includes('초기 등록'))throw e;const seed=seedData;if(seed.synthetic!==true)throw new APIError(503,'합성 초기 자료만 허용됩니다.');return db.rpc('rescue_init',{p_document:{schema_version:1,synthetic:true,incidents:seed.incidents,resources:seed.resources,uploads:{}}});}}
function publicJob(j){if(!j)throw new APIError(404,'분석 작업을 찾을 수 없습니다.');const {context_incidents,confirmation,synthetic,...value}=j;return value;}
export function cloudAIConfig(env=process.env){
 const provider=env.AI_PROVIDER||'disabled';
 if(!['disabled','openai','codex_cli'].includes(provider))throw new APIError(503,'AI provider 서버 설정이 잘못되었습니다.');
 const configured=provider==='openai'&&!!(env.OPENAI_API_KEY&&env.OPENAI_MODEL);
 return {provider,configured,enabled:configured,model:provider==='openai'?env.OPENAI_MODEL||null:null,local_demo:false,
  login:{status:'local_only',detail:'ChatGPT 로그인 Codex CLI는 로컬 시연 서버에서 사용합니다.'},
  asr:{available:configured,provider:configured?'openai':'none',model:configured?(env.OPENAI_TRANSCRIBE_MODEL||'gpt-4o-mini-transcribe'):null}};
}
export function settingsFromConfig(ai,env=process.env){
 return {provider:ai.provider,local_demo:ai.local_demo,mutable:false,capabilities:{codex_cli:{installed:false,logged_in:false,login_status:'로컬 시연 서버에서 codex login으로 ChatGPT 로그인'},openai:{configured:!!(env.OPENAI_API_KEY&&env.OPENAI_MODEL)},asr:ai.asr},instructions:['로컬 시연: node scripts/serve_codex_demo.mjs --env-stdin --static dist/ai-preview','Codex CLI 로그인: codex login','OpenAI API는 서버 OPENAI_API_KEY/OPENAI_MODEL 설정 후 AI_PROVIDER=openai로 활성화합니다. 브라우저에는 키를 입력하지 않습니다.']};
}
export async function handle(event,env=process.env,hooks={}){const path=(event.path||'').replace(/^\/.netlify\/functions\/api/,'/api'),method=event.httpMethod||'GET';const getAIConfig=()=>hooks.aiConfig?hooks.aiConfig():cloudAIConfig(env);if(path==='/api/config'&&method==='GET')return output(200,{storage:env.SUPABASE_URL&&env.SUPABASE_SERVICE_ROLE_KEY?'supabase':'unconfigured',ai:await getAIConfig(),synthetic:true,offline_available:true});if(path==='/api/settings'){if(method!=='GET')throw new APIError(405,'공개 서버에서는 AI 설정을 변경할 수 없습니다.');return output(200,settingsFromConfig(await getAIConfig(),env));}
 const db=database(env);const jobMatch=/^\/api\/ai\/analyses\/([A-Za-z0-9_-]+)(\/confirm)?$/.exec(path);
 if(jobMatch&&method==='GET'&&!jobMatch[2])return output(200,publicJob(await db.rpc('rescue_get_job',{p_id:jobMatch[1]})));
 const ws=await workspace(db),{store,snapshot}=engine(ws.document);if(path==='/api/ai/analyses'&&method==='POST'){
  const b=body(event);keys(b,['synthetic','incident_id','expected_revision','report','intake119'],['synthetic','incident_id','expected_revision','report']);if(b.synthetic!==true)throw new APIError(400,'합성 데이터만 분석할 수 있습니다.');const ai=await getAIConfig(),provider=ai.provider;if(!ai.enabled||!ai.configured||provider==='disabled'||provider==='codex_cli'&&(!hooks.local||!hooks.dispatch)||provider==='openai'&&(!env.OPENAI_API_KEY||!env.OPENAI_MODEL)||!hooks.dispatch&&!env.BACKGROUND_HMAC_SECRET)throw new APIError(503,'AI 분석이 비활성 또는 연결되지 않았습니다. 설정에서 실행 방식을 확인하세요.','ai_unconfigured');
  if(b.incident_id!==null){if(!safeID.test(b.incident_id))throw new APIError(400,'사건 ID를 확인하세요.');const i=await store.request('/api/incidents/'+b.incident_id);if(!Number.isSafeInteger(b.expected_revision)||i.revision!==b.expected_revision)throw new APIError(409,'분석할 사건 revision이 변경되었습니다.');}else if(b.expected_revision!==null)throw new APIError(400,'신규 분석 revision은 null이어야 합니다.');
  keys(b.report,['channel','actor','text','kind','attachments','occurred_at'],['channel','actor','text','kind','attachments']);text(b.report.actor,'담당자');text(b.report.text,'신고 원문');if(!['initial','additional','field'].includes(b.report.kind)||!['voice','sms','mms','app','video_call','web','field','kakao'].includes(b.report.channel)||b.incident_id===null&&b.report.kind!=='initial'||b.incident_id!==null&&b.report.kind==='initial')throw new APIError(400,'신고 채널/종류를 확인하세요.');if(b.report.occurred_at!==undefined&&(!/^(?:\d{4}-\d\d-\d\d)T/.test(b.report.occurred_at)||!Number.isFinite(Date.parse(b.report.occurred_at))))throw new APIError(400,'발생 시각을 확인하세요.');
  const reservedSources=new Set(['input',...ws.document.incidents.flatMap(i=>i.reports.map(r=>r.id))]);if(!Array.isArray(b.report.attachments)||b.report.attachments.some(a=>reservedSources.has(a?.id)))throw new APIError(400,'첨부 ID가 원문/보고 ID와 충돌합니다.');
  // Run the same registry validation used by CRUD on an isolated document; never commit the probe.
  await store.request('/api/incidents',{method:'POST',body:{title:'AI 입력 검증',location:'담당자 확인 전',text:b.report.text,channel:b.report.channel,actor:b.report.actor,attachments:b.report.attachments}});if(b.intake119!==undefined)validateIntake(b.intake119);
  const timestamp=new Date().toISOString(),id='AI-'+randomUUID(),job={id,synthetic:true,status:'queued',incident_id:b.incident_id,expected_revision:b.expected_revision,created_at:timestamp,updated_at:timestamp,report:b.report,...(b.intake119?{intake119:b.intake119}:{}),analysis:null,execution:{mode:'live',provider,input_sha256:hash({report:b.report,intake119:b.intake119||null,incident_id:b.incident_id,expected_revision:b.expected_revision})},error:null,context_incidents:ws.document.incidents};const limit=optionalDailyLimit(env);
  const trigger=hooks.dispatch?null:new URL('/.netlify/functions/ai-analysis-background',backgroundOrigin(event,env));
  await db.rpc('rescue_create_job',{p_job:job,p_limit:limit});try{if(hooks.dispatch)await hooks.dispatch(job);else{const response=await fetch(trigger,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(signedPayload(job,env.BACKGROUND_HMAC_SECRET)),redirect:'error',signal:AbortSignal.timeout(10000)});if(response.status!==202)throw 0;}}catch{await db.rpc('rescue_finish_job',{p_id:id,p_payload:{status:'failed',error:'background 분석 시작에 실패했습니다. 원문을 보존했습니다.'}});throw new APIError(502,'AI 작업 시작 실패: 원문이 작업 기록에 보존됩니다.','background_dispatch_failed');}return output(202,{id,status:'queued',incident_id:job.incident_id,expected_revision:job.expected_revision,created_at:timestamp});
 }
 if(jobMatch&&method==='POST'&&jobMatch[2]){
  const b=body(event);keys(b,['synthetic','actor','expected_revision','reason','changes']);if(b.synthetic!==true)throw new APIError(400,'합성 확인만 허용됩니다.');text(b.actor,'담당자');text(b.reason,'검토 사유');const job=await db.rpc('rescue_get_job',{p_id:jobMatch[1]});if(!job)throw new APIError(404,'분석 작업이 없습니다.');if(b.expected_revision!==job.expected_revision)throw new APIError(409,'분석 입력 revision과 확인 revision이 다릅니다.');if(job.status==='confirmed')return output(200,job.confirmation);if(job.status!=='ready')throw new APIError(409,'성공한 AI 초안만 확인할 수 있습니다.');keys(b.changes,['title','category','location','people_count','priority','summary','intake119'],[]);if(b.changes.intake119!==undefined)validateIntake(b.changes.intake119);let incident;
  if(job.incident_id===null){incident=await store.request('/api/incidents',{method:'POST',body:{...Object.fromEntries(Object.entries(b.changes).filter(([k,v])=>k!=='people_count'||v!==null)),channel:job.report.channel,text:job.report.text,actor:b.actor,attachments:job.report.attachments}});}else{const i=await store.request('/api/incidents/'+job.incident_id);if(i.revision!==job.expected_revision)throw new APIError(409,'분석 후 사건이 바뀌었습니다. 다시 분석하세요.');for(const [field,value]of Object.entries(b.changes)){if(['title','location'].includes(field))text(value,field);if(field==='summary'&&(typeof value!=='string'||value.length>20000))throw new APIError(400,'요약을 확인하세요.');if(field==='people_count'&&value!==null&&(!Number.isSafeInteger(value)||value<0))throw new APIError(400,'인원은 0 이상 정수여야 합니다.');if(field==='category'&&!['flood','fire','rescue','medical','other'].includes(value)||field==='priority'&&!['urgent','high','normal'].includes(value))throw new APIError(400,'분류/우선도를 확인하세요.');}incident=await store.request('/api/incidents/'+i.id+'/reports',{method:'POST',body:{expected_revision:i.revision,channel:job.report.channel,actor:b.actor,text:job.report.text,kind:job.report.kind,attachments:job.report.attachments,...(b.changes.people_count!==undefined&&b.changes.people_count!==null?{people_count:b.changes.people_count}:{}),...(b.changes.location!==undefined?{location:b.changes.location}:{})}});}
  const doc=snapshot(),i=doc.incidents.find(i=>i.id===incident.id),old={};for(const k of Object.keys(b.changes))old[k]=i[k]??null;Object.assign(i,b.changes);const report=i.reports.at(-1);report.occurred_at=job.report.occurred_at||report.occurred_at;report.ai_analysis={analysis_id:job.id,analysis:job.analysis,execution:job.execution,confirmed_by:b.actor,confirmed_reason:b.reason};i.audit.push({id:'AUD-'+randomUUID(),action:'ai_review_confirmed',actor:b.actor,reason:b.reason,created_at:new Date().toISOString(),before:old,after:b.changes});const result={incident:await engine(doc).store.request('/api/incidents/'+i.id),analysis_id:job.id};return output(200,await db.rpc('rescue_confirm_job',{p_id:job.id,p_revision:ws.revision,p_document:doc,p_result:result}));
 }
 const media=/^\/api\/media\/([A-Za-z0-9_-]+)$/.exec(path);if(media&&method==='GET'){const at=ws.document.uploads[media[1]];if(!at)throw new APIError(404,'등록된 첨부가 없습니다.');const r=await db.download(at.storage_key);const data=Buffer.from(await r.arrayBuffer());return {statusCode:200,headers:{'Content-Type':at.content_type,'Content-Length':String(data.length),'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'},isBase64Encoded:true,body:data.toString('base64')};}
 if(path==='/api/uploads'&&method==='POST'){const b=body(event);if(typeof b.data_base64!=='string'||b.data_base64.length>4*Math.ceil(3*1024*1024/3))throw new APIError(413,'클라우드 첨부는 최대 3MiB입니다.');const at=await store.request(path,{method,body:b}),doc=snapshot(),bytes=Buffer.from(b.data_base64,'base64');if(bytes.length>3*1024*1024)throw new APIError(413,'클라우드 첨부는 최대 3MiB입니다.');at.url='/api/media/'+at.id;doc.uploads[at.id]={...at,content_type:b.content_type,storage_key:at.id};await db.upload(at.id,bytes,b.content_type);try{await db.rpc('rescue_cas',{p_revision:ws.revision,p_document:doc});}catch(e){try{await db.remove(at.id);}catch{}throw e;}return output(201,at);}
 if(!path.startsWith('/api/incidents'))throw new APIError(404,'API 경로를 찾을 수 없습니다.');const b=method==='GET'?undefined:body(event);if(b?.intake119!==undefined)validateIntake(b.intake119);const result=await store.request(path,{method,body:b});if(method!=='GET')await db.rpc('rescue_cas',{p_revision:ws.revision,p_document:snapshot()});return output(path==='/api/incidents'&&method==='POST'?201:200,result);
}
export const handler=async event=>{try{return await handle(event);}catch(e){return output(e.status||500,{error:e.status?e.message:'서버 처리에 실패했습니다. 원문을 보존하고 다시 확인하세요.',...(e.code?{code:e.code}:{})});}};
