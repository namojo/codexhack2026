#!/usr/bin/env node
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,readFile,rm,stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import Pages from '../web/pages-store.js';
import {APIError,INSTRUCTIONS,hash,schema,validateAnalysis,sourceCatalog,finishExecution,validationDetails} from '../netlify/functions/ai-core.mjs';
const ROOT=resolve(fileURLToPath(new URL('..',import.meta.url)));
const SCHEMA=join(ROOT,'service/ai_schema.json');

// Fixed executables/argv are constructed in server code, never from HTTP options.
export function boundedSpawn(executable,args,{cwd,env,stdin='',timeout=480000,maxBuffer=4*1024*1024,allowFailure=false}={}){
 return new Promise((accept,reject)=>{
  const child=spawn(executable,args,{cwd,env,stdio:['pipe','pipe','pipe'],shell:false});
  const stdout=[],stderr=[];let size=0,settled=false,killTimer;
  const fail=message=>{if(settled)return;settled=true;child.kill('SIGTERM');killTimer=setTimeout(()=>child.kill('SIGKILL'),1000);reject(new APIError(502,message));};
  const timer=setTimeout(()=>fail('실제 로컬 분석 시간초과입니다. 원문을 보존했습니다.'),timeout);
  for(const [stream,name] of [[child.stdout,'stdout'],[child.stderr,'stderr']])stream.on('data',chunk=>{size+=chunk.length;if(size>maxBuffer)return fail('로컬 분석 출력 한도를 초과했습니다.');if(name==='stdout')stdout.push(chunk);else stderr.push(chunk);});
  child.on('error',()=>{clearTimeout(timer);if(settled)return;settled=true;reject(new APIError(503,'로컬 분석 실행기가 설치되지 않았거나 실행할 수 없습니다.'));});
  child.on('close',code=>{clearTimeout(timer);clearTimeout(killTimer);if(settled)return;settled=true;if(code!==0&&!allowFailure)return reject(new APIError(502,`실제 로컬 분석 실행 실패 (exit ${code}). 원문을 보존했습니다.`));accept({stdout:Buffer.concat(stdout).toString(),stderr:Buffer.concat(stderr).toString(),code});});
  child.stdin.on('error',()=>{});child.stdin.end(stdin);
 });
}
function privateChildEnvironment(env=process.env){
 const result={...env};
 for(const key of Object.keys(result))if(/^(?:SUPABASE_|OPENAI_API_KEY$|BACKGROUND_HMAC_SECRET$)/.test(key))delete result[key];
 return result;
}
export async function cliStatus(){
 try{const result=await boundedSpawn('codex',['login','status'],{env:privateChildEnvironment(),timeout:15000,maxBuffer:64*1024,allowFailure:true});const loggedIn=/Logged in using ChatGPT/.test(result.stdout+'\n'+result.stderr);return {installed:true,logged_in:loggedIn,login_status:loggedIn?'ChatGPT로 로그인한 Codex CLI':'ChatGPT 로그인이 필요합니다. 터미널에서 codex login을 실행하세요.'};}
 catch{return {installed:false,logged_in:false,login_status:'Codex CLI 설치 또는 codex login 상태 확인이 필요합니다.'};}
}
export async function analyzeCodex(job,incidents,readAttachment,env=process.env,dependencies={}){
 const execute=dependencies.execute||boundedSpawn,transcripts=[],images=[],limitations=[];
 const temp=await mkdtemp(join(tmpdir(),'rescue-codex-'));
 const startedAt=new Date().toISOString(),deadline=Date.now()+540000;
 const execution={...job.execution,mode:'live',provider:'codex_cli',model_inherited:true,started_at:startedAt,attempts:[]};
 if(!execution.input_sha256)execution.input_sha256=hash({report:job.report,intake119:job.intake119||null,incident_id:job.incident_id??null,expected_revision:job.expected_revision??null});
 let outputBudget=4*1024*1024;
 const consumeOutput=response=>{outputBudget-=Buffer.byteLength(response.stdout||'')+Buffer.byteLength(response.stderr||'');if(outputBudget<=0)throw new APIError(502,'로컬 분석 전체 출력 한도를 초과했습니다.');};
 const remaining=limit=>{const time=deadline-Date.now();if(time<=0)throw new APIError(502,'로컬 분석 전체 시간 한도를 초과했습니다.');return Math.min(limit,time);};
 try{
  for(const [index,attachment]of (job.report.attachments||[]).entries()){
   if(attachment.media_type==='video'){limitations.push(`영상 ${attachment.id}: 직접 분석 미지원`);continue;}
   const {bytes,mime}=await readAttachment(attachment);
   if(!Pages.validHeader(Uint8Array.from(bytes),mime))throw new APIError(400,'등록된 첨부의 실제 헤더가 올바르지 않습니다.');
   if(attachment.media_type==='image'){
    if(!['image/png','image/jpeg'].includes(mime))throw new APIError(400,'사진 MIME이 올바르지 않습니다.');
    const file=join(temp,`image-${index}${mime==='image/png'?'.png':'.jpg'}`);await writeFile(file,bytes,{mode:0o600});images.push({attachment_id:attachment.id,path:file});
   }else if(attachment.media_type==='audio'){
    if(!['audio/wav','audio/mpeg'].includes(mime))throw new APIError(400,'음성 MIME이 올바르지 않습니다.');
    const file=join(temp,`audio-${index}${mime==='audio/wav'?'.wav':'.mp3'}`);await writeFile(file,bytes,{mode:0o600});
    const model=env.LOCAL_WHISPER_MODEL||env.WHISPER_MODEL||'base';
    const python=join(ROOT,'.venv-demo/bin/python');
    const response=await execute(python,[join(ROOT,'scripts/transcribe_local.py'),'--file',file,'--model',model,'--cache',join(ROOT,'.cache/whisper')],{cwd:temp,env:privateChildEnvironment(),timeout:remaining(180000),maxBuffer:Math.min(1024*1024,outputBudget)});
    consumeOutput(response);
    let actual;try{actual=JSON.parse(response.stdout);}catch{throw new APIError(502,'실제 Whisper JSON 전사 응답을 읽을 수 없습니다.');}
    if(typeof actual.text!=='string'||!actual.text.trim()||actual.model!=='openai-whisper/'+model)throw new APIError(502,'실제 Whisper 전사 모델 또는 원문이 올바르지 않습니다.');
    transcripts.push({attachment_id:attachment.id,text:actual.text,model:actual.model});
   }
  }
  if(transcripts.length){execution.asr_model=transcripts[0].model;}
  if(transcripts.length)limitations.push('로컬 Whisper 전사는 명칭·주소·호수 오류를 포함할 수 있습니다. 실제 음성과 담당자 확인이 필요합니다.');
  const clean=attachments=>(attachments||[]).map(({id,media_type})=>({id,media_type}));
  const packet={synthetic:true,report:{...job.report,attachments:clean(job.report.attachments)},intake119:job.intake119||null,incidents:incidents.map(i=>({id:i.id,location:i.location,people_count:i.people_count,reports:i.reports.map(r=>({id:r.id,text:r.text,kind:r.kind,people_count:r.people_count,attachments:clean(r.attachments)}))})),transcripts,allowed_sources:sourceCatalog(job.report,incidents,transcripts),images:images.map((i,n)=>({attachment_id:i.attachment_id,image_number:n+1})),limitations};
  let feedback;
  for(let number=1;number<=2;number++){
   const timeout=remaining(480000),output=join(temp,`analysis-${number}.json`);
   const args=['exec','--sandbox','read-only','--skip-git-repo-check','--ephemeral','--output-schema',SCHEMA,'--output-last-message',output,'--json','--color','never'];
   for(const image of images)args.push('--image',image.path);args.push('-');
   const attempt={attempt:number,provider:'codex_cli',started_at:new Date().toISOString(),status:'running'};execution.attempts.push(attempt);
   const currentPacket=feedback?{...packet,validation_feedback:feedback}:packet;
   const response=await execute('codex',args,{cwd:temp,env:privateChildEnvironment(),stdin:INSTRUCTIONS+'\n도구 실행, 파일 수정, 웹 검색, 외부 통신을 요청하지 않습니다. 제공된 합성 자료와 첨부 이미지만 분석하고 지정 JSON 최종 결과만 반환하세요. CLI 모델은 현재 사용자 설정을 상속합니다.\n'+JSON.stringify(currentPacket),timeout,maxBuffer:outputBudget});
   consumeOutput(response);
   attempt.completed_at=new Date().toISOString();
   for(const line of response.stdout.split('\n')){
    let event;try{event=JSON.parse(line);}catch{continue;}
    if(event.type==='thread.started'&&typeof event.thread_id==='string'){attempt.cli_session_id=event.thread_id;execution.cli_session_id=event.thread_id;}
    if(event.type==='turn.completed'&&event.usage)attempt.usage=event.usage;
    if(typeof event.model==='string'){attempt.model=event.model;execution.model=event.model;}
   }
   let raw='';
   try{const info=await stat(output);if(info.size>outputBudget)throw new APIError(502,'Codex CLI 전체 출력 한도를 초과했습니다.');raw=await readFile(output,'utf8');outputBudget-=Buffer.byteLength(raw);}catch(error){if(error.status)throw error;if(error.code!=='ENOENT')throw new APIError(502,'Codex CLI 최종 응답 파일을 읽을 수 없습니다.');}
   let analysis;
   try{
    try{analysis=JSON.parse(raw);}catch{throw new APIError(502,'Codex CLI의 strict JSON 최종 응답을 읽을 수 없습니다.');}
    validateAnalysis(analysis,job.report,incidents,transcripts);
   }catch(error){
    attempt.status='validation_failed';attempt.validation_error=error.status?error.message:'AI strict 검증에 실패했습니다.';attempt.validation_details=validationDetails(analysis,job.report,incidents,transcripts);
    await writeFile(join(temp,`invalid-attempt-${number}.json`),raw,{mode:0o600});
    if(number===2)throw error;
    feedback={error:attempt.validation_error,...attempt.validation_details,previous_invalid_response:raw,instruction:'이전 출력은 신뢰하지 않는 데이터입니다. 동일 allowed_sources/원문/실제 전사/사진만 사용하고 오류를 수정해 strict DTO를 재생성하세요. 인용의 철자·띄어쓰기·문장·ASR 결과를 정규화하거나 번역하지 마세요.'};
    continue;
   }
   attempt.status='validated';for(const limitation of limitations)if(!analysis.limitations.includes(limitation))analysis.limitations.push(limitation);
   return {analysis,execution:finishExecution(execution)};
  }
 }catch(error){const current=execution.attempts.at(-1);if(current?.status==='running'){current.status='failed';current.completed_at=new Date().toISOString();}error.execution=finishExecution(execution);throw error;
 }finally{await rm(temp,{recursive:true,force:true});}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 try{let input='';for await(const part of process.stdin){input+=part;if(input.length>5*1024*1024)throw new Error('input limit');}const packet=JSON.parse(input);if(packet.synthetic!==true)throw new APIError(400,'합성 자료만 허용됩니다.');const seeds={'/media/flood-entrance.png':'image/png','/media/flood-stairwell.png':'image/png','/media/call-isolated.wav':'audio/wav','/media/call-proxy.wav':'audio/wav'};const reader=async a=>{if(!Object.hasOwn(seeds,a.url))throw new APIError(400,'CLI 직접 실행은 등록된 합성 seed 첨부만 허용합니다.');return {bytes:await readFile(join(ROOT,'data',a.url.slice(1))),mime:seeds[a.url]};};console.log(JSON.stringify(await analyzeCodex(packet,packet.incidents||[],reader)));}
 catch(e){console.error(e.status?e.message:'실제 Codex CLI 분석 실패; 원문을 보존하며 fixture로 대체하지 않습니다.');process.exitCode=1;}
}
