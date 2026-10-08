"""엔진 소유 범위의 개인 smoke. 독립 QA tests/와 구분한다."""

from copy import deepcopy
import unittest

from rescue.engine import replay


def event(eid, minute=0, channel="sms", rid=None, text="합성 근거", occurred=None, decision=None):
    result = {"id": eid, "channel": channel, "actor": "합성 담당자" if channel == "operator" else "합성 제보자",
              "occurred_at": f"2026-10-08T10:{minute if occurred is None else occurred:02}:00+09:00",
              "received_at": f"2026-10-08T10:{minute:02}:00+09:00", "text": text}
    if rid is not None:
        result["request_id"] = rid
    if decision is not None:
        result["decision"] = decision
    return result


def observation(eid, kind="request", ids=None, **fields):
    return {"event_id": eid, "observations": [{"kind": kind, "request_ids": ["R1"] if ids is None else ids,
                                               "evidence_quote": "합성 근거", **fields}]}


def scenario(events=None, analyses=None, expectations=None):
    return {"schema_version": 1, "id": "개인-smoke", "synthetic": True,
            "events": [event("E1", rid="R1")] if events is None else events,
            "fixture_analysis": {"E1": observation("E1", people_count=3, location_text="2층", needs=["고립"])} if analyses is None else analyses,
            "expectations": [{"path": "requests.R1.revision", "equals": 1, "label": "첫 버전"}] if expectations is None else expectations}


def confirmation(eid="E3", minute=2, **fields):
    return event(eid, minute, channel="operator", decision={"kind": "confirm_outcome", "request_id": "R1",
                 "outcome": "rescued", "confirmed_count": 3, "basis_event_ids": ["E2"], "expected_revision": 1, **fields})


def completed_scenario():
    return scenario([event("E1", rid="R1"), event("E2", 1, channel="field"), confirmation()],
                    {"E1": observation("E1", people_count=3, location_text="2층", needs=["고립"]),
                     "E2": observation("E2", "rescue_report", people_count=3)})


