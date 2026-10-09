import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {database} from './supabase.mjs';
import {analyze,verifySignature,hash,APIError} from './ai-core.mjs';
const seeds={'/media/flood-entrance.png':'image/png','/media/flood-stairwell.png':'image/png','/media/call-isolated.wav':'audio/wav','/media/call-proxy.wav':'audio/wav'};

// Only server code supplies hooks; the HTTP DTO has no command/provider/hook inputs.
export async function processJob(id,inputHash,env=process.env,hooks={}){
 const db=hooks.database||database(env);
 const job=await db.rpc('rescue_claim_job',{p_id:id,p_hash:inputHash});
 if(!job)return {statusCode:200,body:'already claimed or missing'};
 try{
  if(hash({report:job.report,intake119:job.intake119||null,incident_id:job.incident_id,expected_revision:job.expected_revision})!==inputHash)throw new APIError(400,'작업 입력 지문 불일치');
  const ws=await db.workspace();
  const readAttachment=async at=>{
   if(Object.hasOwn(seeds,at.url))return {bytes:await readFile(join(process.cwd(),'data',at.url.slice(1))),mime:seeds[at.url]};
   const up=ws.document.uploads[at.id];
   if(!up||up.url!==at.url||up.media_type!==at.media_type)throw new APIError(400,'서버 등록 첨부만 분석할 수 있습니다.');
   const response=await db.download(up.storage_key);
   return {bytes:Buffer.from(await response.arrayBuffer()),mime:up.content_type};
  };
  const provider=job.execution.provider||'openai';
  if(provider==='codex_cli'&&!hooks.local)throw new APIError(503,'Codex CLI는 로컬 시연 서버에서만 실행할 수 있습니다.');
  if(!hooks.analyze&&(provider!=='openai'||env.AI_PROVIDER!=='openai'))throw new APIError(503,'서버 AI 분석 provider가 비활성 상태입니다.');
  const result=await (hooks.analyze||analyze)(job,job.context_incidents,readAttachment,env);
  await db.rpc('rescue_finish_job',{p_id:job.id,p_payload:{status:'ready',...result,error:null}});
 }catch(e){
  await db.rpc('rescue_finish_job',{p_id:job.id,p_payload:{status:'failed',error:e.status?e.message:'실제 AI 분석 실패. 원문을 보존했습니다.',...(e.execution?{execution:e.execution}:{})}});
 }
 return {statusCode:200,body:'analysis processed'};
}
export async function run(event,env=process.env,hooks={}){
 let body;try{body=JSON.parse(event.body||'{}');}catch{return {statusCode:400,body:'invalid JSON'};}
 if(event.httpMethod!=='POST'||!verifySignature(body,env.BACKGROUND_HMAC_SECRET))return {statusCode:403,body:'signed server dispatch required'};
 return processJob(body.id,body.input_sha256,env,hooks);
}
export const handler=async event=>{try{return await run(event);}catch{return {statusCode:503,body:'background storage unavailable'};}};
