"""원문을 보존하면서 현재 필요한 담당자 판단을 파생하는 공개 규칙.

외부 모델, 임의 점수, 자동 우선도·배정·완료 변경은 사용하지 않는다.
각 근거는 해당 사건 보고의 실제 부분 문자열이다.
"""
from datetime import datetime, timezone
import re

LEVEL_ORDER = {"immediate": 0, "decision": 1, "follow_up": 2}
PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2}
TASK_ORDER = {"people": 0, "contact": 1, "location": 2, "reopened": 3, "assignment": 4}
CONTACT_TERMS = ("연락이 끊", "연락 두절", "연락두절", "무응답", "응답 없", "응답이 없",
                 "연락이 되지", "연락 안", "연락 불가", "연락되지", "응답하지")
PROXY_TERMS = ("GPS", "신고자 위치", "제 휴대폰 위치", "어머니 집이 아니", "대리 신고", "대리신고", "대신 신고")
NEGATIVE_CONFIRMATION = re.compile(r"(?:확인|구조|안전|연락|응답|대피).{0,12}(?:못|않|불가|안\s*됨)|(?:미확인|확인\s*불가)")
RESIDUAL = re.compile(r"(?:명|사람|대상|피해자|어머니|아버지|주민).{0,30}(?:남아|남았|남습니다|미구조)|(?:명|사람|대상|피해자).{0,15}만\s*(?:구조|확인|대피|인계)")
NO_RESIDUAL = re.compile(r"(?:미구조|미확인|남은|남아\s*있는)\s*(?:대상|인원|사람|피해자|주민)?\s*(?:은|는|이|가)?\s*(?:없(?:습니다|어요|음|다)?|0명|영\s*명)|남아\s*있지\s*않(?:습니다|아요|음)?")


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).timestamp()
    except (AttributeError, ValueError, TypeError):
        return None


def _count(value):
    return type(value) is int and value >= 0


def _evidence(report, term=None):
    text = report.get("text", "")
    if not isinstance(text, str) or not text:
        return None
    position = text.find(term) if term else 0
    start = max(0, position - 30)
    quote = text[start:start + 240]
    return {"report_id": report["id"], "quote": quote, "received_at": report["received_at"]}


def _contains(text, terms):
    return next((term for term in terms if term in text), None)


def _full_confirmation(report, people):
    text = NO_RESIDUAL.sub("", report.get("text", ""))
    if (report.get("kind") != "field" or not _count(report.get("people_count"))
            or not _count(people) or report["people_count"] != people
            or NEGATIVE_CONFIRMATION.search(text) or RESIDUAL.search(text)
            or _contains(text, CONTACT_TERMS)):
        return False
    # 숫자 필드만 일치하는 것으로 해소하지 않고 확인·안전·구조의 진술도 확인한다.
    return any(word in text for word in ("확인", "구조", "대피", "인계", "안전", "대면", "만났"))


def _after_reopen(incident, report):
    history = incident.get("outcome_history", [])
    if not history:
        return True
    previous = history[-1]
    if "report_ids_at_reopen" in previous:
        return report["id"] not in previous["report_ids_at_reopen"]
    reopened = _instant(previous.get("reopened_at"))
    received = _instant(report.get("received_at"))
    return reopened is None or (received is not None and (received > reopened or
                               received == reopened and report.get("kind") in {"additional", "correction"}))


def _latest_change(incident, field):
    times = []
    for item in incident.get("audit", []):
        before, after = item.get("before"), item.get("after")
        if (isinstance(before, dict) and isinstance(after, dict) and field in before and field in after
                and before[field] != after[field]):
            stamp = _instant(item.get("created_at"))
            if stamp is not None:
                times.append(stamp)
    return max(times, default=None)


