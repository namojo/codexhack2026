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
const units=raw.floor.units.map(u=>({id:u.type+u.id,name:u.type+'타입 '+u.id+'호',box:box(u.bbox),desc:descriptions[u.type+u.id]}));
units.sort((a,b)=>['A1','B2','B3','B4','E7','D6','C5'].indexOf(a.id)-['A1','B2','B3','B4','E7','D6','C5'].indexOf(b.id));
for(const id of ['corridor','stairs','elevator']){const u=raw.floor.common_areas.find(a=>a.id===id);units.push({id,name:u.label,box:box(u.bbox),color:'#b9d5eb',desc:u.source_evidence+'. '+u.uncertainty})}
const internal=Object.fromEntries(raw.selected_unit.spaces.map(u=>[u.id,{...u,box:box(u.bbox)}]));
const entryPoint=point(raw.selected_unit.openings.find(o=>o.id==='entry_door').point);
const region=box(analysis.candidates[0].proposed_region_bbox);
let selected='B3',selectedFloor=3,ambiguous=false,mode='building',yaw=-.22,pitch=.84,zoom=1;let hit=[];
const canvas=$('scene'),ctx=canvas.getContext('2d');
for(const unit of units){const b=document.createElement('button');b.textContent=unit.name;b.dataset.space=unit.id;b.setAttribute('aria-pressed',String(unit.id===selected));b.onclick=()=>select(unit.id);$('spaces').append(b)}
function select(id){selected=id;for(const b of $('spaces').children)b.setAttribute('aria-pressed',String(b.dataset.space===id));const u=units.find(u=>u.id===id);$('selected').replaceChildren();const strong=document.createElement('strong');strong.textContent=selectedFloor+'층 · '+u.name;const p=document.createElement('p');p.textContent=selectedFloor===3?u.desc:('3~16층 동일 평면 가정으로 표시한 공간입니다. 이 층에는 가상 신고가 없습니다. '+u.desc.replace('원문이 지정한 가상 라인.','같은 배치의 라인.').replace('위치 후보입니다.','주공간입니다.'));$('selected').append(strong,p);draw()}
function rect(x,y,w,h,z=0){return [[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]]}
function targetIDs(){return ambiguous?['B2','B3','B4']:['B3']}
// Display geometry traced against the preserved 1120 × 745 source image.
// These are approximate plan coordinates, never measured metres or model output.
const planPoint=([x,y])=>point([x/1120,y/745]);
const architecture={
  wallHeight:5.2,wallThickness:.65,slabThickness:1.1,
  // Visible exterior opening symbols. Heights/materials are illustrative.
  northWindows:[[171,218],[273,319],[372,388],[471,519],[575,593],[677,724],[778,799],[877,926],[980,1003]],
  southWindows:[[169,218],[271,317],[379,418],[473,515],[580,619],[672,717]],
  westWindows:[[211,258],[355,397],[539,577],[642,682]],
  doors:[[284,327,413],[452,492,413],[697,742,413],[869,912,413],[255,297,491],[430,472,491],[636,678,491]],
  // B3 bathroom: approximate angled/curved partition, not the source bbox.
  bathWall:[[743,285],[796,278],[800,329],[797,346],[791,359],[779,368],[759,373],[739,368]],
};
function draw(){
 const width=canvas.clientWidth,height=canvas.clientHeight,dpr=Math.min(window.devicePixelRatio||1,2);
 canvas.width=width*dpr;canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);hit=[];
 const tower=mode==='building',split=tower&&width>=620,ca=Math.cos(yaw),sa=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),top=mode==='top';
 const labels=[],stats={faces:0,windows:0,volumes:0};
 ctx.fillStyle='#edf1f2';ctx.fillRect(0,0,width,height);
 // A self-contained orthographic mesh renderer: lit solid faces and depth ordering.
 // No external libraries, network calls, or additional model calls.
 function view(origin,scale,center){
  const faces=[],shadows=[];
  const camera=top?[0,0,1]:[sa*sp,ca*sp,cp],light=[-.38,-.48,.79];
  function project(v){const x=v[0]-center[0],y=v[1]-center[1],z=(v[2]||0)-center[2];return [origin[0]+(x*ca-y*sa)*scale,origin[1]+(top?(x*sa+y*ca):(x*sa+y*ca)*cp-z*sp)*scale]}
  const depth=v=>v[0]*camera[0]+v[1]*camera[1]+v[2]*camera[2];
  function path(vs){ctx.beginPath();vs.forEach((v,i)=>{const p=project(v);i?ctx.lineTo(...p):ctx.moveTo(...p)});ctx.closePath()}
  function line(vs,color='#8297a3',dash=[],weight=1){ctx.save();ctx.beginPath();vs.forEach((v,i)=>{const p=project(v);i?ctx.lineTo(...p):ctx.moveTo(...p)});ctx.strokeStyle=color;ctx.lineWidth=weight;ctx.setLineDash(dash);ctx.stroke();ctx.restore()}
  function flat(vs,color,stroke=null){path(vs);ctx.fillStyle=color;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=.65;ctx.stroke()}}
  function tint(hex,factor){const n=parseInt(hex.slice(1),16);return 'rgb('+[n>>16,(n>>8)&255,n&255].map(v=>Math.round(Math.min(255,v*factor))).join(',')+')'}
  function face(vs,color,normal=[0,0,1],edge=false){
   // Offline video builder reuses this geometry before view-dependent culling.
   if(typeof window.spatialGeometrySink==='function')window.spatialGeometrySink({vertices:vs,color,normal});
   if(!top&&normal.reduce((n,v,i)=>n+v*camera[i],0)<-.001)return;
   if(top&&normal[2]<.9)return;
   const luminance=top?1:.73+.27*Math.max(0,normal.reduce((n,v,i)=>n+v*light[i],0));
   faces.push({vs,color:tint(color,luminance),d:vs.reduce((n,v)=>n+depth(v),0)/vs.length,edge});stats.faces++;
  }
  function solid(poly,z,h,color,shadow=false){
   if(h<=0)return;stats.volumes++;
   face(poly.map(p=>[...p,z+h]),color,[0,0,1],true);
   for(let i=0;i<poly.length;i++){const a=poly[i],b=poly[(i+1)%poly.length],dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);if(!len)continue;
    face([[...a,z],[...b,z],[...b,z+h],[...a,z+h]],color,[dy/len,-dx/len,0]);}
   if(shadow)shadows.push(poly.map(p=>[p[0]+h*.55,p[1]+h*.35,.13]));
  }
  function block(x,y,w,h,z,rise,color,shadow=false){solid([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],z,rise,color,shadow)}
  function wall(a,b,z,h,color='#f6f3eb',thickness=architecture.wallThickness){
   const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);if(len<.03)return;
   const nx=-dy/len*thickness/2,ny=dx/len*thickness/2;
   solid([[a[0]-nx,a[1]-ny],[b[0]-nx,b[1]-ny],[b[0]+nx,b[1]+ny],[a[0]+nx,a[1]+ny]],z,h,color,true);
  }
  function openingWall(a,b,openings,kind='window'){
   const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),at=t=>[a[0]+dx*t/len,a[1]+dy*t/len];
   let last=0;const H=architecture.wallHeight;
   for(const [lo,hi] of openings){const start=Math.max(last,lo),end=Math.min(len,hi);if(end<=start)continue;
    wall(at(last),at(start),.14,H);
    if(kind==='window'){
     if(!top){wall(at(start),at(end),.14,1.35);wall(at(start),at(end),4.2,H-4.06);}
     wall(at(start),at(end),top?.14:1.49,top?.25:2.7,'#a8cbd0',top?.65:.15);stats.windows++;
     for(const t of [start,(start+end)/2,end]){const p=at(t);block(p[0]-.12,p[1]-.12,.24,.24,top?.14:1.48,top?.3:2.76,'#718b94');}
     wall(at(start),at(end),top?.15:1.4,.16,'#e3e8e7',.95);
    }else{
     // Cutaway omits lintels so the doorway remains legible from above.
     const hinge=at(start),leaf=[hinge[0]-dy/len*(end-start)*.75,hinge[1]+dx/len*(end-start)*.75];
     wall(hinge,leaf,.15,top?.18:3.3,'#c8b79a',.2);
    }
    last=end;
   }
   wall(at(last),b,.14,H);
  }
  function render(){
   // Per-pixel depth prevents large floor polygons from hiding walls/fittings.
   // Canvas-only rasterization keeps file:// and the existing strict CSP working.
   for(const shadow of shadows)face(shadow.map(p=>[Math.max(0,Math.min(100,p[0])),Math.max(0,Math.min(64,p[1])),.125]),'#d6d8d0');
   ctx.save();ctx.setTransform(1,0,0,1,0,0);
   const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);ctx.restore();
   if(!pixels?.data){ // DOM-only test contexts do not supply a bitmap.
    faces.sort((a,b)=>a.d-b.d);for(const f of faces)flat(f.vs,f.color);return;
   }
   const W=canvas.width,H=canvas.height,buffer=new Float32Array(W*H);buffer.fill(-Infinity);
   const rgba=pixels.data;
   function triangle(a,b,c,rgb){
    const area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);if(Math.abs(area)<.001)return;
    const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(W-1,Math.ceil(Math.max(a[0],b[0],c[0])));
    const y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(H-1,Math.ceil(Math.max(a[1],b[1],c[1])));
    for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
     const px=x+.5,py=y+.5,u=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area,v=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area,w=1-u-v;
     if(u<-.00001||v<-.00001||w<-.00001)continue;
     const z=u*a[2]+v*b[2]+w*c[2],i=y*W+x;if(z<buffer[i]-.00001)continue;
     buffer[i]=z;const k=i*4;rgba[k]=rgb[0];rgba[k+1]=rgb[1];rgba[k+2]=rgb[2];rgba[k+3]=255;
    }
   }
   const projected=faces.map(f=>({...f,vertices:f.vs.map(v=>{const p=project(v);return [p[0]*dpr,p[1]*dpr,depth(v)]})}));
   for(const f of projected){const rgb=f.color.match(/\d+/g).map(Number),vs=f.vertices;for(let i=1;i<vs.length-1;i++)triangle(vs[0],vs[i],vs[i+1],rgb);}
   // Fine visible edge lines, depth tested as well (no hidden wireframe).
   for(const f of projected){if(!f.edge)continue;const vs=f.vertices;
    for(let i=0;i<vs.length;i++){const a=vs[i],b=vs[(i+1)%vs.length],steps=Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1]));
     for(let n=0;n<=steps;n++){const t=steps?n/steps:0,x=Math.round(a[0]+(b[0]-a[0])*t),y=Math.round(a[1]+(b[1]-a[1])*t);if(x<0||x>=W||y<0||y>=H)continue;
      const index=y*W+x,z=a[2]+(b[2]-a[2])*t;if(!Number.isFinite(buffer[index])||z<buffer[index]-.2)continue;
      const k=index*4;for(let c=0;c<3;c++)rgba[k+c]=Math.round(rgba[k+c]*.88+75*.12);
     }
    }
   }
   ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.putImageData(pixels,0,0);ctx.restore();
  }
  function ground(){ctx.save();ctx.shadowColor='rgba(36,58,68,.20)';ctx.shadowBlur=22;ctx.shadowOffsetY=12;flat(rect(-1,-1,102,66,-1.6),'#dce3e4');ctx.restore();}
  function label(text,v,color='#405a69',anchor=null){const q=project(v),p=anchor||q;ctx.font='600 12px system-ui';const tw=ctx.measureText(text).width,b={x:p[0]-tw/2-7,y:p[1]-12,w:tw+14,h:25};
   if(b.x<4||b.x+b.w>width-4||b.y<58||b.y+b.h>height-4||labels.some(a=>b.x<a.x+a.w+4&&b.x+b.w+4>a.x&&b.y<a.y+a.h+4&&b.y+b.h+4>a.y))return false;
   labels.push(b);ctx.save();if(anchor){ctx.beginPath();ctx.moveTo(...q);ctx.lineTo(...p);ctx.strokeStyle=color;ctx.lineWidth=1;ctx.stroke();}
   ctx.fillStyle='#ffffffed';ctx.fillRect(b.x,b.y,b.w,b.h);ctx.strokeStyle='#d2dddf';ctx.lineWidth=.7;ctx.strokeRect(b.x,b.y,b.w,b.h);ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(text,p[0],p[1]+5);ctx.restore();return true;
  }
  return {project,line,flat,face,block,solid,wall,openingWall,render,ground,label,faces};
 }
 function drawFloor(v,interactive=true){
  const {block,wall,openingWall,face,line}=v,H=architecture.wallHeight;
  v.ground();block(0,0,100,64,-architecture.slabThickness,architecture.slabThickness,'#cbd1cf');
  face(rect(0,0,100,64,.04),'#f0eee6');
  for(const u of units){face(rect(...u.box,.08),['corridor','stairs','elevator'].includes(u.id)?'#cfdee1':u.id===selected?'#e1eaf0':'#ede9dd');if(interactive)hit.push({id:u.id,points:rect(...u.box,.1).map(v.project)});}
  // Partition lines follow plan symbols; shared walls are generated once.
  if($('walls').checked){
   openingWall([0,0],[100,0],architecture.northWindows.map(([a,b])=>[planPoint([a,158])[0],planPoint([b,158])[0]]));
   openingWall([0,64],[100,64],architecture.southWindows.map(([a,b])=>[planPoint([a,733])[0],planPoint([b,733])[0]]));
   openingWall([0,0],[0,64],architecture.westWindows.map(([a,b])=>[planPoint([120,a])[1],planPoint([120,b])[1]]));
   wall([100,0],[100,64],.14,H);
   for(const x of [393,601,806])wall(planPoint([x,160]),planPoint([x,411]),.14,H);
   for(const x of [377,577,773])wall(planPoint([x,493]),planPoint([x,733]),.14,H);
   for(const y of [413,491]){const start=planPoint([120,y]),end=planPoint([y===491?773:913,y]);openingWall(start,end,architecture.doors.filter(d=>d[2]===y).map(d=>[planPoint([d[0],y])[0],planPoint([d[1],y])[0]]),'door');}
   const ps=architecture.bathWall.map(planPoint);for(let i=1;i<ps.length;i++)wall(ps[i-1],ps[i],.14,4.1,'#f3f0e7',.5);
   // The door location is uncertain: keep a visible opening, no invented hinge.
   wall(planPoint([743,285]),planPoint([733,321]),.14,4.1,'#f3f0e7',.5);
  }
  // Minimal fittings from plan symbols, no photograph-derived invented furniture.
  const kitchen=internal.kitchen.box,storeBox=internal.storage.box,bath=internal.bathroom.box;
  block(...kitchen,.13,1.65,'#bdc4bd',true);block(kitchen[0]-.08,kitchen[1]-.08,kitchen[2]+.16,kitchen[3]+.16,1.78,.25,'#f9f6ec');
  block(kitchen[0]+.7,kitchen[1]+.65,kitchen[2]-1.4,kitchen[3]*.35,2.04,.07,'#8eaaae');
  block(...storeBox,.13,2.35,'#d0c5b1',true);
  face(rect(...bath,.11),'#e0e6e2');
  const shaft=box(raw.floor.common_areas.find(s=>s.id==='service_shaft').bbox);block(...shaft,.13,1.5,'#afb9b9',true);
  const elevator=units.find(u=>u.id==='elevator').box;block(...elevator,.14,3.1,'#bdc9cc',true);block(elevator[0]+.4,elevator[1]-.16,elevator[2]-.8,.23,.2,2.6,'#91a5ad');
  const stairs=units.find(u=>u.id==='stairs').box,[sx,sy,sw,sh]=stairs;
  for(let i=0;i<9;i++){block(sx+1,sy+1+i*(sh-2)/9,(sw-3)/2,(sh-2)/9,.14,.25+i*.33,'#dce1df');block(sx+(sw+1)/2,sy+1+i*(sh-2)/9,(sw-3)/2,(sh-2)/9,.14,3.1-i*.33,'#dce1df');}
  if(selectedFloor===3)for(const id of targetIDs()){const u=units.find(u=>u.id===id),[x,y,w]=u.box,r=id==='B3'?region:[x+1.5,y+1.1,w-3,region[3]];face(rect(...r,.18),'#edbd69');}
  v.render();
  if($('connection').checked){const corridor=units.find(u=>u.id==='corridor').box;line([[sx+sw/2,sy+sh/2,3.6],[82,42,3.6],[82,corridor[1]+corridor[3]/2,.3],[entryPoint[0],corridor[1]+corridor[3]/2,.3],[...entryPoint,.3],[region[0]+region[2]/2,region[1]+region[3]/2,.3]],'#637f94',[4,5],1.4);}
  const u=units.find(u=>u.id===selected);const ring=rect(...u.box,.25);line([...ring,ring[0]],'#326889',[],2);
  // Candidate first, so optional room tags cannot suppress this essential label.
  if(selectedFloor===3){const target=[region[0]+region[2]/2,region[1]+region[3]/2,1],anchor=v.project([target[0],region[1],H+3]);anchor[0]=Math.max(70,Math.min(width-70,anchor[0]));anchor[1]=Math.max(73,anchor[1]-12);v.label(ambiguous?'창가 · 복수 후보':'창가 후보',target,'#8b5b18',anchor);}
  for(const u of units){const [x,y,w,h]=u.box;v.label(u.id==='corridor'?'복도':u.id==='stairs'?'계단':u.id==='elevator'?'승강기':u.id,[x+w/2,y+h*.62,1]);}
 }
 if(tower){
  const scale=Math.min(width/(split?265:155),(height-90)/177)*zoom;
  const v=view([width*(split?.27:.47),height*.55],scale,[50,32,56]);v.ground();
  v.block(0,0,100,64,0,13.2,'#b9c3c6');v.block(-.6,-.6,101.2,65.2,13.2,.8,'#d7dedc');
  for(let f=3;f<=16;f++){
   const z=(f-1)*7,isSelected=f===selectedFloor;
   // Opaque massing, with a slab joint per repeated floor, rather than 14 x-ray plans.
   v.block(.6,.6,98.8,62.8,z,6.25,isSelected?(f===3?'#eed5a3':'#b5ccd9'):'#e8e6dd');
   v.block(-.4,-.4,100.8,64.8,z+6.25,.75,isSelected?'#819aa5':'#cad1cf');
   for(const [a,b] of architecture.northWindows){const [x]=planPoint([a,158]),[x2]=planPoint([b,158]);v.face([[x,.57,z+1.5],[x2,.57,z+1.5],[x2,.57,z+4.9],[x,.57,z+4.9]],'#97b8c0',[0,-1,0]);stats.windows++;}
   for(const [a,b] of architecture.southWindows){const [x]=planPoint([a,733]),[x2]=planPoint([b,733]);v.face([[x,63.43,z+1.5],[x2,63.43,z+1.5],[x2,63.43,z+4.9],[x,63.43,z+4.9]],'#a7c5c9',[0,1,0]);stats.windows++;}
   for(const [a,b] of architecture.westWindows){const y=planPoint([120,a])[1],y2=planPoint([120,b])[1];v.face([[.57,y,z+1.5],[.57,y2,z+1.5],[.57,y2,z+4.9],[.57,y,z+4.9]],'#97b8c0',[-1,0,0]);stats.windows++;}
  }
  const z=(selectedFloor-1)*7,band=selectedFloor===3?'#d39c43':'#648da8';
  // Highlight only visible facade edges; never draw a hidden floor through the tower.
  for(const h of [z+.18,z+6.1]){
   v.face([[.5,.5,h],[99.5,.5,h],[99.5,.5,h+.3],[.5,.5,h+.3]],band,[0,-1,0]);
   v.face([[.5,63.5,h],[99.5,63.5,h],[99.5,63.5,h+.3],[.5,63.5,h+.3]],band,[0,1,0]);
   v.face([[.5,.5,h],[.5,63.5,h],[.5,63.5,h+.3],[.5,.5,h+.3]],band,[-1,0,0]);
   v.face([[99.5,.5,h],[99.5,63.5,h],[99.5,63.5,h+.3],[99.5,.5,h+.3]],band,[1,0,0]);
  }
  v.render();
  const q=v.project([100,64,z+3]);v.label(selectedFloor+'F · '+(selectedFloor===3?'신고':'선택'),[100,64,z+3],selectedFloor===3?'#8b5b18':'#326889',[Math.min(width-53,q[0]+34),q[1]]);
  const roof=v.project([0,0,112]);v.label('16F',[0,0,112],'#405a69',[roof[0],roof[1]-17]);
  const base=v.project([0,64,4]);v.label('1~2F 미확인',[0,64,4],'#637985',[Math.max(64,base[0]-16),base[1]+25]);
  if(split){const floorView=view([width*.75,height*.65],Math.min(width/265,(height-110)/130)*zoom,[50,32,0]);drawFloor(floorView);floorView.label(selectedFloor+'층 · 절개 모형',[50,-10,7],'#405a69');}
 }else{
  const scale=Math.min((width-40)/132,(height-110)/(top?100:92))*zoom;
  drawFloor(view([width/2,height*.57],scale,[50,32,0]));
 }
 $('scene-caption').textContent=tower?(split?'전체 건물 + 선택 층 절개':'전체 건물 · 선택 층 강조'):selectedFloor+'층 '+(top?'평면':'절개 모형')+' · 도면 위쪽 ≠ 진북';
 $('scene-status').textContent=selectedFloor===3?(ambiguous?'가상 신고: 3층 · B타입 2~4호 · 복수 후보':'가상 신고: 3층 · B타입 3호 라인 · 창가 구역'):selectedFloor+'층 배치 확인 · 이 층에는 가상 신고 없음';
 $('scene-detail').textContent=selectedFloor===3?'2명은 원문 진술입니다. 색칠한 구역은 후보이며 정확한 사람 위치는 미확정입니다.':'신고는 3층에 유지됩니다. “신고 위치 보기”를 누르면 3층 후보를 다시 표시합니다.';
 window.spatialState={mode,selected,selectedFloor,ambiguous,yaw,pitch,zoom,focus:false,candidates:targetIDs(),visibleCandidates:selectedFloor===3?targetIDs():[],modeledFloors:Array.from({length:14},(_,i)=>i+3),unknownFloors:[1,2],labelBoxes:labels,renderer:'lit-solid-cutaway',splitView:split,geometryStats:stats};
}
function setMode(m){mode=m;for(const [id,name] of [['building','building'],['three','3d'],['top','top']])$(id).setAttribute('aria-pressed',String(m===name));draw()}
$('building').onclick=()=>setMode('building');$('three').onclick=()=>setMode('3d');$('top').onclick=()=>setMode('top');
$('floor-select').onchange=e=>{selectedFloor=+e.target.value;select(selected)};
$('focus').onclick=()=>{selectedFloor=3;$('floor-select').value='3';selected='B3';zoom=1;$('zoom').value=100;setMode('3d');select('B3')};
$('reset').onclick=()=>{yaw=-.22;pitch=.84;zoom=1;selectedFloor=3;$('zoom').value=100;$('floor-select').value='3';$('walls').checked=true;$('connection').checked=true;setMode('building');setAmbiguous(false);select('B3')};
$('zoom').oninput=e=>{zoom=+e.target.value/100;draw()};$('walls').onchange=draw;$('connection').onchange=draw;
function setAmbiguous(value){ambiguous=value;$('normal').setAttribute('aria-pressed',String(!value));$('ambiguous').setAttribute('aria-pressed',String(value));$('result').classList.toggle('empty',value);$('result').querySelector('strong').textContent=value?'B타입 2~4호 · 복수 후보':'B타입 3호 라인 · 창가 주공간';$('result').querySelector('p').textContent=value?'라인 정보가 없으면 사진만으로 같은 타입의 세대를 구분할 수 없습니다.':'정확한 점이 아닌 후보 구역입니다.';$('comparison').textContent=value?'규칙 기반 비교 목업: 3호 라인이 없으면 3층 B타입 2·3·4호를 모두 유지합니다. 다른 층의 요청을 새로 만들지 않습니다.':'원문의 라인 지정이 후보를 좁히는 주요 근거입니다.';draw()}
$('normal').onclick=()=>setAmbiguous(false);$('ambiguous').onclick=()=>setAmbiguous(true);
let drag=null;canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY};canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;yaw+=dx*.007;if(mode!=='top')pitch=Math.min(1.35,Math.max(.2,pitch+dy*.006));drag.x=e.clientX;drag.y=e.clientY;draw()};
canvas.onpointerup=e=>{if(drag&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<6){const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;for(const h of [...hit].reverse()){let inside=false;for(let i=0,j=h.points.length-1;i<h.points.length;j=i++){const a=h.points[i],b=h.points[j];if(((a[1]>y)!==(b[1]>y))&&(x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]))inside=!inside}if(inside){select(h.id);break}}}drag=null};canvas.onpointercancel=()=>drag=null;
canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-','=','Escape'].includes(e.key)){e.preventDefault();if(e.key==='ArrowLeft')yaw-=.12;if(e.key==='ArrowRight')yaw+=.12;if(e.key==='ArrowUp')pitch=Math.min(1.35,pitch+.08);if(e.key==='ArrowDown')pitch=Math.max(.2,pitch-.08);if(e.key==='+'||e.key==='=')zoom=Math.min(1.8,zoom+.1);if(e.key==='-')zoom=Math.max(.65,zoom-.1);if(e.key==='Escape')$('reset').click();$('zoom').value=Math.round(zoom*100);draw()}};
function imageDialog(src,title){$('dialog-image').src=src;$('dialog-image').alt=title;$('dialog-title').textContent=title;$('image-dialog').showModal()}
$('report-image').onclick=()=>imageDialog('assets/synthetic-report.png','합성 신고 이미지 · 실제 사고 사진 아님');$('close-dialog').onclick=()=>$('image-dialog').close();$('image-dialog').onclick=e=>{if(e.target===$('image-dialog'))$('image-dialog').close()};new ResizeObserver(draw).observe(canvas);select('B3');

