"""Independent static build and Python/JS state contract checks; synthetic temp DB only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.parse import urljoin

from service.store import APIError, Store, ROOT

spec = importlib.util.spec_from_file_location('pages_build_qa', ROOT / 'scripts' / 'build_pages.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PagesIndependentQA(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='independent-pages-qa-')
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        output = self.base / 'static'
        builder.build(output)
        return output

    def test_public_build_allowlist_hashes_and_synthetic_counts(self):
        output = self.build()
        expected = {'index.html', 'app.js', 'style.css', 'pages-store.js', 'seed.json', '.nojekyll', 'build-info.json',
                    'media/flood-entrance.png', 'media/flood-stairwell.png', 'media/call-isolated.wav', 'media/call-proxy.wav', 'media/provenance.json', 'media/parking-pillar-dark.png', 'media/parking-stair-flood.png', 'media/parking-call-noisy.wav', 'media/parking-call-enhanced.wav',
                    'about/index.html', 'guide/index.html', 'references/index.html', 'judge/index.html', 'judge/evidence.json',
                    'public-guide.css', 'llms.txt', 'llms-full.txt', 'sitemap.xml', 'robots.txt',
                    'spatial/index.html', 'spatial/app.js', 'spatial/style.css', 'spatial/assets/floor-model.json',
                    'spatial/assets/analysis.json', 'spatial/assets/report.json', 'spatial/assets/provenance.json',
                    'spatial/assets/synthetic-report.png', 'spatial/assets/walkthrough.mp4',
                    'spatial/assets/walkthrough-poster.png', 'spatial/assets/walkthrough.ko.vtt',
                    'spatial/assets/walkthrough.json', 'routes/index.html', 'routes/app.js',
                    'routes/style.css', 'routes/engine.js', 'routes/network.json', 'routes/flood-history.json'}
        self.assertEqual({str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}, expected)
        bundle = json.loads((output / 'seed.json').read_text())
        self.assertTrue(bundle['synthetic'])
        self.assertEqual(len(bundle['incidents']), 12)
        self.assertEqual(sum(len(i['reports']) for i in bundle['incidents']), 30)
        self.assertTrue(all(i['synthetic'] for i in bundle['incidents']))
        info = json.loads((output / 'build-info.json').read_text())
        for name, digest in info['files_sha256'].items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(info['source_sha256']['data/seed.json'], hashlib.sha256((ROOT / 'data/seed.json').read_bytes()).hexdigest())

    def test_relative_entrypoints_support_netlify_root_and_subpath(self):
        html = (self.build() / 'index.html').read_text()
        self.assertIn('href="style.css"', html)
        self.assertLess(html.index('src="pages-store.js"'), html.index('src="app.js"'))
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn('/replay', html)
        for base in ['https://example.netlify.app/', 'https://example.test/hack-test/']:
            for name in ['app.js', 'pages-store.js', 'style.css', 'seed.json', 'media/call-proxy.wav']:
                self.assertEqual(urljoin(base, name), base + name)
        self.assertNotIn('pages-store.js', (ROOT / 'web/index.html').read_text(), 'local server HTML must not enable storage adapter')

    def test_existing_unrelated_output_cli_fails_and_preserves_content(self):
        output = self.base / 'unrelated'
        output.mkdir()
        sentinel = output / 'private.txt'
        sentinel.write_text('synthetic preservation sentinel')
        result = subprocess.run(['python3', '-B', str(ROOT / 'scripts/build_pages.py'), '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('기존 출력', result.stderr)
        self.assertEqual(sentinel.read_text(), 'synthetic preservation sentinel')

    def test_source_and_symlink_output_targets_rejected(self):
        with self.assertRaises(ValueError):
            builder.build(ROOT / 'web' / 'unwritten-qa-output')
        link = self.base / 'link'
        link.symlink_to(ROOT / 'data', target_is_directory=True)
        with self.assertRaises(ValueError):
            builder.build(link)
        self.assertTrue(link.is_symlink())

    def test_generated_media_exact_allowlist_provenance_preserved(self):
        output = self.build()
        media = output / 'media'
        for name in ['flood-entrance.png', 'flood-stairwell.png', 'call-isolated.wav', 'call-proxy.wav', 'parking-pillar-dark.png', 'parking-stair-flood.png', 'parking-call-noisy.wav', 'parking-call-enhanced.wav', 'provenance.json']:
            self.assertEqual((media / name).read_bytes(), (ROOT / 'data/media' / name).read_bytes())
        self.assertTrue(json.loads((media / 'provenance.json').read_text())['synthetic'])

    def test_representative_continuous_state_matches_python_store(self):
        result = subprocess.run(['node', str(ROOT / 'tests/pages_qa.cjs'), '--trace'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        js = json.loads(result.stdout)
        store = Store(self.base / 'parity.sqlite3')
        trace = []

        def save(i):
            trace.append({'status':i['status'], 'people_count':i['people_count'], 'priority':i['priority'], 'revision':i['revision'],
                          'assigned_team_id':i['assigned_team_id'], 'report_count':len(i['reports']), 'progress_count':len(i['progress']),
                          'audit_count':len(i['audit']), 'history_count':len(i['outcome_history']), 'outcome':i['outcome']['outcome'] if i['outcome'] else None,
                          'attention':[t['id'].split(':')[-1] for t in i['attention']], 'location':i['location']})
            return i

        def report(i, n, text='현장 직접 대면: 전원 안전 확인', kind='field'):
            return save(store.add_report(i['id'], {'expected_revision':i['revision'], 'kind':kind, 'channel':'field' if kind=='field' else 'sms', 'text':text, 'people_count':n}))

        def close(i):
            return save(store.confirm_outcome(i['id'], {'expected_revision':i['revision'], 'outcome':'rescued', 'confirmed_count':i['people_count'],
                                                       'basis_report_id':i['reports'][-1]['id'], 'note':'합성 현장 근거를 담당자가 대조'}))

        i = save(store.create_incident({'title':'합성 QA 사건','location':'가상동 검증빌라 201호','text':'합성 신고: 세 명 고립','people_count':3,'priority':'urgent'}))
        i = save(store.add_progress(i['id'], {'expected_revision':i['revision'],'status':'dispatched','team_id':'TEAM-04','note':'합성 팀배정 검증'}))
        i = report(i, 2, '현장 두 명 안전 확인, 한 명 미확인')
        i = report(i, 3)
        i = close(i)
        i = save(store.reopen(i['id'], {'expected_revision':i['revision'],'reason':'인원 정정 필요'}))
        i = report(i, 2, '대상 인원은 두 명으로 정정', 'correction')
        i = report(i, 2)
        close(i)
        self.assertEqual(trace, js)

    def test_python_equal_count_residual_completion_is_rejected(self):
        # The AI service extension now applies the residual guard to both backends.
        store = Store(self.base / 'difference.sqlite3')
        i = store.create_incident({'title':'합성 기존 서버 경계','location':'가상동','text':'세 명 대상','people_count':3})
        i = store.add_report(i['id'], {'expected_revision':i['revision'],'channel':'field','kind':'field','text':'두 명만 구조, 한 명 남아 있음','people_count':3})
        with self.assertRaises(APIError) as error:
            store.confirm_outcome(i['id'], {'expected_revision':i['revision'],'outcome':'rescued','confirmed_count':3,'basis_report_id':i['reports'][-1]['id'],'note':'잔여 대상 차단 확인'})
        self.assertEqual(error.exception.status, 400)
        self.assertNotEqual(store.get_incident(i['id'])['status'], 'closed')


if __name__ == '__main__':
    unittest.main()