class EngineSmoke(unittest.TestCase):
    def test_initial_and_immutable(self):
        value = scenario()
        original = deepcopy(value)
        result = replay(value)
        self.assertTrue(result["passed"])
        self.assertEqual(value, original)
        self.assertEqual(result["final"]["requests"]["R1"]["status"], "open")
        self.assertEqual(result["final"]["audit"][0]["original"], value["events"][0])

    def test_no_fixture_fallback(self):
        result = replay(scenario(), "live")
        self.assertEqual(result["metrics"]["rejected_analyses"], 1)
        self.assertIsNone(result["final"]["requests"]["R1"]["people_count"])

    def test_rejection_atomic(self):
        value = scenario()
        value["fixture_analysis"]["E1"]["observations"].append({"kind": "count_correction", "request_ids": ["UNKNOWN"], "people_count": 2, "evidence_quote": "합성 근거"})
        result = replay(value)
        card = result["final"]["requests"]["R1"]
        self.assertEqual(card["evidence_event_ids"], ["E1"])
        self.assertIsNone(card["people_count"])
        self.assertEqual(result["metrics"]["rejected_analyses"], 1)

    def test_invalid_analysis_variants(self):
        mutations = [lambda a: a.update(event_id="OTHER"), lambda a: a.update(extra=True),
                     lambda a: a["observations"][0].update(people_count=True),
                     lambda a: a["observations"][0].update(kind="unknown"),
                     lambda a: a["observations"][0].update(kind=[]),
                     lambda a: a["observations"][0].update(evidence_quote="창작 근거"),
                     lambda a: a["observations"][0].update(extra="unknown"),
                     lambda a: a["observations"][0].update(request_ids=["R1", "R1"])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = scenario()
                mutate(value["fixture_analysis"]["E1"])
                self.assertEqual(replay(value)["metrics"]["rejected_analyses"], 1)

    def test_dispatch_not_closure(self):
        value = scenario()
        value["events"].append(event("E2", 1, channel="operator", decision={"kind": "dispatch", "request_id": "R1"}))
        result = replay(value)
        self.assertEqual(result["final"]["requests"]["R1"]["status"], "dispatched")
        self.assertEqual(result["final"]["requests"]["R1"]["revision"], 1)

    def test_report_and_human_confirmation(self):
        result = replay(completed_scenario())
        self.assertEqual(result["snapshots"][1]["requests"]["R1"]["status"], "awaiting_confirmation")
        self.assertEqual(result["metrics"]["resolved"], 1)
        self.assertEqual(result["metrics"]["blocked_closures"], 0)

    def test_partial_report(self):
        value = completed_scenario()
        value["events"] = value["events"][:2]
        value["fixture_analysis"]["E2"]["observations"][0]["people_count"] = 2
        result = replay(value)
        self.assertEqual(result["metrics"]["resolved"], 0)
        self.assertTrue(any(a["code"] == "count_unreconciled" for a in result["final"]["alerts"]))

    def test_partial_or_missing_basis_count_blocks(self):
        for count in [2, None]:
            with self.subTest(count=count):
                value = completed_scenario()
                report = value["fixture_analysis"]["E2"]["observations"][0]
                if count is None:
                    del report["people_count"]
                else:
                    report["people_count"] = count
                result = replay(value)
                self.assertEqual(result["metrics"]["resolved"], 0)
                self.assertEqual(result["metrics"]["blocked_closures"], 1)

    def test_reports_never_auto_sum(self):
        value = completed_scenario()
        value["events"][2:3] = [event("E3", 2, channel="field"), confirmation("E4", 3, basis_event_ids=["E2", "E3"])]
        value["fixture_analysis"]["E2"]["observations"][0]["people_count"] = 2
        value["fixture_analysis"]["E3"] = observation("E3", "rescue_report", people_count=1)
        result = replay(value)
        self.assertEqual(result["metrics"]["resolved"], 0)
        self.assertEqual(result["metrics"]["blocked_closures"], 1)

    def test_stale_revision(self):
        value = completed_scenario()
        value["events"][2]["decision"]["expected_revision"] = 0
        result = replay(value)
        self.assertEqual(result["metrics"]["blocked_closures"], 1)
        self.assertEqual(result["metrics"]["resolved"], 0)

    def test_count_and_basis_block(self):
        for fields in ({"confirmed_count": 2}, {"confirmed_count": True}, {"expected_revision": True},
                       {"basis_event_ids": []}, {"basis_event_ids": ["E1"]}, {"basis_event_ids": ["FUTURE"]},
                       {"outcome": "transferred"}):
            with self.subTest(fields=fields):
                value = completed_scenario()
                value["events"][2]["decision"].update(fields)
                self.assertEqual(replay(value)["metrics"]["blocked_closures"], 1)

    def test_unknown_count_cannot_close(self):
        value = completed_scenario()
        del value["fixture_analysis"]["E1"]["observations"][0]["people_count"]
        self.assertEqual(replay(value)["metrics"]["resolved"], 0)

    def test_late_location_no_overwrite(self):
        value = scenario()
        value["events"] += [event("E2", 2, text="합성 근거"), event("E3", 3, occurred=1)]
        value["fixture_analysis"].update({"E2": observation("E2", "location_update", location_text="옥상"),
                                           "E3": observation("E3", "location_update", location_text="1층")})
        result = replay(value)
        self.assertEqual(result["final"]["requests"]["R1"]["location_text"], "옥상")
        self.assertEqual(result["final"]["requests"]["R1"]["revision"], 2)
        self.assertTrue(any(a["code"] == "late_location_ignored" for a in result["final"]["alerts"]))

    def test_post_resolution_location_and_late(self):
        for occurred, location, resolved in [(3, "옥상", 0), (0, "1층", 1)]:
            with self.subTest(occurred=occurred):
                value = completed_scenario()
                value["events"].append(event("E4", 3, occurred=occurred))
                value["fixture_analysis"]["E4"] = observation("E4", "location_update", location_text=location)
                result = replay(value)
                self.assertEqual(result["metrics"]["resolved"], resolved)

    def test_new_need_and_same_need_reopen(self):
        for need in ["추가 도움", "고립"]:
            value = completed_scenario()
            value["events"].append(event("E4", 3))
            value["fixture_analysis"]["E4"] = observation("E4", needs=[need])
            result = replay(value)
            self.assertEqual(result["metrics"]["resolved"], 0)
            self.assertEqual(result["final"]["requests"]["R1"]["revision"], 2 if need == "추가 도움" else 1)

    def test_count_correction_history(self):
        value = scenario()
        value["events"].append(event("E2", 1))
        value["fixture_analysis"]["E2"] = observation("E2", "count_correction", people_count=4)
        card = replay(value)["final"]["requests"]["R1"]
        self.assertEqual(card["people_count"], 4)
        self.assertEqual(card["revision"], 2)
        self.assertEqual(card["count_history"][1]["previous"], 3)

    def test_request_no_implicit_count_correction(self):
        value = scenario()
        value["events"].append(event("E2", 1, rid="R1"))
        value["fixture_analysis"]["E2"] = observation("E2", people_count=4)
        card = replay(value)["final"]["requests"]["R1"]
        self.assertEqual(card["people_count"], 3)
        self.assertEqual(card["revision"], 1)
        self.assertFalse(card["count_history"][1]["applied"])

    def test_duplicate_candidate_keeps_cards(self):
        value = scenario()
        value["events"] += [event("E2", 1, rid="R2"), event("E3", 2, channel="field")]
        value["fixture_analysis"].update({"E2": observation("E2", ids=["R2"], people_count=3),
                                           "E3": observation("E3", "duplicate_candidate", ids=["R1", "R2"])})
        result = replay(value)
        self.assertEqual(result["metrics"]["requests"], 2)
        self.assertEqual(result["final"]["requests"]["R2"]["canonical_id"], "R2")
        value["events"].append(event("E4", 3, channel="operator", decision={"kind": "link_duplicate", "request_id": "R1", "related_request_id": "R2"}))
        result = replay(value)
        self.assertEqual(result["metrics"]["requests"], 2)
        self.assertEqual(result["final"]["requests"]["R2"]["canonical_id"], "R1")

    def test_link_count_mismatch_block(self):
        value = scenario()
        value["events"] += [event("E2", 1, rid="R2"), event("E3", 2, channel="operator", decision={"kind": "link_duplicate", "request_id": "R1", "related_request_id": "R2"})]
        value["fixture_analysis"]["E2"] = observation("E2", ids=["R2"], people_count=2)
        result = replay(value)
        self.assertEqual(result["metrics"]["blocked_closures"], 1)
        self.assertEqual(result["final"]["requests"]["R2"]["canonical_id"], "R2")

    def test_ambiguous_report(self):
        value = scenario()
        value["events"] += [event("E2", 1, rid="R2"), event("E3", 2, channel="field")]
        value["fixture_analysis"].update({"E2": observation("E2", ids=["R2"], people_count=2),
                                           "E3": observation("E3", "rescue_report", ids=["R1", "R2"], people_count=2)})
        result = replay(value)
        self.assertEqual(result["metrics"]["resolved"], 0)
        self.assertTrue(any(a["code"] == "ambiguous_match" for a in result["final"]["alerts"]))

    def test_problem_never_resolves(self):
        for kind in ["unreadable_media", "location_conflict", "no_response", "delivery_failure"]:
            with self.subTest(kind=kind):
                value = scenario()
                value["events"].append(event("E2", 1, channel="system"))
                value["fixture_analysis"]["E2"] = observation("E2", kind)
                self.assertEqual(replay(value)["metrics"]["resolved"], 0)

    def test_attachment_evidence_and_gps_subject(self):
        value = scenario()
        value["events"][0].update(channel="app", text="",
                                 location={"latitude": 37.0, "longitude": 127.0, "accuracy_m": 5, "captured_at": "2026-10-08T10:00:00+09:00", "subject": "reporter"},
                                 attachments=[{"id": "A1", "media_type": "image", "description": "합성 근거", "transcript_source": "fixture", "captured_at": "2026-10-08T10:00:00+09:00", "readable": False}])
        result = replay(value)
        self.assertEqual(result["metrics"]["rejected_analyses"], 0)
        self.assertNotIn("latitude", result["final"]["requests"]["R1"])

    def test_expectations_all_operations(self):
        value = completed_scenario()
        value["expectations"] = [{"after": "E2", "path": "requests.R1.status", "equals": "awaiting_confirmation"},
                                 {"path": "requests", "length": 1},
                                 {"path": "requests.R1.evidence_event_ids", "contains": "E1"},
                                 {"path": "alerts", "not_contains_code": "analysis_rejected"}]
        self.assertTrue(replay(value)["passed"])

    def test_expectation_malformed_never_passes(self):
        for expected in [[], None, [{"path": "requests.R1.status"}], [{"path": "requests", "unknown": 1}],
                         [{"path": "missing", "equals": None}], [{"path": "requests", "length": True}],
                         [{"path": "requests", "length": 1, "equals": {}}],
                         [{"after": "missing", "path": "requests", "length": 1}],
                         [{"path": "alerts", "not_contains_code": "unused", "active": "yes"}]]:
            with self.subTest(expected=expected):
                value = scenario()
                value["expectations"] = expected
                self.assertFalse(replay(value)["passed"])

    def test_invalid_original_events(self):
        for update in [{"channel": "unknown"}, {"occurred_at": "2026-10-08T10:01:00+09:00"},
                       {"received_at": "2026-10-08T10:00:00"}, {"text": None},
                       {"decision": {"kind": "dispatch", "request_id": "R1"}}]:
            with self.subTest(update=update):
                value = scenario()
                value["events"][0].update(update)
                with self.assertRaises(ValueError):
                    replay(value)

    def test_nonmonotonic_and_duplicate(self):
        for next_event in [event("E1", 1), event("E2", 0, occurred=0)]:
            value = scenario()
            value["events"][0].update(occurred_at="2026-10-08T10:01:00+09:00", received_at="2026-10-08T10:01:00+09:00")
            value["events"].append(next_event)
            with self.assertRaises(ValueError):
                replay(value)

    def test_synthetic_and_mode(self):
        value = scenario()
        value["synthetic"] = False
        with self.assertRaises(ValueError):
            replay(value)
        with self.assertRaises(ValueError):
            replay(scenario(), "mixed")

    def test_deterministic(self):
        value = completed_scenario()
        self.assertEqual(replay(value), replay(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