// The prerecorded walkthrough is always synthetic floor 3, independent of the viewer.
const walkVideo=$('walkthrough-video');
const walkChapters=[
 ['walk-stairs',0,'계단 도착부 · 문 개방·통과 상태 확인 필요'],
 ['walk-corridor',5,'공용 복도 · 장애물·현재 유효 폭 확인 필요'],
 ['walk-entry',10.5,'현관 통과 · 신고된 뿌연 현상, 원인·농도 미확인'],
 ['walk-room',15.5,'실내 이동 · 주방을 지나 창가까지 시점 유지'],
 ['walk-window',22.5,'창가 후보 구역 · 2명은 원문 진술, 정확 위치 미확정']
];
let walkActive=0;
function updateWalkChapter(){const t=walkVideo.currentTime||0;let index=0;for(let i=0;i<walkChapters.length;i++)if(t>=walkChapters[i][1])index=i;if(index===walkActive)return;walkActive=index;for(let i=0;i<walkChapters.length;i++)$(walkChapters[i][0]).setAttribute('aria-pressed',String(i===index));$('walkthrough-status').textContent=walkChapters[index][2];}
for(const [id,t] of walkChapters)$(id).onclick=()=>{walkVideo.currentTime=t;updateWalkChapter();const playing=walkVideo.play();if(playing&&typeof playing.catch==='function')playing.catch(()=>{$('walkthrough-status').textContent='영상 재생 버튼을 눌러 선택한 구간을 확인하세요.';});};
walkVideo.ontimeupdate=updateWalkChapter;
walkVideo.onseeked=updateWalkChapter;
walkVideo.onerror=()=>{$('walkthrough-status').textContent='영상을 불러오지 못했습니다. MP4 저장 링크에서 파일을 확인하세요.';};
