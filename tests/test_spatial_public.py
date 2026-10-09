"""Independent public spatial boundary QA. Synthetic builds; DOM/canvas are mocked."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.parse import urljoin, urlparse

from scripts.build_pages import build

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SPATIAL = {'index.html', 'app.js', 'style.css', 'assets/floor-model.json',
                  'assets/analysis.json', 'assets/report.json', 'assets/provenance.json',
                  'assets/synthetic-report.png'}


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


NODE_UI = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=process.argv[1],html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const data=JSON.parse(html.match(/<script id="spatial-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
const cases=[];
for(const [width,height] of [[1000,560],[390,350]]){
 const nodes=new Map(),paint=[],requests=[],writes=[];
 function el(id){if(!nodes.has(id)){const n={id,children:[],textContent:'',value:'',dataset:{},attrs:{},checked:false,src:'',open:false,clientWidth:width,clientHeight:height,
  classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v},append(...x){this.children.push(...x)},replaceChildren(...x){this.children=[...x]},querySelector(s){return el(this.id+':'+s)},showModal(){this.open=true},close(){this.open=false},click(){this.onclick?.({target:this})},setPointerCapture(){},getBoundingClientRect(){return {left:0,top:0}}};nodes.set(id,n);}return nodes.get(id);}
 el('spatial-data').textContent=JSON.stringify(data);el('walls').checked=true;el('connection').checked=true;
 const ctx=new Proxy({measureText:t=>({width:t.length*7}),fillText:t=>paint.push(t)}, {get:(o,k)=>k in o?o[k]:(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
 el('scene').getContext=()=>ctx;
 const bomb=(...args)=>{requests.push(args);throw Error('spatial must not call network or storage');};
 const window={devicePixelRatio:1,fetch:bomb,localStorage:{setItem:bomb},sessionStorage:{setItem:bomb},RescueCloud:new Proxy({},{get:()=>bomb})};
 const context={console,window,document:{getElementById:el,createElement:t=>({textContent:'',dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v}})},ResizeObserver:class{constructor(fn){this.fn=fn}observe(){this.fn()}},fetch:bomb,localStorage:{setItem:bomb},sessionStorage:{setItem:bomb},XMLHttpRequest:class{constructor(){bomb()}},WebSocket:class{constructor(){bomb()}}};
 vm.createContext(context);vm.runInContext(source,context);
 const state=()=>JSON.parse(JSON.stringify(window.spatialState));
 function labels(){const bs=state().labelBoxes;for(const b of bs){assert(b.x>=4&&b.y>=58&&b.x+b.w<=width-4&&b.y+b.h<=height-4);}for(let i=0;i<bs.length;i++)for(let j=i+1;j<bs.length;j++){const a=bs[i],b=bs[j];assert(!(a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y),'label overlap');}}
 assert.equal(state().mode,'building');assert.equal(state().selectedFloor,3);assert.deepEqual(state().modeledFloors,Array.from({length:14},(_,i)=>i+3));assert.deepEqual(state().unknownFloors,[1,2]);assert.equal(el('spaces').children.length,10);assert.equal(el('report-text').textContent,data.report.text);assert.deepEqual(JSON.parse(el('analysis-json').textContent),data.analysis);labels();
 el('floor-select').onchange({target:{value:'16'}});assert.equal(state().selectedFloor,16);assert.deepEqual(state().visibleCandidates,[]);assert.match(el('scene-status').textContent,/이 층에는 가상 신고 없음/);assert.match(el('scene-detail').textContent,/신고는 3층에 유지/);labels();
 el('top').click();assert.equal(state().mode,'top');assert.deepEqual(state().visibleCandidates,[]);labels();
 el('focus').click();assert.equal(state().selectedFloor,3);assert.equal(state().selected,'B3');assert.equal(state().mode,'3d');assert.deepEqual(state().visibleCandidates,['B3']);labels();
 el('ambiguous').click();assert.equal(state().ambiguous,true);assert.deepEqual(state().visibleCandidates,['B2','B3','B4']);assert.match(el('comparison').textContent,/규칙 기반 비교 목업/);assert.match(el('scene-detail').textContent,/2명은 원문 진술/);labels();
 el('floor-select').onchange({target:{value:'8'}});assert.deepEqual(state().visibleCandidates,[]);assert.equal(state().ambiguous,true);
 el('focus').click();assert.deepEqual(state().visibleCandidates,['B2','B3','B4']);
 el('normal').click();assert.deepEqual(state().visibleCandidates,['B3']);
 let previous=state();el('scene').onkeydown({key:'ArrowRight',preventDefault(){}});assert(state().yaw>previous.yaw);
 el('scene').onkeydown({key:'+',preventDefault(){}});assert(state().zoom>previous.zoom);labels();
 el('zoom').oninput({target:{value:'180'}});labels();el('zoom').oninput({target:{value:'65'}});labels();
 el('scene').onpointerdown({clientX:10,clientY:10,pointerId:1});previous=state();el('scene').onpointermove({clientX:50,clientY:30});assert(state().yaw>previous.yaw);el('scene').onpointercancel();
 el('report-image').click();assert.equal(el('dialog-image').src,'assets/synthetic-report.png');assert.equal(el('image-dialog').open,true);assert.match(el('dialog-title').textContent,/합성/);el('close-dialog').click();assert.equal(el('image-dialog').open,false);
 el('scene').onkeydown({key:'Escape',preventDefault(){}});assert.equal(state().mode,'building');assert.equal(state().selectedFloor,3);assert.equal(state().ambiguous,false);assert.equal(state().zoom,1);labels();
 assert.equal(el('source-open').onclick,undefined);assert.equal(el('source-preview').onclick,undefined);
 assert.equal(requests.length,0);assert.equal(writes.length,0);assert.deepEqual(JSON.parse(el('spatial-data').textContent),data);assert(!paint.some(t=>t.includes('?')||t.includes(data.report.text)));
 cases.push({width,height,mode:'mock_DOM_canvas',navigation:true,unknownFloor:true,candidates:true,photo:true,immutableInputs:true,noNetworkOrWrites:true,labels:true});
}
console.log(JSON.stringify({actual_browser:false,cases}));
'''


class SpatialPublicQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='spatial-public-independent-')
        cls.outputs = {}
        for mode in ('cloud', 'offline'):
            output = Path(cls.temp.name) / mode
            build(output, mode)
            cls.outputs[mode] = output

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_both_modes_exact_public_allowlist_and_hashes(self):
        for mode, output in self.outputs.items():
            with self.subTest(mode=mode):
                spatial = output / 'spatial'
                actual = {str(p.relative_to(spatial)) for p in spatial.rglob('*') if p.is_file()}
                self.assertEqual(actual, PUBLIC_SPATIAL)
                info = json.loads((output / 'build-info.json').read_text())
                self.assertEqual(info['mode'], mode)
                for relative in PUBLIC_SPATIAL:
                    p = spatial / relative
                    self.assertEqual(p.read_bytes(), (ROOT / 'web/spatial' / relative).read_bytes())
                    self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), info['files_sha256']['spatial/' + relative])
                self.assertFalse(any(p.suffix.lower() in ('.jpg', '.jpeg') for p in output.rglob('*')))
                self.assertNotIn('web/spatial/assets/floorplan-source.jpg', info['source_sha256'])
                self.assertFalse((spatial / 'assets/synthetic-report.png').is_symlink())
                self.assertTrue((spatial / 'assets/synthetic-report.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))

    def test_assets_provenance_hash_and_original_local_drawing_retained(self):
        assets = ROOT / 'web/spatial/assets'
        provenance = json.loads((assets / 'provenance.json').read_text())
        for name, sha in provenance['sha256'].items():
            self.assertEqual(hashlib.sha256((assets / name).read_bytes()).hexdigest(), sha, name)
        self.assertTrue((assets / 'floorplan-source.jpg').read_bytes().startswith(b'\xff\xd8'))
        self.assertIs(provenance['floorplan']['public_copy_included'], False)
        self.assertEqual(provenance['floorplan']['redistribution_permission'], 'not_verified')
        self.assertTrue(provenance['photo']['synthetic'])
        self.assertFalse(provenance['analysis']['new_model_call_for_upgrade'])

    def test_direct_menu_and_resolvable_executable_resources(self):
        for mode, output in self.outputs.items():
            with self.subTest(mode=mode):
                main = Document((output / 'index.html').read_text())
                menu = [a for tag, a in main.elements if tag == 'a' and a.get('data-nav') == 'spatial']
                self.assertEqual(len(menu), 1)
                self.assertEqual(menu[0]['href'], 'spatial/')
                page = Document((output / 'spatial/index.html').read_text())
                for tag, attrs in page.elements:
                    for key in ('src', 'href'):
                        url = attrs.get(key, '')
                        if not url or url.startswith('#') or urlparse(url).scheme:
                            continue
                        parsed = urlparse(url)
                        p = (output / parsed.path.lstrip('/')) if url.startswith('/') else (output / 'spatial' / parsed.path).resolve()
                        if p.is_dir():
                            p /= 'index.html'
                        self.assertTrue(p.is_file(), (mode, tag, url))
                        self.assertNotIn(p.suffix.lower(), ('.jpg', '.jpeg'))
                scripts = [a['src'] for tag, a in main.elements if tag == 'script' and 'src' in a]
                self.assertEqual('cloud-client.js' in scripts, mode == 'cloud')
                self.assertLess(scripts.index('pages-store.js'), scripts.index('app.js'))

    def test_original_json_full_metadata_and_source_links_preserved(self):
        provenance = json.loads((ROOT / 'web/spatial/assets/provenance.json').read_text())
        html = (self.outputs['cloud'] / 'spatial/index.html').read_text()
        import re
        data = json.loads(re.search(r'<script id="spatial-data"[^>]*>(.*?)</script>', html, re.S).group(1))
        for key, name in [('floor_model', 'floor-model.json'), ('analysis', 'analysis.json'), ('report', 'report.json')]:
            self.assertEqual(data[key], json.loads((ROOT / 'web/spatial/assets' / name).read_text()))
        self.assertTrue(data['report']['synthetic'])
        self.assertEqual(data['report']['floor'], 3)
        self.assertEqual(data['report']['id'], 'SYN-SP-001')
        self.assertIsNone(data['analysis']['numerical_probability'])
        self.assertFalse(data['analysis']['ground_truth_used'])
        self.assertIn('floorplan-source.jpg', data['floor_model']['source_image'])
        links = [a for tag, a in Document(html).elements if tag == 'a' and a.get('id') in ('source-open', 'source-preview')]
        self.assertEqual(len(links), 2)
        for a in links:
            self.assertEqual(a['href'], provenance['floorplan']['source_page'])
            self.assertEqual(a['target'], '_blank')
            self.assertEqual(set(a['rel'].split()), {'noopener', 'noreferrer'})
        for tag, attrs in Document(html).elements:
            for key in ('src', 'href'):
                self.assertNotIn(urlparse(attrs.get(key, '')).path.lower().split('.')[-1], ('jpg', 'jpeg'))

    def test_preanalysis_and_rule_counterfactual_are_visible(self):
        html = (self.outputs['offline'] / 'spatial/index.html').read_text()
        for text in ('사전 분석 결과', '실행 시 모델 호출은 없습니다', '규칙 기반 목업', '별도 모델 실행 결과가 아닙니다',
                     '2명은 원문 진술', '실측값이 아닙니다', '안전 경로로 확정되지 않았습니다', '선택 층 변경은 신고 위치의 변경을 뜻하지 않습니다'):
            self.assertIn(text, html)
        source = (self.outputs['offline'] / 'spatial/app.js').read_text()
        self.assertNotIn('floorplan-source.jpg', source)
        self.assertNotIn('imageDialog(data.floor_model.source_image', source)

    def test_machine_readable_links_and_preserved_analysis(self):
        for mode, output in self.outputs.items():
            for name in ('llms.txt', 'llms-full.txt', 'sitemap.xml', 'judge/index.html', 'about/index.html', 'guide/index.html', 'references/index.html'):
                with self.subTest(mode=mode, file=name):
                    self.assertIn('/spatial/', (output / name).read_text())
            evidence = json.loads((output / 'judge/evidence.json').read_text())['spatial']
            self.assertEqual(evidence['mode'], 'preserved-model-analysis-static-view')
            self.assertFalse(evidence['new_model_call_on_view'])
            self.assertFalse(evidence['original_drawing_redistributed'])
            self.assertEqual(evidence['analysis'], json.loads((ROOT / 'web/spatial/assets/analysis.json').read_text()))
            self.assertEqual(evidence['synthetic_report'], json.loads((ROOT / 'web/spatial/assets/report.json').read_text()))

    def test_existing_synthetic_reports_originals_and_ai_boundaries(self):
        original = json.loads((ROOT / 'data/seed.json').read_text())
        for mode, output in self.outputs.items():
            seed = json.loads((output / 'seed.json').read_text())
            self.assertTrue(seed['synthetic'])
            self.assertEqual(len(seed['incidents']), 10)
            self.assertEqual(sum(len(i['reports']) for i in seed['incidents']), 20)
            got = {i['id']: i for i in seed['incidents']}
            for i in original['incidents']:
                self.assertEqual(got[i['id']]['reports'], i['reports'])
                for field in ('status', 'revision', 'audit', 'outcome', 'outcome_history'):
                    self.assertEqual(got[i['id']][field], i[field])
            main = (output / 'index.html').read_text()
            self.assertIn('합성', main)
            if mode == 'cloud':
                self.assertIn('data-service-mode="cloud"', main)
            self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY=', main)
            self.assertNotIn('OPENAI_API_KEY=', main)

    def test_independent_runtime_navigation_candidates_labels_and_photo(self):
        p = subprocess.run(['node', '-e', NODE_UI, str(self.outputs['cloud'] / 'spatial')], capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        report = json.loads(p.stdout)
        self.assertFalse(report['actual_browser'])
        self.assertEqual([c['width'] for c in report['cases']], [1000, 390])
        self.assertTrue(all(c['noNetworkOrWrites'] and c['immutableInputs'] for c in report['cases']))


if __name__ == '__main__':
    unittest.main()
