/* Local OSM snapshot renderer. No external tiles or routing service requests. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const canvas = $('route-map');
  const context = canvas.getContext('2d');
  const presets = {rescue:[2.5,3.2,.25], compact:[1.8,2.2,.2], large:[2.8,3.8,.3]};
  const state = {network:null,result:null,selected:'recommended',view:{scale:1,x:0,y:0},width:0,height:0,request:0,drag:null};
  const edges = new Map();
  let roads = [], waterways = [], labels = [];
  const originLon = 126.94, originLat = 37.478;
  const metersLon = 111320 * Math.cos(originLat * Math.PI / 180);
  const project = ([lon,lat]) => [(lon-originLon)*metersLon, -(lat-originLat)*111320];
  const screen = point => [point[0]*state.view.scale+state.view.x,point[1]*state.view.scale+state.view.y];
  const distance = meters => meters >= 1000 ? `${(meters/1000).toFixed(2)} km` : `${Math.round(meters)} m`;
  const element = (tag, className, content) => {const el=document.createElement(tag);if(className)el.className=className;if(content!==undefined)el.textContent=content;return el;};
  function setStatus(text, noRoute=false) {$('route-status').textContent=text;$('route-status').classList.toggle('no-route',noRoute);}
  function currentDestination() {return state.network?.destinations.find(item => item.id===$('destination').value);}
  function closedIds() {return Array.from($('closures').querySelectorAll('input:checked')).flatMap(input => state.network.closures.find(item => item.id===input.value).edge_ids);}
  function options() {return {destination_id:$('destination').value,vehicle_width_m:Number($('vehicle-width').value),vehicle_height_m:Number($('vehicle-height').value),clearance_m:Number($('clearance').value),mode:$('strict-mode').checked?'strict':'training',closed_edge_ids:closedIds()};}
  function updateContext() {
    const width=Number($('vehicle-width').value), clearance=Number($('clearance').value);
    $('required-width').replaceChildren();
    if(Number.isFinite(width)&&Number.isFinite(clearance)&&$('vehicle-width').value&&$('clearance').value){
      $('required-width').append('필요 유효폭 ',element('strong','',`${(width+2*clearance).toFixed(2)}m`),` = 차량 ${width.toFixed(2)} + 여유 ${clearance.toFixed(2)} × 2`);
    } else {$('required-width').textContent='차량 폭과 좌우 여유를 입력하세요.';}
    $('mode-description').textContent=$('strict-mode').checked?'엄격 모드: 현장 확인 유효폭이 없는 도로를 제외합니다. 공개 스냅샷의 확인값은 0건입니다.':'훈련 모드: 도로 등급별 폭 가정을 사용합니다.';
    const destination=currentDestination();
    if(!destination)return;
    $('report-original').textContent=destination.report;
    $('google-map').href=`https://www.google.com/maps/search/?api=1&query=${destination.lat},${destination.lon}`;
    $('naver-map').href=`https://map.naver.com/p/search/${encodeURIComponent('신원시장')}`;
  }
  function clearResults() {
    state.result=null;
    state.selected='recommended';
    $('route-comparison').replaceChildren();
    $('route-steps').replaceChildren();
    $('route-warnings').replaceChildren();
    $('steps-panel').hidden=true;
    $('route-error').hidden=true;
    canvas.dataset.routeEdges='0';
    draw();
  }
  function calculate() {
    updateContext();
    const request=++state.request;
    clearResults();
    if(!state.network)return;
    setStatus('접근 조건을 적용해 경로를 계산하는 중입니다.');
    $('calculate').disabled=true;
    requestAnimationFrame(() => {
      if(request!==state.request)return;
      try {
        for(const id of ['vehicle-width','vehicle-height','clearance']) {
          if(!$(id).value||!$(id).checkValidity())throw new Error(`${$(id).labels[0].textContent} 값을 허용 범위 안에서 입력하세요.`);
        }
        state.result=window.RescueRouting.plan(state.network,options());
        renderResults();
        if(state.result.recommended)fit(state.result.recommended.geometry.map(project));else draw();
      } catch(error) {
        clearResults();
        $('route-error').textContent=error.message||'경로를 계산할 수 없습니다. 입력을 확인하세요.';
        $('route-error').hidden=false;
        setStatus('입력 조건을 확인하세요. 지도에 이전 경로를 표시하지 않습니다.');
      } finally {if(request===state.request)$('calculate').disabled=false;}
    });
  }
  function addStat(parent,value,unit,label) {
    const item=element('div');const number=element('strong','',value);number.append(element('small','',unit));item.append(number,element('span','',label));parent.append(item);
  }
  function card(kind,route) {
    const recommended=kind==='recommended';
    const article=element('article',`route-card ${kind}-card`);
    article.id=`${kind}-route`;
    const heading=element('div','route-card-heading');heading.append(element('h3','',recommended?'훈련 추천 경로':'최단 비교 경로'),element('span','route-card-tag',recommended?($('strict-mode').checked?'현장 확인 폭 기준':'도로폭 가정 적용'):'물리 폭 필터 제외'));article.append(heading);
    if(route) {
      const stats=element('div','route-stats');
      addStat(stats,(route.distance_m/1000).toFixed(2),'km','도로 이동 거리');
      addStat(stats,route.estimated_minutes.toFixed(1),'분','훈련 예상 시간');
      addStat(stats,String(route.turn_count),'회','개략 방향 전환');article.append(stats);
      article.append(element('p','',recommended?`폭 가정 ${route.assumed_width_count}구간 · 미확인 폭 ${route.unknown_width_count}구간`:'동일 통제·일방통행·표기된 최대폭 및 높이 제한 적용'));
      const button=element('button','',recommended?'추천 경로 선택':'최단 비교 선택');button.type='button';button.dataset.route=kind;button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>selectRoute(kind,true));article.append(button);
    } else {
      article.append(element('p','',recommended?'조건을 충족하는 경로가 없습니다.':'같은 통제와 통행 조건에서 경로가 없습니다.'));
      if(recommended)article.append(element('p','',$('strict-mode').checked?'현장 확인 유효폭 자료가 없어 경로를 제안하지 않습니다.':'차량 제원과 가상 통제 조건을 검토하세요.'));
    }
    return article;
  }
  function renderResults() {
    const result=state.result;
    $('route-comparison').append(card('recommended',result.recommended),card('shortest',result.shortest));
    if(result.recommended) {
      const delta=result.shortest?Math.round(result.recommended.distance_m-result.shortest.distance_m):null;
      setStatus(`훈련 추천 경로 ${distance(result.recommended.distance_m)}${delta!==null?` · 최단 비교보다 ${delta>=0?'+':''}${delta}m`:''}. 출입구와 최종 진입을 현장에서 확인하세요.`);
      selectRoute('recommended');
    } else {
      setStatus($('strict-mode').checked?'현장 확인 유효폭이 없어 추천 경로가 없습니다. 최단 비교는 차량의 물리 폭을 보증하지 않습니다.':'현재 조건에서 추천 경로가 없습니다. 최단 비교를 출동 대안으로 자동 선택하지 않습니다.',true);
      $('map-description').textContent='추천 경로 없음 · 이전 경로 제거됨';
      draw();
    }
  }
  function selectRoute(kind,fitView=false) {
    const route=state.result?.[kind];if(!route)return;
    state.selected=kind;
    for(const button of $('route-comparison').querySelectorAll('button[data-route]')) {
      const selected=button.dataset.route===kind;
      button.setAttribute('aria-pressed',String(selected));button.closest('article').classList.toggle('selected',selected);
      button.textContent=selected?'지도에 선택됨':(button.dataset.route==='recommended'?'추천 경로 선택':'최단 비교 선택');
    }
    $('map-description').textContent=kind==='recommended'?'훈련 추천 경로 선택 · 도로폭 가정에 따른 현장 검토 필요':'최단 비교 선택 · 차량 물리 폭 및 좌우 여유 필터 제외';
    $('steps-title').textContent=(kind==='recommended'?'훈련 추천':'최단 비교')+' · 구간별 안내';
    $('route-steps').replaceChildren();
    for(const step of route.steps) {
      const row=element('li');const text=element('div','step-name',step.name||'이름 없는 도로');
      const details=[step.turn||'계속'];
      if(kind==='recommended'&&Number.isFinite(step.effective_width_m))details.push(`유효폭 ${step.effective_width_m.toFixed(1)}m${step.assumed_width_count?' (훈련 가정)':''}`);
      text.append(element('small','',details.join(' · ')));row.append(text,element('span','step-distance',distance(step.distance_m)));$('route-steps').append(row);
    }
    $('route-warnings').replaceChildren();
    const speed=state.result.assumptions?.speed_kmh??24;
    $('route-warnings').append(element('p','',`시간 가정: ${speed}km/h와 방향 전환 부담. 실시간 도착 예정 시간이 아닙니다.`));
    if(kind==='shortest')$('route-warnings').append(element('p','', '이 비교 경로는 차량 물리 폭과 좌우 여유를 필터링하지 않습니다. 통행 가능 경로로 확정하지 마세요.'));
    for(const warning of route.warnings||[])$('route-warnings').append(element('p','',warning));
    $('steps-panel').hidden=false;
    if(fitView)fit(route.geometry.map(project));else draw();
  }
  function path(points,color,width,dash=[]) {
    if(points.length<2)return;
    context.beginPath();points.forEach((p,i)=>{const [x,y]=screen(p);i?context.lineTo(x,y):context.moveTo(x,y);});context.strokeStyle=color;context.lineWidth=width;context.setLineDash(dash);context.lineJoin='round';context.lineCap='round';context.stroke();context.setLineDash([]);
  }
  function bubble(point,text,color,offset=0) {
    const [x,y]=screen(point);if(x<-130||y<-50||x>state.width+130||y>state.height+50)return;
    context.fillStyle='#fff';context.beginPath();context.arc(x,y,7,0,Math.PI*2);context.fill();context.strokeStyle=color;context.lineWidth=3;context.stroke();
    context.font='600 12px -apple-system, sans-serif';
    const width=context.measureText(text).width+18;
    const left=Math.max(6,Math.min(state.width-width-6,x+12));const top=Math.max(7,Math.min(state.height-27,y-14+offset));
    context.fillStyle='#ffffffef';context.fillRect(left,top,width,25);context.strokeStyle='#cedbe2';context.lineWidth=1;context.strokeRect(left,top,width,25);context.fillStyle=color;context.fillText(text,left+9,top+17);
  }
  function visible(points) {
    return points.some(p=>{const [x,y]=screen(p);return x>-60&&y>-60&&x<state.width+60&&y<state.height+60;});
  }
  function draw() {
    if(!state.width||!context)return;
    const dpr=window.devicePixelRatio||1;context.setTransform(dpr,0,0,dpr,0,0);context.clearRect(0,0,state.width,state.height);context.fillStyle='#eaf0ee';context.fillRect(0,0,state.width,state.height);
    if(!state.network)return;
    for(const item of waterways)path(item.points,'#abd9e5',Math.max(9,22*state.view.scale));
    const widths={trunk:7,primary:7,secondary:6,tertiary:5,residential:3,unclassified:3,living_street:2,service:2};
    for(const road of roads) {
      if(!visible(road.points))continue;
      const type=road.highway.replace(/_link$/,'');const width=(widths[type]||2)*Math.max(.7,Math.min(1.5,state.view.scale*2));
      path(road.points,'#c6d1d3',width+1.4);path(road.points,['primary','trunk','secondary'].includes(type)?'#fff4d7':'#ffffff',width);
    }
    for(const id of closedIds()) {const edge=edges.get(id);if(edge)path(edge.geometry.map(project),'#c94e53',5,[4,4]);}
    const recommended=state.result?.recommended, shortest=state.result?.shortest;
    const showShort=shortest&&(recommended||state.selected==='shortest');
    if(showShort)path(shortest.geometry.map(project),'#bd720e',state.selected==='shortest'?5:3.5,[7,5]);
    if(recommended){path(recommended.geometry.map(project),'#ffffff',state.selected==='recommended'?8:5.5);path(recommended.geometry.map(project),'#087d70',state.selected==='recommended'?5:3);}
    if(showShort&&state.selected==='shortest')path(shortest.geometry.map(project),'#bd720e',5,[7,5]);
    context.font='11px -apple-system, sans-serif';context.textAlign='center';const drawn=[];
    for(const label of labels){const [x,y]=screen(label.point);if(x<65||y<30||x>state.width-60||y>state.height-45||drawn.some(p=>Math.hypot(x-p[0],y-p[1])<75))continue;drawn.push([x,y]);context.lineWidth=4;context.strokeStyle='#ffffffd9';context.strokeText(label.name,x,y);context.fillStyle='#526c7a';context.fillText(label.name,x,y);}
    for(const water of waterways){if(water.name&&water.points.length>2){const [x,y]=screen(water.points[Math.floor(water.points.length/2)]);if(x>25&&x<state.width-30&&y>30&&y<state.height-30){context.fillStyle='#368299';context.font='600 12px sans-serif';context.fillText(water.name,x,y);break;}}}context.textAlign='left';
    const origin=state.network.origin;const station=origin.station_location||origin;
    bubble(project([station.lon,station.lat]),'관악소방서','#225e9e',-20);
    bubble(project([origin.lon,origin.lat]),'도로 출발점','#225e9e',10);
    const dest=currentDestination();if(dest)bubble(project([dest.lon,dest.lat]),dest.name.replace(' 합성 접근 지점',' · 합성 요청'),'#087d70');
    const scaleMeters=100/state.view.scale;
    $('map-scale').textContent=`화면 100px ≈ ${Math.round(scaleMeters)}m`;
    canvas.dataset.routeEdges=String((recommended?.edge_ids.length||0)+(showShort?shortest.edge_ids.length:0));
  }
  function fit(points) {
    if(!points.length||!state.width||!state.height)return;
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    state.view.scale=Math.min((state.width-135)/Math.max(100,maxX-minX),(state.height-100)/Math.max(100,maxY-minY));
    state.view.x=state.width/2-(minX+maxX)/2*state.view.scale;state.view.y=state.height/2-(minY+maxY)/2*state.view.scale;draw();
  }
  function resetMap(){if(state.network){const [minLon,minLat,maxLon,maxLat]=state.network.meta.bbox;fit([[minLon,minLat],[maxLon,maxLat]].map(project));}}
  function zoom(factor,x=state.width/2,y=state.height/2){const old=state.view.scale;const next=Math.max(.08,Math.min(12,old*factor));state.view.x=x-(x-state.view.x)*next/old;state.view.y=y-(y-state.view.y)*next/old;state.view.scale=next;draw();}
  function resize() {
    const rect=$('map-shell').getBoundingClientRect();state.width=rect.width;state.height=rect.height;const dpr=window.devicePixelRatio||1;canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);if(state.network)resetMap();else draw();
  }
  $('route-form').addEventListener('submit',event=>{event.preventDefault();calculate();});
  $('vehicle-preset').addEventListener('change',()=>{const preset=presets[$('vehicle-preset').value];if(preset){['vehicle-width','vehicle-height','clearance'].forEach((id,i)=>{$(id).value=preset[i];});}calculate();});
  for(const id of ['vehicle-width','vehicle-height','clearance'])$(id).addEventListener('input',()=>{$('vehicle-preset').value='custom';calculate();});
  $('destination').addEventListener('change',calculate);$('strict-mode').addEventListener('change',calculate);$('closures').addEventListener('change',calculate);
  $('zoom-in').addEventListener('click',()=>zoom(1.35));$('zoom-out').addEventListener('click',()=>zoom(1/1.35));$('reset-map').addEventListener('click',resetMap);
  $('fit-route').addEventListener('click',()=>{const route=state.result?.[state.selected];if(route)fit(route.geometry.map(project));});
  canvas.addEventListener('pointerdown',event=>{if(event.button!==0)return;state.drag={x:event.clientX,y:event.clientY};canvas.setPointerCapture(event.pointerId);});
  canvas.addEventListener('pointermove',event=>{if(!state.drag)return;state.view.x+=event.clientX-state.drag.x;state.view.y+=event.clientY-state.drag.y;state.drag={x:event.clientX,y:event.clientY};draw();});
  const stopDrag=()=>{state.drag=null;};canvas.addEventListener('pointerup',stopDrag);canvas.addEventListener('pointercancel',stopDrag);canvas.addEventListener('lostpointercapture',stopDrag);
  canvas.addEventListener('wheel',event=>{event.preventDefault();const rect=canvas.getBoundingClientRect();zoom(event.deltaY<0?1.14:1/1.14,event.clientX-rect.left,event.clientY-rect.top);},{passive:false});
  canvas.addEventListener('keydown',event=>{const moves={ArrowLeft:[45,0],ArrowRight:[-45,0],ArrowUp:[0,45],ArrowDown:[0,-45]};if(moves[event.key]){event.preventDefault();state.view.x+=moves[event.key][0];state.view.y+=moves[event.key][1];draw();}else if(['+','=','-','0'].includes(event.key)){event.preventDefault();event.key==='0'?resetMap():zoom(event.key==='-'?1/1.3:1.3);}});
  if(window.ResizeObserver)new ResizeObserver(resize).observe($('map-shell'));else window.addEventListener('resize',resize);
  async function initialize() {
    resize();
    try {
      if(!window.RescueRouting)throw new Error('경로 계산 엔진을 불러오지 못했습니다. 페이지를 다시 열어 주세요.');
      const response=await fetch('network.json');if(!response.ok)throw new Error(`도로망을 불러오지 못했습니다 (${response.status}).`);
      const network=await response.json();if(network.schema_version!==1||!network.destinations?.length)throw new Error('지원하지 않는 도로망 형식입니다.');state.network=network;
      roads=network.roads.map(item=>({...item,points:item.geometry.map(project)}));waterways=network.waterways.map(item=>({...item,points:item.geometry.map(project)}));
      const names=new Set();for(const road of roads.filter(item=>/^(trunk|primary|secondary|tertiary)$/.test(item.highway))){if(road.name&&!names.has(road.name)){names.add(road.name);labels.push({name:road.name,point:road.points[Math.floor(road.points.length/2)]});}}
      for(const edge of network.edges)edges.set(edge.id,edge);
      $('destination').replaceChildren(...network.destinations.map(item=>{const option=element('option','',item.name);option.value=item.id;return option;}));$('destination').disabled=false;
      const legend=element('legend','','가상 침수 통제');$('closures').replaceChildren(legend);
      for(const closure of network.closures){const label=element('label','toggle');const input=element('input');input.type='checkbox';input.id=`closure-${closure.id}`;input.value=closure.id;const text=element('span','',closure.label);label.append(input,text);$('closures').append(label);}
      $('closures').append(element('p','helper','실제 관측 및 통제 정보가 아닌 훈련용 조건입니다.'));
      $('origin-note').textContent=`도로 출발점은 소방서 부지에서 약 ${Math.round(network.origin.snap_distance_m)}m 떨어져 있습니다. 차고 출입 동선과 최종 건물 진입은 미확인입니다.`;
      $('restriction-note').textContent=`단일 via-node 통행제한을 반영합니다. 복합 via-way 제한은 지원하지 않습니다 (스냅샷 ${network.meta.unsupported_restriction_count}건). 지도에 없는 실제 제한은 현장 확인이 필요합니다.`;
      $('network-source').href=network.meta.source_url;
      $('map-loading').hidden=true;resetMap();calculate();
    } catch(error) {
      clearResults();$('map-loading').textContent='도로망을 표시할 수 없습니다.';$('route-error').textContent=error.message;$('route-error').hidden=false;setStatus('자료 로딩에 실패했습니다. 페이지를 다시 열어 주세요.');
    }
  }
  initialize();
})();
