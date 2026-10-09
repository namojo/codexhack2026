"""Exercise the actual software depth buffer without browser or canvas dependencies."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE_RASTER = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('web/spatial/index.html','utf8');
const nodes=new Map();
function el(id){if(!nodes.has(id))nodes.set(id,{id,children:[],dataset:{},attrs:{},textContent:'',value:'100',checked:true,clientWidth:850,clientHeight:560,
 classList:{toggle(){}},append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x},setAttribute(k,v){this.attrs[k]=v},
 querySelector(s){return el(id+s)},click(){this.onclick?.()},setPointerCapture(){},getBoundingClientRect(){return {left:0,top:0}},showModal(){},close(){}});return nodes.get(id);}
el('spatial-data').textContent=html.match(/<script id="spatial-data"[^>]*>([\s\S]*?)<\/script>/)[1];
const scene=el('scene');let pixels=null,depthPasses=0,transform=[1,0,0,1,0,0],stack=[];
const ctx=new Proxy({
 save(){stack.push([...transform]);},restore(){transform=stack.pop();},setTransform(...t){transform=t;},
 clearRect(){pixels=null;},measureText(t){return {width:t.length*7};},
 getImageData(x,y,w,h){return {data:pixels?pixels.data.slice():new Uint8ClampedArray(w*h*4),width:w,height:h};},
 putImageData(p){assert.deepEqual(transform,[1,0,0,1,0,0],'pixel transfer must use device coordinates');pixels=p;depthPasses++;},
},{get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
scene.getContext=()=>ctx;
const context={console,document:{getElementById:el,createElement:()=>({textContent:'',dataset:{},setAttribute(){}})},window:{devicePixelRatio:1},ResizeObserver:class{constructor(f){this.f=f}observe(){this.f()}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('web/spatial/app.js','utf8'),context);
function run(s){vm.runInContext(s,context);}
function colors(){const out=new Map();for(let i=0;i<pixels.data.length;i+=4){if(!pixels.data[i+3])continue;const key=[...pixels.data.slice(i,i+3)].join(',');out.set(key,(out.get(key)||0)+1);}return out;}
function count(rgb){return colors().get(rgb)||0;}
function labels(){const bs=context.window.spatialState.labelBoxes;for(let i=0;i<bs.length;i++){const a=bs[i];assert(a.x>=4&&a.y>=58&&a.x+a.w<=scene.clientWidth-4&&a.y+a.h<=scene.clientHeight-4);for(let j=0;j<i;j++){const b=bs[j];assert(!(a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y));}}}
assert.equal(context.window.spatialState.splitView,true);
run("mode='top';yaw=0;draw()");
// Regression: a large floor polygon used to paint over the candidate and fittings.
assert(count('237,189,105')>300,'candidate must survive floor occlusion');
assert(count('142,170,174')>3,'kitchen sink must survive floor occlusion');
assert(count('168,203,208')>3,'window openings must remain visible');labels();
const normal=count('237,189,105');el('ambiguous').click();assert(count('237,189,105')>normal*2,'three candidate regions');
el('floor-select').onchange({target:{value:'16'}});assert.equal(count('237,189,105'),0,'no request on floor 16');
el('focus').click();el('normal').click();
for(const angle of [-2.1,-.22,1.3,2.8]){run(`mode='3d';yaw=${angle};draw()`);assert(pixels.data.some(v=>v>0));assert(count('224,178,99')>20,'candidate visible in the open cutaway');labels();}
run("mode='top';yaw=0;draw()");const withWalls=context.window.spatialState.geometryStats.volumes;
el('walls').checked=false;run('draw()');assert(context.window.spatialState.geometryStats.volumes<withWalls);el('walls').checked=true;
scene.clientWidth=390;scene.clientHeight=350;context.window.devicePixelRatio=2;el('reset').click();
assert.equal(pixels.width,780);assert.equal(pixels.height,700);assert.equal(context.window.spatialState.splitView,false);labels();
assert(context.window.spatialState.geometryStats.windows>200,'repeat plan windows across floors');
console.log(JSON.stringify({actual_browser:false,depthPasses,checks:['occlusion','candidatePixels','threeCandidates','otherFloor','rotation','wallToggle','mobileDPR2','labels']}));
'''


class SpatialRenderQA(unittest.TestCase):
    def test_actual_depth_buffer_and_candidate_visibility(self):
        result = subprocess.run(['node', '-e', NODE_RASTER], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['actual_browser'])
        self.assertGreaterEqual(report['depthPasses'], 10)


if __name__ == '__main__':
    unittest.main()
