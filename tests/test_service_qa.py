"""Operator workflow and API boundary checks authored outside the product workers."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer

from service.store import Store, APIError, ROOT

spec = importlib.util.spec_from_file_location('service_http_qa', ROOT / 'scripts' / 'serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class ServiceWorkflowQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'operator.sqlite3'
        self.store = Store(self.db)
        self.uploads = []

    def tearDown(self):
        for p in self.uploads:
            p.unlink(missing_ok=True)
        self.tmp.cleanup()

    def create(self, count=3):
        return self.store.create_incident({'title':'가상동 독립 검증 사건', 'location':'가상동 QA빌라 201호', 'text':'물 때문에 세 명이 고립됐어요.', 'people_count':count, 'channel':'sms'})

    def report(self, incident, n, kind='field'):
        return self.store.add_report(incident['id'], {'expected_revision':incident['revision'], 'channel':'field' if kind=='field' else 'sms', 'kind':kind, 'actor':'가상 현장대원', 'text':f'현재 확인 인원 {n}명. 현장 확인 기록.', 'people_count':n})

    def close(self, incident, basis=None, n=None):
        return self.store.confirm_outcome(incident['id'], {'expected_revision':incident['revision'], 'outcome':'rescued', 'confirmed_count':incident['people_count'] if n is None else n, 'basis_report_id':basis or incident['reports'][-1]['id'], 'actor':'검증 담당자', 'note':'대상과 전원 인원 대조 확인'})

    def denied(self, status, operation):
        with self.assertRaises(APIError) as ctx:
            operation()
        self.assertEqual(ctx.exception.status, status)

    def test_seed_has_all_work_states_and_local_evidence(self):
        data=self.store.list_incidents()
        self.assertEqual(len(data['incidents']),10)
        self.assertEqual({i['status'] for i in data['incidents']},{'received','dispatched','on_scene','rescuing','reviewing','closed'})
        self.assertEqual(len(data['resources']),4)
        refs=[]
        for i in data['incidents']:
            self.assertTrue(i['synthetic'])
            ids={r['id'] for r in i['reports']}
            for c in i['checks']:self.assertTrue(set(c['report_ids']) <= ids)
            if i['outcome']: self.assertIn(i['outcome']['basis_report_id'],ids)
            for r in i['reports']:
                for a in r['attachments']:
                    p=self.store.allowed_media(a['url']); self.assertGreater(p.stat().st_size,1000);refs.append(a['url'])
                    if a['media_type']=='audio':
                        self.assertEqual(a['transcript'],r['text'])
                        with wave.open(str(p)) as w: self.assertGreater(w.getnframes()/w.getframerate(),5)
        self.assertEqual(len(set(refs)),4)

    def test_additional_report_does_not_overwrite_original_or_implicitly_correct_count(self):
        i=self.create(); original=copy.deepcopy(i['reports'][0]); i=self.report(i,2,'additional')
        self.assertEqual(i['people_count'],3)
        self.assertEqual(i['reports'][0],original)
        self.assertEqual(i['revision'],2)
        self.assertEqual(len(i['audit']),2)

    def test_count_correction_and_location_edit_preserve_audit(self):
        i=self.create(); original=copy.deepcopy(i['reports'][0]);i=self.report(i,4,'correction')
        self.assertEqual(i['people_count'],4)
        i=self.store.update_incident(i['id'],{'expected_revision':i['revision'],'location':'가상동 QA빌라 옥상','reason':'신고자 추가 확인'})
        self.assertEqual(i['reports'][0],original)
        self.assertEqual(i['audit'][-1]['before']['location'],'가상동 QA빌라 201호')
        self.assertEqual(i['audit'][-1]['after']['location'],'가상동 QA빌라 옥상')

    def test_stale_revision_and_blank_reason_are_atomic(self):
        i=self.create();i=self.report(i,3,'additional'); before=copy.deepcopy(i)
        self.denied(409,lambda:self.store.update_incident(i['id'],{'expected_revision':1,'priority':'urgent','reason':'지난 화면'}))
        self.denied(400,lambda:self.store.update_incident(i['id'],{'expected_revision':i['revision'],'location':'가상동 다른곳','reason':' '}))
        self.assertEqual(self.store.get_incident(i['id']),before)

    def test_partial_report_and_sum_of_partial_reports_cannot_close(self):
        i=self.create();i=self.report(i,2);i=self.report(i,1)
        for n in (1,2,3):self.denied(400,lambda n=n:self.close(i,n=n))
        self.assertNotEqual(self.store.get_incident(i['id'])['status'],'closed')

    def test_basis_cannot_come_from_other_incident_or_initial_report(self):
        i=self.report(self.create(),3); other=self.report(self.create(),3)
        self.denied(400,lambda:self.close(i,other['reports'][-1]['id']))
        self.denied(400,lambda:self.close(i,i['reports'][0]['id']))

    def test_dispatched_team_is_released_only_after_valid_result(self):
        i=self.create(); i=self.store.add_progress(i['id'],{'expected_revision':i['revision'],'status':'dispatched','team_id':'TEAM-04','note':'현장 출동 확인'})
        self.assertEqual(i['status'],'dispatched')
        i=self.report(i,2);self.denied(400,lambda:self.close(i))
        self.assertEqual(next(r for r in self.store.list_incidents()['resources'] if r['id']=='TEAM-04')['status'],'assigned')
        i=self.report(i,3);i=self.close(i)
        self.assertEqual(i['status'],'closed');self.assertIsNone(i['assigned_team_id'])
        self.assertEqual(next(r for r in self.store.list_incidents()['resources'] if r['id']=='TEAM-04')['status'],'available')
        self.assertTrue(all(c['level']=='info' for c in i['checks']))

    def test_team_assignment_race_has_one_winner(self):
        incidents=[self.create(),self.create()]
        def assign(i):
            try:return self.store.add_progress(i['id'],{'expected_revision':1,'status':'dispatched','team_id':'TEAM-04','note':'동시 배정 검사'})['id']
            except APIError as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(assign,incidents))
        self.assertEqual(results.count(409),1)
        assigned=[i for i in self.store.list_incidents()['incidents'] if i['assigned_team_id']=='TEAM-04']
        self.assertEqual(len(assigned),1)

    def test_new_information_reopens_closed_incident_and_preserves_result(self):
        i=self.close(self.report(self.create(),3));old=copy.deepcopy(i['outcome']); i=self.report(i,4,'additional')
        self.assertEqual(i['status'],'reviewing');self.assertIsNone(i['outcome'])
        self.assertEqual(i['outcome_history'][-1]['basis_report_id'],old['basis_report_id'])
        self.assertTrue(i['outcome_history'][-1]['reopen_reason'])

    def test_reopen_requires_fresh_field_report_and_keeps_both_outcomes(self):
        i=self.close(self.report(self.create(),3));old=i['outcome']['basis_report_id']
        i=self.store.reopen(i['id'],{'expected_revision':i['revision'],'reason':'인계 결과 대신 전원 구조로 정정'})
        self.denied(400,lambda:self.close(i,basis=old))
        i=self.close(self.report(i,3))
        self.assertEqual(i['status'],'closed');self.assertEqual(len(i['outcome_history']),1)
        self.assertNotEqual(i['outcome']['basis_report_id'],old)

    def test_closed_progress_rejected_and_important_edit_reopens(self):
        i=self.close(self.report(self.create(),3))
        self.denied(409,lambda:self.store.add_progress(i['id'],{'expected_revision':i['revision'],'status':'reviewing','note':'과거 상태 직접변경'}))
        i=self.store.update_incident(i['id'],{'expected_revision':i['revision'],'location':'가상동 QA빌라 옥상','reason':'완료 후 새 위치 확인'})
        self.assertEqual(i['status'],'reviewing');self.assertEqual(len(i['outcome_history']),1)

    def test_unknown_count_and_invalid_counts_never_confirm(self):
        i=self.create(count=0);i=self.report(i,0)
        self.denied(400,lambda:self.close(i,n=True))
        for value in (True,-1,1.5,'3'):
            self.denied(400,lambda value=value:self.store.create_incident({'title':'가상 QA','location':'가상동','text':'신고','people_count':value}))
        i=self.store.create_incident({'title':'가상 미확인인원','location':'가상동','text':'사람이 있어요'})
        i=self.report(i,1)
        self.denied(400,lambda:self.close(i,n=1))

    def test_conflicting_additional_count_needs_explicit_correction(self):
        i=self.create();i=self.report(i,4,'additional');i=self.report(i,3)
        self.denied(400,lambda:self.close(i))
        i=self.report(i,3,'correction');i=self.report(i,3);self.assertEqual(self.close(i)['status'],'closed')

    def test_restart_preserves_changes_and_does_not_reload_seed(self):
        i=self.close(self.report(self.create(),3));before=self.store.list_incidents()
        other=Store(self.db, seed_path=Path(self.tmp.name)/'absent-seed.json')
        self.assertEqual(other.list_incidents(),before)
        self.assertEqual(other.get_incident(i['id'])['status'],'closed')

    def test_upload_header_size_path_and_real_audio(self):
        body={'filename':'신고-합성.wav','content_type':'audio/wav','data_base64':base64.b64encode((ROOT/'data/media/call-isolated.wav').read_bytes()).decode()}
        a=self.store.upload(body);p=self.store.allowed_media(a['url']);self.uploads.append(p)
        self.assertEqual(a['source'],'operator_upload');self.assertEqual(p.read_bytes(),(ROOT/'data/media/call-isolated.wav').read_bytes())
        for bad in ({**body,'filename':'../x.wav'},{**body,'data_base64':'!bad!'},{**body,'data_base64':base64.b64encode(b'fake audio').decode()},{**body,'content_type':'text/html'}):
            self.denied(400,lambda bad=bad:self.store.upload(bad))
        self.denied(413,lambda:self.store.upload({**body,'data_base64':'A'*(12*1024*1024)}))
        for url in ('/media/../seed.json','/media/%2e%2e/seed.json','/media/call-isolated.wav?x=1','/etc/passwd'):
            self.denied(400,lambda url=url:self.store.media_path(url))


class ServiceHTTPQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.tmp.name)/'http.sqlite3')
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),serve.make_service_handler(cls.store,{'synthetic':True,'mode':'fixture','results':[{'scenario_id':'stub'}]}))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup()

    def request(self,route,method='GET',body=None,headers=None,raw=None):
        headers=dict(headers or {})
        if body is not None:headers['Content-Type']='application/json';raw=json.dumps(body,ensure_ascii=False).encode()
        req=urllib.request.Request(self.base+route,data=raw,headers=headers,method=method)
        try:r=urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,dict(r.headers),r.read()

    def test_real_http_full_operator_flow(self):
        status,_,data=self.request('/api/incidents','POST',{'title':'가상 HTTP 검증','location':'가상동 QA 옥상','text':'둘이 고립','people_count':2})
        self.assertEqual(status,201);i=json.loads(data)
        status,_,data=self.request('/api/incidents/'+i['id']+'/reports','POST',{'expected_revision':i['revision'],'channel':'field','kind':'field','text':'전원 두 명 확인','people_count':2})
        self.assertEqual(status,200);i=json.loads(data)
        status,_,data=self.request('/api/incidents/'+i['id']+'/outcome','POST',{'expected_revision':i['revision'],'outcome':'rescued','confirmed_count':2,'basis_report_id':i['reports'][-1]['id'],'note':'전원 구조 확인'})
        self.assertEqual(status,200);i=json.loads(data);self.assertEqual(i['status'],'closed')
        status,_,data=self.request('/api/incidents/'+i['id']+'/reopen','POST',{'expected_revision':i['revision'],'reason':'결과 재확인 요청'})
        self.assertEqual(status,200);self.assertEqual(json.loads(data)['status'],'reviewing')
        status,_,data=self.request('/api/incidents/'+i['id']);self.assertEqual(len(json.loads(data)['outcome_history']),1)

    def test_media_range_headers_and_route_allowlist(self):
        status,h,data=self.request('/media/call-isolated.wav',headers={'Range':'bytes=0-63'})
        self.assertEqual(status,206);self.assertEqual(len(data),64);self.assertEqual(data[:4],b'RIFF');self.assertEqual(h['Content-Type'],'audio/wav')
        self.assertIn('Content-Range',h)
        self.assertEqual(self.request('/media/call-isolated.wav',headers={'Range':'bytes=99999999-'})[0],416)
        self.assertEqual(self.request('/data/seed.json')[0],404)
        self.assertEqual(self.request('/service/store.py')[0],404)
        self.assertEqual(self.request('/replay/app.js')[0],404)
        status,h,data=self.request('/');self.assertEqual(status,200);self.assertIn('Content-Security-Policy',h)
        self.assertIn('신고·구조 상황관리'.encode(),data)

    def test_malformed_json_foreign_origin_and_duplicate_fields_rejected(self):
        self.assertEqual(self.request('/api/incidents','POST',raw=b'{bad}',headers={'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.request('/api/incidents','POST',raw=b'{}',headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/api/incidents','POST',body={'title':'x'},headers={'Origin':'https://foreign.invalid'})[0],403)
        self.assertEqual(self.request('/api/incidents','POST',raw=b'{"title":"a","title":"b"}',headers={'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.request('/api/incidents','POST',raw=b'{"people_count":NaN}',headers={'Content-Type':'application/json'})[0],400)


if __name__=='__main__':unittest.main()
