"""Independent routing contract verification; temporary DB and static build only."""
import hashlib
import contextlib
from html.parser import HTMLParser
import importlib.util
import json
import io
import math
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse
from http.server import ThreadingHTTPServer

from service.store import Store, ROOT


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module('routing_qa_builder', 'build_pages.py')
serve = load_module('routing_qa_http', 'serve.py')
extractor = load_module('routing_qa_extractor', 'build_route_network.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.labels, self.scripts, self.attrs, self.links = [], [], [], {}, []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
            self.attrs[attrs['id']] = attrs
        if tag == 'label' and 'for' in attrs:
            self.labels.append(attrs['for'])
        if tag == 'script':
            self.scripts.append(attrs.get('src'))
        if tag == 'a':
            self.links.append(attrs)


class RoutingIndependentQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = json.loads((ROOT / 'data/routing/network.json').read_text())

    def test_node_engine_fixtures_snapshot_and_mock_dom(self):
        completed = subprocess.run(['node', 'tests/routing_qa.cjs'], cwd=ROOT,
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'passed')
        self.assertGreaterEqual(result['count'], 120)
        self.assertTrue(all(c['status'] == 'passed' for c in result['checks']))

    def test_source_extraction_retains_node_and_way_conditional_limits(self):
        # A synthetic OSM XML verifies that restrictions survive extraction.
        xml = '''<osm version="0.6">
          <node id="1" lat="37.4800" lon="126.9280"/>
          <node id="2" lat="37.4801" lon="126.9281">
            <tag k="maxwidth:physical" v="2.4"/>
            <tag k="maxheight:physical:conditional" v="2 @ (wet)"/>
            <tag k="access:conditional" v="no @ (wet)"/>
            <tag k="maxwidth:forward" v="2.3"/>
          </node>
          <node id="3" lat="37.4802" lon="126.9282"/>
          <way id="10"><nd ref="1"/><nd ref="2"/><tag k="name" v="관악소방서"/></way>
          <way id="11"><nd ref="2"/><nd ref="3"/><tag k="name" v="신원시장"/></way>
          <way id="20"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
            <tag k="name" v="합성 QA 도로"/><tag k="highway" v="residential"/>
            <tag k="width:conditional" v="2 @ (wet)"/>
            <tag k="maxheight:physical:conditional" v="2 @ (wet)"/>
            <tag k="maxheight:physical" v="3.1"/>
            <tag k="width:backward" v="2.2"/>
          </way></osm>'''
        with tempfile.TemporaryDirectory(prefix='routing-extract-qa-') as temp:
            source, output = Path(temp) / 'synthetic.xml', Path(temp) / 'network.json'
            source.write_text(xml)
            with contextlib.redirect_stdout(io.StringIO()):
                extractor.extract(source, output)
            n = json.loads(output.read_text())
        self.assertEqual(len(n['edges']), 4)
        expected = {
            'width:conditional': '2 @ (wet)',
            'maxheight:physical:conditional': '2 @ (wet)',
            'maxheight:physical': '3.1',
            'width:backward': '2.2',
            'node:2:maxwidth:physical': '2.4',
            'node:2:maxheight:physical:conditional': '2 @ (wet)',
            'node:2:access:conditional': 'no @ (wet)',
            'node:2:maxwidth:forward': '2.3',
        }
        for edge in n['edges']:
            for key, value in expected.items():
                self.assertEqual(edge['tags'].get(key), value, key)

    def test_network_provenance_synthetic_reports_and_excluded_segments(self):
        n = self.network
        self.assertEqual(n['schema_version'], 1)
        meta = n['meta']
        self.assertEqual(meta['source'], 'OpenStreetMap API 0.6')
        self.assertTrue(meta['source_url'].startswith('https://www.openstreetmap.org/api/0.6/map?bbox='))
        self.assertEqual(meta['downloaded_at'], '2026-10-09')
        self.assertRegex(meta['source_sha256'], r'^[a-f0-9]{64}$')
        self.assertEqual(meta['attribution'], '© OpenStreetMap contributors')
        self.assertIn('ODbL', meta['license'])
        self.assertFalse(meta['real_time_traffic'])
        self.assertEqual(meta['verified_effective_width_count'], 0)
        self.assertEqual(len(n['destinations']), 3)
        self.assertEqual(len({d['id'] for d in n['destinations']}), 3)
        for destination in n['destinations']:
            self.assertIs(destination['synthetic'], True)
            self.assertIn('SYN-ROUTE-', destination['report'])
            self.assertIn('가상', destination['report'])
            self.assertIn(destination['node_id'], n['nodes'])
        ids = {e['id'] for e in n['edges']}
        for closure in n['closures']:
            self.assertIs(closure['synthetic'], True)
            self.assertTrue(closure['edge_ids'])
            self.assertLessEqual(set(closure['edge_ids']), ids)
        prohibited = {'footway', 'path', 'pedestrian', 'steps', 'cycleway', 'construction', 'proposed', 'bridleway', 'corridor'}
        for e in n['edges']:
            self.assertNotIn(e['highway'], prohibited)
            for key in ('access', 'vehicle', 'motor_vehicle', 'motorcar'):
                self.assertNotIn(e['tags'].get(key), ('no', 'private'))
            self.assertNotIn('rescue:verified_width', e['tags'])
        # The public road snapshot must not carry OSM editor account metadata.
        def walk(value):
            if isinstance(value, dict):
                self.assertFalse({'uid', 'user', 'username', 'changeset'} & set(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(n)

    def test_all_snapshot_edge_geometry_and_oneway_direction(self):
        n = self.network
        ids = set()
        directions = {(str(e['way_id']), e['from'], e['to']) for e in n['edges']}
        min_lon, min_lat, max_lon, max_lat = n['meta']['bbox']
        oneway_count = 0
        for e in n['edges']:
            self.assertNotIn(e['id'], ids)
            ids.add(e['id'])
            self.assertTrue(math.isfinite(e['length_m']))
            self.assertGreater(e['length_m'], 0)
            self.assertIn(e['from'], n['nodes'])
            self.assertIn(e['to'], n['nodes'])
            start, end = n['nodes'][e['from']], n['nodes'][e['to']]
            self.assertEqual(e['geometry'][0], [start['lon'], start['lat']])
            self.assertEqual(e['geometry'][-1], [end['lon'], end['lat']])
            for lon, lat in e['geometry']:
                self.assertTrue(math.isfinite(lon) and math.isfinite(lat))
                self.assertTrue(min_lon <= lon <= max_lon and min_lat <= lat <= max_lat)
            if e['tags'].get('oneway') in ('yes', '1', 'true', '-1') or (e['tags'].get('junction') == 'roundabout' and e['tags'].get('oneway') != 'no'):
                oneway_count += 1
                self.assertNotIn((str(e['way_id']), e['to'], e['from']), directions)
        self.assertGreater(oneway_count, 0)

    def test_html_labels_single_engine_and_attribution(self):
        html = (ROOT / 'web/routes/index.html').read_text()
        markup = Markup(html)
        self.assertEqual(len(markup.ids), len(set(markup.ids)))
        self.assertLessEqual(set(markup.labels), set(markup.ids))
        self.assertEqual(markup.scripts, ['engine.js', 'app.js'])
        self.assertEqual(markup.attrs['route-map']['tabindex'], '0')
        self.assertEqual(markup.attrs['route-status']['aria-live'], 'polite')
        self.assertEqual(markup.attrs['route-error']['role'], 'alert')
        self.assertEqual(markup.attrs['vehicle-width']['min'], '1.5')
        self.assertEqual(markup.attrs['vehicle-width']['max'], '3.5')
        self.assertEqual(markup.attrs['vehicle-height']['max'], '4.5')
        self.assertEqual(markup.attrs['clearance']['min'], '0.1')
        self.assertEqual(markup.attrs['clearance']['max'], '0.8')
        for text in ('© OpenStreetMap contributors', 'ODbL', '합성', '공식 119 연계 없음', '차체 길이·회전반경', '현재 피해 상황을 뜻하지 않습니다', '차량 조건·가상 통제·내부 추천은 전달되지'):
            self.assertIn(text, html)
        css = (ROOT / 'web/routes/style.css').read_text()
        self.assertIn(':focus-visible', css)
        self.assertIn('@media', css)
        app = (ROOT / 'web/routes/app.js').read_text()
        self.assertEqual(app.count("fetch('network.json')"), 1)
        self.assertNotIn('/api/incidents', app)
        self.assertNotIn('localStorage', app)

    def test_static_build_includes_exact_route_assets_when_requested(self):
        before_seed = digest(ROOT / 'data/seed.json')
        with tempfile.TemporaryDirectory(prefix='routing-static-qa-') as temp:
            output = Path(temp) / 'with-routes'
            builder.build(output, include_routes=True)
            expected = {'index.html', 'app.js', 'style.css', 'engine.js', 'network.json', 'flood-history.json'}
            self.assertEqual({p.name for p in (output / 'routes').iterdir()}, expected)
            self.assertEqual((output / 'routes/engine.js').read_bytes(), (ROOT / 'service/route-engine.js').read_bytes())
            self.assertEqual((output / 'routes/network.json').read_bytes(), (ROOT / 'data/routing/network.json').read_bytes())
            self.assertEqual((output / 'routes/flood-history.json').read_bytes(), (ROOT / 'data/routing/flood-history.json').read_bytes())
            markup = Markup((output / 'index.html').read_text())
            menu = [a['href'] for a in markup.links if a.get('data-nav') == 'routes']
            self.assertEqual(len(menu), 1)
            target = urlparse(urljoin('https://example.invalid/review/index.html', menu[0])).path
            self.assertEqual(target, '/review/routes/')
            info = json.loads((output / 'build-info.json').read_text())
            self.assertEqual(info['route_page'], 'routes/index.html')
            self.assertIn('ODbL', info['route_data_license'])
            for asset in expected:
                self.assertEqual(info['files_sha256']['routes/' + asset], digest(output / 'routes' / asset))
            self.assertFalse(list(output.rglob('*.sqlite3')))
            self.assertTrue((output / 'spatial/index.html').is_file())
            self.assertFalse((output / 'spatial/assets/floorplan-source.jpg').exists())
            self.assertIn('공공누리', info['flood_history_license'])
            self.assertIn('OA-15636', info['flood_history_source'])
        self.assertEqual(before_seed, digest(ROOT / 'data/seed.json'))

    def test_explicit_static_build_exclusion_has_no_broken_routes_menu(self):
        with tempfile.TemporaryDirectory(prefix='routing-default-qa-') as temp:
            output = Path(temp) / 'explicit-exclusion'
            builder.build(output, include_routes=False)
            self.assertFalse((output / 'routes').exists())
            self.assertFalse(any(a.get('data-nav') == 'routes' for a in Markup((output / 'index.html').read_text()).links))
            info = json.loads((output / 'build-info.json').read_text())
            self.assertNotIn('route_page', info)
            self.assertFalse(any(name.startswith('routes/') for name in info['files_sha256']))

    def test_http_get_head_allowlist_404_and_incident_state_unchanged(self):
        # A short-lived loopback server with temporary SQLite; no preview server.
        with tempfile.TemporaryDirectory(prefix='routing-http-qa-') as temp:
            store = Store(Path(temp) / 'routing.sqlite3')
            before = store.list_incidents()
            before_details = {i['id']: store.get_incident(i['id']) for i in before['incidents']}
            server = ThreadingHTTPServer(('127.0.0.1', 0), serve.make_service_handler(store))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(server.server_port)
            routes = {
                '/routes/': (ROOT / 'web/routes/index.html', 'text/html'),
                '/routes/index.html': (ROOT / 'web/routes/index.html', 'text/html'),
                '/routes/app.js': (ROOT / 'web/routes/app.js', 'text/javascript'),
                '/routes/style.css': (ROOT / 'web/routes/style.css', 'text/css'),
                '/routes/engine.js': (ROOT / 'service/route-engine.js', 'text/javascript'),
                '/routes/network.json': (ROOT / 'data/routing/network.json', 'application/json'),
                '/routes/flood-history.json': (ROOT / 'data/routing/flood-history.json', 'application/json'),
            }
            try:
                for route, (source, mime) in routes.items():
                    for method in ('GET', 'HEAD'):
                        with urllib.request.urlopen(urllib.request.Request(base + route, method=method), timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            self.assertTrue(response.headers['Content-Type'].startswith(mime))
                            self.assertEqual(int(response.headers['Content-Length']), source.stat().st_size)
                            self.assertEqual(response.read(), source.read_bytes() if method == 'GET' else b'')
                            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                for route in ('/routes/missing.js', '/routes/../service/route-engine.js', '/routes/%2e%2e/service/route-engine.js', '/service/route-engine.js', '/data/routing/network.json', '/data/workspace.sqlite3', '/api/bundle', '/replay/', '/data/routing/flood-history.json', '/routes/../data/routing/flood-history.json', '/routes/%2e%2e/data/routing/flood-history.json'):
                    for method in ('GET', 'HEAD'):
                        with self.assertRaises(urllib.error.HTTPError) as ctx:
                            urllib.request.urlopen(urllib.request.Request(base + route, method=method), timeout=5)
                        self.assertEqual(ctx.exception.code, 404)
                        if method == 'HEAD':
                            self.assertEqual(ctx.exception.read(), b'')
                        ctx.exception.close()
                self.assertEqual(store.list_incidents(), before)
                # Original reports, revisions, audit and completion evidence are equal.
                reopened = Store(Path(temp) / 'routing.sqlite3')
                for incident_id, original in before_details.items():
                    self.assertEqual(store.get_incident(incident_id), original)
                    self.assertEqual(reopened.get_incident(incident_id), original)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

    def test_offline_cloud_routes_four_build_combinations(self):
        before = digest(ROOT / 'data/seed.json')
        with tempfile.TemporaryDirectory(prefix='routing-build-matrix-') as temp:
            for mode in ('offline', 'cloud'):
                for include in (False, True):
                    with self.subTest(mode=mode, include_routes=include):
                        output = Path(temp) / f'{mode}-{include}'
                        builder.build(output, mode=mode, include_routes=include)
                        info = json.loads((output / 'build-info.json').read_text())
                        self.assertEqual(info['mode'], mode)
                        self.assertEqual((output / 'cloud-client.js').is_file(), mode == 'cloud')
                        html = (output / 'index.html').read_text()
                        self.assertEqual('data-service-mode="cloud"' in html, mode == 'cloud')
                        self.assertEqual('cloud-client.js' in Markup(html).scripts, mode == 'cloud')
                        self.assertEqual((output / 'routes').exists(), include)
                        self.assertEqual('route_page' in info, include)
                        self.assertEqual('flood_history_license' in info, include)
                        self.assertEqual('flood_history_source' in info, include)
                        self.assertTrue((output / 'spatial/index.html').is_file())
                        self.assertFalse(list(output.rglob('floorplan-source.jpg')))
                        self.assertFalse(list(output.rglob('*.sqlite3')))
                        self.assertFalse(list(output.rglob('*.shp')))
                        self.assertFalse(list(output.rglob('*.zip')))
                        for name, fingerprint in info['files_sha256'].items():
                            self.assertEqual(digest(output / name), fingerprint, name)
                        if include:
                            self.assertEqual((output / 'routes/flood-history.json').read_bytes(), (ROOT / 'data/routing/flood-history.json').read_bytes())
                            self.assertEqual(info['source_sha256']['data/routing/flood-history.json'], digest(ROOT / 'data/routing/flood-history.json'))
                        self.assertEqual(len(json.loads((output / 'seed.json').read_text())['incidents']), 12)
        self.assertEqual(before, digest(ROOT / 'data/seed.json'))

    def test_flood_provenance_geometry_privacy_and_network_link(self):
        flood = json.loads((ROOT / 'data/routing/flood-history.json').read_text())
        meta = flood['meta']
        years = [2010, 2011, 2012, 2013, 2014, 2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025]
        self.assertEqual(flood['schema_version'], 1)
        self.assertEqual(meta['years_available'], years)
        self.assertEqual(meta['years_without_files'], [2015, 2021])
        self.assertEqual(meta['network_sha256'], digest(ROOT / 'data/routing/network.json'))
        self.assertEqual(meta['nearby_buffer_m'], 10)
        self.assertEqual(meta['risk_penalty_per_year_m'], 8)
        self.assertEqual(meta['calculation_crs'], 'EPSG:5179')
        self.assertEqual(meta['display_crs'], 'EPSG:4326')
        self.assertIn('OA-15636', meta['source_url'])
        self.assertIn('공공누리', meta['license'])
        self.assertEqual(meta['dataset_updated_at'], '2026-04-27')
        self.assertEqual([s['year'] for s in meta['sources']], years)
        for source in meta['sources']:
            self.assertRegex(source['zip_sha256'], r'^[a-f0-9]{64}$')
            self.assertGreater(source['zip_bytes'], 0)
            self.assertLessEqual(source['selected_record_count'], source['original_record_count'])
        self.assertEqual(set(flood), {'schema_version', 'meta', 'traces', 'edge_exposure'})
        self.assertEqual(flood['traces']['type'], 'FeatureCollection')
        min_lon, min_lat, max_lon, max_lat = self.network['meta']['bbox']
        for feature in flood['traces']['features']:
            self.assertEqual(set(feature['properties']), {'year', 'source_record_count'})
            self.assertIn(feature['properties']['year'], meta['years_available'])
            self.assertGreater(feature['properties']['source_record_count'], 0)
            for key in ('geometry', 'nearby_geometry'):
                geometry = feature[key]
                self.assertIn(geometry['type'], ('Polygon', 'MultiPolygon'))
                polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
                for polygon in polygons:
                    for ring in polygon:
                        self.assertGreaterEqual(len(ring), 4)
                        self.assertEqual(ring[0], ring[-1])
                        for lon, lat in ring:
                            self.assertTrue(math.isfinite(lon) and math.isfinite(lat))
                            # Straight projected clipping edges curve slightly in WGS84.
                            # Independent GIS verifies EPSG:5179 containment separately.
                            self.assertTrue(min_lon - 2e-6 <= lon <= max_lon + 2e-6)
                            self.assertTrue(min_lat - 2e-6 <= lat <= max_lat + 2e-6)
        self.assertEqual(meta['years_in_bbox'], [f['properties']['year'] for f in flood['traces']['features']])


if __name__ == '__main__':
    unittest.main()
