'use strict';
// Independent adapter contract tests: synthetic storage only, no browser or user DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createStore} = require('../web/pages-store.js');
const root = path.resolve(__dirname, '..');
let serial = 0;
class MemoryStorage {
  constructor() { this.values = new Map(); this.fail = false; }
  getItem(k) { return this.values.has(k) ? this.values.get(k) : null; }
  setItem(k, v) { if (this.fail) throw new Error('quota'); this.values.set(k, String(v)); }
}
const seed = () => ({synthetic:true, incidents:[], resources:[{id:'TEAM-04',name:'가상 검증팀',type:'rescue',crew_count:3,status:'available',incident_id:null}]});
function fixture(storage = new MemoryStorage(), basePath = '/hack-test/', extra = {}) {
  let tick = 0;
  const store = createStore({storage,seed:seed(),basePath,now:()=>new Date(Date.UTC(2026,9,8,3,0,tick++)).toISOString(),uuid:()=>`qa${++serial}`,...extra});
  return {store,storage};
}
const create = (s, extra={}) => s.request('/api/incidents',{method:'POST',body:{title:'합성 QA 사건',location:'가상동 검증빌라 201호',text:'합성 신고: 세 명 고립',people_count:3,priority:'urgent',...extra}});
const report = (s,i,n,text='현장 직접 대면: 전원 안전 확인',kind='field',extra={}) => s.request(`/api/incidents/${i.id}/reports`,{method:'POST',body:{expected_revision:i.revision,channel:kind==='field'?'field':'sms',kind,text,people_count:n,...extra}});
const close = (s,i,extra={}) => s.request(`/api/incidents/${i.id}/outcome`,{method:'POST',body:{expected_revision:i.revision,outcome:'rescued',confirmed_count:i.people_count,basis_report_id:i.reports.at(-1).id,note:'합성 현장 근거를 담당자가 대조',...extra}});
const progress = (s,i) => s.request(`/api/incidents/${i.id}/progress`,{method:'POST',body:{expected_revision:i.revision,status:'dispatched',team_id:'TEAM-04',note:'합성 팀배정 검증'}});
const edit = (s,i,extra={}) => s.request(`/api/incidents/${i.id}`,{method:'PATCH',body:{expected_revision:i.revision,reason:'명시 확인 후 정정',...extra}});
async function denied(s,storage,status,fn) {
  await s.request('/api/incidents'); const raw=storage.getItem(s.storageKey);
  await assert.rejects(fn,e=>e.status===status && /[가-힣]/.test(e.message));
  assert.equal(storage.getItem(s.storageKey),raw,'failed mutation must leave storage byte-identical');
}
function projection(i) {
  return {status:i.status,people_count:i.people_count,priority:i.priority,revision:i.revision,assigned_team_id:i.assigned_team_id,report_count:i.reports.length,progress_count:i.progress.length,audit_count:i.audit.length,history_count:i.outcome_history.length,outcome:i.outcome?.outcome||null,attention:i.attention.map(t=>t.id.split(':').at(-1)),location:i.location};
}
async function representativeFlow(s) {
  const trace=[];const save=i=>{trace.push(projection(i));return i;};
  let i=save(await create(s));const original=structuredClone(i.reports[0]);
  i=save(await progress(s,i));i=save(await report(s,i,2,'현장 두 명 안전 확인, 한 명 미확인'));
  i=save(await report(s,i,3));i=save(await close(s,i));
  i=save(await s.request(`/api/incidents/${i.id}/reopen`,{method:'POST',body:{expected_revision:i.revision,reason:'인원 정정 필요'}}));
  i=save(await report(s,i,2,'대상 인원은 두 명으로 정정','correction'));
  i=save(await report(s,i,2));i=save(await close(s,i));
  assert.deepEqual(i.reports[0],original);return trace;
}
const tests=[];const test=(name,fn)=>tests.push({name,fn});
test('continuous CRUD, explicit outcome, reopen, correction, audit and raw preservation',async()=>{
 const {store:s}=fixture(),trace=await representativeFlow(s);
 assert.equal(trace.length,9);assert.deepEqual(trace.map(x=>x.revision),[1,2,3,4,5,6,7,8,9]);
 assert.equal(trace[4].status,'closed');assert.equal(trace[4].assigned_team_id,null);assert.equal(trace[5].status,'reviewing');
 assert.equal(trace[8].history_count,1);assert.equal(trace[8].people_count,2);assert.equal(trace[8].audit_count,9);
 assert.deepEqual(trace[8].attention,[]);
});
test('partial report cannot close or release assigned team',async()=>{
 const {store:s,storage}=fixture();let i=await progress(s,await create(s));i=await report(s,i,2);
 await denied(s,storage,400,()=>close(s,i));assert.equal((await s.request('/api/incidents')).resources[0].status,'assigned');
});
test('equal numeric counts cannot conceal residual, negative or unanswered evidence',async()=>{
 for(const text of ['두 명만 구조, 한 명 남아 있음','현장 안전을 확인하지 못함','대상 세 명이 무응답','현장 확인 불가','구조 대상이 아직 남아 있습니다']){
  const {store:s,storage}=fixture();const i=await report(s,await create(s),3,text);
  await denied(s,storage,400,()=>close(s,i));
 }
});
test('explicit no-residual wording permits full safe confirmation',async()=>{
 const {store:s}=fixture();const i=await report(s,await create(s),3,'미확인 인원 없음. 미구조 인원 없음. 전원 안전 확인');
 assert.equal((await close(s,i)).status,'closed');
});
test('report counts are not summed, other incident and initial basis rejected',async()=>{
 const {store:s,storage}=fixture();let i=await create(s),other=await report(s,await create(s),3);i=await report(s,i,2);i=await report(s,i,1);
 for(const basis of [i.reports.at(-1).id,other.reports.at(-1).id,i.reports[0].id])await denied(s,storage,400,()=>close(s,i,{basis_report_id:basis}));
});
test('additional count conflict requires explicit correction',async()=>{
 const {store:s,storage}=fixture();let i=await report(s,await create(s),4,'추가 대상 네 명','additional');assert.equal(i.people_count,3);
 i=await report(s,i,3);await denied(s,storage,400,()=>close(s,i));
 i=await report(s,i,4,'대상 네 명 명시 정정','correction');i=await report(s,i,4);assert.equal((await close(s,i)).people_count,4);
});
test('old field basis is unusable after reopen even at same clock',async()=>{
 const {store:s,storage}=fixture(undefined,'/hack-test/',{now:()=> '2026-10-08T03:00:00Z'});let i=await close(s,await report(s,await create(s),3));const old=i.outcome.basis_report_id;
 i=await s.request(`/api/incidents/${i.id}/reopen`,{method:'POST',body:{expected_revision:i.revision,reason:'다시 확인'}});
 await denied(s,storage,400,()=>close(s,i,{basis_report_id:old}));i=await report(s,i,3);assert.equal((await close(s,i)).status,'closed');
});
test('completed additional information and important edits reopen while retaining outcomes',async()=>{
 const {store:s}=fixture();let i=await close(s,await report(s,await create(s),3));const old=structuredClone(i.outcome);
 i=await report(s,i,4,'추가 인원 네 명','additional');assert.equal(i.status,'reviewing');assert.equal(i.outcome,null);assert.equal(i.people_count,3);assert.equal(i.outcome_history[0].basis_report_id,old.basis_report_id);
 i=await report(s,i,4,'네 명 명시 정정','correction');i=await close(s,await report(s,i,4));i=await edit(s,i,{location:'가상동 다른 확인 위치'});
 assert.equal(i.status,'reviewing');assert.equal(i.outcome_history.length,2);
});
test('unknown count and malformed mutation fields reject atomically',async()=>{
 const {store:s,storage}=fixture();let i=await create(s);for(const n of [-1,1.2,true,'3',null])await denied(s,storage,400,()=>edit(s,i,{people_count:n}));
 for(const b of [{title:' ',location:'가상',text:'신고'},{title:'합성',location:'가상',text:'신고',unknown:1},{title:'합성',location:'가상'},['not object']])await denied(s,storage,400,()=>s.request('/api/incidents',{method:'POST',body:b}));
 i=await create(s,{people_count:undefined});i=await report(s,i,3);await denied(s,storage,400,()=>close(s,i,{confirmed_count:3}));
});
test('same revision simultaneous mutations have one winner across factories',async()=>{
 const {store:s,storage}=fixture();const other=fixture(storage).store,i=await create(s);
 const result=await Promise.allSettled([edit(s,i,{title:'합성 A'}),edit(other,i,{title:'합성 B'})]);
 assert.equal(result.filter(x=>x.status==='fulfilled').length,1);assert.equal(result.find(x=>x.status==='rejected').reason.status,409);
 assert.equal((await other.request(`/api/incidents/${i.id}`)).revision,2);
});
test('shared storage team assignment race has one winner and consistent team incident',async()=>{
 const {store:s,storage}=fixture();const b=fixture(storage).store,a=await create(s),i=await create(b);
 const results=await Promise.allSettled([progress(s,a),progress(b,i)]);assert.equal(results.filter(x=>x.status==='fulfilled').length,1);
 assert.equal(results.find(x=>x.status==='rejected').reason.status,409);const list=await s.request('/api/incidents');
 assert.equal(list.incidents.filter(x=>x.assigned_team_id==='TEAM-04').length,1);assert.equal(list.resources[0].incident_id,results.find(x=>x.status==='fulfilled').value.id);
});
test('persisted reload reads fresh data and returned object mutation does not leak',async()=>{
 const {store:s,storage}=fixture();let i=await create(s);i.title='external mutation';const b=fixture(storage).store;
 assert.equal((await b.request(`/api/incidents/${i.id}`)).title,'합성 QA 사건');await edit(b,await b.request(`/api/incidents/${i.id}`),{location:'가상동 새 위치'});
 assert.equal((await s.request(`/api/incidents/${i.id}`)).location,'가상동 새 위치');
});
test('contact and proxy warnings clear only after valid confirmation and location correction',async()=>{
 const {store:s}=fixture();let i=await create(s,{text:'대리 신고 GPS는 제 휴대폰 위치. 대상 연락 두절'});
 assert(i.attention.some(t=>t.id.endsWith(':contact')));assert(i.attention.some(t=>t.id.endsWith(':location')));
 i=await report(s,i,3,'현장 안전 확인하지 못함, 대상 무응답');assert(i.attention.some(t=>t.id.endsWith(':contact')||t.reason.includes('연락')));
 i=await report(s,i,3,'현장 직접 대면 전원 안전 확인 및 응답 확인');assert(!i.attention.some(t=>t.id.endsWith(':contact')||t.reason.includes('연락 두절')));
 i=await report(s,i,3,'구조 대상 주소 명시 정정','correction',{location:'가상동 구조 대상 집'});assert(!i.attention.some(t=>t.id.endsWith(':location')));
 assert.equal(i.priority,'urgent');for(const t of i.attention){assert.equal(t.source,'rule');for(const e of t.evidence)assert(i.reports.find(r=>r.id===e.report_id).text.includes(e.quote));}
});
test('quota failures do not commit incident edits or uploaded media',async()=>{
 const {store:s,storage}=fixture();const i=await create(s);storage.fail=true;
 await denied(s,storage,507,()=>edit(s,i,{title:'저장되면 안됨'}));
 const bytes=fs.readFileSync(path.join(root,'data/media/flood-entrance.png'));
 await denied(s,storage,507,()=>s.request('/api/uploads',{method:'POST',body:{filename:'합성.png',content_type:'image/png',data_base64:bytes.toString('base64')}}));
 storage.fail=false;assert.equal((await s.request(`/api/incidents/${i.id}`)).title,'합성 QA 사건');
});
test('5MiB storage connects one generated stairwell attachment without duplication and rejects second atomically',async()=>{
 const storage=new MemoryStorage();storage.setItem=function(k,v){if(Buffer.byteLength(String(v),'utf8')>5*1024*1024)throw Error('5MiB JSON quota');this.values.set(k,String(v));};
 const {store:s}=fixture(storage),bytes=fs.readFileSync(path.join(root,'data/media/flood-stairwell.png'));
 const payload={filename:'합성계단.png',content_type:'image/png',data_base64:bytes.toString('base64')};
 const up=await s.request('/api/uploads',{method:'POST',body:payload});
 let i=await create(s,{attachments:[up]});
 assert.equal(i.reports[0].attachments.length,1);
 for(let n=0;n<4;n++)i=await report(s,i,3,'같은 합성 사진을 참조하는 추가보고','additional',{attachments:[up]});
 const wav=fs.readFileSync(path.join(root,'data/media/call-isolated.wav'));
 const voice=await s.request('/api/uploads',{method:'POST',body:{filename:'합성음성.wav',content_type:'audio/wav',data_base64:wav.toString('base64')}});
 i=await report(s,i,3,'합성 음성 추가보고','additional',{attachments:[voice]});
 const reloaded=fixture(storage).store;
 const reread=await reloaded.request(`/api/incidents/${i.id}`);
 assert.equal(reloaded.mediaUrl(reread.reports[0].attachments[0].url),'data:image/png;base64,'+payload.data_base64);
 assert.equal(reloaded.mediaUrl(reread.reports.at(-1).attachments[0].url),'data:audio/wav;base64,'+wav.toString('base64'));
 const raw=storage.getItem(s.storageKey);
 assert.equal(raw.split(payload.data_base64).length-1,1,'same picture payload stored once across five reports');
 assert.equal(raw.split(wav.toString('base64')).length-1,1,'voice payload stored once');
 await denied(s,storage,507,()=>s.request('/api/uploads',{method:'POST',body:{...payload,filename:'두번째합성계단.png'}}));
});
test('upload header base64 filename size and external attachment boundaries',async()=>{
 const {store:s,storage}=fixture();const bytes=fs.readFileSync(path.join(root,'data/media/call-isolated.wav'));
 const up=await s.request('/api/uploads',{method:'POST',body:{filename:'합성.wav',content_type:'audio/wav',data_base64:bytes.toString('base64')}});
 for(const b of [{filename:'../a.wav',content_type:'audio/wav',data_base64:bytes.toString('base64')},{filename:'a.png',content_type:'image/png',data_base64:bytes.toString('base64')},{filename:'a.wav',content_type:'audio/wav',data_base64:'!'},{filename:'a.wav',content_type:'audio/wav',data_base64:''}])await denied(s,storage,b.data_base64===''?413:400,()=>s.request('/api/uploads',{method:'POST',body:b}));
 await denied(s,storage,413,()=>s.request('/api/uploads',{method:'POST',body:{filename:'x.png',content_type:'image/png',data_base64:'A'.repeat(4*Math.ceil((8*1024*1024)/3)+4)}}));
 const header=Buffer.alloc(33);Buffer.from([137,80,78,71,13,10,26,10]).copy(header);header.write('IHDR',12);
 const small=await s.request('/api/uploads',{method:'POST',body:{filename:'헤더검증.png',content_type:'image/png',data_base64:header.toString('base64')}});
 await denied(s,storage,400,()=>create(s,{attachments:[{...small,url:'https://example.test/private.png'}]}));
 await denied(s,storage,400,()=>create(s,{attachments:[small,small]}));
 const i=await create(s,{attachments:[up]});assert.equal(i.reports[0].attachments[0].id,up.id);assert.equal(fixture(storage).store.mediaUrl(i.reports[0].attachments[0].url),'data:audio/wav;base64,'+bytes.toString('base64'));
});
test('schema1 registered dataURL survives reload and new report references normalize without reset',async()=>{
 const {store:s,storage}=fixture();const header=Buffer.alloc(33);Buffer.from([137,80,78,71,13,10,26,10]).copy(header);header.write('IHDR',12);
 const uri='data:image/png;base64,'+header.toString('base64');
 const up=await s.request('/api/uploads',{method:'POST',body:{filename:'합성구형.png',content_type:'image/png',data_base64:header.toString('base64')}});
 const i=await create(s,{attachments:[up]});
 const saved=JSON.parse(storage.getItem(s.storageKey));
 saved.uploads[up.id]={...up,url:uri};saved.incidents[0].reports[0].attachments[0]={...up,url:uri};
 storage.setItem(s.storageKey,JSON.stringify(saved));const oldRaw=storage.getItem(s.storageKey);
 const reloaded=fixture(storage).store,current=await reloaded.request(`/api/incidents/${i.id}`);
 assert.equal(storage.getItem(s.storageKey),oldRaw,'read compatibility cannot reset or rewrite storage');
 assert.equal(reloaded.mediaUrl(current.reports[0].attachments[0].url),uri);
 const next=await report(reloaded,current,3,'구형 합성 사진 재참조','additional',{attachments:[{...up,url:uri}]});
 assert.notEqual(next.reports.at(-1).attachments[0].url,uri,'new reference is compact');
 assert.equal(reloaded.mediaUrl(next.reports.at(-1).attachments[0].url),uri);
 assert.deepEqual(next.reports[0],current.reports[0],'original legacy report remains exact');
 assert.equal(JSON.parse(storage.getItem(s.storageKey)).schema_version,1);
});
test('media allowlist works at root/subpath without URL traversal or unregistered data',async()=>{
 const storage=new MemoryStorage(),a=fixture(storage,'/').store,b=fixture(storage,'/hack-test/').store;
 await create(a);assert.equal((await b.request('/api/incidents')).incidents.length,0);assert.notEqual(a.storageKey,b.storageKey);
 for(const name of ['flood-entrance.png','flood-stairwell.png','call-isolated.wav','call-proxy.wav']){assert.equal(a.mediaUrl('/media/'+name),'/media/'+name);assert.equal(b.mediaUrl('/media/'+name),'/hack-test/media/'+name);}
 for(const url of ['/media/../../seed.json','/media/not-present.png','https://example.test/flood-entrance.png','data:image/png;base64,AAAA','javascript:alert(1)','/hack-test/media/%2e%2e/seed.json'])assert.equal(b.mediaUrl(url),null);
});
test('unavailable corrupted versioned storage is never silently reset',async()=>{
 const {store:s,storage}=fixture();await create(s);const old=storage.getItem(s.storageKey);storage.setItem(s.storageKey,'{broken');
 await assert.rejects(()=>s.request('/api/incidents'),e=>e.status===503);assert.equal(storage.getItem(s.storageKey),'{broken');
 storage.setItem(s.storageKey,old);const value=JSON.parse(old);value.schema_version=99;storage.setItem(s.storageKey,JSON.stringify(value));
 await assert.rejects(()=>s.request('/api/incidents'),e=>e.status===503);assert.equal(JSON.parse(storage.getItem(s.storageKey)).schema_version,99);
 await assert.rejects(()=>createStore({storage:()=>{throw Error('disabled')},seed:seed()}).request('/api/incidents'),e=>e.status===503);
});
test('seed load failure is retriable and navigation locks surround operations',async()=>{
 let loads=0,locks=0;const {store:s}=fixture(undefined,'/hack-test/',{seed:undefined,loadSeed:async()=>{if(!loads++)throw Error('network');return seed();},locks:{request:async(k,o,run)=>{assert.equal(o.mode,'exclusive');locks++;return run();}}});
 await assert.rejects(()=>s.request('/api/incidents'),e=>e.status===503);await create(s);assert.equal(loads,2);assert.equal(locks,2);
});
test('unknown API and unsupported methods fail with CLI-safe error status',async()=>{
 const {store:s,storage}=fixture();await denied(s,storage,404,()=>s.request('/api/bundle'));await denied(s,storage,404,()=>s.request('/api/incidents/unknown'));
 await denied(s,storage,405,()=>s.request('/api/incidents',{method:'DELETE'}));
});
async function main(){
 if(process.argv.includes('--trace')){console.log(JSON.stringify(await representativeFlow(fixture().store)));return;}
 let failed=0;for(const t of tests){try{await t.fn();console.log('PASS '+t.name);}catch(e){failed++;console.error('FAIL '+t.name+'\n'+e.stack);}}
 console.log(JSON.stringify({suite:'independent-pages-qa',tests:tests.length,passed:tests.length-failed,failed,synthetic:true,browser:'not_run'}));
 if(failed)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
