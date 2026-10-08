'use strict';
const $ = id => document.getElementById(id);
const labels = {sms:'문자',mms:'사진·영상 첨부',app:'앱 위치 신고',video_call:'영상통화 기록',web:'인터넷 신고',field:'현장 보고',operator:'담당자 결정',system:'전송·연락 기록'};
const statuses = {open:'확인 대기',dispatched:'배정됨 · 구조 미확인',awaiting_confirmation:'결과 확인 필요',resolved:'안전 확인 완료'};
const outcomes = {rescued:'구조 확인',self_evacuated:'자력 대피 확인',transferred:'다른 팀 인계 확인'};
const alertTitles = {ambiguous_match:'어느 요청의 결과인지 확인하세요',count_unreconciled:'신고 인원과 보고 인원이 다릅니다',duplicate_review:'동일 요청인지 확인하세요',unreadable_media:'첨부를 읽지 못했습니다',location_conflict:'위치의 대상·시각을 확인하세요',no_response:'연락 여부가 확인되지 않았습니다',delivery_failure:'정보가 전달되지 않았습니다',analysis_rejected:'분석을 사용하지 않았습니다',closure_blocked:'완료 처리가 차단됐습니다',post_resolution_update:'새 정보로 다시 확인이 필요합니다',late_location_ignored:'늦은 위치 정보는 현재 위치에 반영하지 않았습니다'};
let bundle, currentCase, step=-1;
function el(tag, text, className){const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(className)node.className=className;return node;}
function timeLabel(value){if(!value)return '미상';const date=new Date(value);return Number.isNaN(date.valueOf())?String(value):new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);}
function renderCases(){
  const filter=$('channel').value;const list=$('cases');list.replaceChildren();
  const visible=bundle.results.filter(c=>filter==='all'||c.channels.includes(filter));
  visible.forEach(c=>{const button=el('button',undefined,'case-button');button.type='button';button.dataset.caseId=c.scenario_id;button.setAttribute('aria-current',String(c===currentCase));button.append(el('span',c.title),el('small',c.channels.map(x=>labels[x]||x).join(' / ')));button.addEventListener('click',()=>selectCase(c));list.append(button);});
  if(!visible.length)list.append(el('p','이 채널의 사례가 없습니다.','empty'));
}
function selectCase(c){currentCase=c;step=-1;renderCases();render();}
function renderRequests(snapshot){
  const cards=$('requests');cards.replaceChildren();const requests=Object.values(snapshot.requests||{});
  $('request-total').textContent=`${requests.length}개 원본 요청`;
  if(!requests.length)cards.append(el('p','다음 사건을 재생하면 요청별 카드가 생깁니다.','empty'));
  for(const r of requests){
    const card=el('article',undefined,'request');card.dataset.requestId=r.id;
    const head=el('div',undefined,'request-head');head.append(el('h3',`${r.id} · ${r.building_id||'건물 확인 필요'}`),el('span',statuses[r.status]||r.status,`status ${r.status}`));card.append(head);
    const dl=el('dl',undefined,'request-data');
    for(const [name,value] of [['위치',r.location_text||'확인 필요'],['인원',r.people_count===null||r.people_count===undefined?'확인 필요':`${r.people_count}명`],['필요 정보',(r.needs||[]).join(', ')||'추가 확인'],['결과',outcomes[r.outcome]||'미확정']]){dl.append(el('dt',name),el('dd',value));}
    card.append(dl,el('p',`근거 ${(r.evidence_event_ids||[]).join(', ')} · 정보 버전 ${r.revision}${r.canonical_id&&r.canonical_id!==r.id?' · 연결 요청 '+r.canonical_id:''}`,'muted'));cards.append(card);
  }
  const unresolved=requests.filter(r=>r.status!=='resolved').length;
  $('remaining').textContent=requests.length?`안전 미확인 요청 ${unresolved}건`:'아직 들어온 요청이 없습니다';
  const active=(snapshot.alerts||[]).filter(a=>a.active);
  $('summary-detail').textContent=`안전 확인 ${requests.length-unresolved}건 / 확인 항목 ${active.length}개`;
  const questions=$('questions');questions.replaceChildren();
  for(const alert of active){const block=el('article',undefined,`question ${['closure_blocked','analysis_rejected'].includes(alert.code)?'blocked':''}`);block.dataset.alertCode=alert.code;block.append(el('h3',alertTitles[alert.code]||alert.code),el('p',alert.message));if(alert.question)block.append(el('p',`다음 확인: ${alert.question}`));block.append(el('small',`요청 ${(alert.request_ids||[]).join(', ')||'식별 필요'} / 원문 ${(alert.event_ids||[]).join(', ')}`));questions.append(block);}
}
function eventCard(event){
  const card=el('article',undefined,'event-sheet');card.append(el('p',`${event.id} / ${labels[event.channel]||event.channel} / ${event.actor}`,'event-meta'),el('blockquote',event.text));
  const times=el('p',undefined,'times');times.append(el('span',`발생 ${timeLabel(event.occurred_at)} / 수신 ${timeLabel(event.received_at)} (한국 시간)`));card.append(times);
  for(const attachment of event.attachments||[]){const media=el('div',undefined,'attachment');media.append(el('strong',`합성 ${attachment.media_type==='video'?'영상':'사진'} 설명 · ${attachment.readable===false?'읽기 어려움':'설명 제공'}`),el('p',attachment.description||'설명 없음'));if(attachment.transcript)media.append(el('p',`모의 전사: ${attachment.transcript}`));media.append(el('small',`촬영 ${timeLabel(attachment.captured_at)} / 전사 출처 ${attachment.transcript_source||'없음'}`));card.append(media);}
  if(event.location)card.append(el('p',`위치 메타데이터: ${event.location.latitude}, ${event.location.longitude} / 오차 ${event.location.accuracy_m}m / 대상 ${event.location.subject||'unknown'}`,'location'));
  if(event.decision)card.append(el('p',`각본의 담당자 결정\n${event.decision.kind} / 요청 ${event.decision.request_id||''}${event.decision.outcome?' / '+(outcomes[event.decision.outcome]||event.decision.outcome):''}`,'decision'));
  return card;
}
function render(){
  if(!currentCase)return;
  $('title').textContent=currentCase.title;$('description').textContent=currentCase.description.split(' 모든 인물')[0];
  $('case-type').textContent='집중호우 구조 대응 / 합성 사건 재생';
  const events=currentCase.events, snapshot=step<0?{requests:{},alerts:[]}:currentCase.snapshots[step];
  $('step-count').textContent=`${step+1} / ${events.length} 사건`;
  $('previous').disabled=step<0;$('reset').disabled=step<0;$('next').disabled=step>=events.length-1;$('finish').disabled=step>=events.length-1;
  $('next').textContent=events[step+1]?.channel==='operator'?'각본의 담당자 결정 적용':'다음 사건';
  renderRequests(snapshot);
  const event=$('event');event.replaceChildren(step<0?el('p','사례를 선택한 뒤 ‘다음 사건’을 눌러 시작하세요.','empty'):eventCard(events[step]));
  const evidence=$('evidence');evidence.replaceChildren();events.slice(0,step+1).forEach(e=>{const entry=el('div',undefined,'evidence-entry');entry.append(el('small',`${e.id} / ${labels[e.channel]||e.channel} / 발생 ${timeLabel(e.occurred_at)}`),el('p',e.text));evidence.append(entry);});
  const timeline=$('timeline');timeline.replaceChildren();events.forEach((e,i)=>{const li=el('li'),button=el('button',`${i+1}. ${labels[e.channel]||e.channel}`,i===step?'current':i>step?'future':'');button.type='button';button.title=e.text;button.dataset.eventId=e.id;button.addEventListener('click',()=>{step=i;render();});li.append(button);timeline.append(li);});
  const checks=currentCase.checks||[];$('check-summary').textContent=`전체 재생 기대값 ${checks.filter(c=>c.passed).length}/${checks.length} 통과`;
  const list=$('checks');list.replaceChildren();checks.forEach(c=>list.append(el('p',`${c.passed?'통과':'실패'} · ${c.label}${c.after?' / '+c.after:''}`,`check ${c.passed?'':'fail'}`)));
  $('demo-note').textContent=currentCase.demo_notes||'';
}
$('next').addEventListener('click',()=>{if(currentCase&&step<currentCase.events.length-1){step++;render();}});
$('previous').addEventListener('click',()=>{if(step>=0){step--;render();}});
$('reset').addEventListener('click',()=>{step=-1;render();});
$('finish').addEventListener('click',()=>{if(currentCase){step=currentCase.events.length-1;render();}});
$('channel').addEventListener('change',()=>{renderCases();const filter=$('channel').value;if(currentCase&&!currentCase.channels.includes(filter)&&filter!=='all'){const first=bundle.results.find(c=>c.channels.includes(filter));if(first)selectCase(first);}});
fetch('/api/bundle').then(response=>{if(!response.ok)throw new Error(`HTTP ${response.status}`);return response.json();}).then(data=>{if(data.synthetic!==true||!Array.isArray(data.results)||!data.results.length)throw new Error('유효한 합성 재생 결과가 없습니다');bundle=data;const featured=['same-building','proxy-gps','late-location','partial-rescue','unreadable-photo'];bundle.results.sort((a,b)=>{const ai=featured.indexOf(a.scenario_id),bi=featured.indexOf(b.scenario_id);return (ai<0?featured.length:ai)-(bi<0?featured.length:bi);});$('mode').textContent=`합성 데이터 / ${data.mode==='fixture'?'수작업 분석 픽스처':data.analysis_source||'외부 분석 결과'}`;selectCase(bundle.results[0]);}).catch(error=>{$('error').hidden=false;$('error').textContent=`결과를 불러오지 못했습니다. 서버와 시나리오를 확인한 뒤 새로고침하세요. (${error.message})`;});
