"""Independent showcase QA: temporary DB, real media bytes, mocked AI only."""
import array
import base64
import copy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from service import ai
from service.store import APIError, Store
from scripts.build_pages import build

ROOT = Path(__file__).resolve().parents[1]
FEATURED = 'INC-20261009-100'
DUPLICATE = 'INC-20261009-101'
MEDIA = ('flood-entrance.png', 'flood-stairwell.png', 'call-isolated.wav', 'call-proxy.wav',
         'parking-pillar-dark.png', 'parking-stair-flood.png', 'parking-call-noisy.wav', 'parking-call-enhanced.wav')
LEGACY_SHA = '6c1558212885b0ec5cdc0814134115d623ee284e00fce5b903ad2ed5df4ccdd7'


def empty(schema):
    if 'anyOf' in schema: return None
    if 'enum' in schema: return None if None in schema['enum'] else schema['enum'][0]
    typ = schema.get('type')
    if isinstance(typ, list) and 'null' in typ: return None
    if typ == 'object': return {k: empty(v) for k, v in schema['properties'].items()}
    return {'array': [], 'string': '', 'integer': 0, 'number': 0, 'boolean': True}[typ]


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.elements = []; self.text = []
        self.feed(text)
    def handle_starttag(self, tag, attrs): self.elements.append((tag, dict(attrs)))
    def handle_data(self, value): self.text.append(value)


