"""제작자가 실행하는 attention 경계 자체검증. 독립 QA와 구분한다."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from service.attention import derive_attention, attention_sort_key
from service.store import Store

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import serve


def report(rid, minute, text, kind="field", count=None, **fields):
    value = {"id": rid, "kind": kind, "text": text, "received_at": f"2026-10-08T10:{minute:02}:00+09:00", **fields}
    if count is not None:
        value["people_count"] = count
    return value


def incident():
    return {"id": "SYN-001", "status": "received", "people_count": 3, "priority": "high", "assigned_team_id": "TEAM-01",
            "created_at": "2026-10-08T10:00:00+09:00", "updated_at": "2026-10-08T10:00:00+09:00", "audit": [], "outcome_history": [],
            "reports": [report("R1", 0, "가상집 세 명 고립 신고입니다.", "initial", 3)]}


def kinds(value):
    return {item["id"].rsplit(":", 1)[-1]: item for item in derive_attention(value)}


class AttentionSmoke(unittest.TestCase):
    def test_closed_empty(self):
        value = incident()
        value.update(status="closed", assigned_team_id=None, people_count=None)
        self.assertEqual(derive_attention(value), [])

    def test_partial_count_and_full_resolution(self):
        value = incident()
        value["reports"].append(report("R2", 1, "현장에서 대상 두 명을 확인했습니다.", count=2))
        task = kinds(value)["people"]
        self.assertEqual(task["level"], "immediate")
        self.assertIn("1명의 상태가 미확인", task["reason"])
        value["reports"].append(report("R3", 2, "현장에서 대상 세 명 모두 안전 확인.", count=3))
        self.assertEqual(derive_attention(value), [])

    def test_no_sum_and_explicit_count_correction(self):
        value = incident()
        value["reports"] += [report("R2", 1, "두 명 현장 확인", count=2), report("R3", 2, "한 명 현장 확인", count=1)]
        self.assertEqual(kinds(value)["people"]["level"], "immediate")
        value["people_count"] = 1
        value["reports"].append(report("R4", 3, "확인 대상은 한 명으로 인원 정정", "correction", 1))
        self.assertNotIn("people", kinds(value))

    def test_metadata_matching_partial_words_remain(self):
        value = incident()
        value["reports"].append(report("R2", 1, "세 명 중 두 명만 구조했습니다.", count=3))
        self.assertEqual(kinds(value)["people"]["level"], "immediate")

    def test_clear_no_residual_words_resolve(self):
        for text in ["세 명 모두 구조했습니다. 미구조 인원 없음.", "세 명 모두 안전 확인. 남아 있는 사람은 없습니다.",
                     "대상 세 명 모두 대피했습니다. 남은 대상은 없습니다."]:
            with self.subTest(text=text):
                value = incident()
                value["reports"] += [report("R2", 1, "한 명이 남아 있습니다.", count=2), report("R3", 2, text, count=3)]
                self.assertNotIn("people", kinds(value))

    def test_unconfirmed_negative_never_resolves(self):
        value = incident()
        value["reports"].append(report("R2", 1, "현장에서 세 명의 안전을 확인하지 못했습니다.", count=3))
        self.assertIn("people", kinds(value))

    def test_contact_field_resolution_and_negative(self):
        value = incident()
        value["reports"].append(report("R2", 1, "연락 두절이며 응답 없음", "additional"))
        self.assertEqual(kinds(value)["contact"]["level"], "decision")
        value["reports"].append(report("R3", 2, "현장에서 안전을 확인하지 못했습니다.", count=3))
        self.assertTrue(any("연락" in item["reason"] or "연락" in item["title"] for item in derive_attention(value)))
        value["reports"].append(report("R4", 3, "현장에서 대상 세 명 모두 안전을 직접 확인했습니다.", count=3))
        self.assertNotIn("contact", kinds(value))
        self.assertNotIn("people", kinds(value))

    def test_proxy_and_explicit_location_correction(self):
        value = incident()
        value["reports"].append(report("R2", 1, "제 휴대폰 위치는 어머니 집이 아니에요. 대신 신고합니다.", "additional"))
        self.assertIn("location", kinds(value))
        value["reports"].append(report("R3", 2, "어머니 집 주소를 확인했습니다.", "correction", location="가상동 301호"))
        self.assertNotIn("location", kinds(value))

    def test_proxy_location_patch_resolves(self):
        value = incident()
        value["reports"].append(report("R2", 1, "대리 신고자의 GPS입니다.", "additional"))
        value["audit"].append({"created_at": "2026-10-08T10:02:00+09:00", "before": {"location": "GPS 위치"}, "after": {"location": "가상 대상 주소"}})
        self.assertNotIn("location", kinds(value))

    def test_additional_count_is_proposed_not_applied(self):
        value = incident()
        value["reports"].append(report("R2", 1, "한 명이 더 있어 전체 네 명입니다.", "additional", 4))
        before = deepcopy(value)
        self.assertIn("people", kinds(value))
        self.assertEqual(value, before)
        self.assertEqual(value["people_count"], 3)

    def test_reopen_cutoff_and_trigger_same_timestamp(self):
        value = incident()
        value["reports"] += [report("R2", 1, "대상 세 명 전원 안전 확인", count=3),
                             report("R3", 2, "정정합니다. 한 명이 301호에 남아 있습니다.", "correction", 4)]
        value["people_count"] = 4
        value["outcome_history"] = [{"reopened_at": "2026-10-08T10:02:00+09:00"}]
        self.assertEqual(kinds(value)["people"]["level"], "immediate")
        self.assertEqual(kinds(value)["people"]["evidence"][0]["report_id"], "R3")
        value["reports"].append(report("R4", 3, "대상 네 명 모두 안전 확인", count=4))
        self.assertNotIn("people", kinds(value))
        self.assertNotIn("reopened", kinds(value))

    def test_reopen_ids_need_fresh_field(self):
        value = incident()
        value["reports"].append(report("R2", 1, "현장 세 명 모두 안전 확인", count=3))
        value["outcome_history"] = [{"report_ids_at_reopen": ["R1", "R2"]}]
        self.assertIn("reopened", kinds(value))
        value["reports"].append(report("R3", 2, "현장 세 명 모두 안전 확인", count=3))
        self.assertNotIn("reopened", kinds(value))

    def test_unknown_count_and_assignment_priority(self):
        value = incident()
        value["people_count"] = None
        self.assertIn("people", kinds(value))
        for priority, level in [("urgent", "immediate"), ("high", "decision"), ("normal", "follow_up")]:
            with self.subTest(priority=priority):
                value.update(priority=priority, assigned_team_id=None)
                self.assertEqual(kinds(value)["assignment"]["level"], level)
                self.assertEqual(value["priority"], priority)
        value["assigned_team_id"] = "TEAM-01"
        self.assertNotIn("assignment", kinds(value))

    def test_grouping_and_concrete_task_before_assignment(self):
        value = incident()
        value["assigned_team_id"] = None
        value["reports"] += [report("R2", 1, "연락 두절", "additional"), report("R3", 2, "대리 신고자의 GPS", "additional")]
        tasks = derive_attention(value)
        self.assertEqual([item["id"].rsplit(":", 1)[-1] for item in tasks], ["contact", "location", "assignment"])
        value["reports"].append(report("R4", 3, "현장 두 명 확인", count=2))
        tasks = derive_attention(value)
        self.assertEqual(sum(item["id"].endswith(":people") for item in tasks), 1)
        self.assertEqual(sum(item["id"].endswith(":contact") for item in tasks), 0)

    def test_schema_evidence_and_sort(self):
        value = incident()
        value["reports"].append(report("R2", 1, "응답 없음", "additional"))
        before = deepcopy(value)
        for item in derive_attention(value):
            self.assertEqual(set(item), {"id", "level", "title", "situation", "reason", "next_action", "action", "source", "requires_human", "evidence"})
            self.assertEqual(item["source"], "rule")
            self.assertIs(item["requires_human"], True)
            for evidence in item["evidence"]:
                original = next(r for r in value["reports"] if r["id"] == evidence["report_id"])
                self.assertIn(evidence["quote"], original["text"])
                self.assertEqual(evidence["received_at"], original["received_at"])
        self.assertEqual(value, before)
        value["attention"] = derive_attention(value)
        urgent = deepcopy(value)
        urgent["priority"] = "urgent"
        self.assertLess(attention_sort_key(urgent), attention_sort_key(value))

    def test_seed_current_residual_and_legacy_db_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "test.sqlite3")
            with sqlite3.connect(store.db_path) as db:
                before = list(db.execute("SELECT id,payload FROM incidents ORDER BY id"))
            original = store.get_incident("INC-20261008-010")
            self.assertEqual(kinds(original)["people"]["level"], "immediate")
            self.assertEqual(kinds(original)["people"]["evidence"][0]["report_id"], "REP-010-03")
            store.list_incidents()
            store.get_incident(original["id"])
            with sqlite3.connect(store.db_path) as db:
                after = list(db.execute("SELECT id,payload FROM incidents ORDER BY id"))
            self.assertEqual(before, after)
            self.assertTrue(all("attention" not in json.loads(payload) for _, payload in after))
            changed = store.update_incident(original["id"], {"expected_revision": original["revision"], "title": "합성 제목 변경", "reason": "합성 변경"})
            self.assertIn("attention", changed)
            with sqlite3.connect(store.db_path) as db:
                payload = db.execute("SELECT payload FROM incidents WHERE id=?", (original["id"],)).fetchone()[0]
            self.assertNotIn("attention", json.loads(payload))

    def test_resolved_old_checks_display_history(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "test.sqlite3")
            contact = store.get_incident("INC-20261008-006")
            resolved = store.add_report(contact["id"], {"expected_revision": contact["revision"], "kind": "field", "channel": "field", "people_count": 2, "text": "현장에서 대상 두 명 모두 안전을 직접 확인했습니다."})
            self.assertFalse(any("연락" in a["title"] for a in resolved["attention"]))
            contact_checks = [c for c in resolved["checks"] if "연락" in c["title"]]
            self.assertTrue(contact_checks)
            self.assertTrue(all(c["level"] == "info" for c in contact_checks))
            proxy = store.get_incident("INC-20261008-005")
            resolved = store.add_report(proxy["id"], {"expected_revision": proxy["revision"], "kind": "correction", "channel": "sms", "location": "가상동 대상 302호", "text": "대상 주소를 명시 정정합니다."})
            self.assertFalse(any(a["id"].endswith(":location") for a in resolved["attention"]))
            self.assertTrue(all(c["level"] == "info" for c in resolved["checks"] if "위치" in c["title"] or "GPS" in c["title"]))

    def test_default_tools_block_and_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "test.sqlite3")
            for enabled in (False, True):
                server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_service_handler(store, {"synthetic": True, "results": []}, dev_tools=enabled))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    for path in ("/replay/", "/replay/app.js", "/api/bundle"):
                        if enabled:
                            with urlopen(base + path, timeout=3) as response:
                                self.assertEqual(response.status, 200)
                        else:
                            with self.assertRaises(HTTPError) as error:
                                urlopen(base + path, timeout=3)
                            self.assertEqual(error.exception.code, 404)
                    with urlopen(base + "/api/incidents", timeout=3) as response:
                        self.assertTrue(all("attention" in i for i in json.load(response)["incidents"]))
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


def main():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AttentionSmoke)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    print(json.dumps({"command": "python3 -B -m service.attention_smoke", "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "exit_code": 0 if result.wasSuccessful() else 1,
                      "output": stream.getvalue()}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
