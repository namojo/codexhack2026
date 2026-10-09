"""Independent AI boundary QA. All model calls are mocked, all stores temporary."""
import base64
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from service import ai
from service.store import Store, APIError

ROOT = Path(__file__).resolve().parents[1]


def empty(schema):
    if "anyOf" in schema:
        return None
    if "enum" in schema:
        return None if None in schema["enum"] else schema["enum"][0]
    t = schema.get("type")
    if isinstance(t, list) and "null" in t:
        return None
    if t == "object":
        return {k: empty(v) for k, v in schema["properties"].items()}
    return {"array": [], "string": "", "integer": 0, "number": 0, "boolean": True}[t]


class AIServiceQA(unittest.TestCase):
    def setUp(self):
        self.dto = empty(ai.SCHEMA)
        self.report = {"channel": "sms", "actor": "가상 QA", "text": "가상 QA빌라 201호 두 명 고립", "kind": "initial", "attachments": []}
        self.packet = {"synthetic": True, "report": self.report, "incidents": []}

    def validate(self, dto=None, report=None, transcripts=None):
        return ai.validate_analysis(dto or self.dto, report or self.report, [], transcripts or [])

    def test_multiline_input_existing_report_and_asr_keep_exact_source_binding(self):
        for separator in ("\n", "\r\n", "\t"):
            with self.subTest(separator=repr(separator)):
                report = copy.deepcopy(self.report)
                report["text"] = "합성 첫째" + separator + "합성 둘째"
                report["attachments"] = [{"id": "A", "media_type": "audio"}]
                incidents = [{"id": "I", "reports": [{"id": "R", "text": "이전 첫째" + separator + "이전 둘째"}]}]
                transcripts = [{"attachment_id": "A", "text": "전사 첫째" + separator + "전사 둘째", "model": "mock-asr"}]
                before = copy.deepcopy((report, incidents, transcripts))
                for source, kind, quote in (("input", "text", "합성 둘째"), ("R", "text", "이전 둘째"), ("A", "audio_transcript", "전사 둘째")):
                    dto = copy.deepcopy(self.dto)
                    dto["transcripts"] = copy.deepcopy(transcripts)
                    dto["evidence"] = [{"field": "summary", "source_id": source, "type": kind, "quote": quote, "observation": None}]
                    ai.validate_analysis(dto, report, incidents, transcripts)
                    for bad_source, bad_quote in (("unknown", quote), (source, "허위 인용"), ("input" if source != "input" else "R", quote)):
                        bad = copy.deepcopy(dto)
                        bad["evidence"][0].update(source_id=bad_source, quote=bad_quote)
                        with self.assertRaises(ValueError):
                            ai.validate_analysis(bad, report, incidents, transcripts)
                self.assertEqual((report, incidents, transcripts), before)

    def test_all_keys_and_nulls_are_required(self):
        self.validate()
        for mutation in (lambda a: a.pop("handoff"), lambda a: a.update(status="closed"), lambda a: a["proposed_changes"].update(people_count=True), lambda a: a["intake119"]["location"].update(gps={"latitude": 91, "longitude": 0}), lambda a: a["authenticity"].update(status="true")):
            a = copy.deepcopy(self.dto); mutation(a)
            with self.assertRaises(ValueError): self.validate(a)

    def test_nonfinite_gps_is_not_strict_json(self):
        for number in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(number=number):
                a = copy.deepcopy(self.dto)
                a["intake119"]["location"]["gps"] = {"latitude": number, "longitude": 0}
                with self.assertRaises(ValueError): self.validate(a)

    def test_strict_json_rejects_nonfinite_constants_and_overflow(self):
        for encoded in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}', '{"x":-1e999}'):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                ai.strict_json_loads(encoded)
        self.assertEqual(ai.strict_json_loads('{"gps":null,"n":1.5,"z":0}'), {"gps": None, "n": 1.5, "z": 0})

    def test_real_http_response_parser_rejects_nonfinite_without_live_call(self):
        for encoded in (b'{"text":"QA","usage":NaN}', b'{"text":"QA","usage":1e999}'):
            class Fake:
                def __enter__(self): return io.BytesIO(encoded)
                def __exit__(self, *args): pass
            with patch.object(ai, "urlopen", return_value=Fake()), self.assertRaises(ValueError):
                ai.api("responses", b'{}', "mock-key")

    def test_nested_model_dto_nonfinite_json_rejected(self):
        for encoded in ('NaN', '1e999'):
            a = copy.deepcopy(self.dto)
            a["intake119"]["location"]["gps"] = {"latitude": 0, "longitude": 0}
            text = json.dumps(a).replace('"latitude": 0', '"latitude": ' + encoded)
            response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
            with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(ai, "api", return_value=response), self.assertRaises(ValueError):
                ai.analyze_service(self.packet)

    def test_cli_bad_packet_and_bad_response_strict_json(self):
        spec = importlib.util.spec_from_file_location("qa_strict_analyzer", ROOT / "scripts/analyzer_openai.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            packet = '{"synthetic":true,"mode":"service","intake119":{"location":{"gps":{"latitude":' + token + ',"longitude":0}}}}'
            with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(sys, "stdin", io.StringIO(packet)), patch.object(sys, "stdout", io.StringIO()) as out, patch.object(sys, "stderr", io.StringIO()), patch.object(sys, "argv", ["analyzer", "--service"]), patch.object(module, "urlopen") as call, patch.object(ai, "analyze_service") as service_call:
                self.assertEqual(module.main(), 1); self.assertEqual(out.getvalue(), "")
                call.assert_not_called(); service_call.assert_not_called()
        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"event_id":"evt","observations":[],"value":NaN}'}]}]}
        class Fake:
            def __enter__(self): return io.StringIO(json.dumps(response))
            def __exit__(self, *args): pass
        with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(sys, "stdin", io.StringIO('{"synthetic":true,"event":{"id":"evt"}}')), patch.object(sys, "stdout", io.StringIO()) as out, patch.object(sys, "stderr", io.StringIO()), patch.object(sys, "argv", ["analyzer"]), patch.object(module, "urlopen", return_value=Fake()):
            self.assertEqual(module.main(), 1); self.assertEqual(out.getvalue(), "")

    def test_public_cloud_build_raw_reports_and_no_js_sources(self):
        from scripts.build_pages import build
        from html import escape
        seed = json.loads((ROOT / "data/seed.json").read_text())
        with tempfile.TemporaryDirectory(prefix="ai-qa-public-") as d:
            stage = Path(d) / "pages"
            build(stage, mode="cloud")
            index = (stage / "index.html").read_text()
            judge = (stage / "judge/index.html").read_text()
            full = (stage / "llms-full.txt").read_text()
            self.assertIn('data-service-mode="cloud"', index)
            self.assertIn('id="judge-snapshot"', index)
            for incident in seed["incidents"]:
                self.assertIn(escape(incident["title"]), index)
                for report in incident["reports"]:
                    self.assertIn(escape(report["text"]), judge)
                    self.assertIn(report["text"], full)
                    self.assertIn(report["id"], judge)
            for slug in ("about", "guide", "references", "judge"):
                self.assertIn(f'href="/{slug}/"', index)
                page = (stage / slug / "index.html").read_text()
                self.assertIn("<main>", page)
                self.assertNotIn("<script", page)
            evidence = json.loads((stage / "judge/evidence.json").read_text())
            self.assertTrue(evidence["readable_without_javascript"])
            self.assertFalse(evidence["official_119_connected"])
            self.assertIn("https://github.com/namojo/codexhack2026", full)
            for name in ("llms.txt", "sitemap.xml", "robots.txt"):
                self.assertGreater((stage / name).stat().st_size, 50)

    def test_evidence_quote_source_field_and_candidate_boundaries(self):
        a = copy.deepcopy(self.dto)
        a["proposed_changes"]["location"] = "가상 QA빌라 201호"
        evidence = {"field": "location", "source_id": "input", "quote": "가상 QA빌라 201호", "observation": None, "type": "text"}
        a["evidence"] = [evidence]; self.validate(a)
        for field, value in (("source_id", "invented"), ("quote", "없는 주소"), ("field", "status"), ("type", "image_observation")):
            bad = copy.deepcopy(a); bad["evidence"][0][field] = value
            with self.assertRaises(ValueError): self.validate(bad)
        bad = copy.deepcopy(a); bad["evidence"] = []
        with self.assertRaises(ValueError): self.validate(bad)
        for key, value in (("duplicate_candidates", [{"incident_id": "invented", "report_id": None, "reason": "동일", "needs_human_confirmation": True}]), ("person_overlap", [{"source_ids": ["invented"], "reason": "동일", "needs_human_confirmation": True}])):
            bad = copy.deepcopy(self.dto); bad[key] = value
            with self.assertRaises(ValueError): self.validate(bad)

    def test_real_asr_array_and_image_observation_boundaries(self):
        report = copy.deepcopy(self.report); report["attachments"] = [{"id": "audio", "media_type": "audio"}, {"id": "image", "media_type": "image"}]
        actual = [{"attachment_id": "audio", "text": "실제 모의 ASR 원문", "model": "qa-asr"}]
        a = copy.deepcopy(self.dto); a["transcripts"] = actual
        a["evidence"] = [{"field": "summary", "source_id": "audio", "quote": "모의 ASR", "observation": None, "type": "audio_transcript"}, {"field": "hazards", "source_id": "image", "quote": None, "observation": "입구 물 관찰", "type": "image_observation"}]
        self.validate(a, report, actual)
        bad = copy.deepcopy(a); bad["transcripts"][0]["text"] = "seed 대본"
        with self.assertRaises(ValueError): self.validate(bad, report, actual)
        bad = copy.deepcopy(a); bad["evidence"][1]["quote"] = "가짜 OCR"
        with self.assertRaises(ValueError): self.validate(bad, report, actual)

    def test_media_uses_real_bytes_and_asr_not_seed_labels(self):
        png = (ROOT / "data/media/flood-entrance.png").read_bytes()
        wav = (ROOT / "data/media/call-isolated.wav").read_bytes()
        attachments = [{"id": "pic", "url": "/api/media/pic", "media_type": "image", "caption": "DO NOT USE CAPTION", "transcript": "DO NOT USE TRANSCRIPT"}, {"id": "voice", "url": "/api/media/voice", "media_type": "audio", "transcript": "DO NOT USE TRANSCRIPT"}, {"id": "video", "url": "bad", "media_type": "video"}]
        packet = copy.deepcopy(self.packet); packet["report"]["attachments"] = attachments
        packet["media_registry"] = {"pic": {"url": "/api/media/pic", "content_type": "image/png", "data_base64": base64.b64encode(png).decode()}, "voice": {"url": "/api/media/voice", "content_type": "audio/wav", "data_base64": base64.b64encode(wav).decode()}}
        calls = []
        def mock_api(path, payload, key, content_type="application/json"):
            calls.append((path, payload, content_type))
            if path == "audio/transcriptions":
                self.assertIn(wav, payload); return {"text": "ASR가 반환한 모의 전사"}
            parsed = json.loads(payload); raw = parsed["input"][0]["content"][0]["text"]
            self.assertNotIn("DO NOT USE", raw); self.assertIn("ASR가 반환한", raw)
            self.assertEqual(parsed["input"][0]["content"][1]["image_url"], "data:image/png;base64," + base64.b64encode(png).decode())
            self.assertTrue(parsed["text"]["format"]["strict"]); self.assertFalse(parsed["store"])
            a = copy.deepcopy(self.dto); a["transcripts"] = [{"attachment_id": "voice", "text": "ASR가 반환한 모의 전사", "model": "qa-asr"}]
            return {"status": "completed", "id": "mock-response", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(a)}]}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "OPENAI_MODEL": "qa-model", "OPENAI_TRANSCRIBE_MODEL": "qa-asr"}, clear=True), patch.object(ai, "api", mock_api):
            result = ai.analyze_service(packet)
        self.assertEqual([x[0] for x in calls], ["audio/transcriptions", "responses"])
        self.assertIn("영상", result["analysis"]["limitations"][0]); self.assertEqual(result["execution"]["mode"], "live")

    def test_no_env_no_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(ai, "api") as call:
            with self.assertRaisesRegex(ValueError, "no fixture fallback"): ai.analyze_service(self.packet)
            call.assert_not_called()

    def test_ssrf_and_bad_registered_header_are_blocked_before_model(self):
        for url, registry in (("https://127.0.0.1/private", {}), ("/api/media/x", {"x": {"url": "/api/media/x", "content_type": "image/png", "data_base64": base64.b64encode(b"wrong header").decode()}})):
            packet = copy.deepcopy(self.packet); packet["report"]["attachments"] = [{"id": "x", "url": url, "media_type": "image"}]; packet["media_registry"] = registry
            with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(ai, "api") as call:
                with self.assertRaises(ValueError): ai.analyze_service(packet)
                call.assert_not_called()

    def test_model_refusal_and_failure_never_produce_fixture(self):
        for response in ({"status": "incomplete", "output": []}, {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(ai, "api", return_value=response):
                with self.assertRaises(ValueError): ai.analyze_service(self.packet)

    def test_sqlite_negative_completion_raw_audit_restart(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "qa.sqlite")
            i = store.create_incident({"title": "QA", "location": "가상 QA", "text": "두 명 고립", "people_count": 2, "intake119": {"rescue": {"people_count": None}}})
            raw = copy.deepcopy(i["reports"][0])
            for text in ("두 명 구조 확인 못함", "2명 중 1명만 구조, 1명 남아 있음", "두 명 전원 구조했으나 다른 주민 미확인"):
                i = store.add_report(i["id"], {"expected_revision": i["revision"], "channel": "field", "kind": "field", "text": text, "people_count": 2})
                before = store.get_incident(i["id"])
                with self.assertRaises(APIError) as e: store.confirm_outcome(i["id"], {"expected_revision": i["revision"], "outcome": "rescued", "confirmed_count": 2, "basis_report_id": i["reports"][-1]["id"], "note": "QA"})
                self.assertEqual(e.exception.status, 400); self.assertEqual(store.get_incident(i["id"]), before)
            self.assertEqual(i["reports"][0], raw)
            self.assertEqual(Store(Path(d) / "qa.sqlite").get_incident(i["id"])["reports"], i["reports"])

    def test_cli_replay_and_service_modes_remain_separate(self):
        spec = importlib.util.spec_from_file_location("qa_analyzer", ROOT / "scripts/analyzer_openai.py"); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        packet = {"synthetic": True, "event": {"id": "evt", "text": "가상 원문"}, "prior_state": {}, "allowed_kinds": []}
        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"event_id":"evt","observations":[]}'}]}]}
        class Fake:
            def __enter__(self): return io.StringIO(json.dumps(response))
            def __exit__(self, *args): pass
        with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(sys, "stdin", io.StringIO(json.dumps(packet))), patch.object(sys, "stdout", io.StringIO()) as output, patch.object(sys, "argv", ["analyzer"]), patch.object(module, "urlopen", return_value=Fake()):
            self.assertEqual(module.main(), 0); self.assertEqual(json.loads(output.getvalue()), {"event_id": "evt", "observations": []})
        service_packet = {**self.packet, "mode": "service"}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "mock", "OPENAI_MODEL": "mock"}, clear=True), patch.object(sys, "stdin", io.StringIO(json.dumps(service_packet))), patch.object(sys, "stdout", io.StringIO()) as output, patch.object(sys, "argv", ["analyzer"]), patch.object(ai, "analyze_service", return_value={"analysis": self.dto}) as call:
            self.assertEqual(module.main(), 0); call.assert_called_once(); self.assertIn("analysis", json.loads(output.getvalue()))


if __name__ == "__main__": unittest.main()
