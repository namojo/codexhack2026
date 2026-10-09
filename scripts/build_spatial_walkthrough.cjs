#!/usr/bin/env node
'use strict';
/* Deterministic, local video build. No browser, AI generation, or external calls.
 * CANVAS_MODULE=@napi-rs/canvas node scripts/build_spatial_walkthrough.cjs
 * --preview renders milestone stills only. --test validates geometry/path only.
 */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),{spawn}=require('node:child_process');
const ROOT=path.resolve(__dirname,'..'),ASSETS=path.join(ROOT,'web/spatial/assets'),OUT=path.join(ROOT,'_workspace/spatial-mvp/walkthrough');
const W=960,H=540,FPS=24,DURATION=28,NEAR=.16;
const html=fs.readFileSync(path.join(ROOT,'web/spatial/index.html'),'utf8'),app=fs.readFileSync(path.join(ROOT,'web/spatial/app.js'),'utf8');
const sourceData=JSON.parse(html.match(/<script id="spatial-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
const nodes=new Map();let mesh=[];
function el(id){if(!nodes.has(id))nodes.set(id,{children:[],textContent:'',value:'100',checked:true,clientWidth:850,clientHeight:560,dataset:{},classList:{toggle(){}},append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x},setAttribute(){},querySelector(s){return el(id+s)},click(){this.onclick?.()},showModal(){},close(){},setPointerCapture(){}});return nodes.get(id);}
el('spatial-data').textContent=JSON.stringify(sourceData);
const mockCtx=new Proxy({measureText:t=>({width:t.length*7})},{get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});el('scene').getContext=()=>mockCtx;
const world={document:{getElementById:el,createElement:()=>({dataset:{},setAttribute(){}})},window:{devicePixelRatio:1,spatialGeometrySink:f=>mesh.push(JSON.parse(JSON.stringify(f)))},ResizeObserver:class{observe(){}}};
vm.createContext(world);vm.runInContext(app,world);mesh=[];vm.runInContext("mode='3d';selectedFloor=3;selected='B3';draw()",world);
// Assumed ceiling for the eye-level demonstration; not a surveyed height.
mesh.push({vertices:[[0,0,5.6],[0,64,5.6],[100,64,5.6],[100,0,5.6]],normal:[0,0,-1],color:'#ecebe5'});
const route=[
 {t:0,p:[83,49,3.05],look:[89,60,1.5]},
 {t:2.5,p:[83,49,3.05],look:[83,36,3.05]},
 {t:6,p:[83,34,3.05],look:[71,34,3.05]},
 {t:10,p:[67,34,3.05],look:[67,24,3.05]},
 {t:13,p:[67,27,3.05],look:[65,18,3.05]},
 {t:17,p:[65,19,3.05],look:[64,7,2.9]},
 {t:22,p:[63.5,9,3.05],look:[64,0,2.65]},
 {t:25,p:[63.5,6.8,3.05],look:[64,1,.3]},
 {t:28,p:[63.5,6.8,3.05],look:[64,1,.3]},
];
const chapters=[
 {start:0,end:5,title:'01  계단 도착부',label:'계단 출입부',detail:'문 개방·계단 통과 상태 미확인',basis:'현장 확인 필요',at:[83,46,2.4]},
 {start:5,end:10.5,title:'02  공용 복도',label:'복도 통과 조건',detail:'현재 장애물·유효 통과 폭 확인 필요',basis:'현장 확인 필요',at:[75,34,2]},
 {start:10.5,end:15.5,title:'03  B3 현관 통과',label:'현관 주변의 뿌연 현상',detail:'원문·합성 사진에 근거 · 원인과 농도 미확인',basis:'신고 근거 있음',at:[67,28.6,3]},
 {start:15.5,end:22.5,title:'04  주방을 지나 주공간으로',label:'실내 배치 확인',detail:'가구·구획 변경과 실제 통과 가능성 미확인',basis:'현장 확인 필요',at:[63,15,2]},
 {start:22.5,end:28,title:'05  창가 후보 구역',label:'창가 구역이 위치 후보',detail:'2명은 원문 진술 · 정확한 위치·상태 미확정',basis:'위치 후보',at:[64,3,.3]},
];
const mix=(a,b,t)=>a.map((x,i)=>x+(b[i]-x)*t),sub=(a,b)=>a.map((x,i)=>x-b[i]);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),norm=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function camera(t){let i=0;while(i<route.length-2&&t>route[i+1].t)i++;const a=route[i],b=route[i+1],u=Math.max(0,Math.min(1,(t-a.t)/(b.t-a.t))),s=u*u*(3-2*u);return {p:mix(a.p,b.p,s),look:mix(a.look,b.look,s)};}
function chapter(t){return chapters.find(c=>t>=c.start&&t<c.end)||chapters.at(-1);}
// Validate the camera path against every vertical opaque wall face at eye level.
// This only checks the illustrative mesh; it does not verify real-world passage.
function validate(){
 const walls=mesh.filter(f=>Math.abs(f.normal[2])<.1&&!['#a8cbd0','#718b94','#e3e8e7'].includes(f.color));
 let wallCrossings=[];const positions=[];
 for(let n=0;n<=DURATION*FPS;n++)positions.push(camera(n/FPS).p);
 for(let i=1;i<positions.length;i++)for(const wall of walls){const a=positions[i-1],b=positions[i],v=wall.vertices,da=dot(sub(a,v[0]),wall.normal),db=dot(sub(b,v[0]),wall.normal);if(da*db>=0)continue;
  const zMin=Math.min(...v.map(p=>p[2])),zMax=Math.max(...v.map(p=>p[2])),t=da/(da-db),p=mix(a,b,t);if(p[2]<=zMin||p[2]>=zMax)continue;
  const lo=[0,1].map(k=>Math.min(...v.map(p=>p[k]))-.001),hi=[0,1].map(k=>Math.max(...v.map(p=>p[k]))+.001);
  if(p[0]>=lo[0]&&p[0]<=hi[0]&&p[1]>=lo[1]&&p[1]<=hi[1])wallCrossings.push({frame:i,point:p});
 }
 if(wallCrossings.length)throw Error('Camera crosses a displayed solid wall: '+JSON.stringify(wallCrossings));
 const r=sourceData.analysis.candidates[0].proposed_region_bbox,bounds=[.108,.2121,.9054,.9839];
 const candidate=[(r[0]-bounds[0])/(bounds[2]-bounds[0])*100,(r[1]-bounds[1])/(bounds[3]-bounds[1])*64,(r[2]-bounds[0])/(bounds[2]-bounds[0])*100,(r[3]-bounds[1])/(bounds[3]-bounds[1])*64];
 const end=camera(DURATION).p;if(!(end[0]>candidate[0]&&end[0]<candidate[2]&&end[1]>candidate[1]&&end[1]<candidate[3]))throw Error('Route does not finish inside the candidate region');
 const maxStep=Math.max(...positions.slice(1).map((p,i)=>Math.hypot(...sub(p,positions[i]))));if(maxStep>.4)throw Error('Discontinuous camera path');
 return {sampled_positions:positions.length,eye_level_wall_crossings:wallCrossings.length,max_frame_step_display_units:maxStep,ends_inside_candidate:true,room_continuation_seconds:15};
}
const validation=validate();
if(process.argv.includes('--test')){console.log(JSON.stringify({synthetic:true,validation,chapters:chapters.length,faces:mesh.length,actual_browser:false}));process.exit(0);}
const {createCanvas}=require(process.env.CANVAS_MODULE||'@napi-rs/canvas');
const canvas=createCanvas(W,H),ctx=canvas.getContext('2d');
const focal=W/(2*Math.tan(76*Math.PI/360)),cy=H*.52,light=norm([-.3,-.4,1]);
function render(t){
 const cam=camera(t),forward=norm(sub(cam.look,cam.p)),right=norm([-forward[1],forward[0],0]),up=norm(cross(forward,right));
 const toCam=p=>{const v=sub(p,cam.p);return [dot(v,right),dot(v,up),dot(v,forward)];};
 const project=v=>[W/2+focal*v[0]/v[2],cy-focal*v[1]/v[2],1/v[2]];
 const image=ctx.createImageData(W,H),pixels=image.data,depth=new Float32Array(W*H);depth.fill(-Infinity);
 for(let i=0;i<W*H;i++){pixels[i*4]=227;pixels[i*4+1]=233;pixels[i*4+2]=232;pixels[i*4+3]=255;}
 function clip(vs){const out=[];for(let i=0;i<vs.length;i++){const a=vs[i],b=vs[(i+1)%vs.length],ina=a[2]>=NEAR,inb=b[2]>=NEAR;if(ina)out.push(a);if(ina!==inb)out.push(mix(a,b,(NEAR-a[2])/(b[2]-a[2])));}return out;}
 function triangle(a,b,c,rgb){
  const area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);if(Math.abs(area)<.001)return;
  const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(W-1,Math.ceil(Math.max(a[0],b[0],c[0]))),y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(H-1,Math.ceil(Math.max(a[1],b[1],c[1])));
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){const px=x+.5,py=y+.5,u=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area,v=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area,w=1-u-v;if(Math.min(u,v,w)<-.00001)continue;
   const z=u*a[2]+v*b[2]+w*c[2],i=y*W+x;if(z<depth[i])continue;depth[i]=z;const haze=Math.min(.20,1/z/160),k=i*4;for(let c=0;c<3;c++)pixels[k+c]=rgb[c]*(1-haze)+[216,225,225][c]*haze;
  }
 }
 for(const f of mesh){if(dot(f.normal,sub(cam.p,f.vertices[0]))<-.001)continue;const vs=clip(f.vertices.map(toCam)).map(project);if(vs.length<3)continue;const n=parseInt(f.color.slice(1),16),brightness=.78+.22*Math.max(0,dot(f.normal,light)),rgb=[n>>16,(n>>8)&255,n&255].map(v=>v*brightness);for(let i=1;i<vs.length-1;i++)triangle(vs[0],vs[i],vs[i+1],rgb);}
 ctx.putImageData(image,0,0);
 // Marker is a report annotation, not simulated fire/smoke or a confirmed obstacle.
 const ch=chapter(t),v=toCam(ch.at);if(v[2]>.5){const p=project(v),x=Math.max(30,Math.min(W-255,p[0])),y=Math.max(112,Math.min(H-175,p[1]));
  ctx.strokeStyle='#c98a28';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(x+15,y);ctx.stroke();ctx.fillStyle='#fff6e4';ctx.fillRect(x,y-16,205,32);ctx.fillStyle='#865d1d';ctx.font='bold 17px sans-serif';ctx.fillText(ch.label,x+10,y+7);
 }
 overlay(t,cam,ch);
 return canvas;
}
function overlay(t,cam,ch){
 ctx.fillStyle='#183449f2';ctx.fillRect(0,0,W,82);ctx.fillStyle='#e6b863';ctx.font='bold 13px sans-serif';ctx.fillText('SYNTHETIC  /  도면 기반 설명용 이동',24,25);
 ctx.fillStyle='#ffffff';ctx.font='bold 22px sans-serif';ctx.fillText('3층 · 계단에서 B3 창가 후보까지',24,57);
 ctx.textAlign='right';ctx.font='13px sans-serif';ctx.fillStyle='#cddce6';ctx.fillText('안전 경로·현장 재현 아님',W-24,27);ctx.fillText('문 개방·높이·재질은 영상용 가정',W-24,54);ctx.textAlign='left';
 // Compact plan remains visible after crossing the doorway.
 const mx=W-202,my=97,mw=180,mh=122,s=1.55,ox=mx+12,oy=my+9;
 ctx.fillStyle='#ffffffea';ctx.fillRect(mx,my,mw,mh);ctx.strokeStyle='#aebec6';ctx.strokeRect(mx,my,mw,mh);ctx.fillStyle='#eef0e9';ctx.fillRect(ox,oy,100*s,64*s);
 for(const u of sourceData.floor_model.floor.units){const b=u.bbox,x=(b[0]-.108)/(.9054-.108)*100,y=(b[1]-.2121)/(.9839-.2121)*64,w=(b[2]-b[0])/(.9054-.108)*100,h=(b[3]-b[1])/(.9839-.2121)*64;ctx.strokeStyle='#a8b7b9';ctx.lineWidth=.8;ctx.strokeRect(ox+x*s,oy+y*s,w*s,h*s);}
 ctx.fillStyle='#e9b65f';ctx.fillRect(ox+54.4*s,oy+1*s,21.3*s,7.6*s);
 ctx.strokeStyle='#a8bac6';ctx.lineWidth=2;ctx.setLineDash([3,3]);ctx.beginPath();route.forEach((r,i)=>i?ctx.lineTo(ox+r.p[0]*s,oy+r.p[1]*s):ctx.moveTo(ox+r.p[0]*s,oy+r.p[1]*s));ctx.stroke();ctx.setLineDash([]);
 ctx.fillStyle='#226386';ctx.beginPath();ctx.arc(ox+cam.p[0]*s,oy+cam.p[1]*s,4,0,Math.PI*2);ctx.fill();ctx.fillStyle='#426273';ctx.font='11px sans-serif';ctx.fillText('현재 위치 → 창가 후보',mx+12,my+115);
 ctx.fillStyle='#162f42ed';ctx.fillRect(0,H-112,W,112);ctx.fillStyle='#f7fbfe';ctx.font='bold 18px sans-serif';ctx.fillText(ch.title,24,H-83);
 ctx.fillStyle='#f0c277';ctx.font='bold 15px sans-serif';ctx.fillText(ch.basis,24,H-55);ctx.fillStyle='#f3f7fa';ctx.font='16px sans-serif';ctx.fillText(ch.detail,170,H-55);
 ctx.fillStyle='#b9ccd9';ctx.font='12px sans-serif';ctx.fillText('보고된 현상과 미확인 조건을 구분합니다. 실제 진입 판단은 현장 확인이 필요합니다.',24,H-25);
 ctx.fillStyle='#d8a14b';ctx.fillRect(0,H-4,W*Math.min(1,t/DURATION),4);
}
async function main(){
 fs.mkdirSync(OUT,{recursive:true});
 for(const t of [0,6,11.5,15,20,26]){render(t);fs.writeFileSync(path.join(OUT,`frame-${String(t).replace('.','_')}.png`),canvas.toBuffer('image/png'));}
 if(process.argv.includes('--preview')){console.log(JSON.stringify({preview:OUT,validation}));return;}
 render(11.5);fs.writeFileSync(path.join(ASSETS,'walkthrough-poster.png'),canvas.toBuffer('image/png'));
 const movie=path.join(ASSETS,'walkthrough.mp4'),tmp=path.join(OUT,'walkthrough.tmp.mp4');
 const encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','image2pipe','-vcodec','png','-r',String(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','medium','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',tmp],{stdio:['pipe','ignore','pipe']});
 let errors='';encoder.stderr.on('data',b=>errors+=b);const completion=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error(errors)));});
 for(let f=0;f<DURATION*FPS;f++){
  render(f/FPS);const png=canvas.toBuffer('image/png');if(!encoder.stdin.write(png))await require('node:events').once(encoder.stdin,'drain');
  if(f%120===0)console.log(`Rendered ${f}/${DURATION*FPS} frames`);
 }
 encoder.stdin.end();await completion;fs.renameSync(tmp,movie);
 const timestamp=t=>{const s=Math.floor(t),ms=Math.round((t-s)*1000);return `00:${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;};
 const vtt='WEBVTT\n\n'+chapters.map(c=>`${timestamp(c.start)} --> ${timestamp(c.end)}\n${c.title} · ${c.basis}\n${c.detail}\n`).join('\n');fs.writeFileSync(path.join(ASSETS,'walkthrough.ko.vtt'),vtt);
 const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const manifest={synthetic:true,generated_locally:true,live_model_calls:0,actual_browser:false,width:W,height:H,fps:FPS,duration_seconds:DURATION,audio:false,route,chapters,validation,geometry_source:'web/spatial/app.js',geometry_source_sha256:crypto.createHash('sha256').update(app).digest('hex'),generator_sha256:sha(__filename),assumptions:['계단 3층 도착부에서 시작','실제 문 상태와 통과 가능성 미확인; 영상에서는 열린 상태 가정','높이·재질·천장 및 카메라 눈높이는 표시용 가정','신고된 뿌연 현상은 주석으로 표시하며 실제 연기를 재현하지 않음','후보 구역 도착은 구조 완료가 아님'],files_sha256:{}};
 for(const f of ['walkthrough.mp4','walkthrough-poster.png','walkthrough.ko.vtt'])manifest.files_sha256[f]=sha(path.join(ASSETS,f));
 fs.writeFileSync(path.join(ASSETS,'walkthrough.json'),JSON.stringify(manifest,null,2));console.log(JSON.stringify({video:movie,bytes:fs.statSync(movie).size,validation}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
