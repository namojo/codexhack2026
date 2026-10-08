"""서비스 소유 범위의 자체 검증. 독립 QA와 구분한다."""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from service import store as module
from service.store import Store, APIError

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))
import serve


class BackendSmoke(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data" / "media").mkdir(parents=True)
        for path in (PROJECT / "data" / "media").glob("*"):
            if path.is_file():
                shutil.copyfile(path, self.root / "data" / "media" / path.name)
        self.seed = self.root / "seed.json"
        self.seed.write_bytes((PROJECT / "data" / "seed.json").read_bytes())
        self.old_root = module.ROOT
        module.ROOT = self.root
        self.db = self.root / "workspace.sqlite3"
        self.store = Store(self.db, self.seed)

    def tearDown(self):
        module.ROOT = self.old_root
        self.temp.cleanup()

    def create(self, **fields):
        return self.store.create_incident({"title": "합성 새 접수", "location": "가상동 1호", "text": "두 명 고립", "people_count": 2, **fields})

    def report(self, incident, **fields):
        return self.store.add_report(incident["id"], {"expected_revision": incident["revision"], "channel": "field", "kind": "field", "text": "가상 대상 두 명 확인", "people_count": 2, **fields})

    def confirm(self, incident, **fields):
        return self.store.confirm_outcome(incident["id"], {"expected_revision": incident["revision"], "outcome": "rescued", "confirmed_count": 2, "basis_report_id": incident["reports"][-1]["id"], "note": "동일 대상 전체 인원 확인", **fields})

    def test_seed_and_persistence(self):
        self.assertEqual(len(self.store.list_incidents()["incidents"]), 10)
        incident = self.create()
        self.seed.write_text('{"synthetic":false}')
        restarted = Store(self.db, self.seed)
        self.assertEqual(restarted.get_incident(incident["id"]), self.store.get_incident(incident["id"]))

    def test_original_and_audit(self):
        incident = self.create()
        original = deepcopy(incident["reports"][0])
        changed = self.store.update_incident(incident["id"], {"expected_revision": 1, "location": "가상동 2호", "people_count": 3, "reason": "담당자가 원문 확인"})
        self.assertEqual(changed["reports"][0], original)
        self.assertEqual(changed["audit"][-1]["before"]["people_count"], 2)
        self.assertEqual(changed["audit"][-1]["after"]["people_count"], 3)

    def test_revision_race(self):
        incident = self.create()
        def edit(title):
            try:
                self.store.update_incident(incident["id"], {"expected_revision": 1, "title": title, "reason": "합성 동시수정"})
                return 200
            except APIError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(edit, ["변경 A", "변경 B"]))
        self.assertEqual(sorted(result), [200, 409])
        self.assertEqual(self.store.get_incident(incident["id"])["revision"], 2)

    def test_assignment_race(self):
        incidents = [self.create(), self.create()]
        team = next(t for t in self.store.list_incidents()["resources"] if t["status"] == "available")
        def assign(incident):
            try:
                self.store.add_progress(incident["id"], {"expected_revision": 1, "status": "dispatched", "team_id": team["id"], "note": "합성 출동"})
                return 200
            except APIError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(assign, incidents))
        self.assertEqual(sorted(result), [200, 409])
        assigned = [i for i in self.store.list_incidents()["incidents"] if i["assigned_team_id"] == team["id"]]
        self.assertEqual(len(assigned), 1)

    def test_assignment_release_on_complete(self):
        incident = self.create()
        team = next(t for t in self.store.list_incidents()["resources"] if t["status"] == "available")
        incident = self.store.add_progress(incident["id"], {"expected_revision": 1, "status": "dispatched", "team_id": team["id"], "note": "출동"})
        closed = self.confirm(self.report(incident))
        self.assertEqual(closed["status"], "closed")
        self.assertIsNone(closed["assigned_team_id"])
        resource = next(t for t in self.store.list_incidents()["resources"] if t["id"] == team["id"])
        self.assertEqual(resource["status"], "available")

    def test_partial_no_closure(self):
        incident = self.report(self.create(), people_count=1)
        with self.assertRaises(APIError):
            self.confirm(incident)
        self.assertNotEqual(self.store.get_incident(incident["id"])["status"], "closed")

    def test_wrong_incident_basis_and_nonfield(self):
        first = self.report(self.create())
        second = self.create()
        for basis in [first["reports"][-1]["id"], second["reports"][0]["id"]]:
            with self.subTest(basis=basis), self.assertRaises(APIError):
                self.confirm(second, basis_report_id=basis)

    def test_unknown_and_bool_validation(self):
        for fields in [{"people_count": True}, {"people_count": -1}, {"category": []}, {"extra": 1}, {"text": ""}, {"attachments": {}}]:
            with self.subTest(fields=fields), self.assertRaises(APIError):
                self.create(**fields)
        incident = self.create()
        with self.assertRaises(APIError):
            self.store.update_incident(incident["id"], {"expected_revision": True, "title": "변경", "reason": "사유"})

    def test_correction_and_total_count_confirmation(self):
        incident = self.report(self.create(), kind="additional", people_count=3)
        self.assertEqual(incident["people_count"], 2)
        incident = self.report(incident)
        with self.assertRaises(APIError):
            self.confirm(incident)
        incident = self.report(incident, kind="correction", people_count=3, text="총 세 명으로 명시 정정")
        self.assertEqual(incident["people_count"], 3)
        incident = self.report(incident, people_count=3)
        self.assertEqual(self.confirm(incident, confirmed_count=3)["status"], "closed")

    def test_reopen_and_old_basis_block(self):
        incident = self.confirm(self.report(self.create()))
        old = deepcopy(incident["outcome"])
        reopened = self.store.reopen(incident["id"], {"expected_revision": incident["revision"], "reason": "추가 확인 필요"})
        self.assertIsNone(reopened["outcome"])
        self.assertEqual(reopened["outcome_history"][-1]["confirmed_at"], old["confirmed_at"])
        with self.assertRaises(APIError):
            self.confirm(reopened, basis_report_id=old["basis_report_id"])
        self.assertEqual(self.confirm(self.report(reopened))["status"], "closed")

    def test_auto_reopen_and_important_update(self):
        for mode in ("report", "patch"):
            with self.subTest(mode=mode):
                incident = self.confirm(self.report(self.create()))
                if mode == "report":
                    changed = self.report(incident, kind="additional", text="추가 정보 접수")
                else:
                    changed = self.store.update_incident(incident["id"], {"expected_revision": incident["revision"], "people_count": 3, "reason": "새 인원 확인"})
                self.assertEqual(changed["status"], "reviewing")
                self.assertIsNone(changed["outcome"])
                self.assertEqual(len(changed["outcome_history"]), 1)

    def test_closed_progress_block(self):
        incident = self.confirm(self.report(self.create()))
        with self.assertRaises(APIError):
            self.store.add_progress(incident["id"], {"expected_revision": incident["revision"], "status": "reviewing", "note": "재개 없는 변경"})

    def test_resolved_checks_and_latest_report(self):
        incident = self.report(self.create(), people_count=1)
        incident = self.report(incident)
        old_counts = [c for c in incident["checks"] if c["title"] == "현장 인원 대조"]
        self.assertTrue(old_counts)
        self.assertTrue(all(c["level"] == "info" for c in old_counts))
        incident = self.confirm(incident)
        self.assertTrue(all(c["level"] == "info" for c in incident["checks"]))

    def test_media_allowlist_and_upload(self):
        data = (self.root / "data" / "media" / "call-isolated.wav").read_bytes()
        attachment = self.store.upload({"filename": "합성 음성.wav", "content_type": "audio/wav", "data_base64": base64.b64encode(data).decode()})
        self.assertEqual(self.store.allowed_media(attachment["url"]).read_bytes(), data)
        incident = self.create(attachments=[attachment])
        self.assertEqual(incident["reports"][0]["attachments"][0], attachment)
        for url in ["/media/../seed.json", "/media/%2e%2e/seed.json", "https://example.com/a.png", "/media/missing.wav", "/media/provenance.json"]:
            with self.subTest(url=url), self.assertRaises(APIError):
                self.store.allowed_media(url)

    def test_fake_media_headers_and_paths(self):
        for content in [b"plain text", b"RIFF" + b"0" * 40]:
            with self.assertRaises(APIError):
                self.store.upload({"filename": "fake.wav", "content_type": "audio/wav", "data_base64": base64.b64encode(content).decode()})
        with self.assertRaises(APIError):
            self.store.upload({"filename": "../x.wav", "content_type": "audio/wav", "data_base64": "eA=="})
        with self.assertRaises(APIError):
            self.store.upload({"filename": "x.wav", "content_type": "audio/wav", "data_base64": "@"})

    def test_http_lifecycle_media_and_errors(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_service_handler(self.store, {"synthetic": True, "results": []}, dev_tools=True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        def call(path, body=None, method="GET", headers=None):
            data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
            return urlopen(Request(base + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})}), timeout=3)
        try:
            with call("/api/incidents") as response:
                self.assertEqual(len(json.load(response)["incidents"]), 10)
            with call("/api/incidents", {"title": "HTTP 사건", "location": "가상동", "text": "한 명", "people_count": 1}, "POST") as response:
                self.assertEqual(response.status, 201)
                incident = json.load(response)
            with call(f"/api/incidents/{incident['id']}") as response:
                self.assertEqual(json.load(response)["revision"], 1)
            with call("/media/call-isolated.wav", headers={"Range": "bytes=0-43"}) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(len(response.read()), 44)
                self.assertEqual(response.headers["Content-Type"], "audio/wav")
            with call("/replay") as response:
                self.assertTrue(response.url.endswith("/replay/"))
            with call("/replay/app.js") as response:
                self.assertEqual(response.status, 200)
            for path, body, method, expected in [("/api/incidents", {"title": "x"}, "POST", 400), ("/api/incidents/missing", None, "GET", 404)]:
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    call(path, body, method)
                self.assertEqual(error.exception.code, expected)
                self.assertIn("error", json.loads(error.exception.read()))
            with self.assertRaises(HTTPError) as error:
                call("/api/incidents", {}, "POST", {"Origin": "http://localhost:bad"})
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def main():
    stream = io.StringIO()
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(BackendSmoke)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    print(json.dumps({"command": "python3 -B -m service.smoke", "exit_code": 0 if result.wasSuccessful() else 1,
                      "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "output": stream.getvalue(), "not_run": ["독립 QA", "브라우저 UX", "실제 OCR/ASR/LLM"]}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
