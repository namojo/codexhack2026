#!/usr/bin/env node
import {createServer} from 'node:http';
import {readFile,stat,realpath} from 'node:fs/promises';
import {join,resolve,extname,sep} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {randomBytes,timingSafeEqual} from 'node:crypto';
import {createInterface} from 'node:readline';
import {handle as cloudHandle,settingsFromConfig} from '../netlify/functions/api.mjs';
import {processJob} from '../netlify/functions/ai-analysis-background.mjs';
import {analyze,APIError} from '../netlify/functions/ai-core.mjs';
import {cliStatus,analyzeCodex,boundedSpawn} from './analyzer_codex.mjs';
const ROOT=resolve(fileURLToPath(new URL('..',import.meta.url)));
const json=(statusCode,value,headers={})=>({statusCode,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...headers},body:JSON.stringify(value)});
const PROVIDERS=['codex_cli','openai','disabled'];
const token=()=>randomBytes(32).toString('hex');
const equal=(left,right)=>typeof left==='string'&&typeof right==='string'&&/^[a-f0-9]{64}$/.test(left)&&/^[a-f0-9]{64}$/.test(right)&&timingSafeEqual(Buffer.from(left),Buffer.from(right));

export function createDemoRuntime({env=process.env,origin='http://127.0.0.1:8769',probe=cliStatus,cliAnalyzer=analyzeCodex,worker=processJob,maxQueued=6}={}){
 const ownURL=new URL(origin);
 if(ownURL.protocol!=='http:'||ownURL.hostname!=='127.0.0.1'||ownURL.username||ownURL.password||ownURL.pathname!=='/'||ownURL.search||ownURL.hash)throw new Error('Exact loopback origin required');
 let provider=env.AI_PROVIDER||'codex_cli';if(!PROVIDERS.includes(provider))throw new Error('Unknown local provider');
 const sessions=new Map(),queue=[];let running=false,statusCache=null,statusAt=0,whisperCache=false,whisperAt=0;
 async function capabilities(refresh=false){
  if(refresh||!statusCache||Date.now()-statusAt>60000){statusCache=await probe();statusAt=Date.now();}
  if(refresh||Date.now()-whisperAt>60000){try{await boundedSpawn(join(ROOT,'.venv-demo/bin/python'),['-c',"import whisper; print('available')"],{timeout:15000,maxBuffer:64000});whisperCache=true;}catch{whisperCache=false;}whisperAt=Date.now();}const whisper=whisperCache;
  return {codex_cli:statusCache,openai:{configured:!!(env.OPENAI_API_KEY&&env.OPENAI_MODEL)},asr:{available:whisper,provider:whisper?'local_whisper':'none',model:whisper?'openai-whisper/'+(env.LOCAL_WHISPER_MODEL||env.WHISPER_MODEL||'base'):null}};
 }
 async function aiConfig(){const c=await capabilities(),configured=provider==='codex_cli'?c.codex_cli.installed&&c.codex_cli.logged_in:provider==='openai'?c.openai.configured:false;return {provider,configured,enabled:provider!=='disabled'&&configured,model:provider==='openai'?env.OPENAI_MODEL||null:null,local_demo:true,login:{status:c.codex_cli.logged_in?'logged_in':'login_required',detail:c.codex_cli.login_status},asr:provider==='openai'?{available:c.openai.configured,provider:c.openai.configured?'openai':'none',model:c.openai.configured?(env.OPENAI_TRANSCRIBE_MODEL||'gpt-4o-mini-transcribe'):null}:c.asr};}
 const workerHooks={local:true,analyze:(job,incidents,reader)=>job.execution.provider==='codex_cli'?cliAnalyzer(job,incidents,reader,env):job.execution.provider==='openai'?analyze(job,incidents,reader,env):Promise.reject(new APIError(503,'작업 provider가 비활성 상태입니다.'))};
 async function drain(){if(running)return;running=true;try{while(queue.length){const job=queue.shift();try{await worker(job.id,job.execution.input_sha256,env,workerHooks);}catch{/* DB polling reports timeout when the persistent worker cannot record failure. */}}}finally{running=false;}}
 const hooks={local:true,aiConfig,dispatch:async job=>{if(queue.length>=maxQueued)throw new APIError(503,'로컬 분석 대기 한도를 초과했습니다.');queue.push(job);void drain();}};
 function headers(event){return Object.fromEntries(Object.entries(event.headers||{}).map(([k,v])=>[k.toLowerCase(),v]));}
 function boundary(event,requireOrigin=false){const h=headers(event);if(h.host!==ownURL.host||requireOrigin&&h.origin!==ownURL.origin||h.origin!==undefined&&h.origin!==ownURL.origin)throw new APIError(403,'로컬 서버 자신의 출처에서만 요청할 수 있습니다.');return h;}
 async function request(event){
  try{
   const h=boundary(event),method=event.httpMethod||'GET';
   if(event.path==='/api/settings'){
    if(method==='GET'){
     const c=await capabilities(true),ai=await aiConfig(),result={...settingsFromConfig(ai,env),mutable:true,capabilities:c};
     const cookie=/\brescue_demo_session=([a-f0-9]{64})(?:;|$)/.exec(h.cookie||'')?.[1];let session=cookie&&sessions.get(cookie);
     for(const [id,value]of sessions)if(value.expires<Date.now())sessions.delete(id);
     if(!session||session.expires<Date.now()){if(sessions.size>=100)sessions.delete(sessions.keys().next().value);const id=token();session={id,csrf:token(),expires:Date.now()+3600000};sessions.set(id,session);}
     result.csrf_token=session.csrf;
     return json(200,result,{'Set-Cookie':`rescue_demo_session=${session.id}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600`});
    }
    if(method==='POST'){
     boundary(event,true);
     const cookie=/\brescue_demo_session=([a-f0-9]{64})(?:;|$)/.exec(h.cookie||'')?.[1],session=cookie&&sessions.get(cookie);
     if(!session||session.expires<Date.now()||!equal(session.csrf,h['x-csrf-token']))throw new APIError(403,'로컬 설정 CSRF 검증에 실패했습니다. 설정 화면을 다시 여세요.');
     let b;try{b=JSON.parse(event.body||'{}');}catch{throw new APIError(400,'설정 JSON을 확인하세요.');}
     if(!b||typeof b!=='object'||Array.isArray(b)||Object.keys(b).length!==1||!PROVIDERS.includes(b.provider))throw new APIError(400,'설정에는 provider만 지정할 수 있습니다.');
     if(b.provider==='openai'&&(!env.OPENAI_API_KEY||!env.OPENAI_MODEL))throw new APIError(503,'서버의 OpenAI 키/모델을 먼저 설정하세요. 키는 화면에 입력하지 않습니다.');
     provider=b.provider;
     const c=await capabilities(),ai=await aiConfig();return json(200,{...settingsFromConfig(ai,env),mutable:true,capabilities:c});
    }
    throw new APIError(405,'설정 요청 방식을 확인하세요.');
   }
   return await cloudHandle(event,env,hooks);
  }catch(e){return json(e.status||500,{error:e.status?e.message:'로컬 서버 처리 실패. 원문을 보존하세요.',...(e.code?{code:e.code}:{})});}
 }
 return {request,hooks,aiConfig,boundary};
}
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.wav':'audio/wav','.mp3':'audio/mpeg','.txt':'text/plain; charset=utf-8','.xml':'application/xml; charset=utf-8'};
export function createDemoServer({env=process.env,port=8769,staticRoot=join(ROOT,'dist/ai-preview'),runtime}={}){
 runtime=runtime||createDemoRuntime({env,origin:`http://127.0.0.1:${port}`});
 const root=resolve(staticRoot);
 return createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://127.0.0.1:'+port),event={path:url.pathname,httpMethod:req.method,headers:req.headers,rawUrl:'http://127.0.0.1:'+port+req.url};runtime.boundary(event);
   if(event.path.startsWith('/api/')){
    let total=0,parts=[];for await(const part of req){total+=part.length;if(total>5*1024*1024)throw new APIError(413,'로컬 요청 본문 한도 5MiB를 초과했습니다.');parts.push(part);}event.body=Buffer.concat(parts).toString();
    const result=await runtime.request(event);res.writeHead(result.statusCode,result.headers);res.end(result.isBase64Encoded?Buffer.from(result.body,'base64'):result.body);return;
   }
   if(req.method!=='GET'&&req.method!=='HEAD')throw new APIError(405,'정적 자료는 읽기만 가능합니다.');
   const pathname=decodeURIComponent(url.pathname);
   if(pathname.includes('\\')||pathname.includes('\0')||pathname.split('/').some(p=>p==='..'))throw new APIError(404,'허용된 정적 경로가 아닙니다.');
   let file=resolve(root,'.'+pathname);if(!file.startsWith(root+sep)&&file!==root)throw new APIError(404,'정적 경로를 찾을 수 없습니다.');
   const info=await stat(file);if(info.isDirectory())file=join(file,'index.html');file=await realpath(file);const actualRoot=await realpath(root);if(!file.startsWith(actualRoot+sep))throw new APIError(404,'허용된 정적 파일이 아닙니다.');const data=await readFile(file),type=TYPES[extname(file)];if(!type)throw new APIError(404,'허용된 정적 형식이 아닙니다.');
   res.writeHead(200,{'Content-Type':type,'Content-Length':String(data.length),'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"});res.end(req.method==='HEAD'?undefined:data);
  }catch(e){const response=json(e.status||404,{error:e.status?e.message:'정적 자료를 찾을 수 없습니다.'});res.writeHead(response.statusCode,response.headers);res.end(response.body);}
 });
}
async function stdinEnvironment(){
 const lines=createInterface({input:process.stdin,crlfDelay:Infinity});let raw;
 for await(const line of lines){raw=line;lines.close();break;}
 if(!raw||raw.length>64000)throw new Error('한 줄 서버 환경 JSON이 필요합니다.');const input=JSON.parse(raw);
 const allowed=new Set(['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENAI_MODEL','OPENAI_TRANSCRIBE_MODEL','BACKGROUND_HMAC_SECRET','AI_PROVIDER','AI_DAILY_LIMIT','LOCAL_WHISPER_MODEL','WHISPER_MODEL']);
 if(!input||typeof input!=='object'||Array.isArray(input)||Object.entries(input).some(([k,v])=>!allowed.has(k)||typeof v!=='string'))throw new Error('서버 환경 JSON 형식을 확인하세요.');return {...process.env,...input};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 try{const args=process.argv.slice(2);let useStdin=false,port=8769,staticRoot=join(ROOT,'dist/ai-preview');for(let n=0;n<args.length;n++){if(args[n]==='--env-stdin')useStdin=true;else if(args[n]==='--port')port=Number(args[++n]);else if(args[n]==='--static')staticRoot=resolve(args[++n]);else throw new Error('지원되지 않은 서버 옵션입니다.');}if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('loopback 포트를 확인하세요.');const env=useStdin?await stdinEnvironment():process.env;const server=createDemoServer({env,port,staticRoot});server.listen(port,'127.0.0.1',()=>console.log(`Codex CLI 합성 시연: http://127.0.0.1:${port} (비밀은 메모리에만 유지)`));server.on('error',()=>{console.error('로컬 시연 서버 시작 실패. 포트와 실행 경로를 확인하세요.');process.exitCode=1;});}
 catch(e){console.error('로컬 시연 서버 설정 실패. 한 줄 환경 JSON과 실행 옵션을 확인하세요. 비밀값은 출력하지 않습니다.');process.exitCode=1;}
}
