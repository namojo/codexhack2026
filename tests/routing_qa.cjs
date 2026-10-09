/* Independent contract fixtures. Mock DOM checks are not a real browser run. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'service/route-engine.js'), 'utf8');
const routing = require('../service/route-engine.js');
const checks = [];
function check(name, fn) {try {fn();checks.push({name,status:'passed'});}catch(error){checks.push({name,status:'failed',error:error.message.split('\n')[0],code:error.code||null});}}
const opts = {destination_id:'target', vehicle_width_m:2.5, vehicle_height_m:3.2, clearance_m:.25, mode:'training', closed_edge_ids:[]};
const positions = {o:[126.94,37.47], a:[126.941,37.47], b:[126.942,37.47], c:[126.941,37.471], d:[126.943,37.47]};
function edge(id, from, to, length=100, tags={}, highway='residential', way=id) {
  return {id,from,to,length_m:length,tags,highway,way_id:way,name:id,geometry:[positions[from],positions[to]]};
}
function network(edges, destination='d', restrictions=[]) {
  return {schema_version:1, meta:{bbox:[126.94,37.47,126.943,37.471],unsupported_restriction_count:0}, nodes:Object.fromEntries(Object.entries(positions).map(([id,[lon,lat]])=>[id,{lon,lat}])),edges,restrictions,roads:edges,waterways:[],origin:{node_id:'o',name:'합성 출발',lon:126.94,lat:37.47,snap_distance_m:0},destinations:[{id:'target',node_id:destination,name:'합성 목적지',lon:positions[destination][0],lat:positions[destination][1],report:'SYN-QA 합성 원문',synthetic:true}],closures:[]};
}
function plan(n, change={}) {return routing.plan(n,{...opts,...change});}
function assertRoute(n, route, target, closed=[]) {
  assert.ok(route); assert.equal(route.node_ids[0],String(n.origin.node_id)); assert.equal(route.node_ids.at(-1),String(target));
  const edges = new Map(n.edges.map(e=>[e.id,e]));
  let last=String(n.origin.node_id), distance=0;const geometry=[];
  for(const id of route.edge_ids) {
    const e=edges.get(id);assert.ok(e);assert.equal(String(e.from),last);assert.ok(!closed.includes(id));last=String(e.to);distance+=e.length_m;
    const from=n.nodes[e.from],to=n.nodes[e.to];assert.deepEqual(e.geometry[0],[from.lon,from.lat]);assert.deepEqual(e.geometry.at(-1),[to.lon,to.lat]);
    for(const point of e.geometry)if(!geometry.length||geometry.at(-1)[0]!==point[0]||geometry.at(-1)[1]!==point[1])geometry.push(point);
  }
  assert.deepEqual(route.geometry,geometry.length?geometry:[[n.origin.lon,n.origin.lat]]);
  assert.ok(Math.abs(route.distance_m-distance)<.011);assert.ok(Number.isFinite(route.estimated_minutes));
  assert.deepEqual(route.steps.flatMap(s=>s.edge_ids),route.edge_ids);
  assert.ok(Math.abs(route.steps.reduce((sum,s)=>sum+s.distance_m,0)-route.distance_m)<route.steps.length*.011+.011);
}
check('CommonJS and browser UMD use the identical engine',()=>{
  const context={};vm.runInNewContext(source,context);assert.equal(typeof context.RescueRouting.plan,'function');
  const n=network([edge('direct','o','d')]);assert.equal(JSON.stringify(context.RescueRouting.plan(n,opts)),JSON.stringify(plan(n)));
});
const choice = network([edge('narrow','o','d',100,{width:'2.9'}),edge('wide1','o','c',90,{},'tertiary'),edge('wide2','c','d',90,{},'tertiary')]);
check('Vehicle width makes the recommendation longer than shortest',()=>{const r=plan(choice);assert.deepEqual(r.shortest.edge_ids,['narrow']);assert.deepEqual(r.recommended.edge_ids,['wide1','wide2']);assert.equal(r.recommended.distance_m,180);assert.equal(r.shortest.distance_m,100);assertRoute(choice,r.recommended,'d');assert.match(r.shortest.warnings.join(' '),/여유 필터는 제외/);});
check('Clearance counts on both sides; exact boundary accepted',()=>{const n=network([edge('direct','o','d',100,{width:'3 m'})]);assert.ok(plan(n).recommended);assert.equal(plan(n,{clearance_m:.25001}).recommended,null);assert.ok(plan(n,{vehicle_width_m:2.8,clearance_m:.1}).recommended);});
check('OSM width caps the training class assumption',()=>{const n=network([edge('direct','o','d',100,{width:'20'},'service')]);assert.equal(plan(n).recommended,null);assert.ok(plan(n).shortest);});
check('maxwidth checks vehicle width without adding clearance',()=>{const n=network([edge('direct','o','d',100,{maxwidth:'2.5'},'tertiary')]);assert.ok(plan(n).recommended);const r=plan(n,{vehicle_width_m:2.51});assert.equal(r.recommended,null);assert.equal(r.shortest,null);assert.equal(r.rejected.shortest.maxwidth,1);});
check('maxheight applies to both recommendation and shortest',()=>{const n=network([edge('direct','o','d',100,{maxheight:'320 cm'})]);assert.ok(plan(n).recommended);const r=plan(n,{vehicle_height_m:3.21});assert.equal(r.shortest,null);assert.equal(r.rejected.recommended.maxheight,1);});
check('Physical maxwidth/maxheight and node-tag restrictions apply',()=>{for(const tags of [{'maxwidth:physical':'2.4'},{'maxheight:physical':'3.1'},{'node:42:maxwidth':'2.4'},{'node:42:access':'no'},{'node:42:barrier':'gate'}]){const r=plan(network([edge('direct','o','d',100,tags)]));assert.equal(r.recommended,null);assert.equal(r.shortest,null);}});
check('Meter, feet and foot-inch legal limits parse',()=>{for(const tags of [{maxheight:'11 ft'},{maxheight:'10\' 6"'},{maxwidth:'250 cm'},{maxwidth:'2.5 metres'}])assert.ok(plan(network([edge('direct','o','d',100,tags)])).recommended);});
check('Unparsed width and legal or conditional limits fail closed',()=>{for(const tags of [{width:'unknown'},{maxwidth:'none'},{maxheight:'3;4'},{'maxheight:conditional':'4 @ (wet)'},{'width:conditional':'4 @ (Mo-Fr)'},{'access:conditional':'yes @ (delivery)'},{'node:1:maxwidth':'bad'},{'rescue:verified_width':'bad'}]){const r=plan(network([edge('direct','o','d',100,tags)]));assert.equal(r.recommended,null);assert.equal(r.shortest,null);assert.equal(r.rejected.recommended.unparsed_restriction,1);}});
check('Nested physical/directional conditional restrictions fail closed',()=>{for(const tags of [{'maxheight:physical:conditional':'2 @ (wet)'},{'maxwidth:forward:conditional':'2 @ (wet)'},{'motor_vehicle:forward:conditional':'no @ (wet)'},{'oneway:conditional':'yes @ (wet)'},{'node:42:maxheight:physical:conditional':'2 @ (wet)'}]){const r=plan(network([edge('direct','o','d',100,tags)]));assert.equal(r.recommended,null,JSON.stringify(tags));assert.equal(r.shortest,null);assert.equal(r.rejected.recommended.unparsed_restriction,1);}});
check('Unsupported directional limits never become unconditional permission',()=>{for(const key of ['maxwidth:forward','maxheight:backward','width:forward','access:backward','motor_vehicle:forward','node:42:maxwidth:forward','node:42:width:backward']){const r=plan(network([edge('direct','o','d',100,{[key]:'yes'})]));assert.equal(r.recommended,null,key);assert.equal(r.shortest,null,key);assert.equal(r.rejected.shortest.unparsed_restriction,1,key);}});
check('Excluded highways and access/barrier restrictions cannot route',()=>{for(const highway of ['footway','steps','construction','path'])assert.equal(plan(network([edge('direct','o','d',100,{},highway)])).shortest,null);for(const tags of [{access:'private'},{vehicle:'no'},{motor_vehicle:'no'},{motorcar:'private'},{barrier:'bollard'}])assert.equal(plan(network([edge('direct','o','d',100,tags)])).shortest,null);});
check('Directed edges permit only the available direction',()=>{const n=network([edge('oneway','o','d',100,{oneway:'yes'})]);assert.ok(plan(n).recommended);n.origin={...n.nodes.d,node_id:'d'};n.destinations[0].node_id='o';assert.equal(plan(n).shortest,null);});
const turns=()=>network([edge('oa','o','a',10,{},'tertiary','incoming'),edge('ad','a','d',10,{},'tertiary','straight'),edge('ac','a','c',30,{},'tertiary','allowed'),edge('cd','c','d',30,{},'tertiary','finish')]);
check('via-node no-turn forces a legal detour',()=>{const n=turns();n.restrictions=[{from_way:'incoming',via_node:'a',to_way:'straight',restriction:'no_right_turn'}];const r=plan(n);assert.deepEqual(r.shortest.edge_ids,['oa','ac','cd']);assert.ok(r.rejected.shortest.turn_restriction);assertRoute(n,r.recommended,'d');});
check('via-node only-turn excludes other outgoing ways',()=>{const n=turns();n.restrictions=[{from_way:'incoming',via_node:'a',to_way:'allowed',restriction:'only_left_turn'}];assert.deepEqual(plan(n).shortest.edge_ids,['oa','ac','cd']);});
check('no_u_turn blocks reversal while permitting same-way continuation',()=>{const n=network([edge('oa','o','a',10,{},'tertiary','incoming'),edge('ab','a','b',10,{},'tertiary','branch'),edge('ba','b','a',10,{},'tertiary','branch'),edge('ad','a','d',10,{},'tertiary','finish')]);n.restrictions=[{from_way:'incoming',via_node:'a',to_way:'branch',restriction:'only_right_turn'}];assert.deepEqual(plan(n).shortest.edge_ids,['oa','ab','ba','ad']);n.restrictions.push({from_way:'branch',via_node:'b',to_way:'branch',restriction:'no_u_turn'});assert.equal(plan(n).shortest,null);const straight=network([edge('oa','o','a',10,{},'tertiary','same'),edge('ad','a','d',10,{},'tertiary','same')]);straight.restrictions=[{from_way:'same',via_node:'a',to_way:'same',restriction:'no_u_turn'}];assert.ok(plan(straight).shortest);});
check('Closures cause avoidance and complete disconnection',()=>{const r=plan(choice,{closed_edge_ids:['wide1']});assert.equal(r.recommended,null);assert.deepEqual(r.shortest.edge_ids,['narrow']);const r2=plan(choice,{closed_edge_ids:['narrow']});assert.deepEqual(r2.shortest.edge_ids,['wide1','wide2']);assertRoute(choice,r2.shortest,'d',['narrow']);const r3=plan(choice,{closed_edge_ids:['narrow','wide1']});assert.equal(r3.status,'no_route');assert.equal(r3.shortest,null);});
check('Strict excludes unknown and OSM-only width; accepts verified route',()=>{assert.equal(plan(choice,{mode:'strict'}).recommended,null);assert.ok(plan(choice,{mode:'strict'}).shortest);const n=network([edge('direct','o','d',100,{'rescue:verified_width':'3'})]);let r=plan(n,{mode:'strict'});assert.ok(r.recommended);assert.equal(r.recommended.unknown_width_count,0);assert.equal(r.recommended.assumed_width_count,0);n.edges[0].tags.width='2.9';assert.equal(plan(n,{mode:'strict'}).recommended,null);});
check('Invalid numeric ranges, NaN, ids and modes give Korean errors',()=>{const n=choice;const changes=[{vehicle_width_m:NaN},{vehicle_width_m:Infinity},{vehicle_width_m:'2.5'},{vehicle_width_m:1.49},{vehicle_width_m:3.51},{vehicle_height_m:4.51},{vehicle_height_m:1.49},{clearance_m:.09},{clearance_m:.81},{destination_id:'missing'},{mode:'free'},{closed_edge_ids:['missing']},{closed_edge_ids:[1]},{closed_edge_ids:'narrow'}];for(const change of changes)assert.throws(()=>plan(n,change),/[가-힣]/);assert.throws(()=>routing.plan(n,null),/[가-힣]/);});
check('Route planning preserves network and options',()=>{const n=structuredClone(choice),input={...opts,closed_edge_ids:['narrow','narrow']};const before=JSON.stringify({n,input});routing.plan(n,input);assert.equal(JSON.stringify({n,input}),before);});
const snapshot=JSON.parse(fs.readFileSync(path.join(root,'data/routing/network.json')));
for(const dest of snapshot.destinations)for(const [vehicle_width_m,vehicle_height_m,clearance_m] of [[1.8,2.2,.2],[2.5,3.2,.25],[2.8,3.8,.3]])for(const closure of [false,true]) {
  check(`OSM ${dest.id} width=${vehicle_width_m} closure=${closure} training/strict`,()=>{
    const closed_edge_ids=closure?snapshot.closures.flatMap(c=>c.edge_ids):[];
    const input={destination_id:dest.id,vehicle_width_m,vehicle_height_m,clearance_m,closed_edge_ids,mode:'training'};
    const r=routing.plan(snapshot,input);assertRoute(snapshot,r.shortest,dest.node_id,closed_edge_ids);assert.equal(r.assumptions.real_time_traffic,false);
    if(vehicle_width_m===2.8) {assert.equal(r.status,'no_route');assert.equal(r.recommended,null);assert.ok(r.rejected.recommended.effective_width>0);}
    else {assert.equal(r.status,'ok');assertRoute(snapshot,r.recommended,dest.node_id,closed_edge_ids);assert.ok(r.recommended.distance_m>=r.shortest.distance_m-.02);assert.ok(r.recommended.unknown_width_count>0);}
    const strict=routing.plan(snapshot,{...input,mode:'strict'});assert.equal(strict.status,'no_route');assert.equal(strict.recommended,null);assert.ok(strict.shortest);assert.ok(strict.rejected.recommended.unknown_width>0);
  });
}

class Element {
  constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.parent=null;this.dataset={};this.attrs={};this.handlers={};this.hidden=false;this.disabled=false;this.checked=false;this._value='';this._text='';this.labels=[{textContent:id}];this.classList={toggle(){},add(){},remove(){}};}
  set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
  set value(v){this._value=String(v);}get value(){return this._value||(this.tagName==='SELECT'&&this.children[0]?.value)||'';}
  append(...items){for(const child of items){this.children.push(child);if(typeof child==='object')child.parent=this;}}
  replaceChildren(...items){this.children=[];this._text='';this.append(...items);}
  addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}fire(type,event={}){for(const fn of this.handlers[type]||[])fn({preventDefault(){},...event});}
  setAttribute(name,v){this.attrs[name]=v;}getAttribute(name){return this.attrs[name];}
  checkValidity(){return this.value!==''&&Number.isFinite(Number(this.value));}
  getBoundingClientRect(){return {width:900,height:500,left:0,top:0};}setPointerCapture(){}
  closest(tag){return this.tagName===tag.toUpperCase()?this:this.parent?.closest(tag);}
  querySelectorAll(selector){const descendants=[];function walk(el){for(const c of el.children)if(typeof c==='object'){descendants.push(c);walk(c);}}walk(this);return descendants.filter(c=>selector==='input:checked'?c.tagName==='INPUT'&&c.checked:selector==='button[data-route]'?c.tagName==='BUTTON'&&c.dataset.route:false);}
}
async function mockApp({fail=false,missingEngine=false}={}) {
  const html=fs.readFileSync(path.join(root,'web/routes/index.html'),'utf8');const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element(m[1]==='destination'?'select':'div',m[1])]));
  for(const [id,value] of [['vehicle-width','2.5'],['vehicle-height','3.2'],['clearance','.25'],['vehicle-preset','rescue']])elements.get(id).value=value;
  const drawing=new Proxy({measureText(text){return {width:text.length*6};}},{get(o,p){return p in o?o[p]:()=>{};},set(o,p,v){o[p]=v;return true;}});elements.get('route-map').getContext=()=>drawing;
  const frames=[],requests=[];const n=structuredClone(choice);n.closures=[{id:'test-flood',label:'합성 통제',edge_ids:['wide1','narrow'],synthetic:true}];
  const sandbox={document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag)},requestAnimationFrame:fn=>frames.push(fn),fetch:async url=>{requests.push(url);if(fail)throw Error('QA 로딩 실패');return {ok:true,json:async()=>n};},ResizeObserver:class{observe(){}},console};sandbox.window={devicePixelRatio:1,ResizeObserver:sandbox.ResizeObserver,addEventListener(){},...(missingEngine?{}:{RescueRouting:routing})};
  vm.runInNewContext(fs.readFileSync(path.join(root,'web/routes/app.js'),'utf8'),sandbox);
  await new Promise(resolve=>setImmediate(resolve));
  const flush=()=>{while(frames.length)frames.shift()();};return {elements,frames,requests,flush,n};
}
async function main() {
  const ui=await mockApp();ui.flush();
  check('Mock DOM renders initial route and fetches only local snapshot',()=>{assert.ok(Number(ui.elements.get('route-map').dataset.routeEdges)>0);assert.equal(ui.elements.get('steps-panel').hidden,false);assert.deepEqual(ui.requests,['network.json']);});
  check('Mock DOM strict immediately clears old route and remains empty after RAF',()=>{ui.elements.get('strict-mode').checked=true;ui.elements.get('strict-mode').fire('change');assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');assert.equal(ui.elements.get('steps-panel').hidden,true);ui.flush();assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');assert.match(ui.elements.get('route-status').textContent,/추천 경로가 없습니다/);assert.equal(ui.elements.get('route-comparison').querySelectorAll('button[data-route]').length,1);});
  check('Mock DOM shortest requires explicit selection after strict no-route',()=>{const button=ui.elements.get('route-comparison').querySelectorAll('button[data-route]')[0];assert.equal(button.dataset.route,'shortest');button.fire('click');assert.ok(Number(ui.elements.get('route-map').dataset.routeEdges)>0);assert.match(ui.elements.get('map-description').textContent,/물리 폭/);});
  check('Mock DOM invalid input removes selected shortest and shows Korean error',()=>{ui.elements.get('vehicle-width').value='';ui.elements.get('vehicle-width').fire('input');assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');ui.flush();assert.equal(ui.elements.get('route-error').hidden,false);assert.match(ui.elements.get('route-error').textContent,/[가-힣]/);assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');});
  check('Mock DOM rapid changes do not commit stale calculation',()=>{ui.elements.get('vehicle-width').value='2.5';ui.elements.get('strict-mode').checked=false;ui.elements.get('strict-mode').fire('change');ui.elements.get('strict-mode').checked=true;ui.elements.get('strict-mode').fire('change');ui.flush();assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');assert.equal(ui.elements.get('calculate').disabled,false);});
  check('Mock DOM training recovery and closure remove unreachable route',()=>{ui.elements.get('strict-mode').checked=false;ui.elements.get('strict-mode').fire('change');ui.flush();assert.ok(Number(ui.elements.get('route-map').dataset.routeEdges)>0);const label=ui.elements.get('closures').children.find(c=>c.tagName==='LABEL');label.children[0].checked=true;ui.elements.get('closures').fire('change');assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');ui.flush();assert.equal(ui.elements.get('route-map').dataset.routeEdges,'0');});
  const loadFailed=await mockApp({fail:true});check('Mock DOM loading failure shows error with zero route',()=>{assert.equal(loadFailed.elements.get('route-error').hidden,false);assert.equal(loadFailed.elements.get('route-map').dataset.routeEdges,'0');assert.match(loadFailed.elements.get('route-status').textContent,/실패/);});
  const missing=await mockApp({missingEngine:true});check('Mock DOM missing engine produces actionable loading error',()=>{assert.equal(missing.elements.get('route-error').hidden,false);assert.match(missing.elements.get('route-error').textContent,/엔진/);assert.equal(missing.requests.length,0);});
  const failedCount=checks.filter(c=>c.status==='failed').length;
  console.log(JSON.stringify({status:failedCount?'failed':'passed',count:checks.length,passed:checks.length-failedCount,failed:failedCount,checks,scope:'deterministic Node engine and mocked DOM; no actual browser, LLM, OCR, ASR or field driving'},null,2));
  if(failedCount)process.exitCode=1;
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