def derive_attention(incident):
    """입력을 변경하지 않고 현재 원문 근거에서 담당자의 다음 업무만 반환한다."""
    if incident.get("status") == "closed":
        return []
    reports = incident.get("reports", [])
    active = [(index, report) for index, report in enumerate(reports) if _after_reopen(incident, report)]
    people = incident.get("people_count")
    entries = []

    def add(suffix, level, title, situation, reason, next_action, action, basis):
        evidence, used = [], set()
        for report in basis:
            item = _evidence(report)
            if item and item["report_id"] not in used:
                evidence.append(item)
                used.add(item["report_id"])
        entries.append({"id": f"{incident['id']}:{suffix}", "level": level, "title": title,
                        "situation": situation, "reason": reason, "next_action": next_action,
                        "action": action, "source": "rule", "requires_human": True, "evidence": evidence})

    correction_index = max((i for i, r in active if r.get("kind") == "correction" and "people_count" in r), default=-1)
    count_changed_at = _latest_change(incident, "people_count")
    def after_count_change(index, report, include_correction=False):
        if index < correction_index or (index == correction_index and not include_correction):
            return False
        received = _instant(report.get("received_at"))
        # 정정 원문은 그 변경 시점에도 남은 대상을 언급할 수 있다.
        if include_correction and index == correction_index:
            return True
        return count_changed_at is None or (received is not None and received > count_changed_at)

    fields = [(i, r) for i, r in active if r.get("kind") == "field" and after_count_change(i, r)]
    latest_field = fields[-1][1] if fields else None
    full = [(i, r) for i, r in fields if _full_confirmation(r, people)]
    latest_full_index = full[-1][0] if full else -1
    residual = [(i, r) for i, r in active if after_count_change(i, r, True) and i > latest_full_index
                and RESIDUAL.search(NO_RESIDUAL.sub("", r.get("text", "")))]
    conflicts = [(i, r) for i, r in active if r.get("kind") == "additional" and _count(r.get("people_count"))
                 and r["people_count"] != people and after_count_change(i, r)]

    count_basis = [r for _, r in conflicts]
    count_reason, count_situation, count_level = [], [], "decision"
    if residual:
        count_level = "immediate"
        count_basis.append(residual[-1][1])
        count_situation.append("최신 원문에 남은 대상의 상태 확인이 필요한 내용이 있습니다.")
        count_reason.append("남은 대상의 현재 상태를 현장에서 확인해야 합니다.")
    if _count(people) and latest_field and _count(latest_field.get("people_count")):
        reported = latest_field["people_count"]
        if reported < people:
            count_level = "immediate"
            count_basis = [latest_field] + [r for _, r in conflicts]
            count_situation = [f"접수 {people}명 / 현장 확인 {reported}명입니다."]
            count_reason = [f"{people - reported}명의 상태가 미확인입니다. 남은 대상의 현장 확인이 필요합니다."]
        elif reported > people:
            count_basis.append(latest_field)
            count_situation.append(f"접수 {people}명과 현장 보고 {reported}명이 충돌합니다.")
            count_reason.append("확인 대상 총수의 명시 정정이 필요합니다. 여러 보고의 인원을 합산하지 않습니다.")
        elif NEGATIVE_CONFIRMATION.search(NO_RESIDUAL.sub("", latest_field["text"])) and not _contains(latest_field["text"], CONTACT_TERMS):
            count_basis.append(latest_field)
            count_situation.append("보고 인원은 접수 인원과 같지만 원문에 상태를 확인하지 못했다고 기록되어 있습니다.")
            count_reason.append("전체 대상의 현재 상태를 현장에서 다시 확인해야 합니다.")
    if conflicts:
        count_situation.append("추가 정보의 인원이 현재 접수 인원과 다릅니다.")
        count_reason.append("새 인원 정보를 공식 접수 인원에 자동 반영하지 않았습니다. 전체 대상과 정정 근거를 확인하세요.")
    if not _count(people):
        count_basis.extend([active[-1][1]] if active else [])
        count_situation.append("현재 접수 인원이 알려지지 않았습니다.")
        count_reason.append("확인할 전체 인원을 모르면 현장 보고와 처리 결과를 대조할 수 없습니다.")
    if count_reason:
        add("people", count_level, "전체 대상 인원·현재 상태 대조", " ".join(count_situation), " ".join(count_reason),
            "전체 대상과 남은 인원을 현장에서 확인하고, 필요하면 인원 정정 원문을 등록하세요.", "field-report", count_basis)

    contact = [(i, r) for i, r in active if _contains(r.get("text", ""), CONTACT_TERMS)]
    if contact:
        index, report = contact[-1]
        resolved = any(i > index and _full_confirmation(r, people)
                       and any(term in r["text"] for term in ("현장", "직접", "대면", "대상", "연락 재개", "연락이 닿", "통화", "응답 확인"))
                       for i, r in fields)
        if not resolved:
            if count_reason:
                entries[0]["reason"] += " 연락 두절 신고도 있어 현재 안부를 현장에서 확인해야 합니다."
                item = _evidence(report)
                if item and item["report_id"] not in {e["report_id"] for e in entries[0]["evidence"]}:
                    entries[0]["evidence"].append(item)
            else:
                add("contact", "decision", "연락 두절 대상의 현재 상태 확인", "원문에 연락 두절 또는 무응답이 신고되어 있습니다.",
                    "현재 안부는 후속 현장 확인이 필요합니다.",
                    "구조 대상과 현장 확인을 대조한 새 보고를 등록하세요.", "field-report", [report])

    location_correction_index = max((i for i, r in active if r.get("kind") == "correction" and "location" in r), default=-1)
    location_changed_at = _latest_change(incident, "location")
    proxies = []
    for index, report in active:
        received = _instant(report.get("received_at"))
        if (index > location_correction_index and _contains(report.get("text", ""), PROXY_TERMS)
                and (location_changed_at is None or received is not None and received > location_changed_at)):
            proxies.append(report)
    if proxies:
        add("location", "decision", "신고자 위치와 구조 대상 위치 구분", "대리 신고 또는 휴대폰 위치의 대상 구분이 필요한 원문이 있습니다.",
            "구조 대상 주소와 신고자 휴대폰 위치를 대조해야 합니다.",
            "대상 위치를 확인하고 명시 위치 정정 정보를 등록하세요.", "report", [proxies[-1]])

    if incident.get("outcome_history") and not full:
        # 같은 원인의 잔여 인원·재개 경고는 people 과제에 묶는다.
        if count_reason:
            entries[0]["reason"] += " 재개 이후 전체 대상을 확인한 새 현장 근거가 필요합니다."
        else:
            add("reopened", "decision", "재개 이후 새 현장 근거 확인", "완료 결과를 보존하고 사건을 다시 확인 상태로 열었습니다.",
                "재개 전 현장 보고는 현재 확인을 대신할 수 없습니다. 새 정보 이후 전체 대상의 확인이 필요합니다.",
                "재개 이후 현장에서 확인한 대상과 인원을 보고로 등록하세요.", "field-report", [r for _, r in active][-1:])

    if not incident.get("assigned_team_id"):
        priority = incident.get("priority", "normal")
        level = "immediate" if priority == "urgent" else "decision" if priority == "high" else "follow_up"
        add("assignment", level, "대응팀 배정 판단", f"담당자 우선도는 { {'urgent': '긴급', 'high': '높음', 'normal': '보통'}.get(priority, priority) }이고 담당팀은 미배정입니다.",
            "현재 신고 상황과 가용팀을 대조해 담당자가 배정 여부를 판단해야 합니다.",
            "가용팀과 사건 정보를 확인한 뒤 담당팀·진행을 지정하세요.", "progress", [r for _, r in active][:1] or reports[:1])
    return sorted(entries, key=lambda item: (LEVEL_ORDER[item["level"]],
                                            TASK_ORDER[item["id"].rsplit(":", 1)[-1]], item["id"]))


def attention_sort_key(incident):
    levels = [LEVEL_ORDER[item["level"]] for item in incident.get("attention", [])]
    created = _instant(incident.get("created_at"))
    return (min(levels, default=3), PRIORITY_ORDER.get(incident.get("priority"), 2),
            created if created is not None else float("inf"), incident.get("id", ""))
