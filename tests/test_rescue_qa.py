"""계약 v1에 대한 독립 QA. 실제 모델/API를 호출하지 않는다."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from rescue.engine import replay
import replay as cli
import serve


def case(name):
    return json.loads((ROOT / "scenarios" / (name + ".json")).read_text())


def event(number, text, channel="field", **extra):
    stamp = f"2026-07-15T10:{number:02d}:00+09:00"
    return dict(id=f"Q{number}", channel=channel, actor="합성 QA", occurred_at=stamp,
                received_at=stamp, text=text, **extra)


def observe(evt, kind, ids=("R-A",), **extra):
    return {"event_id": evt["id"], "observations": [dict(kind=kind,
            request_ids=list(ids), evidence_quote=evt["text"], **extra)]}


def scenario(events, analyses):
    return dict(schema_version=1, id="qa-synthetic", synthetic=True, events=events,
                fixture_analysis=analyses,
                expectations=[{"path": "requests", "length": 1, "label": "개별 요청"}])


def closure(number, count, basis, revision=1):
    return event(number, "합성 담당자 확정", "operator", decision={
        "kind": "confirm_outcome", "request_id": "R-A", "outcome": "rescued",
        "confirmed_count": count, "basis_event_ids": basis, "expected_revision": revision})


def codes(result):
    return [a["code"] for a in result["final"]["alerts"] if a["active"]]


class EngineBoundaryTests(unittest.TestCase):
    def test_all_twenty_cases_and_every_expectation(self):
        files = sorted((ROOT / "scenarios").glob("*.json"))
        self.assertEqual(len(files), 20)
        events = assertions = intermediate = 0
        for file in files:
            original = json.loads(file.read_text())
            before = deepcopy(original)
            with self.subTest(case=original["id"]):
                result = replay(original)
                self.assertEqual(original, before, "재생이 입력을 변경하면 안 된다")
                self.assertEqual(len(result["checks"]), len(original["expectations"]))
                self.assertTrue(result["passed"], result["checks"])
                self.assertTrue(all(c["passed"] for c in result["checks"]))
                self.assertEqual(replay(original), result, "결정적 재생")
                events += len(original["events"])
                assertions += len(result["checks"])
                intermediate += sum("after" in c for c in original["expectations"])
        self.assertEqual((events, assertions, intermediate), (57, 91, 38))

    def test_same_building_preserves_ids_and_every_raw_event(self):
        original = case("same-building")
        result = replay(original)
        self.assertEqual(set(result["final"]["requests"]), {"R-A", "R-B"})
        self.assertEqual([a["original"] for a in result["final"]["audit"]], original["events"])
        for rid in ("R-A", "R-B"):
            self.assertEqual(result["final"]["requests"][rid]["id"], rid)

    def test_dispatch_and_rescue_report_do_not_automatically_complete(self):
        result = replay(case("normal-completion"))
        for snap in result["snapshots"][1:3]:
            self.assertNotEqual(snap["requests"]["R-A"]["status"], "resolved")
            self.assertIsNone(snap["requests"]["R-A"]["outcome"])
            self.assertEqual(snap["requests"]["R-A"]["revision"], 1)

    def test_no_response_and_delivery_failure_remain_unresolved(self):
        for name in ("no-response", "delivery-failure"):
            with self.subTest(case=name):
                result = replay(case(name))
                self.assertEqual(result["metrics"]["resolved"], 0)
                self.assertIn(name.replace("-", "_"), codes(result))

    def test_rejected_analysis_is_atomic_and_preserves_receipt(self):
        original = case("normal-completion")
        original["events"] = original["events"][:1]
        valid = original["fixture_analysis"]["E1"]["observations"][0]
        original["fixture_analysis"]["E1"]["observations"].append(dict(valid, evidence_quote="없는 근거"))
        result = replay(original)
        card = result["final"]["requests"]["R-A"]
        self.assertIsNone(card["people_count"])
        self.assertIsNone(card["location_text"])
        self.assertEqual(card["needs"], [])
        self.assertEqual(card["evidence_event_ids"], ["E1"])
        self.assertEqual(result["final"]["audit"][0]["original"], original["events"][0])
        self.assertIn("analysis_rejected", codes(result))

    def test_bad_analysis_fields_ids_quotes_counts_and_shapes_rejected(self):
        base = case("normal-completion")
        base["events"] = base["events"][:1]
        base["fixture_analysis"] = {"E1": base["fixture_analysis"]["E1"]}
        mutations = [
            lambda a: a.update(event_id="wrong"),
            lambda a: a.update(unapproved="field"),
            lambda a: a["observations"][0].update(request_ids=["R-FUTURE"]),
            lambda a: a["observations"][0].update(request_ids="R-A"),
            lambda a: a["observations"][0].update(evidence_quote="가짜 근거"),
            lambda a: a["observations"][0].update(evidence_quote=""),
            lambda a: a["observations"][0].update(people_count=True),
            lambda a: a["observations"][0].update(people_count=-1),
            lambda a: a["observations"][0].update(people_count=2.0),
            lambda a: a["observations"][0].update(people_count=None),
            lambda a: a["observations"][0].update(needs=[False]),
            lambda a: a["observations"][0].update(decision={"kind": "confirm_outcome"}),
            lambda a: a["observations"][0].pop("evidence_quote"),
            lambda a: a.update(observations={}),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                current = deepcopy(base)
                mutate(current["fixture_analysis"]["E1"])
                result = replay(current)
                self.assertEqual(result["metrics"]["rejected_analyses"], 1)
                self.assertIsNone(result["final"]["requests"]["R-A"]["people_count"])
                self.assertEqual(len(result["final"]["audit"]), 1)

    def test_missing_live_analysis_never_falls_back(self):
        original = case("normal-completion")
        result = replay(original, mode="live", analyses={})
        self.assertIsNone(result["final"]["requests"]["R-A"]["people_count"])
        self.assertEqual(result["metrics"]["rejected_analyses"], 2)
        self.assertEqual(result["metrics"]["resolved"], 0)

    def test_late_location_preserves_latest_location_and_old_evidence(self):
        result = replay(case("late-location"))
        card = result["final"]["requests"]["R-A"]
        self.assertIn("late_location_ignored", codes(result))
        self.assertTrue(any(not h["applied"] for h in card["location_history"]))
        self.assertEqual(card["location_text"], "301호")
        self.assertEqual(card["location_occurred_at"], "2026-07-15T10:02:00+09:00")
        self.assertEqual(card["revision"], 2)

    def test_partial_report_cannot_confirm_current_total(self):
        original = case("partial-rescue")
        original["events"] = original["events"][:3]
        original["events"][2]["decision"]["confirmed_count"] = 3
        result = replay(original)
        self.assertNotEqual(result["final"]["requests"]["R-A"]["status"], "resolved")
        self.assertIn("closure_blocked", codes(result))

    def test_reports_must_not_sum_into_total(self):
        request = event(1, "합성 세 명 고립", "sms", request_id="R-A")
        first, second = event(2, "합성 두 명 구조"), event(3, "합성 한 명 구조")
        original = scenario([request, first, second, closure(4, 3, ["Q2", "Q3"])], {
            "Q1": observe(request, "request", people_count=3),
            "Q2": observe(first, "rescue_report", people_count=2),
            "Q3": observe(second, "rescue_report", people_count=1)})
        result = replay(original)
        self.assertIn("closure_blocked", codes(result))
        self.assertEqual(result["metrics"]["resolved"], 0)

    def test_stale_revision_approval_blocks(self):
        result = replay(case("count-correction-stale"))
        blocked = [s for s in result["snapshots"] if any(a["code"] == "closure_blocked" and a["active"] for a in s["alerts"])]
        self.assertTrue(blocked)
        self.assertTrue(all(s["requests"]["R-A"]["status"] != "resolved" for s in blocked))

    def test_completion_then_new_location_count_or_need_reopens(self):
        for kind, extra in (("location_update", {"location_text": "합성 옥상"}),
                            ("count_correction", {"people_count": 3}),
                            ("request", {"needs": ["고립"]})):
            with self.subTest(kind=kind):
                original = case("normal-completion")
                update = event(5, "합성 새 정보", "sms", request_id="R-A")
                original["events"].append(update)
                original["fixture_analysis"]["Q5"] = observe(update, kind, **extra)
                result = replay(original)
                self.assertEqual(result["final"]["requests"]["R-A"]["status"], "open")
                self.assertIsNone(result["final"]["requests"]["R-A"]["outcome"])
                self.assertIn("post_resolution_update", codes(result))

    def test_manual_link_does_not_propagate_completion(self):
        original = case("manual-duplicate-link")
        report = event(5, "합성 R-A 두 명 구조")
        original["events"] += [report, closure(6, 2, ["Q5"])]
        original["fixture_analysis"]["Q5"] = observe(report, "rescue_report", people_count=2)
        result = replay(original)
        self.assertEqual(result["final"]["requests"]["R-A"]["status"], "resolved")
        self.assertEqual(result["final"]["requests"]["R-B"]["status"], "open")
        self.assertIsNone(result["final"]["requests"]["R-B"]["outcome"])
        self.assertEqual(len(result["final"]["requests"]), 2)

    def test_link_resolved_and_open_or_different_counts_is_rejected(self):
        for differing_count in (False, True):
            with self.subTest(differing_count=differing_count):
                original = case("manual-duplicate-link")
                original["events"] = original["events"][:2]
                if differing_count:
                    original["fixture_analysis"]["E2"]["observations"][0]["people_count"] = 3
                else:
                    report = event(3, "합성 두 명 구조")
                    original["events"] += [report, closure(4, 2, ["Q3"])]
                    original["fixture_analysis"]["Q3"] = observe(report, "rescue_report", people_count=2)
                link = event(5, "합성 수동 연결", "operator", decision={"kind": "link_duplicate", "request_id": "R-A", "related_request_id": "R-B"})
                original["events"].append(link)
                result = replay(original)
                self.assertIn("closure_blocked", codes(result))
                self.assertEqual(result["final"]["requests"]["R-B"]["canonical_id"], "R-B")

    def test_missing_expectations_or_assertion_path_fails(self):
        for assertions in ([], [{"path": "requests.R-UNKNOWN.status", "equals": "open"}],
                           [{"path": "alerts", "not_contains_code": "x", "after": "FUTURE"}],
                           [{"path": "requests"}]):
            with self.subTest(assertions=assertions):
                original = case("normal-completion")
                original["expectations"] = assertions
                self.assertFalse(replay(original)["passed"])

    def test_required_original_times_and_operator_identity(self):
        for mutation in (lambda e: e.update(received_at="2026-07-15T09:00:00+09:00"),
                         lambda e: e.update(occurred_at="2026-07-15T10:01:00"),
                         lambda e: e.pop("text")):
            original = case("normal-completion")
            mutation(original["events"][0])
            with self.assertRaises(ValueError):
                replay(original)
        for actor, channel in (("", "operator"), ("합성 담당자", "sms")):
            original = case("normal-completion")
            original["events"][1].update(actor=actor, channel=channel)
            with self.assertRaises(ValueError):
                replay(original)


class AdapterAndCLITests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts/replay.py"), *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=20)

    def test_packet_contains_only_current_event_and_prior_state(self):
        original = case("normal-completion")
        packets = []
        def fake_run(argv, **kwargs):
            packet = json.loads(kwargs["input"])
            packets.append(packet)
            current = packet["event"]
            return subprocess.CompletedProcess(argv, 0, json.dumps(original["fixture_analysis"][current["id"]]), "")
        with patch.object(cli.subprocess, "run", side_effect=fake_run):
            analyses, failures = cli.live_analyses(original, "synthetic-adapter", 1)
        self.assertEqual(failures, [])
        self.assertEqual(set(analyses), {"E1", "E3"})
        for packet in packets:
            self.assertEqual(set(packet), {"protocol_version", "synthetic", "event", "prior_state", "allowed_kinds"})
            encoded = json.dumps(packet)
            self.assertNotIn("fixture_analysis", encoded)
            self.assertNotIn("expectations", encoded)
            self.assertNotIn("demo_notes", encoded)
            i = [e["id"] for e in original["events"]].index(packet["event"]["id"])
            self.assertEqual([a["event_id"] for a in packet["prior_state"]["audit"]], [e["id"] for e in original["events"][:i]])
            for future in original["events"][i + 1:]:
                self.assertNotIn(future["text"], encoded)

    def test_adapter_exit_timeout_invalid_json_os_failure_no_fallback(self):
        original = cli.load_cases("normal-completion")[0]
        faults = [subprocess.CompletedProcess([], 7, "", "SECRET_PROVIDER_ERROR"),
                  subprocess.TimeoutExpired("synthetic-adapter", 1),
                  subprocess.CompletedProcess([], 0, "not json", ""), FileNotFoundError("none")]
        for fault in faults:
            with self.subTest(fault=type(fault).__name__):
                kwargs = {"side_effect": fault} if isinstance(fault, Exception) else {"return_value": fault}
                with patch.object(cli.subprocess, "run", **kwargs):
                    report = cli.run_cases([original], "live", analyzer_command="synthetic-adapter", timeout=1)
                result = report["results"][0]
                self.assertEqual(report["analyzer_failure_count"], 2)
                self.assertEqual(result["metrics"]["rejected_analyses"], 2)
                self.assertEqual(result["metrics"]["resolved"], 0)
                self.assertNotIn("SECRET_PROVIDER_ERROR", json.dumps(report))

    def test_real_local_subprocess_failure_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "synthetic_adapter.py"
            adapter.write_text("import sys\nsys.stderr.write('SYNTHETIC_SECRET_SENTINEL')\nsys.exit(7)\n")
            output = Path(directory) / "result"
            import shlex
            command = shlex.join([sys.executable, "-B", str(adapter)])
            process = self.invoke("--case", "normal-completion", "--mode", "live", "--analyzer-command", command, "--output", output)
            self.assertEqual(process.returncode, 1, process.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["analyzer_failure_count"], 2)
            self.assertEqual(report["results"][0]["metrics"]["resolved"], 0)
            self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", json.dumps(report) + process.stderr)

    def test_real_local_subprocess_timeout_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "synthetic_timeout.py"
            adapter.write_text("import time\ntime.sleep(3)\n")
            output = Path(directory) / "result"
            import shlex
            command = shlex.join([sys.executable, "-B", str(adapter)])
            process = self.invoke("--case", "normal-completion", "--mode", "live", "--analyzer-command", command, "--timeout", "1", "--output", output)
            self.assertEqual(process.returncode, 1, process.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["analyzer_failure_count"], 2)
            self.assertTrue(all(f["error_type"] == "TimeoutExpired" for f in report["results"][0]["analyzer_failures"]))
            self.assertEqual(report["results"][0]["metrics"]["resolved"], 0)

    def test_live_missing_analysis_files_and_output_fault_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            process = self.invoke("--all", "--mode", "live", "--analysis-dir", directory, "--output", output)
            self.assertEqual(process.returncode, 1, process.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["case_count"], 17)
            self.assertEqual(len(report["excluded_output_fault_cases"]), 3)
            self.assertEqual(report["analyzer_failure_count"], 17)
            self.assertTrue(all(r["metrics"]["resolved"] == 0 for r in report["results"]))

    def test_fixture_cli_hashes_command_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            first = self.invoke("--all", "--output", output)
            self.assertEqual(first.returncode, 0, first.stderr)
            report_bytes = (output / "report.json").read_bytes()
            report = json.loads(report_bytes)
            self.assertEqual((report["case_count"], report["checks_count"], report["passed_checks"]), (20, 91, 91))
            self.assertEqual(report["mode"], "fixture")
            self.assertIn("--all", report["command"])
            self.assertTrue(report["python_version"])
            self.assertTrue(report["created_at"])
            for result in report["results"]:
                self.assertEqual(result["input_sha256"], hashlib.sha256((ROOT / result["input_path"]).read_bytes()).hexdigest())
            for path, digest in report["code_sha256"].items():
                self.assertEqual(digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
            second = self.invoke("--all", "--output", output)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((output / "report.json").read_bytes(), report_bytes)

    def test_cli_invalid_mode_configuration_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in (("--mode", "live"), ("--timeout", "0"), ("--analysis-dir", directory),
                         ("--case", "fabricated-evidence", "--mode", "live", "--analysis-dir", directory)):
                output = Path(directory) / "result"
                process = self.invoke(*args, "--output", output)
                self.assertEqual(process.returncode, 2, process.stderr)
                self.assertFalse(output.exists())


class HTTPBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = cli.run_cases(cli.load_cases())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cls.bundle))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_api_bundle_matches_fixture_and_is_synthetic(self):
        with urlopen(self.base + "/api/bundle", timeout=3) as response:
            bundle = json.load(response)
            self.assertTrue(bundle["synthetic"])
            self.assertEqual(bundle["mode"], "fixture")
            self.assertEqual(bundle["case_count"], 20)
            self.assertEqual(bundle["passed_checks"], 91)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_static_allowlist_is_accessible(self):
        for route in ("/", "/index.html", "/app.js", "/style.css"):
            with self.subTest(route=route), urlopen(self.base + route, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 0)
                self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_unknown_and_traversal_routes_are_denied(self):
        for route in ("/docs/contract.md", "/../docs/contract.md", "/%2e%2e/docs/contract.md", "/.codex/config.toml", "/scenarios/normal-completion.json"):
            with self.subTest(route=route), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + route, timeout=3)
            self.assertEqual(caught.exception.code, 404)

    def test_post_has_no_state_changing_route(self):
        from urllib.request import Request
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + "/api/bundle", data=b"{}", method="POST"), timeout=3)
        self.assertEqual(caught.exception.code, 501)


if __name__ == "__main__":
    unittest.main()
