/* 합성 업무 체험용 정적 저장 어댑터. 서버 공유·실모델 연결 없음. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root && root.document) {
    const script = root.document.currentScript;
    const base = new URL('.', script ? script.src : root.location.href);
    root.RescuePagesOffline = api.createStore({
      storage: () => root.localStorage, basePath: base.pathname,
      locks: root.navigator && root.navigator.locks,
      loadSeed: async () => {
        const response = await root.fetch(new URL('seed.json', base).href, {cache: 'no-store'});
        if (!response.ok) throw new api.PagesError(503, '합성 초기 자료를 읽을 수 없습니다.');
        return response.json();
      }
    });
    if (root.document.documentElement?.dataset.serviceMode !== 'cloud') root.RescuePages = root.RescuePagesOffline;
  }
})(typeof window === 'object' ? window : null, function () {
  'use strict';
  const VERSION = 1, MAX_UPLOAD = 8 * 1024 * 1024;
  const SEED_MEDIA = {'/media/flood-entrance.png':'image/png','/media/flood-stairwell.png':'image/png','/media/call-isolated.wav':'audio/wav','/media/call-proxy.wav':'audio/wav',
    '/media/parking-pillar-dark.png':'image/png','/media/parking-stair-flood.png':'image/png',
    '/media/parking-call-noisy.wav':'audio/wav','/media/parking-call-enhanced.wav':'audio/wav'};
  const MIME = {'image/png':['image','.png'],'image/jpeg':['image','.jpg'],'audio/wav':['audio','.wav'],'audio/mpeg':['audio','.mp3'],'video/mp4':['video','.mp4']};
  const CHANNELS = ['voice','sms','mms','app','video_call','web','field','kakao'];
  const CATEGORIES = ['flood','fire','rescue','medical','other'], PRIORITIES = ['urgent','high','normal'];
  const LEVELS = {immediate:0,decision:1,follow_up:2}, TASKS = {people:0,contact:1,location:2,reopened:3,assignment:4};
  const CONTACT = ['연락이 끊','연락 두절','연락두절','무응답','응답 없','응답이 없','연락이 되지','연락 안','연락 불가','연락되지','응답하지'];
  const PROXY = ['GPS','신고자 위치','제 휴대폰 위치','어머니 집이 아니','대리 신고','대리신고','대신 신고'];
  const NEGATIVE = /(?:확인|구조|안전|연락|응답|대피).{0,12}(?:못|않|불가|안\s*됨)|(?:미확인|확인\s*불가)/;
  const RESIDUAL = /(?:명|사람|대상|피해자|어머니|아버지|주민).{0,30}(?:남아|남았|남습니다|미구조)|(?:명|사람|대상|피해자).{0,15}만\s*(?:구조|확인|대피|인계)/;
  const NO_RESIDUAL = /(?:미구조|미확인|남은|남아\s*있는)\s*(?:대상|인원|사람|피해자|주민)?\s*(?:은|는|이|가)?\s*(?:없(?:습니다|어요|음|다)?|0명|영\s*명)|남아\s*있지\s*않(?:습니다|아요|음)?/g;
  const QUEUES = new WeakMap();
  class PagesError extends Error { constructor(status,message) { super(message); this.name='PagesError'; this.status=status; this.status_code=status; } }
  const clone = value => JSON.parse(JSON.stringify(value));
  const own = (value,key) => Object.prototype.hasOwnProperty.call(value,key);
  const object = value => value !== null && typeof value==='object' && !Array.isArray(value);
  const validCount = value => typeof value==='number' && Number.isSafeInteger(value) && value>=0;
  function count(value,label='인원') { if (!validCount(value)) throw new PagesError(400,`${label}은 0 이상의 정수여야 합니다.`); return value; }
  function string(value,label,empty=false) { if(typeof value!=='string'||(!empty&&!value.trim())||value.length>20000) throw new PagesError(400,`${label}은 ${empty?'문자열':'비어 있지 않은 문자열'}이어야 합니다.`); return value; }
  function choice(value,values,label) { if(typeof value!=='string'||!values.includes(value)) throw new PagesError(400,`${label} 값이 올바르지 않습니다.`); return value; }
  function fields(body,allowed,required) { if(!object(body)) throw new PagesError(400,'JSON 객체가 필요합니다.'); if(Object.keys(body).some(k=>!allowed.includes(k))) throw new PagesError(400,'알 수 없는 입력 필드가 있습니다.'); if(required.some(k=>!own(body,k))) throw new PagesError(400,'필수 입력 필드가 누락되었습니다.'); }
  function instant(value) { if(typeof value!=='string'||!/(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null; const n=Date.parse(value); return Number.isFinite(n)?n:null; }
  function contains(text,terms) { return terms.some(term=>text.includes(term)); }
  function afterReopen(i,r) { const h=i.outcome_history||[]; if(!h.length) return true; const p=h[h.length-1]; if(own(p,'report_ids_at_reopen')) return !p.report_ids_at_reopen.includes(r.id); const a=instant(p.reopened_at),b=instant(r.received_at); return a===null || b!==null&&(b>a||b===a&&['additional','correction'].includes(r.kind)); }
  function fullConfirmation(r,people) { const t=(r.text||'').replace(NO_RESIDUAL,''); return r.kind==='field'&&validCount(r.people_count)&&validCount(people)&&r.people_count===people&&!NEGATIVE.test(t)&&!RESIDUAL.test(t)&&!contains(t,CONTACT)&&contains(t,['확인','구조','대피','인계','안전','대면','만났']); }
  function latestChange(i,key) { const times=(i.audit||[]).filter(a=>object(a.before)&&object(a.after)&&own(a.before,key)&&own(a.after,key)&&a.before[key]!==a.after[key]).map(a=>instant(a.created_at)).filter(n=>n!==null); return times.length?Math.max(...times):null; }
  function evidence(r) { return typeof r.text==='string'&&r.text?{report_id:r.id,quote:r.text.slice(0,240),received_at:r.received_at}:null; }
  function deriveAttention(i) {
    if(i.status==='closed') return [];
    const reports=i.reports||[], active=reports.map((r,n)=>[n,r]).filter(([,r])=>afterReopen(i,r)),people=i.people_count,entries=[];
    function add(id,level,title,situation,reason,next_action,action,basis) { const seen=new Set(),ev=[]; for(const r of basis){const e=evidence(r);if(e&&!seen.has(e.report_id)){seen.add(e.report_id);ev.push(e);}} entries.push({id:`${i.id}:${id}`,level,title,situation,reason,next_action,action,source:'rule',requires_human:true,evidence:ev}); }
    const corrections=active.filter(([,r])=>r.kind==='correction'&&own(r,'people_count'));
    const correction=corrections.length?corrections[corrections.length-1][0]:-1,changed=latestChange(i,'people_count');
    function afterCount(n,r,inclusive=false) { if(n<correction||n===correction&&!inclusive)return false; if(inclusive&&n===correction)return true;const t=instant(r.received_at);return changed===null||t!==null&&t>changed; }
    const field=active.filter(([n,r])=>r.kind==='field'&&afterCount(n,r)),latest=field.length?field[field.length-1][1]:null,full=field.filter(([,r])=>fullConfirmation(r,people)),fullIndex=full.length?full[full.length-1][0]:-1;
    const residual=active.filter(([n,r])=>afterCount(n,r,true)&&n>fullIndex&&RESIDUAL.test((r.text||'').replace(NO_RESIDUAL,'')));
    const conflicts=active.filter(([n,r])=>r.kind==='additional'&&validCount(r.people_count)&&r.people_count!==people&&afterCount(n,r));
    let basis=conflicts.map(([,r])=>r),situation=[],reason=[],level='decision';
    if(residual.length){level='immediate';basis.push(residual[residual.length-1][1]);situation.push('최신 원문에 남은 대상의 상태 확인이 필요한 내용이 있습니다.');reason.push('남은 대상의 현재 상태를 현장에서 확인해야 합니다.');}
    if(validCount(people)&&latest&&validCount(latest.people_count)){
      if(latest.people_count<people){level='immediate';basis=[latest,...conflicts.map(([,r])=>r)];situation=[`접수 ${people}명 / 현장 확인 ${latest.people_count}명입니다.`];reason=[`${people-latest.people_count}명의 상태가 미확인입니다. 남은 대상의 현장 확인이 필요합니다.`];}
      else if(latest.people_count>people){basis.push(latest);situation.push(`접수 ${people}명과 현장 보고 ${latest.people_count}명이 충돌합니다.`);reason.push('확인 대상 총수의 명시 정정이 필요합니다. 여러 보고의 인원을 합산하지 않습니다.');}
      else if(NEGATIVE.test(latest.text.replace(NO_RESIDUAL,''))&&!contains(latest.text,CONTACT)){basis.push(latest);situation.push('보고 인원은 접수 인원과 같지만 원문에 상태를 확인하지 못했다고 기록되어 있습니다.');reason.push('전체 대상의 현재 상태를 현장에서 다시 확인해야 합니다.');}
    }
    if(conflicts.length){situation.push('추가 정보의 인원이 현재 접수 인원과 다릅니다.');reason.push('새 인원 정보를 공식 접수 인원에 자동 반영하지 않았습니다. 전체 대상과 정정 근거를 확인하세요.');}
    if(!validCount(people)){if(active.length)basis.push(active[active.length-1][1]);situation.push('현재 접수 인원이 알려지지 않았습니다.');reason.push('확인할 전체 인원을 모르면 현장 보고와 처리 결과를 대조할 수 없습니다.');}
    if(reason.length)add('people',level,'전체 대상 인원·현재 상태 대조',situation.join(' '),reason.join(' '),'전체 대상과 남은 인원을 현장에서 확인하고, 필요하면 인원 정정 원문을 등록하세요.','field-report',basis);
    const contact=active.filter(([,r])=>contains(r.text||'',CONTACT));
    if(contact.length){const [n,r]=contact[contact.length-1],resolved=field.some(([p,f])=>p>n&&fullConfirmation(f,people)&&contains(f.text,['현장','직접','대면','대상','연락 재개','연락이 닿','통화','응답 확인']));if(!resolved){if(reason.length){entries[0].reason+=' 연락 두절 신고도 있어 현재 안부를 현장에서 확인해야 합니다.';const e=evidence(r);if(e&&!entries[0].evidence.some(a=>a.report_id===e.report_id))entries[0].evidence.push(e);}else add('contact','decision','연락 두절 대상의 현재 상태 확인','원문에 연락 두절 또는 무응답이 신고되어 있습니다.','현재 안부는 후속 현장 확인이 필요합니다.','구조 대상과 현장 확인을 대조한 새 보고를 등록하세요.','field-report',[r]);}}
    const locationCorrections=active.filter(([,r])=>r.kind==='correction'&&own(r,'location')),locationIndex=locationCorrections.length?locationCorrections[locationCorrections.length-1][0]:-1,locationChanged=latestChange(i,'location');
    const proxies=active.filter(([n,r])=>{const t=instant(r.received_at);return n>locationIndex&&contains(r.text||'',PROXY)&&(locationChanged===null||t!==null&&t>locationChanged);});
    if(proxies.length)add('location','decision','신고자 위치와 구조 대상 위치 구분','대리 신고 또는 휴대폰 위치의 대상 구분이 필요한 원문이 있습니다.','구조 대상 주소와 신고자 휴대폰 위치를 대조해야 합니다.','대상 위치를 확인하고 명시 위치 정정 정보를 등록하세요.','report',[proxies[proxies.length-1][1]]);
    if((i.outcome_history||[]).length&&!full.length){if(reason.length)entries[0].reason+=' 재개 이후 전체 대상을 확인한 새 현장 근거가 필요합니다.';else add('reopened','decision','재개 이후 새 현장 근거 확인','완료 결과를 보존하고 사건을 다시 확인 상태로 열었습니다.','재개 전 현장 보고는 현재 확인을 대신할 수 없습니다. 새 정보 이후 전체 대상의 확인이 필요합니다.','재개 이후 현장에서 확인한 대상과 인원을 보고로 등록하세요.','field-report',active.slice(-1).map(([,r])=>r));}
    if(!i.assigned_team_id){const p=i.priority||'normal',l=p==='urgent'?'immediate':p==='high'?'decision':'follow_up';add('assignment',l,'대응팀 배정 판단',`담당자 우선도는 ${{urgent:'긴급',high:'높음',normal:'보통'}[p]||p}이고 담당팀은 미배정입니다.`,'현재 신고 상황과 가용팀을 대조해 담당자가 배정 여부를 판단해야 합니다.','가용팀과 사건 정보를 확인한 뒤 담당팀·진행을 지정하세요.','progress',active.length?[active[0][1]]:reports.slice(0,1));}
    return entries.sort((a,b)=>LEVELS[a.level]-LEVELS[b.level]||TASKS[a.id.split(':').pop()]-TASKS[b.id.split(':').pop()]||a.id.localeCompare(b.id));
  }
  function decorated(raw) {
    const i=clone(raw),reports=i.reports||[],field=reports.filter(r=>r.kind==='field'&&afterReopen(i,r)),latest=field[field.length-1],matches=!!latest&&fullConfirmation(latest,i.people_count);
    i.checks=(i.checks||[]).filter(c=>!c.id.startsWith('rule-'));
    for(const c of i.checks){c.detail=c.detail.replace('confirmed_count=3 또는 2','확인 인원 3명 또는 2명');if(i.status==='closed'||matches&&['인원','부분'].some(w=>c.title.includes(w)))c.level='info';}
    function add(id,title,detail,rs,level='warning'){i.checks.push({id:`rule-${id}`,level:i.status==='closed'?'info':level,title,detail,report_ids:rs});}
    for(const r of reports){const t=r.text;
      if(r.kind==='field'&&r.people_count!==i.people_count){const old=matches&&latest.id!==r.id;add(`count-${r.id}`,'현장 인원 대조',old?`이전 보고 ${r.people_count===undefined?'미확인':r.people_count}명과 접수 ${i.people_count}명 차이가 있었습니다. 최신 현장 보고 ${latest.people_count}명으로 대조했으며 이전 원문을 보존합니다.`:'현장 보고 인원과 현재 접수 인원이 다릅니다. 부분 구조만으로 처리 완료할 수 없습니다.',[r.id],old?'info':'warning');}
      if(contains(t,['다른 세대','다른 가구','같은 건물','동일 건물']))add(`household-${r.id}`,'개별 세대 확인','동일 위치의 다른 세대 요청을 구분하고 각 원문을 확인하세요.',[r.id]);
      if(contains(t,['GPS','제 휴대폰 위치','어머니 집이 아니','신고자 위치']))add(`gps-${r.id}`,'신고자 위치와 대상 위치 구분','휴대폰 위치가 구조 대상 위치인지 별도로 확인하세요.',[r.id]);
      if(contains(t,['연락이 끊','연락 두절','응답 없','응답이 없']))add(`contact-${r.id}`,'연락 두절 확인','연락 여부만으로 결과를 확정하지 말고 현장 근거를 확인하세요.',[r.id]);
      if(r.kind==='correction'&&own(r,'location'))add(`location-${r.id}`,'위치 정정 이력','원문 위치와 담당자가 정정한 현재 위치를 함께 확인하세요.',[r.id],'info');
    }
    if(i.status!=='closed'&&reports.some(r=>r.kind==='field'))add('outcome','처리 결과 미확정','현장 보고가 있어도 담당자 결과 확정 전까지 진행 사건으로 유지됩니다.',reports.filter(r=>r.kind==='field').map(r=>r.id));
    i.attention=deriveAttention(i);const causes=new Set(i.attention.map(a=>a.id.split(':').pop()));if(i.attention.some(a=>a.reason.includes('연락 두절 신고')))causes.add('contact');
    const descriptions={people:'이전 인원 대조 기록입니다. 현재 판단은 최신 원문과 명시 인원 정정을 기준으로 표시합니다.',contact:'이전 연락 확인 기록입니다. 현재 판단은 재개 시점과 최신 현장 확인 원문을 기준으로 표시합니다.',location:'이전 위치 확인 기록입니다. 현재 위치 판단은 명시 정정과 최신 원문을 기준으로 표시합니다.'};
    for(const c of i.checks){let cause=null;if(c.id.startsWith('rule-count-')||contains(c.title,['인원','부분','잔여 대상']))cause='people';else if(c.id.startsWith('rule-contact-')||contains(c.title,['연락','무응답','응답']))cause='contact';else if(c.id.startsWith('rule-gps-')||contains(c.title,['위치','GPS','좌표']))cause='location';if(cause&&!causes.has(cause)){c.level='info';if(!(cause==='people'&&c.detail.startsWith('이전 보고 ')))c.detail=descriptions[cause];}}
    return i;
  }
  function validHeader(bytes,mime) {
    const eq=(start,text)=>Array.from(text).every((c,n)=>bytes[start+n]===c.charCodeAt(0));
    function scan(text){for(let n=0;n<=bytes.length-text.length;n++)if(eq(n,text))return true;return false;}
    if(mime==='image/png')return bytes.length>=33&&[137,80,78,71,13,10,26,10].every((n,k)=>bytes[k]===n)&&eq(12,'IHDR');
    if(mime==='image/jpeg')return bytes.length>=4&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255&&bytes[bytes.length-2]===255&&bytes[bytes.length-1]===217;
    if(mime==='audio/wav')return bytes.length>=44&&eq(0,'RIFF')&&eq(8,'WAVE')&&scan('fmt ')&&scan('data');
    if(mime==='audio/mpeg')return bytes.length>=10&&(eq(0,'ID3')||bytes[0]===255&&(bytes[1]&224)===224);
    if(mime==='video/mp4')return bytes.length>=16&&eq(4,'ftyp')&&new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength).getUint32(0)>=16;
    return false;
  }
  function createStore(options={}) {
    let basePath=options.basePath||'/'; if(!basePath.startsWith('/')||basePath.includes('..')||/[?#\\]/.test(basePath))throw new PagesError(400,'배포 경로가 올바르지 않습니다.');if(!basePath.endsWith('/'))basePath+='/';
    const storageKey=`rescue-pages:v${VERSION}:${basePath}`,clock=options.now||(()=>new Date().toISOString()),uuid=options.uuid||(()=>typeof crypto==='object'&&crypto.randomUUID?crypto.randomUUID():`${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`);
    let sequence=0,seedPromise=null;
    const id=prefix=>`${prefix}-${String(uuid()).replace(/[^a-zA-Z0-9_-]/g,'')}-${++sequence}`;
    function storage(){try{const s=typeof options.storage==='function'?options.storage():options.storage;if(!s||typeof s.getItem!=='function'||typeof s.setItem!=='function')throw new Error();return s;}catch(_){throw new PagesError(503,'브라우저 저장소를 사용할 수 없습니다. 저장 허용 설정을 확인하세요.');}}
    function read(s){let text;try{text=s.getItem(storageKey);}catch(_){throw new PagesError(503,'브라우저 저장 자료를 읽을 수 없습니다.');}if(text===null)return null;let value;try{value=JSON.parse(text);}catch(_){throw new PagesError(503,'브라우저 저장 자료 형식이 손상되었습니다. 기존 자료를 자동 초기화하지 않습니다.');}if(!object(value)||value.schema_version!==VERSION||value.synthetic!==true||!Array.isArray(value.incidents)||!Array.isArray(value.resources)||!object(value.uploads))throw new PagesError(503,'브라우저 저장 자료 버전을 확인할 수 없습니다. 기존 자료를 유지합니다.');return value;}
    function write(s,value){try{s.setItem(storageKey,JSON.stringify(value));}catch(_){throw new PagesError(507,'브라우저 저장 공간이 부족하거나 저장이 차단되었습니다. 입력을 보존하고 첨부 크기와 저장 설정을 확인하세요.');}}
    async function init(s){let value=read(s);if(value)return value;if(!seedPromise)seedPromise=Promise.resolve().then(()=>options.seed!==undefined?clone(options.seed):options.loadSeed?options.loadSeed():Promise.reject(new PagesError(503,'합성 초기 자료가 없습니다.'))).catch(error=>{seedPromise=null;throw error;});let seed;try{seed=await seedPromise;}catch(error){if(error instanceof PagesError)throw error;throw new PagesError(503,'합성 초기 자료를 읽을 수 없습니다.');}value=read(s);if(value)return value;if(!object(seed)||seed.synthetic!==true||!Array.isArray(seed.incidents)||!Array.isArray(seed.resources)||seed.incidents.some(i=>i.synthetic!==true))throw new PagesError(400,'합성 초기 자료만 사용할 수 있습니다.');value={schema_version:VERSION,synthetic:true,incidents:clone(seed.incidents).map(i=>{if(own(i,'demo_featured')&&typeof i.demo_featured!=='boolean')throw new PagesError(400,'발표 대표 사례 표시는 boolean이어야 합니다.');delete i.attention;return i;}),resources:clone(seed.resources),uploads:{}};write(s,value);return value;}
    function before(i){const keys=['title','location','priority','people_count','status','assigned_team_id','revision','outcome','intake119'];return Object.fromEntries(keys.map(k=>[k,clone(i[k]??null)]));}
    function save(i,old,action,actor,reason){i.revision++;i.updated_at=clock();i.audit.push({id:id('AUD'),action,actor,reason,created_at:i.updated_at,before:old,after:before(i)});delete i.attention;return decorated(i);}
    function actor(b){return string(own(b,'actor')?b.actor:'상황실 김담당','담당자');}
    function get(value,iid){const i=value.incidents.find(i=>i.id===iid);if(!i)throw new PagesError(404,'사건을 찾을 수 없습니다.');return i;}
    function team(value,tid){string(tid,'팀 ID');const t=value.resources.find(t=>t.id===tid);if(!t)throw new PagesError(400,'등록된 팀이 아닙니다.');return t;}
    function revision(i,b){if(count(b.expected_revision,'expected_revision')!==i.revision)throw new PagesError(409,'다른 화면에서 사건을 수정했습니다. 최신 사건을 다시 확인하세요.');}
    function restore(i,a,reason){if(i.outcome!==null){i.outcome_history.push({...clone(i.outcome),reopened_at:clock(),reopen_reason:reason,reopened_by:a,report_ids_at_reopen:i.reports.map(r=>r.id)});}i.outcome=null;i.status='reviewing';}
    // Original v1 registrations used url=dataURI. Keep them readable without resetting storage.
    function uploadPayload(up){return typeof up.data_url==='string'?up.data_url:up.url;}
    function uploadLogical(up){
      if(options.cloud===true&&typeof up.url==='string'&&/^\/api\/media\/[A-Za-z0-9_-]+$/.test(up.url))return up.url;
      if(typeof up.url==='string'&&up.url.startsWith('/media/uploads/'))return up.url;
      const payload=uploadPayload(up),mime=typeof payload==='string'&&/^data:([^;,]+);base64,/.exec(payload);
      return mime&&own(MIME,mime[1])?`/media/uploads/${up.id}${MIME[mime[1]][1]}`:null;
    }
    function registeredUpload(value,attachment){
      const up=own(value.uploads,attachment.id)?value.uploads[attachment.id]:null;
      return up&&typeof attachment.url==='string'&&(attachment.url===uploadLogical(up)||attachment.url===up.url)?up:null;
    }
    function attachments(value,list){
      if(!Array.isArray(list)||list.length>20)throw new PagesError(400,'첨부는 최대 20개 배열이어야 합니다.');
      const ids=new Set(),result=[];
      for(const a of list){
        fields(a,['id','url','filename','media_type','caption','source','transcript'],['id','url','filename','media_type','caption','source']);
        for(const k of ['id','filename','caption'])string(a[k],`첨부 ${k}`,k==='caption');
        if(ids.has(a.id))throw new PagesError(400,'첨부 ID가 중복되었습니다.');ids.add(a.id);
        // A legacy registered dataURL can exceed ordinary text limits. Only the registry can authorize it.
        if(typeof a.url!=='string')throw new PagesError(400,'등록된 첨부 URL이 필요합니다.');
        const mime=own(SEED_MEDIA,a.url)?SEED_MEDIA[a.url]:null,copy=clone(a);
        if(mime){choice(a.media_type,[MIME[mime][0]],'첨부 종류');choice(a.source,['ai_generated','tts_synthetic'],'첨부 출처');}
        else{
          const up=registeredUpload(value,a),logical=up&&uploadLogical(up);
          if(!up||!logical||up.media_type!==a.media_type||a.source!=='operator_upload')throw new PagesError(400,'등록된 로컬 첨부 자료만 사용할 수 있습니다.');
          copy.url=logical;
        }
        if(own(a,'transcript'))string(a.transcript,'첨부 대본',true);
        result.push(copy);
      }
      return result;
    }
    function upload(value,b){fields(b,['filename','content_type','data_base64'],['filename','content_type','data_base64']);string(b.filename,'파일명');if(/[\/\\\x00-\x1f]/.test(b.filename)||b.filename.length>255)throw new PagesError(400,'파일명에 경로나 제어 문자를 사용할 수 없습니다.');choice(b.content_type,Object.keys(MIME),'파일 종류');if(typeof b.data_base64!=='string'||b.data_base64.length>4*Math.ceil(MAX_UPLOAD/3))throw new PagesError(413,'첨부 파일은 최대 8MiB입니다.');const padding=b.data_base64.endsWith('==')?2:b.data_base64.endsWith('=')?1:0;if(b.data_base64.length*3/4-padding>MAX_UPLOAD)throw new PagesError(413,'첨부 파일은 최대 8MiB입니다.');if(b.data_base64.length%4!==0||/[^A-Za-z0-9+/]/.test(b.data_base64.slice(0,b.data_base64.length-padding)))throw new PagesError(400,'첨부 base64 데이터가 잘못되었습니다.');let bytes;try{if(options.decodeBase64)bytes=options.decodeBase64(b.data_base64);else if(typeof Buffer==='function')bytes=Uint8Array.from(Buffer.from(b.data_base64,'base64'));else bytes=Uint8Array.from(atob(b.data_base64),c=>c.charCodeAt(0));}catch(_){throw new PagesError(400,'첨부 base64 데이터가 잘못되었습니다.');}if(!bytes.length||bytes.length>MAX_UPLOAD)throw new PagesError(413,'첨부 파일은 비어 있지 않고 최대 8MiB여야 합니다.');if(!validHeader(bytes,b.content_type))throw new PagesError(400,'첨부 파일 헤더가 선언된 파일 종류와 일치하지 않습니다.');const uid=id('UPL'),a={id:uid,url:`/media/uploads/${uid}${MIME[b.content_type][1]}`,filename:b.filename,media_type:MIME[b.content_type][0],caption:b.filename,source:'operator_upload'};value.uploads[a.id]={...a,data_url:`data:${b.content_type};base64,${b.data_base64}`};return a;}
    function mutate(value,path,method,b){
      if(method==='POST'&&path==='/api/uploads')return upload(value,b);
      if(method==='POST'&&path==='/api/incidents'){
        fields(b,['title','category','location','priority','summary','people_count','channel','text','actor','attachments','intake119'],['title','location','text']);for(const k of ['title','location','text'])string(b[k],k);const a=actor(b),category=choice(own(b,'category')?b.category:'rescue',CATEGORIES,'분류'),priority=choice(own(b,'priority')?b.priority:'normal',PRIORITIES,'우선도'),channel=choice(own(b,'channel')?b.channel:'sms',CHANNELS,'채널'),people=own(b,'people_count')?count(b.people_count):null,summary=string(own(b,'summary')?b.summary:'','요약',true),files=attachments(value,own(b,'attachments')?b.attachments:[]),time=clock();let n=1,prefix=`INC-${time.slice(0,10).replace(/-/g,'')}-`;while(value.incidents.some(i=>i.id===`${prefix}${String(n).padStart(3,'0')}`))n++;
        const r={id:id('REP'),channel,actor:a,text:b.text,kind:'initial',received_at:time,occurred_at:time,attachments:files};if(people!==null)r.people_count=people;
        const i={id:`${prefix}${String(n).padStart(3,'0')}`,title:b.title,category,location:b.location,priority,status:'received',summary,people_count:people,revision:1,created_at:time,updated_at:time,assigned_team_id:null,synthetic:true,reports:[r],progress:[],audit:[],outcome:null,outcome_history:[],checks:[]};if(own(b,'intake119')){if(!object(b.intake119))throw new PagesError(400,'119 접수 정보는 객체여야 합니다.');i.intake119=clone(b.intake119);}
        i.audit.push({id:id('AUD'),action:'create',actor:a,reason:'신규 합성 신고 접수',created_at:time,before:null,after:before(i)});value.incidents.push(i);return decorated(i);
      }
      const match=/^\/api\/incidents\/([A-Za-z0-9_-]+)(?:\/(reports|progress|outcome|reopen))?$/.exec(path);if(!match)throw new PagesError(404,'허용된 API가 아닙니다.');const i=get(value,match[1]),action=match[2],a=actor(b);
      if(method==='PATCH'&&!action){fields(b,['expected_revision','actor','reason','title','location','priority','people_count','intake119'],['expected_revision','reason']);string(b.reason,'수정 이유');const keys=['title','location','priority','people_count','intake119'].filter(k=>own(b,k));if(!keys.length)throw new PagesError(400,'수정할 필드를 입력하세요.');for(const k of keys){if(k==='intake119'){if(!object(b[k]))throw new PagesError(400,'119 접수 정보는 객체여야 합니다.');}else if(k==='people_count')count(b[k]);else if(k==='priority')choice(b[k],PRIORITIES,'우선도');else string(b[k],k);}revision(i,b);const old=before(i),important=['people_count','location'].some(k=>own(b,k)&&b[k]!==i[k]);for(const k of keys)i[k]=b[k];if(i.status==='closed'&&important)restore(i,a,b.reason);if(own(b,'location')&&b.location!==old.location)i.checks.push({id:id('CHK'),level:'info',title:'담당자 위치 수정',detail:b.reason,report_ids:[]});return save(i,old,'incident_updated',a,b.reason);}
      if(method!=='POST'||!action)throw new PagesError(405,'이 경로에서 사용할 수 없는 요청 방식입니다.');
      if(action==='reports'){fields(b,['expected_revision','channel','actor','text','kind','people_count','location','attachments','intake119'],['expected_revision','channel','text','kind']);choice(b.channel,CHANNELS,'채널');choice(b.kind,['additional','field','correction'],'보고 종류');string(b.text,'보고 원문');if(own(b,'people_count'))count(b.people_count);if(own(b,'location'))string(b.location,'위치');if(own(b,'intake119')&&!object(b.intake119))throw new PagesError(400,'119 접수 정보는 객체여야 합니다.');if(b.kind==='correction'&&!own(b,'people_count')&&!own(b,'location'))throw new PagesError(400,'정정 보고에는 정정 인원 또는 위치가 필요합니다.');const files=attachments(value,own(b,'attachments')?b.attachments:[]);revision(i,b);const old=before(i),time=clock(),r={id:id('REP'),channel:b.channel,actor:a,text:b.text,kind:b.kind,received_at:time,occurred_at:time,attachments:files};for(const k of ['people_count','location'])if(own(b,k)){r[k]=b[k];if(b.kind==='correction')i[k]=b[k];}if(own(b,'intake119'))r.intake119=clone(b.intake119);if(i.status==='closed')restore(i,a,'완료 후 추가 정보 도착: '+b.text);i.reports.push(r);return save(i,old,'report_added',a,b.text);}
      if(action==='progress'){fields(b,['expected_revision','actor','status','team_id','note'],['expected_revision','status','note']);choice(b.status,['dispatched','on_scene','rescuing','reviewing'],'진행 상태');string(b.note,'진행 메모');if(own(b,'team_id'))string(b.team_id,'팀 ID');revision(i,b);if(i.status==='closed')throw new PagesError(409,'완료 사건은 사유를 입력해 재개한 뒤 진행을 변경하세요.');const old=before(i),tid=own(b,'team_id')?b.team_id:i.assigned_team_id;if(tid===null&&b.status!=='reviewing')throw new PagesError(400,'출동·현장·구조 진행에는 담당팀이 필요합니다.');if(tid!==null){const t=team(value,tid);if(t.incident_id!==null&&t.incident_id!==i.id)throw new PagesError(409,'이 팀은 다른 사건에 배정되어 있습니다.');if(i.assigned_team_id&&i.assigned_team_id!==tid){Object.assign(team(value,i.assigned_team_id),{status:'available',incident_id:null});}Object.assign(t,{status:'assigned',incident_id:i.id});}i.assigned_team_id=tid;i.status=b.status;i.progress.push({id:id('PRG'),status:b.status,team_id:tid,note:b.note,actor:a,created_at:clock()});return save(i,old,'progress_added',a,b.note);}
      if(action==='outcome'){fields(b,['expected_revision','actor','outcome','confirmed_count','basis_report_id','note'],['expected_revision','outcome','confirmed_count','basis_report_id','note']);choice(b.outcome,['rescued','self_evacuated','transferred'],'결과');count(b.confirmed_count,'확인 인원');string(b.basis_report_id,'근거 보고 ID');string(b.note,'결과 확인 메모');revision(i,b);if(i.status==='closed')throw new PagesError(409,'결과 변경은 사유를 입력해 사건을 재개한 뒤 확정하세요.');const r=i.reports.find(r=>r.id===b.basis_report_id);if(i.people_count===null||b.confirmed_count!==i.people_count||!r||r.kind!=='field'||r.people_count!==b.confirmed_count)throw new PagesError(400,'현재 접수 인원과 같은 사건의 현장 보고 인원이 모두 일치해야 결과를 확정할 수 있습니다.');if(i.outcome_history.length){const p=i.outcome_history[i.outcome_history.length-1],stale=own(p,'report_ids_at_reopen')?p.report_ids_at_reopen.includes(r.id):p.reopened_at&&(instant(r.received_at)===null||instant(r.received_at)<=instant(p.reopened_at));if(stale)throw new PagesError(400,'재개 이후의 새로운 현장 보고가 필요합니다. 과거 완료 근거는 재사용할 수 없습니다.');}if(!fullConfirmation(r,i.people_count))throw new PagesError(400,'현장 원문에 남은 대상이나 미확인 상태가 있습니다. 전체 대상의 안전 확인 근거가 필요합니다.');const basisIndex=i.reports.indexOf(r);if(i.reports.slice(basisIndex+1).some(newer=>{const raw=(newer.text||'').replace(NO_RESIDUAL,'');return NEGATIVE.test(raw)||RESIDUAL.test(raw)||contains(raw,CONTACT)||newer.kind==='field'&&!fullConfirmation(newer,b.confirmed_count)||newer.kind==='correction'&&['people_count','location'].some(k=>own(newer,k));}))throw new PagesError(400,'선택한 현장 근거 이후 새 미확인 정보가 있습니다. 최신 현장 확인이 필요합니다.');const corrections=i.reports.map((r,n)=>r.kind==='correction'&&own(r,'people_count')?n:-1),last=Math.max(-1,...corrections);if(i.reports.slice(last+1).some(r=>r.kind==='additional'&&own(r,'people_count')&&r.people_count!==b.confirmed_count))throw new PagesError(400,'추가 신고의 확인 대상 총수가 다릅니다. 인원 정정 근거를 먼저 등록하세요.');const old=before(i);i.status='closed';i.outcome={outcome:b.outcome,confirmed_count:b.confirmed_count,basis_report_id:r.id,note:b.note,actor:a,confirmed_at:clock()};if(i.assigned_team_id)Object.assign(team(value,i.assigned_team_id),{status:'available',incident_id:null});i.assigned_team_id=null;return save(i,old,'outcome_confirmed',a,b.note);}
      if(action==='reopen'){fields(b,['expected_revision','actor','reason'],['expected_revision','reason']);string(b.reason,'재개 사유');revision(i,b);if(i.status!=='closed')throw new PagesError(409,'처리 완료 사건만 재개할 수 있습니다.');const old=before(i);restore(i,a,b.reason);return save(i,old,'incident_reopened',a,b.reason);}
      throw new PagesError(404,'허용된 API가 아닙니다.');
    }
    function list(value){const items=value.incidents.map(decorated),active=items.filter(i=>i.status!=='closed'),closed=items.filter(i=>i.status==='closed');active.sort((a,b)=>Number(b.demo_featured===true)-Number(a.demo_featured===true)||Math.min(3,...a.attention.map(t=>LEVELS[t.level]))-Math.min(3,...b.attention.map(t=>LEVELS[t.level]))||PRIORITIES.indexOf(a.priority)-PRIORITIES.indexOf(b.priority)||(instant(a.created_at)||0)-(instant(b.created_at)||0)||a.id.localeCompare(b.id));closed.sort((a,b)=>(instant(b.updated_at)||0)-(instant(a.updated_at)||0)||b.id.localeCompare(a.id));return {incidents:[...active,...closed],resources:clone(value.resources)};}
    function request(path,{method='GET',body}={}) {
      let input;try{input=body===undefined?undefined:clone(body);}catch(_){return Promise.reject(new PagesError(400,'JSON 입력 형식을 확인하세요.'));}
      let s;try{s=storage();}catch(error){return Promise.reject(error);}let map=QUEUES.get(s);if(!map){map=new Map();QUEUES.set(s,map);}const old=map.get(storageKey)||Promise.resolve();
      const operation=async()=>{const current=await init(s);if(method==='GET'){if(path==='/api/incidents')return list(current);const m=/^\/api\/incidents\/([A-Za-z0-9_-]+)$/.exec(path);if(m)return decorated(get(current,m[1]));throw new PagesError(404,'허용된 API가 아닙니다.');}if(!['POST','PATCH'].includes(method))throw new PagesError(405,'이 요청 방식은 지원하지 않습니다.');if(!object(input))throw new PagesError(400,'JSON 객체가 필요합니다.');const next=clone(current),result=mutate(next,path,method,input);write(s,next);return clone(result);};
      const locks=options.locks,result=old.catch(()=>{}).then(()=>locks&&typeof locks.request==='function'?locks.request(storageKey,{mode:'exclusive'},operation):operation());map.set(storageKey,result.catch(()=>{}));return result;
    }
    function mediaUrl(url){if(typeof url!=='string')return null;if(own(SEED_MEDIA,url))return basePath+url.slice(1);const prefixed=basePath+'media/';if(url.startsWith(prefixed)&&own(SEED_MEDIA,'/media/'+url.slice(prefixed.length)))return url;try{const value=read(storage());if(value){const up=Object.values(value.uploads).find(a=>uploadLogical(a)===url||a.url===url);if(up){const payload=uploadPayload(up);return typeof payload==='string'&&/^data:(?:image\/(?:png|jpeg)|audio\/(?:wav|mpeg)|video\/mp4);base64,/.test(payload)?payload:null;}}}catch(_){return null;}return null;}
    return {request,mediaUrl,storageKey,basePath};
  }
  return {createStore,deriveAttention,validHeader,PagesError,VERSION};
});
