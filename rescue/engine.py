"""합성 구조 요청을 근거와 담당자 확인으로 재생하는 결정적 엔진.

fixture는 수작업 분석이며, live 출력 누락에는 fixture를 사용하지 않는다.
잘못된 시나리오/원본은 ValueError, 잘못된 분석은 보존된 원본과 거절 알림으로
표현한다. 입력 객체는 변경하지 않는다.
"""

from copy import deepcopy
from datetime import datetime
import math


CHANNELS = {"sms", "mms", "app", "video_call", "web", "field", "operator", "system"}
KINDS = {
    "request", "location_update", "count_correction", "rescue_report", "safe_report",
    "duplicate_candidate", "unreadable_media", "location_conflict", "no_response",
    "delivery_failure",
}
OBSERVATION_FIELDS = {
    "kind", "request_ids", "people_count", "location_text", "needs", "evidence_quote",
}
PROBLEM_KINDS = {"unreadable_media", "location_conflict", "no_response", "delivery_failure"}


def _time(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}: 시간대가 있는 ISO 8601 문자열이 필요합니다")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: 잘못된 ISO 8601 시각입니다") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label}: 시간대가 필요합니다")
    return parsed


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _ids(value):
    return (isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
            and len(value) == len(set(value)))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_event(event, previous_received, seen):
    if not isinstance(event, dict):
        raise ValueError("이벤트는 객체여야 합니다")
    for key in ("id", "channel", "actor", "occurred_at", "received_at", "text"):
        if key not in event or not isinstance(event[key], str):
            raise ValueError(f"이벤트의 {key} 문자열이 필요합니다")
    eid = event["id"]
    if not eid.strip() or eid in seen:
        raise ValueError("이벤트 ID는 비어 있지 않고 고유해야 합니다")
    if event["channel"] not in CHANNELS:
        raise ValueError(f"{eid}: 알 수 없는 입력 채널입니다")
    occurred = _time(event["occurred_at"], f"{eid}.occurred_at")
    received = _time(event["received_at"], f"{eid}.received_at")
    if occurred > received:
        raise ValueError(f"{eid}: 사건 시각이 수신 시각보다 늦습니다")
    if previous_received is not None and received < previous_received:
        raise ValueError(f"{eid}: 수신 시각은 비감소 순서여야 합니다")
    for key in ("request_id", "building_id"):
        if key in event and (not isinstance(event[key], str) or not event[key].strip()):
            raise ValueError(f"{eid}.{key}: 비어 있지 않은 문자열이 필요합니다")
    if "candidate_request_ids" in event and not _ids(event["candidate_request_ids"]):
        raise ValueError(f"{eid}: 후보 요청 ID 배열이 잘못되었습니다")
    attachments = event.get("attachments", [])
    if not isinstance(attachments, list):
        raise ValueError(f"{eid}: 첨부는 배열이어야 합니다")
    attachment_ids = set()
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise ValueError(f"{eid}: 첨부는 객체여야 합니다")
        for key in ("id", "media_type", "description", "transcript_source", "captured_at", "readable"):
            if key not in attachment:
                raise ValueError(f"{eid}: 첨부의 {key}가 누락되었습니다")
        if (not isinstance(attachment["id"], str) or not attachment["id"].strip()
                or attachment["id"] in attachment_ids):
            raise ValueError(f"{eid}: 첨부 ID가 잘못되었습니다")
        attachment_ids.add(attachment["id"])
        if not isinstance(attachment["media_type"], str) or attachment["media_type"] not in {"image", "video"}:
            raise ValueError(f"{eid}: 알 수 없는 첨부 종류입니다")
        if not isinstance(attachment["description"], str):
            raise ValueError(f"{eid}: 첨부 설명은 문자열이어야 합니다")
        if "transcript" in attachment and not isinstance(attachment["transcript"], str):
            raise ValueError(f"{eid}: 첨부 기록은 문자열이어야 합니다")
        if not isinstance(attachment["transcript_source"], str) or attachment["transcript_source"] not in {"fixture", "human", "model"}:
            raise ValueError(f"{eid}: 첨부 기록 출처가 잘못되었습니다")
        if not isinstance(attachment["readable"], bool):
            raise ValueError(f"{eid}: 첨부 판독 가능 여부는 bool이어야 합니다")
        _time(attachment["captured_at"], f"{eid}.첨부.captured_at")
    if "location" in event:
        loc = event["location"]
        if not isinstance(loc, dict) or not {"latitude", "longitude", "accuracy_m", "captured_at", "subject"} <= loc.keys():
            raise ValueError(f"{eid}: 위치 메타데이터가 잘못되었습니다")
        if (not _number(loc["latitude"]) or not -90 <= loc["latitude"] <= 90
                or not _number(loc["longitude"]) or not -180 <= loc["longitude"] <= 180
                or not _number(loc["accuracy_m"]) or loc["accuracy_m"] < 0):
            raise ValueError(f"{eid}: 위치 좌표 또는 정확도가 잘못되었습니다")
        if not isinstance(loc["subject"], str) or loc["subject"] not in {"reporter", "victim", "unknown"}:
            raise ValueError(f"{eid}: 위치 대상이 잘못되었습니다")
        _time(loc["captured_at"], f"{eid}.location.captured_at")
    if "decision" in event and (event["channel"] != "operator" or not event["actor"].strip()):
        raise ValueError(f"{eid}: 결정에는 담당자 채널과 담당자가 필요합니다")
    return received


