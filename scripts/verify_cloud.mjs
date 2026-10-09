#!/usr/bin/env node
// Opt-in real requests against the synthetic shared demo. Never inject fixture answers.
import fs from 'node:fs/promises';
const base=process.argv[2],output=process.argv[3];
if(!base||!output||!(/^(?:https:\/\/[a-z0-9-]+\.netlify\.app|http:\/\/127\.0\.0\.1:(?:8769|8770))\/?$/.test(base)))throw new Error('usage: node scripts/verify_cloud.mjs https://SITE.netlify.app|http://127.0.0.1:8769 OUTPUT.json');
const site=base.replace(/\/$/,'');
const request=async(path,body)=>{const response=await fetch(site+path,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(30000)});return {http:response.status,body:await response.json()};};
const config=await request('/api/config'),list=await request('/api/incidents');
const result={checked_at:new Date().toISOString(),site,mode:'live',status:'failed',config:config.body,storage_http:list.http,runs:[],limitations:['합성 사례의 통합 연결 검사이며 정확도·시간 절감·실제 구조 성과 평가는 아니다.','AI 초안을 이 검사에서 자동으로 담당자 확정하거나 구조 완료시키지 않는다.']};
if(list.http!==200)throw new Error('storage unavailable');
const incident=list.body.incidents.find(i=>i.id==='INC-20261008-003');
const detail=await request('/api/incidents/'+incident.id);
const cases=[
 {id:'partial-rescue-text',incident_id:incident.id,expected_revision:detail.body.revision,report:{channel:'kakao',kind:'additional',actor:'합성 통합 검증 담당',text:'합성 추가 신고. 가상동 해솔길 7 해솔다세대 301호 세 명 중 두 명만 구조했고 한 명이 안에 남아 있습니다. 전원 구조가 아닙니다. 302호라는 전달은 잘못된 것으로 301호를 다시 확인해주세요.',attachments:[]}},
 {id:'photo-observation',incident_id:null,expected_revision:null,report:{channel:'mms',kind:'initial',actor:'합성 통합 검증 담당',text:'합성 사진 신고. 출입구가 물에 잠긴 사진을 보냅니다. 건물 위치와 고립 인원은 아직 확인되지 않았습니다. 사진에서 직접 관찰되는 위험과 확인 질문을 구분해주세요.',attachments:[{id:'LIVE-PHOTO',url:'/media/flood-entrance.png',media_type:'image',filename:'flood-entrance.png',caption:'생성 출입구 침수 합성 이미지',source:'ai_generated'}]}},
 {id:'actual-wav-asr',incident_id:null,expected_revision:null,report:{channel:'voice',kind:'initial',actor:'합성 통합 검증 담당',text:'합성 전화 음성 신고. 첨부 WAV 원문을 실제 전사하고 위치·인원·이동 가능 여부를 확인해주세요.',attachments:[{id:'LIVE-AUDIO',url:'/media/call-isolated.wav',media_type:'audio',filename:'call-isolated.wav',caption:'한국어 TTS 합성 음성, 대본은 모델 입력에 전달하지 않음',source:'tts_synthetic'}]}}
];
for(const scenario of cases){const {id,...packet}=scenario;const submitted=await request('/api/ai/analyses',{synthetic:true,...packet});const run={case:id,packet,submit_http:submitted.http,status:'failed',job:submitted.body};if(submitted.http===202){for(let n=0;n<400;n++){const got=await request('/api/ai/analyses/'+submitted.body.id);run.job=got.body;if(['ready','confirmed','failed'].includes(got.body.status)){run.status=got.body.status==='failed'?'failed':'passed';break;}await new Promise(r=>setTimeout(r,1500));}}result.runs.push(run);await fs.writeFile(output,JSON.stringify(result,null,2));console.log(id,submitted.http,run.job.status||run.job.code||'unknown',run.job.error||'');}
result.status=result.runs.every(r=>r.status==='passed')?'passed':'failed';await fs.writeFile(output,JSON.stringify(result,null,2));
