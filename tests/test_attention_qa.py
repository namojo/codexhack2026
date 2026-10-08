"""service-v4 타인 제작 attention 기능의 독립 QA. seed 자체제작과 구분."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from service.attention import derive_attention, attention_sort_key
from service.store import Store, ROOT

spec = importlib.util.spec_from_file_location('attention_http_qa', ROOT / 'scripts/serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


def stamp(minute):
    return f'2026-10-08T13:{minute:02}:00+09:00'


def report(n, text, count=3, kind='field', **extra):
    r = dict(id=f'QA-REP-{n}', channel='field' if kind=='field' else 'sms', kind=kind,
             actor='가상 QA 담당자', text=text, received_at=stamp(n), occurred_at=stamp(n), attachments=[])
    if count is not None:
        r['people_count']=count
    r.update(extra)
    return r


def incident(*reports, count=3, priority='normal', status='reviewing', assigned='TEAM-QA'):
    return dict(id='INC-QA-ATTENTION', title='가상 attention 검증', synthetic=True,
                location='가상동 QA주택 201호', people_count=count, priority=priority,
                status=status, assigned_team_id=assigned, reports=list(reports),
                audit=[], outcome_history=[], created_at=stamp(1), updated_at=stamp(9))


def suffixes(items):
    return {v['id'].rsplit(':',1)[-1] for v in items}


class AttentionRuleQA(unittest.TestCase):
    def test_closed_excluded_even_with_urgent_and_residual(self):
        i=incident(report(1,'세 명 중 한 명은 남아 있습니다.',2),status='closed',priority='urgent',assigned=None)
        self.assertEqual(derive_attention(i),[])

    def test_partial_report_is_immediate_and_unknown_not_asserted_dead(self):
        task=derive_attention(incident(report(1,'현장 두 명만 구조했고 한 명은 미확인입니다.',2)))[0]
        self.assertEqual(task['level'],'immediate')
        self.assertIn('1명의 상태가 미확인',task['reason'])
        self.assertNotIn('사망',task['reason'])
        self.assertEqual(task['action'],'field-report')

    def test_equal_count_residual_statement_is_not_cleared(self):
        for text in ('세 명 중 두 명만 구조했습니다. 한 명은 남아 있습니다.',
                     '보고는 세 명이며 대상 한 명은 아직 남았습니다.',
                     '사람 두 명만 확인했고 다른 대상은 확인하지 못했습니다.'):
            with self.subTest(text=text):
                tasks=derive_attention(incident(report(1,text,3)))
                self.assertIn('people',suffixes(tasks))
                self.assertEqual(tasks[0]['level'],'immediate')

    def test_equal_count_negative_safety_requires_decision(self):
        tasks=derive_attention(incident(report(1,'세 명의 안전은 확인하지 못했습니다.',3)))
        self.assertIn('people',suffixes(tasks))
        self.assertEqual(tasks[0]['level'],'decision')

    def test_latest_full_confirmation_clears_old_partial_without_sum(self):
        i=incident(report(1,'두 명만 구조했고 한 명은 남아 있습니다.',2),
                   report(2,'세 명 전원 구조 확인. 남은 대상은 없습니다.',3))
        self.assertNotIn('people',suffixes(derive_attention(i)))
        i['reports'][-1]=report(2,'한 명만 구조 확인했습니다.',1)
        self.assertIn('people',suffixes(derive_attention(i)))

    def test_explicit_count_correction_clears_older_partial(self):
        i=incident(report(1,'세 명 중 두 명만 구조했습니다.',2),
                   report(2,'접수 인원을 두 명으로 명시 정정합니다.',2,'correction'),count=2)
        self.assertNotIn('people',suffixes(derive_attention(i)))

    def test_additional_count_conflict_preserves_official_count(self):
        i=incident(report(1,'접수 세 명입니다.',3,'additional'),
                   report(2,'전체 대상은 네 명입니다.',4,'additional'))
        before=deepcopy(i);tasks=derive_attention(i)
        self.assertIn('people',suffixes(tasks));self.assertEqual(i,before)
        self.assertEqual(i['people_count'],3)
        self.assertIn('자동 반영하지 않았',tasks[0]['reason'])
        i['reports'].append(report(3,'전체 인원을 네 명으로 정정합니다.',4,'correction'));i['people_count']=4
        self.assertNotIn('people',suffixes(derive_attention(i)))

    def test_unknown_count_has_real_evidence_and_human_task(self):
        tasks=derive_attention(incident(report(1,'사람이 있지만 몇 명인지 모릅니다.',None,'additional'),count=None))
        self.assertIn('people',suffixes(tasks))
        self.assertTrue(tasks[0]['requires_human'])
        self.assertEqual(tasks[0]['evidence'][0]['report_id'],'QA-REP-1')

    def test_reopen_excludes_old_fields_by_id(self):
        i=incident(report(1,'세 명 전원 직접 구조 확인했습니다.',3))
        i['outcome_history']=[{'reopened_at':stamp(2),'report_ids_at_reopen':['QA-REP-1']}]
        self.assertIn('reopened',suffixes(derive_attention(i)))
        i['reports'].append(report(3,'현장에서 세 명 전원을 직접 확인했습니다.',3))
        self.assertNotIn('reopened',suffixes(derive_attention(i)))

    def test_legacy_same_time_field_excluded_correction_cause_included(self):
        i=incident(report(1,'두 명 전원 현장 확인했습니다.',2),
                   report(2,'인원을 세 명으로 정정합니다. 한 명은 201호에 남아 있습니다.',3,'correction'),count=3)
        i['outcome_history']=[{'reopened_at':stamp(2)}]
        i['audit']=[{'created_at':stamp(2),'before':{'people_count':2},'after':{'people_count':3}}]
        tasks=derive_attention(i)
        self.assertEqual(tasks[0]['level'],'immediate');self.assertIn('people',suffixes(tasks))
        self.assertIn('QA-REP-2',{e['report_id'] for t in tasks for e in t['evidence']})
        # 같은 시각의 field는 재개 이후 확인으로 취급하지 않는다.
        i['reports'].append(report(3,'現場で三名全員を確認しました。',3,received_at=stamp(2)))
        self.assertIn('people',suffixes(derive_attention(i)))

    def test_contact_negative_confirmation_does_not_resolve(self):
        for text in ('현장에서 연락을 확인하지 못했습니다.',
                     '현장에서 세 명의 안전 확인 불가입니다.',
                     '현장에서 세 명의 응답이 없고 안전을 확인하지 못했습니다.'):
            with self.subTest(text=text):
                i=incident(report(1,'연락 두절. 응답 없음.',3,'additional'),report(2,text,3))
                tasks=derive_attention(i)
                self.assertTrue('contact' in suffixes(tasks) or any('연락' in t['reason'] for t in tasks),tasks)

    def test_contact_latest_direct_full_confirmation_resolves(self):
        i=incident(report(1,'연락 두절. 응답 없음.',3,'additional'),
                   report(2,'현장에서 대상 세 명과 직접 통화하여 전원 안전을 확인했습니다.',3))
        self.assertNotIn('contact',suffixes(derive_attention(i)))
        self.assertFalse(any('연락 두절 신고' in t['reason'] for t in derive_attention(i)))

    def test_location_explicit_correction_clears_old_proxy(self):
        i=incident(report(1,'대리 신고입니다. 제 휴대폰 위치는 어머니 집이 아니에요.',1,'additional'),count=1)
        self.assertIn('location',suffixes(derive_attention(i)))
        i['reports'].append(report(2,'구조 대상 위치는 가상동 302호로 확인하여 정정합니다.',1,'correction',location='가상동 302호'))
        self.assertNotIn('location',suffixes(derive_attention(i)))

    def test_location_patch_audit_clears_old_proxy(self):
        i=incident(report(1,'신고자 위치 GPS를 보냈습니다.',3,'additional'))
        i['audit']=[{'created_at':stamp(2),'before':{'location':'가상동 201호'},'after':{'location':'가상동 301호'}}]
        self.assertNotIn('location',suffixes(derive_attention(i)))

    def test_assignment_severity_and_assignment_resolves_only_that_cause(self):
        for priority,level in (('urgent','immediate'),('high','decision'),('normal','follow_up')):
            with self.subTest(priority=priority):
                i=incident(report(1,'접수 원문 세 명 고립',3,'additional'),priority=priority,assigned=None)
                self.assertEqual(derive_attention(i)[0]['level'],level)
                i['assigned_team_id']='TEAM-QA';self.assertNotIn('assignment',suffixes(derive_attention(i)))

    def test_concrete_risk_precedes_generic_assignment_and_same_cause_grouped(self):
        i=incident(report(1,'세 명 중 두 명만 구조했고 한 명은 남아 있습니다. 연락 두절입니다.',2),priority='urgent',assigned=None)
        tasks=derive_attention(i)
        self.assertEqual(tasks[0]['id'].rsplit(':',1)[-1],'people')
        self.assertEqual(sum(t['id'].endswith(':people') for t in tasks),1)
        self.assertNotIn('contact',suffixes(tasks))
        self.assertIn('연락',tasks[0]['reason'])

    def test_evidence_schema_substring_and_priority_input_immutable(self):
        i=incident(report(1,'연락 두절. 제 휴대폰 위치는 어머니 집이 아닙니다.',3,'additional'),priority='high',assigned=None)
        before=deepcopy(i);tasks=derive_attention(i);self.assertEqual(i,before)
        required={'id','level','title','situation','reason','next_action','action','source','requires_human','evidence'}
        rm={r['id']:r for r in i['reports']}
        for t in tasks:
            self.assertEqual(set(t),required);self.assertEqual(t['source'],'rule');self.assertIs(t['requires_human'],True)
            self.assertIn(t['action'],{'progress','field-report','report','edit'})
            for e in t['evidence']:
                self.assertEqual(set(e),{'report_id','quote','received_at'})
                self.assertTrue(e['quote']);self.assertIn(e['quote'],rm[e['report_id']]['text'])
                self.assertEqual(e['received_at'],rm[e['report_id']]['received_at'])

    def test_absent_text_does_not_fabricate_evidence(self):
        tasks=derive_attention(incident(count=None,assigned=None))
        self.assertTrue(tasks);self.assertTrue(all(t['evidence']==[] for t in tasks))

    def test_sort_level_then_priority_then_received_time_and_id(self):
        items=[]
        for name,level,priority,minute in [('B','decision','urgent',1),('C','immediate','normal',1),('D','immediate','high',3),('E','immediate','high',2),('A','immediate','high',2)]:
            i=incident(priority=priority);i.update(id=name,created_at=stamp(minute),attention=[{'level':level}]);items.append(i)
        self.assertEqual([i['id'] for i in sorted(items,key=attention_sort_key)],['A','E','D','C','B'])


class AttentionStoreQA(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'attention.sqlite3';self.store=Store(self.db)

    def tearDown(self):self.tmp.cleanup()

    def create(self):
        return self.store.create_incident({'title':'가상 QA 조치 사건','location':'가상동 QA빌라','text':'세 명입니다. 연락 두절입니다.','people_count':3,'priority':'urgent'})

    def add(self,i,text,count=3,kind='field',**extra):
        return self.store.add_report(i['id'],dict(expected_revision=i['revision'],channel='field' if kind=='field' else 'sms',kind=kind,text=text,people_count=count,**extra))

    def payload(self):
        with sqlite3.connect(self.db) as db:return db.execute('SELECT id,payload FROM incidents ORDER BY id').fetchall()

    def test_reads_pure_and_attention_never_stored_even_after_mutation(self):
        i=self.create();before=self.payload()
        for _ in range(2):self.store.list_incidents();self.store.get_incident(i['id'])
        self.assertEqual(self.payload(),before)
        self.assertTrue(i['attention']);self.assertEqual(i['priority'],'urgent')
        i=self.add(i,'현장에서 두 명을 확인했고 한 명은 남아 있습니다.',2)
        self.assertEqual(i['priority'],'urgent')
        self.assertTrue(all('attention' not in json.loads(payload) for _,payload in self.payload()))

    def test_closed_then_new_info_reopens_and_generates_current_tasks(self):
        i=self.add(self.create(),'현장에서 세 명 전원 안전을 직접 확인했습니다.')
        i=self.store.confirm_outcome(i['id'],{'expected_revision':i['revision'],'outcome':'rescued','confirmed_count':3,'basis_report_id':i['reports'][-1]['id'],'note':'전원 대조 확인'})
        self.assertEqual(i['attention'],[])
        i=self.add(i,'실제 네 명이며 한 명은 아직 남아 있습니다.',4,'additional')
        self.assertEqual(i['status'],'reviewing');self.assertIsNone(i['outcome']);self.assertEqual(i['people_count'],3)
        self.assertTrue(any(t['id'].endswith(':people') for t in i['attention']))
        self.assertEqual(len(i['outcome_history']),1)

    def test_store_location_patch_and_latest_contact_clear_tasks(self):
        i=self.add(self.create(),'제 휴대폰 위치는 구조 대상 집이 아닙니다.',3,'additional')
        self.assertIn('location',suffixes(i['attention']))
        i=self.store.update_incident(i['id'],{'expected_revision':i['revision'],'location':'가상동 대상 302호','reason':'당사자 주소 확인'})
        self.assertNotIn('location',suffixes(i['attention']))
        i=self.add(i,'현장에서 대상 세 명과 직접 통화하여 전원 안전을 확인했습니다.')
        self.assertNotIn('contact',suffixes(i['attention']))

    def test_legacy_reopen_same_time_correction_in_compat_seed_is_current_risk(self):
        # 과거 작성한 seed의 정확성을 독립평가하지 않고 현재 backend 호환 규칙을 확인한다.
        i=self.store.get_incident('INC-20261008-010')
        tasks=i['attention'];self.assertTrue(any(t['id'].endswith(':people') and t['level']=='immediate' for t in tasks))
        cited={e['report_id'] for t in tasks for e in t['evidence']}
        self.assertIn('REP-010-03',cited);self.assertNotIn('REP-010-02',cited)

    def test_newly_assigned_team_clears_assignment_but_keeps_concrete_risk(self):
        i=self.add(self.create(),'현장 두 명만 확인했고 한 명은 남아 있습니다.',2)
        i=self.store.add_progress(i['id'],{'expected_revision':i['revision'],'status':'dispatched','team_id':'TEAM-04','note':'담당자가 직접 배정 판단'})
        self.assertNotIn('assignment',suffixes(i['attention']));self.assertIn('people',suffixes(i['attention']))
        self.assertEqual(i['priority'],'urgent')


class DevToolsHTTPQA(unittest.TestCase):
    def check_routes(self,enabled,expected):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'http.sqlite3')
            server=ThreadingHTTPServer(('127.0.0.1',0),serve.make_service_handler(store,{'synthetic':True,'results':[]},dev_tools=enabled))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                for method in ('GET','HEAD'):
                    for route in ('/replay','/replay/','/replay/app.js','/replay/index.html','/api/bundle'):
                        with self.subTest(enabled=enabled,method=method,route=route):
                            try:r=urlopen(Request(f'http://127.0.0.1:{server.server_port}'+route,method=method),timeout=3)
                            except HTTPError as e:r=e
                            with r:self.assertEqual(r.status,expected)
                with urlopen(f'http://127.0.0.1:{server.server_port}/api/incidents') as r:
                    data=json.load(r);self.assertTrue(all('attention' in i for i in data['incidents']))
                with urlopen(f'http://127.0.0.1:{server.server_port}/') as r:
                    html=r.read().decode();self.assertIn('지금 판단',html);self.assertNotIn('/replay/',html)
            finally:server.shutdown();server.server_close();thread.join()

    def test_default_dev_routes_blocked(self):self.check_routes(False,404)
    def test_explicit_opt_in_dev_routes_visible(self):self.check_routes(True,200)


if __name__=='__main__':unittest.main()