class HackathonShowcaseQA(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='showcase-independent-')
        self.path = Path(self.temp.name)
        self.seed = json.loads((ROOT / 'data/seed.json').read_text())
        self.store = Store(self.path / 'synthetic.sqlite3')
    def tearDown(self): self.temp.cleanup()
    def reject(self, callback, status=400):
        with self.assertRaises(APIError) as e: callback()
        self.assertEqual(e.exception.status, status)
    def outcome(self, incident, basis, count):
        return self.store.confirm_outcome(incident['id'], {'expected_revision': incident['revision'],
            'outcome': 'rescued', 'confirmed_count': count, 'basis_report_id': basis,
            'actor': '가상 QA 담당자', 'note': '합성 원문과 현장 인원 대조'})

    def test_original_ten_incidents_twenty_reports_and_four_teams_unchanged(self):
        legacy = {'incidents': [i for i in self.seed['incidents'] if i['id'].startswith('INC-20261008-')],
                  'resources': [r for r in self.seed['resources'] if r['id'] != 'TEAM-DEMO01']}
        self.assertEqual(len(legacy['incidents']), 10)
        self.assertEqual(sum(len(i['reports']) for i in legacy['incidents']), 20)
        self.assertEqual(len(legacy['resources']), 4)
        digest = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, LEGACY_SHA)
        self.assertEqual(len(self.seed['incidents']), 12)
        self.assertEqual(sum(len(i['reports']) for i in self.seed['incidents']), 30)

    def test_featured_first_retains_priority_attention_and_reload(self):
        listed = self.store.list_incidents()
        self.assertEqual(listed['incidents'][0]['id'], FEATURED)
        old = self.store.get_incident(FEATURED)
        self.assertIs(old['demo_featured'], True)
        changed = self.store.update_incident(FEATURED, {'expected_revision': old['revision'], 'reason': '가상 위치 재확인', 'location': old['location'] + ' (대조 중)'})
        self.assertIs(changed['demo_featured'], True)
        self.assertEqual(changed['priority'], old['priority'])
        self.assertEqual(changed['reports'], old['reports'])
        reload = Store(self.path / 'synthetic.sqlite3')
        self.assertEqual(reload.list_incidents()['incidents'][0]['id'], FEATURED)
        self.assertIs(reload.get_incident(FEATURED)['demo_featured'], True)
        self.assertTrue(old['attention'])
        self.assertTrue(all(t['source'] == 'rule' for t in old['attention']))
        for task in old['attention']:
            for ev in task['evidence']:
                report = next(r for r in old['reports'] if r['id'] == ev['report_id'])
                self.assertIn(ev['quote'], report['text'])

    def test_invalid_featured_seed_bool_and_user_flag_injection_rejected(self):
        for invalid in ('true', 1, None):
            broken = copy.deepcopy(self.seed); broken['incidents'][-2]['demo_featured'] = invalid
            path = self.path / ('bad-' + str(invalid) + '.json'); path.write_text(json.dumps(broken))
            self.reject(lambda: Store(self.path / ('bad-' + str(invalid) + '.sqlite3'), path))
        self.reject(lambda: self.store.create_incident({'title': '가상', 'location': '가상', 'text': '가상', 'demo_featured': True}))

    def test_partial_two_of_three_and_residual_equal_count_completion_rejected(self):
        i = self.store.get_incident(FEATURED); before = copy.deepcopy(i)
        self.assertEqual((i['status'], i['people_count'], i['outcome']), ('rescuing', 3, None))
        for basis in ('REP-100-06', 'REP-100-08'):
            self.reject(lambda: self.outcome(i, basis, 2))
            self.reject(lambda: self.outcome(i, basis, 3))
        self.reject(lambda: self.outcome(i, 'REP-101-01', 3))
        self.assertEqual(self.store.get_incident(FEATURED), before)
        i = self.store.add_report(FEATURED, {'expected_revision': i['revision'], 'kind': 'field', 'channel': 'field',
            'actor': '가상 현장팀', 'text': '두 명 구조, 성인 여성 한 명은 아직 남아 있음', 'people_count': 3})
        self.reject(lambda: self.outcome(i, i['reports'][-1]['id'], 3))
        self.assertIsNone(self.store.get_incident(FEATURED)['outcome'])

    def test_duplicate_original_ids_unknown_count_no_team_or_merge(self):
        i = self.store.get_incident(DUPLICATE)
        self.assertEqual(i['status'], 'received')
        self.assertIsNone(i['people_count']); self.assertIsNone(i['assigned_team_id']); self.assertIsNone(i['outcome'])
        self.assertEqual([r['id'] for r in i['reports']], ['REP-101-01', 'REP-101-02'])
        raw = next(x for x in self.seed['incidents'] if x['id'] == DUPLICATE)
        self.assertEqual(i['reports'], raw['reports'])
        team = next(r for r in self.store.list_incidents()['resources'] if r['id'] == 'TEAM-DEMO01')
        self.assertEqual((team['incident_id'], team['crew_count']), (FEATURED, 4))
        self.assertEqual(self.store.get_incident(FEATURED)['people_count'], 3)

    def test_full_field_human_confirm_then_followup_reopens_and_preserves_history(self):
        i = self.store.get_incident(FEATURED); old_reports = copy.deepcopy(i['reports'])
        i = self.store.add_report(FEATURED, {'expected_revision': i['revision'], 'kind': 'field', 'channel': 'field',
            'actor': '가상 현장팀', 'text': '현장 직접 대면으로 원 요청 여성 세 명 전원 구조와 안전 확인', 'people_count': 3})
        i = self.outcome(i, i['reports'][-1]['id'], 3)
        self.assertEqual(i['status'], 'closed'); outcome = copy.deepcopy(i['outcome'])
        i = self.store.add_report(FEATURED, {'expected_revision': i['revision'], 'kind': 'additional', 'channel': 'sms',
            'actor': '가상 성인 신고자', 'text': '추가 위치 정보를 확인해 주세요', 'attachments': []})
        self.assertEqual(i['status'], 'reviewing'); self.assertIsNone(i['outcome'])
        for key, value in outcome.items(): self.assertEqual(i['outcome_history'][-1][key], value)
        self.assertTrue(i['outcome_history'][-1]['reopened_at'])
        self.assertEqual(i['reports'][:8], old_reports)
        self.assertEqual(Store(self.path / 'synthetic.sqlite3').get_incident(FEATURED), i)

    def test_real_eight_media_allowlist_headers_dimensions_hashes_and_PCM(self):
        provenance = json.loads((ROOT / 'data/media/provenance.json').read_text())
        self.assertTrue(provenance['synthetic'])
        entries = {Path(e['path']).name: e for group in ('images', 'audio') for e in provenance[group]}
        frames = {}
        for name in MEDIA:
            p = self.store.allowed_media('/media/' + name); payload = p.read_bytes()
            self.assertEqual(p, ROOT / 'data/media' / name)
            self.assertGreater(len(payload), 1000)
            entry = entries[name]
            if 'sha256' in entry: self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
            if name.endswith('.png'):
                self.assertTrue(payload.startswith(b'\x89PNG\r\n\x1a\n'))
                if name.startswith('parking-'): self.assertEqual(struct.unpack('>II', payload[16:24]), (1536, 1024))
            else:
                with wave.open(str(p)) as w:
                    self.assertEqual(w.getsampwidth(), 2); self.assertGreater(w.getframerate(), 8000)
                    self.assertGreater(w.getnframes() / w.getframerate(), 5)
                    if name.startswith('parking-'):
                        self.assertEqual(w.getnchannels(), 1); self.assertEqual(w.getframerate(), 22050)
                        self.assertAlmostEqual(w.getnframes() / w.getframerate(), 16.27, places=2)
                        frames[name] = w.readframes(w.getnframes())
                        self.assertEqual(entry['transcript_source'], 'TTS script, not ASR')
        noisy = frames['parking-call-noisy.wav']; enhanced = frames['parking-call-enhanced.wav']
        self.assertEqual(len(noisy), len(enhanced)); self.assertNotEqual(noisy, enhanced)
        for payload in (noisy, enhanced):
            pcm = array.array('h'); pcm.frombytes(payload)
            self.assertGreater(max(abs(x) for x in pcm), 1000)
            self.assertGreater(sum(x * x for x in pcm), 0)
        self.reject(lambda: self.store.allowed_media('/media/../seed.json'))
        self.reject(lambda: self.store.allowed_media('/media/unregistered.wav'))

    def test_python_AI_reads_actual_showcase_bytes_and_uses_only_returned_ASR(self):
        report = {'channel': 'mms', 'actor': '가상 QA', 'kind': 'initial', 'text': '가상 지하 여성 세 명, 두 명 구조 후 한 명 남음',
            'attachments': [{'id': str(n), 'url': '/media/' + name, 'media_type': 'audio' if name.endswith('.wav') else 'image',
                             'caption': 'NOT_ACTUAL', 'transcript': 'NOT_ACTUAL'} for n, name in enumerate(MEDIA[4:])]}
        transcripts = []; image_urls = []
        def api_mock(endpoint, payload, key, content_type='application/json'):
            if endpoint == 'audio/transcriptions':
                name = MEDIA[6 + len(transcripts)]
                self.assertIn((ROOT / 'data/media' / name).read_bytes(), payload)
                text = '  모의 실제 반환 ' + name + '\n'; transcripts.append({'attachment_id': str(2 + len(transcripts)), 'text': text, 'model': 'mock-asr'})
                return {'text': text}
            self.assertEqual(endpoint, 'responses'); dto = empty(ai.SCHEMA); dto['transcripts'] = copy.deepcopy(transcripts)
            body = json.loads(payload); content = body['input'][0]['content']; raw = json.loads(content[0]['text'])
            self.assertNotIn('NOT_ACTUAL', content[0]['text']); self.assertEqual(raw['transcripts'], transcripts)
            image_urls.extend(c['image_url'] for c in content if c['type'] == 'input_image')
            return {'status': 'completed', 'id': 'mock-image-audio-response', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(dto)}]}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'mock-key', 'OPENAI_MODEL': 'mock-model', 'OPENAI_TRANSCRIBE_MODEL': 'mock-asr'}), patch.object(ai, 'api', api_mock):
            result = ai.analyze_service({'synthetic': True, 'report': report, 'incidents': []})
        self.assertEqual(len(transcripts), 2); self.assertEqual(result['analysis']['transcripts'], transcripts)
        for url, name in zip(image_urls, MEDIA[4:6]): self.assertEqual(base64.b64decode(url.split(',')[1]), (ROOT / 'data/media' / name).read_bytes())

    def test_static_judge_explains_showcase_with_actual_media_without_JS(self):
        output = self.path / 'public'; build(output, 'cloud')
        html = (output / 'judge/index.html').read_text(); doc = Markup(html)
        self.assertFalse(any(tag == 'script' for tag, attrs in doc.elements))
        text = ''.join(doc.text)
        for value in (FEATURED, DUPLICATE, '여성 3명', '2명', '성인 여성', '부분 구조', '위치 후보', '대본은 실제 ASR 결과가 아닙니다', '향후 연계'):
            self.assertIn(value, text)
        for r in next(i for i in self.seed['incidents'] if i['id'] == FEATURED)['reports']:
            self.assertIn(r['text'], text); self.assertIn(r['received_at'], text); self.assertIn(r['occurred_at'], text)
        for name in MEDIA[4:]:
            tag = 'audio' if name.endswith('.wav') else 'img'
            self.assertTrue(any(t == tag and a.get('src') == '/media/' + name for t, a in doc.elements), name)
        self.assertTrue(all('controls' in a for t, a in doc.elements if t == 'audio'))
        refs = (output / 'references/index.html').read_text()
        for url in ('https://www.nist.gov/programs-projects/public-safety-audio-quality', 'https://arxiv.org/abs/1911.09296', 'https://www.nature.com/articles/s41467-025-68216-z'):
            self.assertIn(url, refs)
        self.assertIn('우리 서비스', refs)
        self.assertIn('실내 요구조자', refs)
        self.assertIn('실시간 3D 연계는 후속 개발', text)

    def test_three_pages_have_same_nine_native_menu_items(self):
        expected = ['dashboard', 'attention', 'active', 'field', 'results', 'resources', 'routes', 'settings', 'spatial']
        for page in ('index.html', 'spatial/index.html', 'routes/index.html'):
            html = (ROOT / 'web' / page).read_text(); doc = Markup(html)
            menu = [a for t, a in doc.elements if t == 'a' and 'data-nav' in a]
            self.assertEqual([a['data-nav'] for a in menu], expected)
            for a in menu:
                self.assertFalse(any(k.startswith('on') for k in a))
            if '/' in page:
                own = page.split('/')[0]; self.assertEqual([a['data-nav'] for a in menu if a.get('aria-current') == 'page'], [own])
                for a in menu:
                    name = a['data-nav']
                    self.assertEqual(a['href'], './' if name == own else '../' + name + '/' if name in ('routes', 'spatial') else '../#' + name)
            else:
                for a in menu:
                    self.assertEqual(a['href'], a['data-nav'] + '/' if a['data-nav'] in ('routes', 'spatial') else '#' + a['data-nav'])


if __name__ == '__main__': unittest.main()
