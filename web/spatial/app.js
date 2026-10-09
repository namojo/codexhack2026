'use strict';
const data=JSON.parse(document.getElementById('spatial-data').textContent);
const report=data.report,analysis=data.analysis;const $=id=>document.getElementById(id);
$('report-text').textContent=report.text;$('analysis-json').textContent=JSON.stringify(analysis,null,2);
const evidenceItems=data.display_evidence;for(const text of evidenceItems){const li=document.createElement('li');li.textContent=text;$('evidence').append(li)}
$('unknowns').textContent='미확인: 사진만으로 정확한 방 좌표·층·사람 수·실제 현장 위험을 확정할 수 없습니다.';
const raw=data.floor_model;
const bounds=[.108,.2121,.9054,.9839];
function box(b){return [(b[0]-bounds[0])/(bounds[2]-bounds[0])*100,(b[1]-bounds[1])/(bounds[3]-bounds[1])*64,(b[2]-b[0])/(bounds[2]-bounds[0])*100,(b[3]-b[1])/(bounds[3]-bounds[1])*64]}
function point(p){return [(p[0]-bounds[0])/(bounds[2]-bounds[0])*100,(p[1]-bounds[1])/(bounds[3]-bounds[1])*64]}
const descriptions={A1:'도면 위쪽 왼편의 세대. 이번 원문은 이 세대를 지정하지 않습니다.',B2:'B타입 세대. 라인 지정이 없으면 비교 후보에 포함됩니다.',B3:'원문이 지정한 가상 라인. 현관·주방을 지난 외벽 창가의 주공간이 위치 후보입니다.',B4:'B타입 세대. 라인 지정이 없으면 비교 후보에 포함됩니다.',E7:'도면 아래쪽 왼편의 세대. 이번 원문의 B타입과 다릅니다.',D6:'도면 아래쪽 중앙의 세대. 실제 호실 대응은 확인되지 않았습니다.',C5:'도면 아래쪽 오른편의 세대. 실제 호실 대응은 확인되지 않았습니다.'};
const colors={A:'#ead6d4',B:'#dce5ce',E:'#d2deea',D:'#ddd9e8',C:'#eadfca'};
const units=raw.floor.units.map(u=>({id:u.type+u.id,name:u.type+'타입 '+u.id+'호',box:box(u.bbox),color:colors[u.type],desc:descriptions[u.type+u.id]}));
units.sort((a,b)=>['A1','B2','B3','B4','E7','D6','C5'].indexOf(a.id)-['A1','B2','B3','B4','E7','D6','C5'].indexOf(b.id));
for(const id of ['corridor','stairs','elevator']){const u=raw.floor.common_areas.find(a=>a.id===id);units.push({id,name:u.label,box:box(u.bbox),color:'#b9d5eb',desc:u.source_evidence+'. '+u.uncertainty})}
const internal=Object.fromEntries(raw.selected_unit.spaces.map(u=>[u.id,{...u,box:box(u.bbox)}]));
const entryPoint=point(raw.selected_unit.openings.find(o=>o.id==='entry_door').point);
const windowPoint=point(raw.selected_unit.openings.find(o=>o.id==='outer_window').point);
const region=box(analysis.candidates[0].proposed_region_bbox);
let selected='B3',selectedFloor=3,ambiguous=false,mode='building',yaw=-.22,pitch=.84,zoom=1;let hit=[];
const canvas=$('scene'),ctx=canvas.getContext('2d');
for(const unit of units){const b=document.createElement('button');b.textContent=unit.name;b.dataset.space=unit.id;b.setAttribute('aria-pressed',String(unit.id===selected));b.onclick=()=>select(unit.id);$('spaces').append(b)}
function select(id){selected=id;for(const b of $('spaces').children)b.setAttribute('aria-pressed',String(b.dataset.space===id));const u=units.find(u=>u.id===id);$('selected').replaceChildren();const strong=document.createElement('strong');strong.textContent=selectedFloor+'층 · '+u.name;const p=document.createElement('p');p.textContent=selectedFloor===3?u.desc:('3~16층 동일 평면 가정으로 표시한 공간입니다. 이 층에는 가상 신고가 없습니다. '+u.desc.replace('원문이 지정한 가상 라인.','같은 배치의 라인.').replace('위치 후보입니다.','주공간입니다.'));$('selected').append(strong,p);draw()}
function rect(x,y,w,h,z=0){return [[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]]}
function targetIDs(){return ambiguous?['B2','B3','B4']:['B3']}
function draw(){const width=canvas.clientWidth,height=canvas.clientHeight,dpr=window.devicePixelRatio||1;canvas.width=width*dpr;canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);hit=[];
 const tower=mode==='building',ca=Math.cos(yaw),sa=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
 const scale=Math.min(width/(tower?185:145),height/(tower?175:110))*zoom;
 const floorZ=tower?(selectedFloor-1)*7:0,centerZ=tower?54:0;
 function project(v){const x=v[0]-50,y=v[1]-32,z=(v[2]||0)-centerZ,rx=x*ca-y*sa,ry=x*sa+y*ca;return [width/2+rx*scale,height/2+(mode==='top'?ry:ry*cp-z*sp)*scale]}
 function depth(v){return (v[0]*sa+v[1]*ca)*sp+(v[2]||0)*cp}
 function path(points){ctx.beginPath();points.forEach((p,i)=>{const q=project(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.closePath()}
 function poly(points,fill,stroke='#8095a6'){path(points);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke()}}
 function line(points,color,dash=[],weight=1){ctx.save();ctx.strokeStyle=color;ctx.lineWidth=weight;ctx.setLineDash(dash);ctx.beginPath();points.forEach((v,i)=>{const p=project(v);i?ctx.lineTo(...p):ctx.moveTo(...p)});ctx.stroke();ctx.restore()}
 const labels=[];function label(text,v,color='#21425a',anchor=null){const q=project(v);const p=anchor||q;ctx.font='600 12px system-ui';const tw=ctx.measureText(text).width;const box={x:p[0]-tw/2-6,y:p[1]-11,w:tw+12,h:24};if(box.x<4||box.x+box.w>width-4||box.y<58||box.y+box.h>height-4)return false;if(labels.some(b=>box.x<b.x+b.w+3&&box.x+box.w+3>b.x&&box.y<b.y+b.h+3&&box.y+box.h+3>b.y))return false;labels.push(box);if(anchor){ctx.beginPath();ctx.moveTo(...q);ctx.lineTo(...p);ctx.strokeStyle=color;ctx.lineWidth=1;ctx.stroke()}ctx.fillStyle='#fffffff5';ctx.fillRect(box.x,box.y,box.w,box.h);ctx.strokeStyle='#d5dfe7';ctx.strokeRect(box.x,box.y,box.w,box.h);ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(text,p[0],p[1]+5);return true}
 if(tower){
   // 1–2F are intentionally unmodeled; no extrapolated interior layout.
   const fs=[{v:[[0,0,0],[100,0,0],[100,0,14],[0,0,14]],c:'#c8d1d9'},{v:[[100,0,0],[100,64,0],[100,64,14],[100,0,14]],c:'#b4c2ce'},{v:[[100,64,0],[0,64,0],[0,64,14],[100,64,14]],c:'#c2cdd6'},{v:[[0,64,0],[0,0,0],[0,0,14],[0,64,14]],c:'#d1d9e0'}];fs.sort((a,b)=>depth(a.v[0])-depth(b.v[0]));for(const f of fs)poly(f.v,f.c);
   for(let f=3;f<=16;f++){const z=(f-1)*7;poly(rect(0,0,100,64,z),'rgba(184,202,216,.10)','#a6b9c988');line([[0,0,z],[0,0,z+7]],'#9eb2c477');line([[100,0,z],[100,0,z+7]],'#9eb2c477');line([[100,64,z],[100,64,z+7]],'#9eb2c477');line([[0,64,z],[0,64,z+7]],'#9eb2c477');
     // Repeated unit boundaries preserve the plan's layout on each layer.
     for(const u of units.slice(0,7)){path(rect(...u.box,z));ctx.strokeStyle='#97b0c244';ctx.lineWidth=.7;ctx.stroke()}
   }
   path(rect(0,0,100,64,112));ctx.strokeStyle='#7895aa';ctx.lineWidth=1.4;ctx.stroke();
 }
 // Selected-layer cutaway: no claims about real building elevations or facades.
 poly(rect(0,0,100,64,floorZ),tower?'rgba(238,244,248,.91)':'#eef1ed');
 for(const u of units){poly(rect(...u.box,floorZ),u.color);hit.push({id:u.id,points:rect(...u.box,floorZ).map(project)})}
 for(const u of [internal.kitchen,internal.bathroom,internal.storage])poly(rect(...u.box,floorZ+.1),u.id==='bathroom'?'#e5ecec':'#aebcb4');
 const shaft=raw.floor.common_areas.find(u=>u.id==='service_shaft');poly(rect(...box(shaft.bbox),floorZ+.1),'#aab3bc');
 const hasRequest=selectedFloor===3;
 if(hasRequest)for(const id of targetIDs()){const u=units.find(x=>x.id===id),[x,y,w]=u.box,r=id==='B3'?region:[x+1.5,y+1.1,w-3,region[3]];poly(rect(...r,floorZ+.2),ambiguous?'#e7c989':'#f4bb60','#b07826')}
 const win=box(raw.selected_unit.openings.find(o=>o.id==='outer_window').extent);poly(rect(...win,floorZ+.2),'#55bacb','#319bad');
 const stairs=units.find(u=>u.id==='stairs').box,corridor=units.find(u=>u.id==='corridor').box;
 if($('connection').checked)line([[stairs[0]+stairs[2]/2,stairs[1]+stairs[3]/2,floorZ+.3],[82,42,floorZ+.3],[82,corridor[1]+corridor[3]/2,floorZ+.3],[entryPoint[0],corridor[1]+corridor[3]/2,floorZ+.3],[...entryPoint,floorZ+.3],[region[0]+region[2]/2,region[1]+region[3]/2,floorZ+.3]],'#667f97',[5,5],2);
 for(let y=stairs[1]+1;y<stairs[1]+stairs[3]-1;y+=1.6)poly(rect(stairs[0]+2,y,stairs[2]-4,.35,floorZ+.2),'#8097aa',null);
 const faces=[];function wall(a,b,z=4,color='#ccd8e0'){if(mode==='top'){line([[...a,floorZ],[...b,floorZ]],'#61798b',[],2);return}const vs=[[...a,floorZ],[...b,floorZ],[...b,floorZ+z],[...a,floorZ+z]];faces.push({vs,color,d:vs.reduce((s,v)=>s+depth(v),0)/4})}
 if($('walls').checked){for(const u of units.slice(0,7)){const [x,y,w,h]=u.box;wall([x,y],[x,y+h]);wall([x+w,y],[x+w,y+h]);wall([x,y<5?y:y+h],[x+w,y<5?y:y+h]);const wy=y<5?y+h:y,door=u.id==='B3'?entryPoint[0]:x+w*.65;wall([x,wy],[door-2,wy]);wall([door+2,wy],[x+w,wy])}const b=internal.bathroom.box;wall([b[0],b[1]],[b[0]+b[2],b[1]],2.5,'#b8c4b9');wall([b[0],b[1]],[b[0],b[1]+b[3]*.7],2.5,'#b8c4b9');faces.sort((a,b)=>a.d-b.d);for(const f of faces)poly(f.vs,f.color,'#8da0ae')}
 const u=units.find(u=>u.id===selected);path(rect(...u.box,floorZ+.3));ctx.strokeStyle='#225e9e';ctx.lineWidth=2.5;ctx.stroke();
 if(tower){path(rect(0,0,100,64,floorZ));ctx.strokeStyle=hasRequest?'#bc791f':'#225e9e';ctx.lineWidth=2.5;ctx.stroke();
   // Sparse outside labels; collision detection omits them at extreme zoom.
   for(const f of [16,selectedFloor,3]){if(f===3&&selectedFloor===3)continue;const q=project([100,64,(f-1)*7]);label(f+'F'+(f===selectedFloor?' · 선택':''),[100,64,(f-1)*7],f===3?'#865006':'#21425a',[Math.min(width-45,q[0]+45),q[1]])}
   if(selectedFloor===3){const q=project([100,64,14]);label('3F · 신고',[100,64,14],'#865006',[Math.min(width-48,q[0]+49),q[1]])}
   const q=project([0,64,5]);label('1~2F 미확인',[0,64,5],'#667f97',[Math.max(63,q[0]-58),q[1]]);
 }else{for(const u of units){const [x,y,w,h]=u.box;label(u.id==='corridor'?'복도':u.id==='stairs'?'계단':u.id==='elevator'?'승강기':u.id,[x+w/2,y+h/2,5])}}
 // No '?' or report text is painted on the scene: the stable status card owns it.
 $('scene-caption').textContent=tower?'전체 건물 투시도 · '+selectedFloor+'층 강조':selectedFloor+'층 '+(mode==='top'?'평면':'입체')+' · 도면 위쪽 ≠ 진북';
 $('scene-status').textContent=hasRequest?(ambiguous?'가상 신고: 3층 · B타입 2~4호 · 복수 후보':'가상 신고: 3층 · B타입 3호 라인 · 창가 구역'):selectedFloor+'층 배치 확인 · 이 층에는 가상 신고 없음';
 $('scene-detail').textContent=hasRequest?'2명은 원문 진술입니다. 색칠한 구역은 후보이며 정확한 사람 위치는 미확정입니다.':'신고는 3층에 유지됩니다. “신고 위치 보기”를 누르면 3층 후보를 다시 표시합니다.';
 window.spatialState={mode,selected,selectedFloor,ambiguous,yaw,pitch,zoom,focus:false,candidates:targetIDs(),visibleCandidates:hasRequest?targetIDs():[],modeledFloors:Array.from({length:14},(_,i)=>i+3),unknownFloors:[1,2],labelBoxes:labels};
}
function setMode(m){mode=m;for(const [id,name] of [['building','building'],['three','3d'],['top','top']])$(id).setAttribute('aria-pressed',String(m===name));draw()}
$('building').onclick=()=>setMode('building');$('three').onclick=()=>setMode('3d');$('top').onclick=()=>setMode('top');
$('floor-select').onchange=e=>{selectedFloor=+e.target.value;select(selected)};
$('focus').onclick=()=>{selectedFloor=3;$('floor-select').value='3';selected='B3';zoom=1.15;$('zoom').value=115;setMode('3d');select('B3')};
$('reset').onclick=()=>{yaw=-.22;pitch=.84;zoom=1;selectedFloor=3;$('zoom').value=100;$('floor-select').value='3';$('walls').checked=true;$('connection').checked=true;setMode('building');setAmbiguous(false);select('B3')};
$('zoom').oninput=e=>{zoom=+e.target.value/100;draw()};$('walls').onchange=draw;$('connection').onchange=draw;
function setAmbiguous(value){ambiguous=value;$('normal').setAttribute('aria-pressed',String(!value));$('ambiguous').setAttribute('aria-pressed',String(value));$('result').classList.toggle('empty',value);$('result').querySelector('strong').textContent=value?'B타입 2~4호 · 복수 후보':'B타입 3호 라인 · 창가 주공간';$('result').querySelector('p').textContent=value?'라인 정보가 없으면 사진만으로 같은 타입의 세대를 구분할 수 없습니다.':'정확한 점이 아닌 후보 구역입니다.';$('comparison').textContent=value?'규칙 기반 비교 목업: 3호 라인이 없으면 3층 B타입 2·3·4호를 모두 유지합니다. 다른 층의 요청을 새로 만들지 않습니다.':'원문의 라인 지정이 후보를 좁히는 주요 근거입니다.';draw()}
$('normal').onclick=()=>setAmbiguous(false);$('ambiguous').onclick=()=>setAmbiguous(true);
let drag=null;canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY};canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;yaw+=dx*.007;if(mode!=='top')pitch=Math.min(1.35,Math.max(.2,pitch+dy*.006));drag.x=e.clientX;drag.y=e.clientY;draw()};
canvas.onpointerup=e=>{if(drag&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<6){const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;for(const h of [...hit].reverse()){let inside=false;for(let i=0,j=h.points.length-1;i<h.points.length;j=i++){const a=h.points[i],b=h.points[j];if(((a[1]>y)!==(b[1]>y))&&(x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]))inside=!inside}if(inside){select(h.id);break}}}drag=null};canvas.onpointercancel=()=>drag=null;
canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-','=','Escape'].includes(e.key)){e.preventDefault();if(e.key==='ArrowLeft')yaw-=.12;if(e.key==='ArrowRight')yaw+=.12;if(e.key==='ArrowUp')pitch=Math.min(1.35,pitch+.08);if(e.key==='ArrowDown')pitch=Math.max(.2,pitch-.08);if(e.key==='+'||e.key==='=')zoom=Math.min(1.8,zoom+.1);if(e.key==='-')zoom=Math.max(.65,zoom-.1);if(e.key==='Escape')$('reset').click();$('zoom').value=Math.round(zoom*100);draw()}};
function imageDialog(src,title){$('dialog-image').src=src;$('dialog-image').alt=title;$('dialog-title').textContent=title;$('image-dialog').showModal()}
$('source-open').onclick=$('source-preview').onclick=()=>imageDialog('assets/floorplan-source.jpg','공개 3~16층 평면도 · 원본 대조');$('report-image').onclick=()=>imageDialog('assets/synthetic-report.png','합성 신고 이미지 · 실제 사고 사진 아님');$('close-dialog').onclick=()=>$('image-dialog').close();$('image-dialog').onclick=e=>{if(e.target===$('image-dialog'))$('image-dialog').close()};new ResizeObserver(draw).observe(canvas);select('B3');