def _validate_analysis(analysis, event, allowed_ids):
    if not isinstance(analysis, dict):
        raise ValueError("분석 출력이 없거나 객체가 아닙니다")
    if set(analysis) != {"event_id", "observations"}:
        raise ValueError("분석 필드가 누락되었거나 알 수 없는 필드가 있습니다")
    if analysis["event_id"] != event["id"]:
        raise ValueError("분석 event_id가 원본과 다릅니다")
    observations = analysis["observations"]
    if not isinstance(observations, list):
        raise ValueError("observations는 배열이어야 합니다")
    sources = [event["text"]]
    for attachment in event.get("attachments", []):
        sources.extend([attachment["description"], attachment.get("transcript", "")])
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) - OBSERVATION_FIELDS:
            raise ValueError("관찰에 알 수 없는 필드가 있습니다")
        if not {"kind", "request_ids", "evidence_quote"} <= observation.keys():
            raise ValueError("관찰 종류, 요청 ID, 원문 근거가 필요합니다")
        kind = observation["kind"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError("알 수 없는 관찰 종류입니다")
        ids = observation["request_ids"]
        if not _ids(ids) or any(rid not in allowed_ids for rid in ids):
            raise ValueError("아직 접수되지 않았거나 잘못된 요청 ID입니다")
        if not ids and kind not in PROBLEM_KINDS:
            raise ValueError("관찰에 대상 요청 ID가 필요합니다")
        if kind == "duplicate_candidate" and len(ids) < 2:
            raise ValueError("중복 후보에는 두 개 이상의 요청 ID가 필요합니다")
        if "people_count" in observation and not _count(observation["people_count"]):
            raise ValueError("인원은 0 이상의 정수여야 합니다")
        if kind == "count_correction" and "people_count" not in observation:
            raise ValueError("인원 정정에 정정 인원이 필요합니다")
        if "location_text" in observation and not isinstance(observation["location_text"], str):
            raise ValueError("위치 진술은 문자열이어야 합니다")
        if kind == "location_update" and not observation.get("location_text", "").strip():
            raise ValueError("위치 변경에는 위치 진술이 필요합니다")
        needs = observation.get("needs", [])
        if not isinstance(needs, list) or not all(isinstance(n, str) and n.strip() for n in needs):
            raise ValueError("필요 정보는 비어 있지 않은 문자열 배열이어야 합니다")
        quote = observation["evidence_quote"]
        if not isinstance(quote, str) or not quote.strip() or not any(quote in source for source in sources):
            raise ValueError("근거 인용이 원문 또는 첨부 설명/기록에 없습니다")
    return observations


def _card(rid, event):
    return {
        "id": rid, "building_id": event.get("building_id"), "people_count": None,
        "location_text": None, "location_occurred_at": None, "needs": [],
        "status": "open", "revision": 1, "outcome": None, "canonical_id": rid,
        "evidence_event_ids": [event["id"]], "count_history": [], "location_history": [],
    }


def _alert(state, code, ids, eid, message, question):
    state["alerts"].append({
        "code": code, "request_ids": list(ids), "event_ids": [eid],
        "message": message, "question": question, "active": True,
    })


def _deactivate(state, rid, codes=None):
    for alert in state["alerts"]:
        if rid in alert["request_ids"] and (codes is None or alert["code"] in codes):
            # 다른 후보가 남아 있는 알림은 그 후보도 확인될 때까지 유지한다.
            if len(alert["request_ids"]) > 1 and codes is None:
                if any(state["requests"][other]["status"] != "resolved" for other in alert["request_ids"]):
                    continue
            alert["active"] = False


def _changed(state, card, event, start_revisions, changed_ids):
    rid = card["id"]
    if rid in start_revisions and rid not in changed_ids:
        card["revision"] += 1
    changed_ids.add(rid)
    _reopen_after_update(state, card, event)


def _reopen_after_update(state, card, event):
    rid = card["id"]
    if card["status"] == "resolved":
        card["status"] = "open"
        card["outcome"] = None
        card.pop("resolution", None)
        _alert(state, "post_resolution_update", [rid], event["id"],
               "완료 이후 새 정보가 도착하여 다시 확인합니다.", "새 위치·인원·도움 요청을 담당자가 확인했나요?")


def _observe(state, observation, event, start_revisions, changed_ids, reports):
    ids, kind, eid = observation["request_ids"], observation["kind"], event["id"]
    for rid in ids:
        card = state["requests"][rid]
        if eid not in card["evidence_event_ids"]:
            card["evidence_event_ids"].append(eid)
    if kind in PROBLEM_KINDS:
        wording = {
            "unreadable_media": ("첨부 내용을 판독할 수 없습니다.", "원문 또는 담당자 확인으로 내용을 보완했나요?"),
            "location_conflict": ("위치 진술이 충돌하여 확인이 필요합니다.", "구조 대상의 현재 위치를 확인했나요?"),
            "no_response": ("연락 응답을 확인하지 못했습니다.", "다른 근거로 현재 상태를 확인했나요?"),
            "delivery_failure": ("전송 실패가 기록되었습니다.", "요청 수신과 현재 상태를 별도로 확인했나요?"),
        }
        _alert(state, kind, ids, eid, *wording[kind])
        return
    if kind == "duplicate_candidate":
        _alert(state, "duplicate_review", ids, eid,
               "동일인·가구일 수 있으나 원본 요청을 유지합니다.", "담당자가 개별 원문과 인원을 확인한 뒤 연결했나요?")
        return
    if kind in {"rescue_report", "safe_report"}:
        reports.setdefault(eid, []).append(deepcopy(observation))
        if len(ids) > 1:
            _alert(state, "ambiguous_match", ids, eid,
                   "현장 보고가 여러 요청의 후보여서 개별 확인이 필요합니다.", "보고가 어느 요청의 누구를 가리키는지 확인했나요?")
        for rid in ids:
            card = state["requests"][rid]
            if card["status"] != "resolved":
                card["status"] = "awaiting_confirmation"
            reported = observation.get("people_count")
            if card["people_count"] is None or reported is None or reported != card["people_count"]:
                _alert(state, "count_unreconciled", [rid], eid,
                       "접수 인원과 보고 인원의 대조가 끝나지 않았습니다.", "개별 요청의 접수 인원과 현장 확인 인원이 일치하나요?")
        return
    for rid in ids:
        card = state["requests"][rid]
        if kind in {"request", "count_correction"} and "people_count" in observation:
            value, previous = observation["people_count"], card["people_count"]
            history = {"event_id": eid, "occurred_at": event["occurred_at"], "kind": kind,
                       "previous": previous, "proposed": value, "applied": True}
            if kind == "request" and previous is not None and previous != value:
                history["applied"] = False
                _alert(state, "count_unreconciled", [rid], eid,
                       "추가 신고의 인원이 기존 접수와 달라 정정 확인이 필요합니다.", "명시적인 인원 정정 근거를 확인했나요?")
                if card["status"] == "resolved":
                    # 묵시적 인원 교체는 거절하되 완료 후 새 인원 신고는 다시 확인한다.
                    _reopen_after_update(state, card, event)
            elif previous != value:
                card["people_count"] = value
                _changed(state, card, event, start_revisions, changed_ids)
            card["count_history"].append(history)
        if kind in {"request", "location_update"} and observation.get("location_text"):
            proposed = observation["location_text"]
            current_at = card["location_occurred_at"]
            older = current_at is not None and _time(event["occurred_at"], eid) < _time(current_at, rid)
            conflict = (current_at is not None and _time(event["occurred_at"], eid) == _time(current_at, rid)
                        and proposed != card["location_text"])
            card["location_history"].append({"event_id": eid, "occurred_at": event["occurred_at"],
                                             "location_text": proposed, "applied": not older and not conflict})
            if older:
                _alert(state, "late_location_ignored", [rid], eid,
                       "늦게 도착한 옛 위치 진술을 이력에 남기고 현재 위치를 유지합니다.", "현재 위치를 더 최신 근거로 확인했나요?")
            elif conflict:
                _alert(state, "location_conflict", [rid], eid,
                       "같은 사건 시각에 서로 다른 위치가 제시되었습니다.", "어느 위치 진술이 현재 상태에 해당하는지 확인했나요?")
            else:
                if card["location_text"] != proposed:
                    card["location_text"] = proposed
                    _changed(state, card, event, start_revisions, changed_ids)
                card["location_occurred_at"] = event["occurred_at"]
        if kind == "request" and "needs" in observation:
            new_needs = list(dict.fromkeys(card["needs"] + observation["needs"]))
            # 완료 이후 같은 도움 요청이 다시 들어와도 현재 안전은 재확인한다.
            if new_needs != card["needs"]:
                card["needs"] = new_needs
                _changed(state, card, event, start_revisions, changed_ids)
            elif card["status"] == "resolved" and observation["needs"]:
                _reopen_after_update(state, card, event)


def _decision(state, event, reports):
    decision, eid = event["decision"], event["id"]

    def block(message, ids=()):
        _alert(state, "closure_blocked", ids, eid, message, "담당자·대상·인원·현재 revision·도착한 근거를 다시 확인했나요?")
        return {"accepted": False, "reason": message}

    if not isinstance(decision, dict):
        return block("담당자 결정은 객체여야 합니다.")
    kind = decision.get("kind")
    fields = {
        "confirm_outcome": {"kind", "request_id", "outcome", "confirmed_count", "basis_event_ids", "expected_revision"},
        "dispatch": {"kind", "request_id"},
        "reopen": {"kind", "request_id", "reason"},
        "link_duplicate": {"kind", "request_id", "related_request_id"},
    }
    rid = decision.get("request_id")
    ids = [rid] if isinstance(rid, str) and rid in state["requests"] else []
    if not isinstance(kind, str) or kind not in fields or set(decision) != fields[kind]:
        return block("담당자 결정의 종류 또는 필드가 잘못되었습니다.", ids)
    if not ids:
        return block("담당자 결정의 요청 ID가 접수되지 않았습니다.")
    card = state["requests"][rid]
    if kind == "dispatch":
        card.setdefault("dispatch_event_ids", []).append(eid)
        if card["status"] == "open":
            card["status"] = "dispatched"
    elif kind == "reopen":
        if not isinstance(decision["reason"], str) or not decision["reason"].strip():
            return block("재확인 사유가 필요합니다.", ids)
        if card["status"] != "resolved":
            return block("완료된 요청만 다시 열 수 있습니다.", ids)
        card["status"], card["outcome"] = "open", None
        card.pop("resolution", None)
        _alert(state, "post_resolution_update", ids, eid,
               "담당자가 완료 요청을 다시 확인 상태로 열었습니다.", decision["reason"])
    elif kind == "link_duplicate":
        other = decision["related_request_id"]
        if not isinstance(other, str) or other not in state["requests"] or other == rid:
            return block("연결할 다른 요청 ID가 잘못되었습니다.", ids)
        group = [c for c in state["requests"].values()
                 if c["canonical_id"] in {card["canonical_id"], state["requests"][other]["canonical_id"]}]
        ids = [c["id"] for c in group]
        resolved = {c["status"] == "resolved" for c in group}
        counts = {c["people_count"] for c in group if c["people_count"] is not None}
        if len(resolved) > 1 or len(counts) > 1:
            return block("완료 여부 또는 알려진 인원이 다른 요청은 연결할 수 없습니다.", ids)
        canonical = card["canonical_id"]
        for item in group:
            item["canonical_id"] = canonical
        for alert in state["alerts"]:
            if alert["code"] == "duplicate_review" and set(alert["request_ids"]) <= set(ids):
                alert["active"] = False
    else:
        revision = decision["expected_revision"]
        if not _count(revision) or revision != card["revision"]:
            return block("완료 승인의 revision이 현재 카드와 다릅니다.", ids)
        if card["people_count"] is None or not _count(decision["confirmed_count"]) or decision["confirmed_count"] != card["people_count"]:
            return block("확인 인원이 알려진 현재 접수 인원과 일치해야 합니다.", ids)
        outcome = decision["outcome"]
        if not isinstance(outcome, str) or outcome not in {"rescued", "self_evacuated", "transferred"}:
            return block("알 수 없는 완료 결과입니다.", ids)
        basis = decision["basis_event_ids"]
        if not _ids(basis) or not basis:
            return block("이미 도착한 구조 또는 안전 보고 근거가 필요합니다.", ids)
        desired = "rescue_report" if outcome == "rescued" else "safe_report"
        for bid in basis:
            matching = [r for r in reports.get(bid, []) if rid in r["request_ids"] and r["kind"] == desired]
            if not matching:
                return block("완료 근거가 도착하지 않았거나 대상·보고 종류가 다릅니다.", ids)
            if not any(r.get("people_count") == decision["confirmed_count"] for r in matching):
                return block("근거 보고의 확인 인원이 현재 확정 인원과 일치해야 합니다. 복수 보고 인원은 합산하지 않습니다.", ids)
        card["status"], card["outcome"] = "resolved", outcome
        card["resolution"] = {"event_id": eid, "actor": event["actor"], "confirmed_count": decision["confirmed_count"],
                              "basis_event_ids": list(basis), "revision": revision}
        _deactivate(state, rid)
    if eid not in card["evidence_event_ids"]:
        card["evidence_event_ids"].append(eid)
    return {"accepted": True, "kind": kind}


def _path(snapshot, path):
    if not isinstance(path, str) or not path:
        return False, None
    value = snapshot
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _checks(expectations, snapshots, final):
    by_event = {snap["event_id"]: snap for snap in snapshots}
    if not isinstance(expectations, list) or not expectations:
        return [{"label": "기대값 누락", "passed": False, "expected": "한 개 이상의 기대값 assertion", "actual": expectations, "after": None}]
    result = []
    operations = {"equals", "contains_code", "not_contains_code", "length", "contains"}
    for expectation in expectations:
        check = {"label": "잘못된 기대값", "passed": False, "expected": deepcopy(expectation), "actual": None, "after": None}
        if not isinstance(expectation, dict):
            result.append(check)
            continue
        check["label"] = expectation.get("label", "이름 없는 기대값")
        check["after"] = expectation.get("after")
        ops = operations & expectation.keys()
        permitted = {"after", "path", "label"} | ops
        if "contains_code" in ops or "not_contains_code" in ops:
            permitted.add("active")
        if len(ops) != 1 or set(expectation) - permitted or "path" not in expectation:
            result.append(check)
            continue
        snapshot = final if "after" not in expectation else by_event.get(expectation["after"]) if isinstance(expectation["after"], str) else None
        if snapshot is None:
            result.append(check)
            continue
        exists, actual = _path(snapshot, expectation["path"])
        check["actual"] = deepcopy(actual)
        op = next(iter(ops))
        expected = expectation[op]
        check["expected"] = {op: deepcopy(expected)}
        if "active" in expectation:
            check["expected"]["active"] = expectation["active"]
        if exists:
            if op == "equals":
                check["passed"] = type(actual) is type(expected) and actual == expected
            elif op == "length":
                check["passed"] = _count(expected) and isinstance(actual, (list, dict, str)) and len(actual) == expected
            elif op == "contains":
                if isinstance(actual, list):
                    check["passed"] = any(type(item) is type(expected) and item == expected for item in actual)
                elif isinstance(actual, (dict, str)) and isinstance(expected, str):
                    check["passed"] = expected in actual
            elif isinstance(actual, list) and isinstance(expected, str):
                if "active" not in expectation or isinstance(expectation["active"], bool):
                    matches = any(isinstance(a, dict) and a.get("code") == expected
                                  and ("active" not in expectation or a.get("active") is expectation["active"]) for a in actual)
                    check["passed"] = matches if op == "contains_code" else not matches
        result.append(check)
    return result


def replay(scenario: dict, mode: str = "fixture", analyses: dict | None = None) -> dict:
    """계약 v1 시나리오를 배열 수신 순서로 재생하고 분리된 검증 결과를 반환한다."""
    if not isinstance(mode, str) or mode not in {"fixture", "live"}:
        raise ValueError("분석 모드는 fixture 또는 live여야 합니다")
    if not isinstance(scenario, dict) or scenario.get("synthetic") is not True:
        raise ValueError("synthetic=true 합성 시나리오만 재생합니다")
    if type(scenario.get("schema_version")) is not int or scenario["schema_version"] != 1:
        raise ValueError("지원하는 schema_version은 1입니다")
    if not isinstance(scenario.get("id"), str) or not scenario["id"].strip():
        raise ValueError("시나리오 ID가 필요합니다")
    events = scenario.get("events")
    if not isinstance(events, list):
        raise ValueError("시나리오 events 배열이 필요합니다")
    if analyses is not None and not isinstance(analyses, dict):
        raise ValueError("analyses는 이벤트 ID 매핑이어야 합니다")
    source = analyses if analyses is not None else scenario.get("fixture_analysis", {}) if mode == "fixture" else {}
    if not isinstance(source, dict):
        raise ValueError("분석 결과는 이벤트 ID 매핑이어야 합니다")
    state = {"event_id": None, "requests": {}, "alerts": [], "audit": []}
    snapshots, seen, reports = [], set(), {}
    previous_received = None
    for event in events:
        previous_received = _validate_event(event, previous_received, seen)
        eid = event["id"]
        seen.add(eid)
        state["event_id"] = eid
        start_revisions = {rid: c["revision"] for rid, c in state["requests"].items()}
        changed_ids = set()
        rid = event.get("request_id")
        if rid is not None:
            if rid not in state["requests"]:
                state["requests"][rid] = _card(rid, event)
            else:
                card = state["requests"][rid]
                if eid not in card["evidence_event_ids"]:
                    card["evidence_event_ids"].append(eid)
        audit = {"event_id": eid, "original": deepcopy(event), "analysis_status": "not_required"}
        state["audit"].append(audit)
        if "decision" in event:
            audit["decision"] = _decision(state, event, reports)
        # 명시적인 분석 또는 담당자 결정 외의 원본에는 분석 결과를 요구한다.
        if eid in source or "decision" not in event:
            try:
                observations = _validate_analysis(source.get(eid), event, set(state["requests"]))
            except ValueError as exc:
                audit["analysis_status"] = "rejected"
                audit["analysis_error"] = str(exc)
                audit["analysis"] = deepcopy(source.get(eid))
                affected = [rid] if rid is not None else [candidate for candidate in event.get("candidate_request_ids", []) if candidate in state["requests"]]
                _alert(state, "analysis_rejected", affected, eid, f"분석을 거절했습니다: {exc}", "원문 근거와 접수된 ID로 분석을 보완했나요?")
            else:
                audit["analysis_status"] = "accepted"
                audit["analysis"] = deepcopy(source[eid])
                for observation in observations:
                    _observe(state, observation, event, start_revisions, changed_ids, reports)
        snapshots.append(deepcopy(state))
    final = deepcopy(state)
    checks = _checks(scenario.get("expectations"), snapshots, final)
    resolved = sum(card["status"] == "resolved" for card in final["requests"].values())
    metrics = {
        "events": len(events), "requests": len(final["requests"]), "resolved": resolved,
        "unresolved": len(final["requests"]) - resolved,
        "active_alerts": sum(alert["active"] for alert in final["alerts"]),
        "rejected_analyses": sum(a["analysis_status"] == "rejected" for a in final["audit"]),
        "blocked_closures": sum(alert["code"] == "closure_blocked" for alert in final["alerts"]),
    }
    return {"scenario_id": scenario["id"], "mode": mode, "synthetic": True,
            "snapshots": snapshots, "final": final, "checks": checks,
            "passed": all(check["passed"] for check in checks), "metrics": metrics}
