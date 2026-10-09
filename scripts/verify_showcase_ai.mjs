#!/usr/bin/env node
// Actual model smoke: raw synthetic inputs, no prewritten analysis and no state mutation.
import {readFile,writeFile} from 'node:fs/promises';
import {analyze} from '../netlify/functions/ai-core.mjs';
import {createInterface} from 'node:readline';
console.log(JSON.stringify({ready:'synthetic OpenAI analysis, stdin secrets kept in memory',pid:process.pid,tty:process.stdin.isTTY}));
const lines=createInterface({input:process.stdin});let env;for await(const line of lines){env=JSON.parse(line);lines.close();break;}
const calls=[]; const actualFetch=globalThis.fetch; globalThis.fetch=async (...args)=>{const response=await actualFetch(...args);const url=String(args[0]);if(url.startsWith('https://api.openai.com/')){const body=await response.clone().json().catch(()=>({}));calls.push({endpoint:url.split('/v1/')[1],status:response.status,model:body.model,response_id:body.id,text:body.text,output:body.output,usage:body.usage});}return response;};
const seed=JSON.parse(await readFile(new URL('../data/seed.json',import.meta.url),'utf8'));
const incidents=seed.incidents.filter(i=>['INC-20261009-100','INC-20261009-101'].includes(i.id));
const main=incidents[0];
const attachments=main.reports.flatMap(r=>r.attachments||[]).filter(a=>a.url.includes('parking'));
const report={kind:'field',channel:'field',text:'합성 현장 추가 보고: 태풍으로 한빛복합센터 B2 지하주차장이 침수됐습니다. 최초 여성 세 명 중 할머니 한 명과 여자아이 한 명, 두 명을 구조했습니다. 성인 여성 한 명은 아직 안에 남아 있습니다. 전원 구조가 아닙니다. 비상등만 켜져 있고 계단 통로로 물이 들어옵니다. 바깥 가족의 재신고가 같은 사람인지 확인이 필요합니다. 최초 전화 음성과 기둥·계단 사진을 원문 첨부합니다.',attachments};
const reader=async a=>({bytes:await readFile(new URL('../data'+a.url,import.meta.url)),mime:a.media_type==='image'?'image/png':'audio/wav'});
try{
 const result=await analyze({report,execution:{mode:'live',provider:'openai'},incident_id:main.id,expected_revision:main.revision},incidents,reader,env);
 const record={synthetic:true,scope:'actual synthetic multimodal analysis; draft only, not human-confirmed state or real-world accuracy',incident_id:main.id,report,...result};
 await writeFile(new URL('../docs/verification/showcase-asr-comparison.json',import.meta.url),JSON.stringify({synthetic:true,transcripts:result.analysis.transcripts,scope:'actual ASR of final noisy and DSP WAV; not speech separation or accuracy measurement'},null,2)+'\n');
 await writeFile(new URL('../docs/verification/showcase-ai-live.json',import.meta.url),JSON.stringify(record,null,2)+'\n');
 console.log(JSON.stringify({status:'passed',provider:result.execution.provider,response_id:result.execution.response_id,transcripts:result.analysis.transcripts,remaining:result.analysis.remaining_people,handoff:result.analysis.handoff,location:result.analysis.location}));
}catch(e){await writeFile(new URL('../docs/verification/showcase-ai-failures.json',import.meta.url),JSON.stringify({synthetic:true,status:'failed',reason:e.status?e.message:'analysis failed',execution:e.execution,calls},null,2)+'\n');console.error(JSON.stringify({status:'failed',message:e.status?e.message:'actual analysis failed',execution:e.execution}));process.exitCode=1;}
