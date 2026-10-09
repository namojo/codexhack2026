"""SQLite 사건 저장소. 원문은 추가만 하며 담당자 변경과 결과를 감사한다."""
import base64
import binascii
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote
import uuid

from service.attention import derive_attention, attention_sort_key, _instant, _full_confirmation, _after_reopen, NEGATIVE_CONFIRMATION, RESIDUAL, NO_RESIDUAL, CONTACT_TERMS

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = {"voice", "sms", "mms", "app", "video_call", "web", "field", "kakao"}
STATUSES = {"received", "dispatched", "on_scene", "rescuing", "reviewing", "closed"}
DEFAULT_ACTOR = "상황실 김담당"
MEDIA = {"image/png": ("image", ".png"), "image/jpeg": ("image", ".jpg"),
         "audio/wav": ("audio", ".wav"), "audio/mpeg": ("audio", ".mp3"), "video/mp4": ("video", ".mp4")}
MAX_UPLOAD = 8 * 1024 * 1024


class APIError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = self.status_code = status


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def count(value, label="인원"):
    if type(value) is not int or value < 0:
        raise APIError(400, f"{label}은 0 이상의 정수여야 합니다.")
    return value


def string(value, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > 20000:
        raise APIError(400, f"{label}은 {'문자열' if empty else '비어 있지 않은 문자열'}이어야 합니다.")
    return value


def enum(value, choices, label):
    if not isinstance(value, str) or value not in choices:
        raise APIError(400, f"{label} 값이 올바르지 않습니다.")
    return value


def body_fields(body, allowed, required):
    if not isinstance(body, dict):
        raise APIError(400, "JSON 객체가 필요합니다.")
    if set(body) - set(allowed):
        raise APIError(400, "알 수 없는 입력 필드가 있습니다.")
    if set(required) - set(body):
        raise APIError(400, "필수 입력 필드가 누락되었습니다.")


def media_mime(path):
    suffix = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mp4": "video/mp4"}.get(suffix)


def valid_header(data, mime):
    if mime == "image/png":
        return len(data) >= 33 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    if mime == "image/jpeg":
        return len(data) >= 4 and data[:3] == b"\xff\xd8\xff" and data[-2:] == b"\xff\xd9"
    if mime == "audio/wav":
        return len(data) >= 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE" and b"fmt " in data and b"data" in data
    if mime == "audio/mpeg":
        return len(data) >= 10 and (data[:3] == b"ID3" or data[0] == 255 and data[1] & 224 == 224)
    if mime == "video/mp4":
        return len(data) >= 16 and data[4:8] == b"ftyp" and int.from_bytes(data[:4], "big") >= 16
    return False


class Store:
    def __init__(self, db_path, seed_path=ROOT / "data" / "seed.json"):
        self.db_path = str(db_path)
        self.seed_path = Path(seed_path)
        if self.db_path == ":memory:":
            raise APIError(400, "영속 저장소 파일 경로가 필요합니다.")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            if not db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                try:
                    seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise APIError(503, "합성 초기 데이터를 읽을 수 없습니다.") from exc
                if not isinstance(seed, dict) or seed.get("synthetic") is not True:
                    raise APIError(400, "합성 초기 데이터만 사용할 수 있습니다.")
                if not isinstance(seed.get("incidents"), list) or not isinstance(seed.get("resources"), list):
                    raise APIError(400, "초기 사건과 팀 배열이 필요합니다.")
                for resource in seed["resources"]:
                    self._validate_resource(resource)
                    self._put(db, "resources", resource)
                for incident in seed["incidents"]:
                    self._validate_seed(incident)
                    self._put(db, "incidents", incident)
                for resource in self._all(db, "resources"):
                    if resource["incident_id"] is not None:
                        incident = self._get(db, resource["incident_id"])
                        if incident["assigned_team_id"] != resource["id"] or incident["status"] == "closed":
                            raise APIError(400, "초기 팀 배정과 사건 상태가 일치하지 않습니다.")
                for incident in self._all(db, "incidents"):
                    if incident["assigned_team_id"]:
                        team = self._team(db, incident["assigned_team_id"])
                        if team["incident_id"] != incident["id"]:
                            raise APIError(400, "초기 사건 배정과 팀 상태가 일치하지 않습니다.")
                db.execute("INSERT INTO meta VALUES ('seeded', ?)", (now(),))

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _put(db, table, value):
        if table == "incidents":
            # 읽기 응답에서 계산한 권고를 원문 저장소에 포함하지 않는다.
            value = {key: item for key, item in value.items() if key != "attention"}
        db.execute(f"INSERT OR REPLACE INTO {table} (id,payload) VALUES (?,?)", (value["id"], json.dumps(value, ensure_ascii=False)))

    @staticmethod
    def _all(db, table):
        return [json.loads(row[0]) for row in db.execute(f"SELECT payload FROM {table} ORDER BY id")]

    @staticmethod
    def _get(db, iid):
        string(iid, "사건 ID")
        row = db.execute("SELECT payload FROM incidents WHERE id=?", (iid,)).fetchone()
        if not row:
            raise APIError(404, "사건을 찾을 수 없습니다.")
        return json.loads(row[0])

    @staticmethod
    def _team(db, tid):
        string(tid, "팀 ID")
        row = db.execute("SELECT payload FROM resources WHERE id=?", (tid,)).fetchone()
        if not row:
            raise APIError(400, "등록된 팀이 아닙니다.")
        return json.loads(row[0])

    def _validate_resource(self, team):
        body_fields(team, {"id", "name", "type", "status", "incident_id", "crew_count"}, {"id", "name", "type", "status", "incident_id", "crew_count"})
        for key in ("id", "name", "type"):
            string(team[key], key)
        count(team["crew_count"], "팀 인원")
        enum(team["status"], {"available", "assigned"}, "팀 상태")
        if (team["status"] == "available") != (team["incident_id"] is None):
            raise APIError(400, "팀 상태와 사건 배정이 일치하지 않습니다.")
        if team["incident_id"] is not None:
            string(team["incident_id"], "배정 사건")

    def _validate_seed(self, incident):
        required = {"id", "title", "category", "location", "priority", "status", "summary", "people_count", "revision", "created_at", "updated_at", "assigned_team_id", "synthetic", "reports", "progress", "audit", "outcome", "outcome_history", "checks"}
        body_fields(incident, required | {"demo_featured"}, required)
        if "demo_featured" in incident and type(incident["demo_featured"]) is not bool:
            raise APIError(400, "발표 대표 사례 표시는 boolean이어야 합니다.")
        if incident["synthetic"] is not True:
            raise APIError(400, "합성 사건만 초기화할 수 있습니다.")
        for key in ("id", "title", "location", "created_at", "updated_at"):
            string(incident[key], key)
        enum(incident["status"], STATUSES, "사건 상태")
        enum(incident["category"], {"flood", "fire", "rescue", "medical", "other"}, "분류")
        enum(incident["priority"], {"urgent", "high", "normal"}, "우선도")
        count(incident["revision"], "revision")
        if incident["revision"] < 1:
            raise APIError(400, "revision은 1 이상이어야 합니다.")
        if incident["people_count"] is not None:
            count(incident["people_count"])
        for key in ("reports", "progress", "audit", "outcome_history", "checks"):
            if not isinstance(incident[key], list):
                raise APIError(400, f"{key}는 배열이어야 합니다.")
        report_ids = set()
        for report in incident["reports"]:
            if not isinstance(report, dict) or not isinstance(report.get("id"), str) or report["id"] in report_ids:
                raise APIError(400, "초기 보고 ID가 잘못되었습니다.")
            report_ids.add(report["id"])
            enum(report.get("channel"), CHANNELS, "보고 채널")
            enum(report.get("kind"), {"initial", "additional", "field", "correction"}, "보고 종류")
            string(report.get("actor"), "보고 담당자")
            string(report.get("text"), "보고 원문")
            if "people_count" in report:
                count(report["people_count"])
            # 미디어 파일은 main이 준비하므로 초기 원문은 경로/형식부터 검증한다.
            self._attachments(report.get("attachments", []), require_exists=False)

    def media_path(self, url, require_exists=True):
        if not isinstance(url, str) or not url.startswith("/media/") or "?" in url or "#" in url or unquote(url) != url:
            raise APIError(400, "허용된 로컬 미디어 URL이 필요합니다.")
        relative = url[len("/media/"):]
        if not re.fullmatch(r"(?:uploads/)?[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|jpg|jpeg|wav|mp3|mp4)", relative):
            raise APIError(400, "미디어 경로가 허용되지 않습니다.")
        media_root = (ROOT / "service" if relative.startswith("uploads/") else ROOT / "data" / "media").resolve()
        path = media_root / relative
        if media_root not in path.resolve().parents or path.is_symlink():
            raise APIError(400, "미디어 경로가 허용되지 않습니다.")
        if require_exists:
            if not path.is_file() or not valid_header(path.read_bytes(), media_mime(path)):
                raise APIError(400, "첨부 파일이 없거나 읽을 수 있는 미디어가 아닙니다.")
        return path

    def _attachments(self, attachments, require_exists=True):
        if not isinstance(attachments, list) or len(attachments) > 20:
            raise APIError(400, "첨부는 최대 20개 배열이어야 합니다.")
        ids = set()
        for attachment in attachments:
            allowed = {"id", "url", "filename", "media_type", "caption", "source", "transcript"}
            body_fields(attachment, allowed, allowed - {"transcript"})
            for key in ("id", "filename", "caption"):
                string(attachment[key], f"첨부 {key}", empty=key == "caption")
            if attachment["id"] in ids:
                raise APIError(400, "첨부 ID가 중복되었습니다.")
            ids.add(attachment["id"])
            path = self.media_path(attachment["url"], require_exists)
            expected_type = MEDIA[media_mime(path)][0]
            enum(attachment["media_type"], {expected_type}, "첨부 종류")
            enum(attachment["source"], {"ai_generated", "tts_synthetic", "operator_upload"}, "첨부 출처")
            if "transcript" in attachment:
                string(attachment["transcript"], "첨부 대본", empty=True)
        return deepcopy(attachments)

    def _decorate(self, incident):
        checks = [deepcopy(c) for c in incident["checks"] if not c.get("id", "").startswith("rule-")]
        reports = incident["reports"]
        field_reports = [r for r in reports if r["kind"] == "field" and _after_reopen(incident, r)]
        latest_field = field_reports[-1] if field_reports else None
        latest_matches = latest_field is not None and _full_confirmation(latest_field, incident["people_count"])
        for check in checks:
            check["detail"] = check["detail"].replace("confirmed_count=3 또는 2", "확인 인원 3명 또는 2명")
            if incident["status"] == "closed" or (latest_matches and any(term in check["title"] for term in ("인원", "부분"))):
                check["level"] = "info"
        def add(cid, title, detail, ids, level="warning"):
            if incident["status"] == "closed":
                level = "info"
            checks.append({"id": f"rule-{cid}", "level": level, "title": title, "detail": detail, "report_ids": ids})
        for report in reports:
            text = report["text"]
            rid = report["id"]
            if report["kind"] == "field" and report.get("people_count") != incident["people_count"]:
                historical = latest_matches and latest_field["id"] != rid
                detail = (f"이전 보고 {report.get('people_count', '미확인')}명과 접수 {incident['people_count']}명 차이가 있었습니다. "
                          f"최신 현장 보고 {latest_field['people_count']}명으로 대조했으며 이전 원문을 보존합니다.") if historical else "현장 보고 인원과 현재 접수 인원이 다릅니다. 부분 구조만으로 처리 완료할 수 없습니다."
                add(f"count-{rid}", "현장 인원 대조", detail, [rid], "info" if historical else "warning")
            if any(term in text for term in ["다른 세대", "다른 가구", "같은 건물", "동일 건물"]):
                add(f"household-{rid}", "개별 세대 확인", "동일 위치의 다른 세대 요청을 구분하고 각 원문을 확인하세요.", [rid])
            if any(term in text for term in ["GPS", "제 휴대폰 위치", "어머니 집이 아니", "신고자 위치"]):
                add(f"gps-{rid}", "신고자 위치와 대상 위치 구분", "휴대폰 위치가 구조 대상 위치인지 별도로 확인하세요.", [rid])
            if any(term in text for term in ["연락이 끊", "연락 두절", "응답 없", "응답이 없"]):
                add(f"contact-{rid}", "연락 두절 확인", "연락 여부만으로 결과를 확정하지 말고 현장 근거를 확인하세요.", [rid])
            if report["kind"] == "correction" and "location" in report:
                add(f"location-{rid}", "위치 정정 이력", "원문 위치와 담당자가 정정한 현재 위치를 함께 확인하세요.", [rid], "info")
        if incident["status"] != "closed" and any(r["kind"] == "field" for r in reports):
            add("outcome", "처리 결과 미확정", "현장 보고가 있어도 담당자 결과 확정 전까지 진행 사건으로 유지됩니다.", [r["id"] for r in reports if r["kind"] == "field"])
        incident["checks"] = checks
        return incident

    def list_incidents(self):
        with self._transaction() as db:
            incidents = [self._response(i) for i in self._all(db, "incidents")]
            active = sorted((i for i in incidents if i["status"] != "closed"), key=attention_sort_key)
            closed = sorted((i for i in incidents if i["status"] == "closed"),
                            key=lambda i: (_instant(i["updated_at"]) or 0, i["id"]), reverse=True)
            return {"incidents": active + closed, "resources": self._all(db, "resources")}

    def get_incident(self, iid):
        with self._transaction() as db:
            return self._response(self._get(db, iid))

    def _response(self, incident):
        result = self._decorate(deepcopy(incident))
        result["attention"] = derive_attention(result)
        causes = {item["id"].rsplit(":", 1)[-1] for item in result["attention"]}
        if any("연락 두절 신고" in item["reason"] for item in result["attention"]):
            causes.add("contact")
        for check in result["checks"]:
            cid, title = check["id"], check["title"]
            cause = None
            if cid.startswith("rule-count-") or any(word in title for word in ("인원", "부분", "잔여 대상")):
                cause = "people"
            elif cid.startswith("rule-contact-") or any(word in title for word in ("연락", "무응답", "응답")):
                cause = "contact"
            elif cid.startswith("rule-gps-") or any(word in title for word in ("위치", "GPS", "좌표")):
                cause = "location"
            if cause and cause not in causes:
                check["level"] = "info"
                descriptions = {
                    "people": "이전 인원 대조 기록입니다. 현재 판단은 최신 원문과 명시 인원 정정을 기준으로 표시합니다.",
                    "contact": "이전 연락 확인 기록입니다. 현재 판단은 재개 시점과 최신 현장 확인 원문을 기준으로 표시합니다.",
                    "location": "이전 위치 확인 기록입니다. 현재 위치 판단은 명시 정정과 최신 원문을 기준으로 표시합니다.",
                }
                if check["detail"].startswith("이전 보고 ") and cause == "people":
                    continue
                check["detail"] = descriptions[cause]
        return result

    @staticmethod
    def _before(incident):
        return {key: deepcopy(incident.get(key)) for key in ("title", "location", "priority", "people_count", "status", "assigned_team_id", "revision", "outcome", "intake119")}

    def _save(self, db, incident, before, action, actor, reason):
        timestamp = now()
        incident["revision"] += 1
        incident["updated_at"] = timestamp
        incident["audit"].append({"id": identity("AUD"), "action": action, "actor": actor, "reason": reason,
                                  "created_at": timestamp, "before": before, "after": self._before(incident)})
        self._decorate(incident)
        self._put(db, "incidents", incident)
        return self._response(incident)

    @staticmethod
    def _revision(incident, body):
        revision = count(body["expected_revision"], "expected_revision")
        if revision != incident["revision"]:
            raise APIError(409, "다른 담당자가 사건을 수정했습니다. 최신 사건을 다시 확인하세요.")

    def _restore_review(self, incident, actor, reason):
        if incident["outcome"] is not None:
            old = deepcopy(incident["outcome"])
            old.update(reopened_at=now(), reopen_reason=reason, reopened_by=actor)
            old["report_ids_at_reopen"] = [r["id"] for r in incident["reports"]]
            incident["outcome_history"].append(old)
        incident["outcome"] = None
        incident["status"] = "reviewing"

    def create_incident(self, body):
        body_fields(body, {"title", "category", "location", "priority", "summary", "people_count", "channel", "text", "actor", "attachments", "intake119"}, {"title", "location", "text"})
        for key in ("title", "location", "text"):
            string(body[key], key)
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        category = enum(body.get("category", "rescue"), {"flood", "fire", "rescue", "medical", "other"}, "분류")
        priority = enum(body.get("priority", "normal"), {"urgent", "high", "normal"}, "우선도")
        channel = enum(body.get("channel", "sms"), CHANNELS, "채널")
        people = count(body["people_count"]) if "people_count" in body else None
        summary = string(body.get("summary", ""), "요약", empty=True)
        attachments = self._attachments(body.get("attachments", []))
        with self._transaction() as db:
            prefix = "INC-" + datetime.now().strftime("%Y%m%d") + "-"
            ids = [i["id"] for i in self._all(db, "incidents")]
            index = 1
            while f"{prefix}{index:03d}" in ids:
                index += 1
            timestamp = now()
            report = {"id": identity("REP"), "channel": channel, "actor": actor, "text": body["text"], "kind": "initial",
                      "received_at": timestamp, "occurred_at": timestamp, "attachments": attachments}
            if people is not None:
                report["people_count"] = people
            incident = {"id": f"{prefix}{index:03d}", "title": body["title"], "category": category, "location": body["location"], "priority": priority,
                        "status": "received", "summary": summary, "people_count": people, "revision": 1,
                        "created_at": timestamp, "updated_at": timestamp, "assigned_team_id": None, "synthetic": True,
                        "reports": [report], "progress": [], "audit": [], "outcome": None, "outcome_history": [], "checks": []}
            if "intake119" in body:
                if not isinstance(body["intake119"], dict):
                    raise APIError(400, "119 접수 정보는 객체여야 합니다.")
                incident["intake119"] = deepcopy(body["intake119"])
            incident["audit"].append({"id": identity("AUD"), "action": "create", "actor": actor, "reason": "신규 합성 신고 접수",
                                      "created_at": timestamp, "before": None, "after": self._before(incident)})
            self._decorate(incident)
            self._put(db, "incidents", incident)
            return self._response(incident)

    def add_report(self, iid, body):
        body_fields(body, {"expected_revision", "channel", "actor", "text", "kind", "people_count", "location", "attachments", "intake119"}, {"expected_revision", "channel", "text", "kind"})
        channel = enum(body["channel"], CHANNELS, "채널")
        kind = enum(body["kind"], {"additional", "field", "correction"}, "보고 종류")
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        string(body["text"], "보고 원문")
        if "people_count" in body:
            count(body["people_count"])
        if "location" in body:
            string(body["location"], "위치")
        if kind == "correction" and not ({"people_count", "location"} & body.keys()):
            raise APIError(400, "정정 보고에는 정정 인원 또는 위치가 필요합니다.")
        attachments = self._attachments(body.get("attachments", []))
        with self._transaction() as db:
            incident = self._get(db, iid)
            self._revision(incident, body)
            before = self._before(incident)
            timestamp = now()
            report = {"id": identity("REP"), "channel": channel, "actor": actor, "text": body["text"], "kind": kind,
                      "received_at": timestamp, "occurred_at": timestamp, "attachments": attachments}
            if "intake119" in body:
                if not isinstance(body["intake119"], dict):
                    raise APIError(400, "119 접수 정보는 객체여야 합니다.")
                report["intake119"] = deepcopy(body["intake119"])
            for key in ("people_count", "location"):
                if key in body:
                    report[key] = body[key]
                    if kind == "correction":
                        incident[key] = body[key]
            if incident["status"] == "closed":
                self._restore_review(incident, actor, "완료 후 추가 정보 도착: " + body["text"])
            incident["reports"].append(report)
            return self._save(db, incident, before, "report_added", actor, body["text"])

    def update_incident(self, iid, body):
        body_fields(body, {"expected_revision", "actor", "reason", "title", "location", "priority", "people_count", "intake119"}, {"expected_revision", "reason"})
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        reason = string(body["reason"], "수정 이유")
        changes = {k: v for k, v in body.items() if k in {"title", "location", "priority", "people_count", "intake119"}}
        if not changes:
            raise APIError(400, "수정할 필드를 입력하세요.")
        for key, value in changes.items():
            if key == "intake119":
                if not isinstance(value, dict):
                    raise APIError(400, "119 접수 정보는 객체여야 합니다.")
            elif key == "people_count":
                count(value)
            elif key == "priority":
                enum(value, {"urgent", "high", "normal"}, "우선도")
            else:
                string(value, key)
        with self._transaction() as db:
            incident = self._get(db, iid)
            self._revision(incident, body)
            before = self._before(incident)
            important = any(k in changes and changes[k] != incident[k] for k in ("people_count", "location"))
            incident.update(changes)
            if incident["status"] == "closed" and important:
                self._restore_review(incident, actor, reason)
            if "location" in changes and changes["location"] != before["location"]:
                incident["checks"].append({"id": identity("CHK"), "level": "info", "title": "담당자 위치 수정", "detail": reason, "report_ids": []})
            return self._save(db, incident, before, "incident_updated", actor, reason)

    def add_progress(self, iid, body):
        body_fields(body, {"expected_revision", "actor", "status", "team_id", "note"}, {"expected_revision", "status", "note"})
        status = enum(body["status"], {"dispatched", "on_scene", "rescuing", "reviewing"}, "진행 상태")
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        note = string(body["note"], "진행 메모")
        if "team_id" in body:
            string(body["team_id"], "팀 ID")
        with self._transaction() as db:
            incident = self._get(db, iid)
            self._revision(incident, body)
            if incident["status"] == "closed":
                raise APIError(409, "완료 사건은 사유를 입력해 재개한 뒤 진행을 변경하세요.")
            before = self._before(incident)
            tid = body.get("team_id", incident["assigned_team_id"])
            if tid is None and status in {"dispatched", "on_scene", "rescuing"}:
                raise APIError(400, "출동·현장·구조 진행에는 담당팀이 필요합니다.")
            if tid is not None:
                team = self._team(db, tid)
                if team["incident_id"] not in {None, iid}:
                    raise APIError(409, "이 팀은 다른 사건에 배정되어 있습니다.")
                if incident["assigned_team_id"] and incident["assigned_team_id"] != tid:
                    old = self._team(db, incident["assigned_team_id"])
                    old.update(status="available", incident_id=None)
                    self._put(db, "resources", old)
                team.update(status="assigned", incident_id=iid)
                self._put(db, "resources", team)
            incident["assigned_team_id"] = tid
            incident["status"] = status
            incident["progress"].append({"id": identity("PRG"), "status": status, "team_id": tid, "note": note, "actor": actor, "created_at": now()})
            return self._save(db, incident, before, "progress_added", actor, note)

    def confirm_outcome(self, iid, body):
        body_fields(body, {"expected_revision", "actor", "outcome", "confirmed_count", "basis_report_id", "note"}, {"expected_revision", "outcome", "confirmed_count", "basis_report_id", "note"})
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        outcome = enum(body["outcome"], {"rescued", "self_evacuated", "transferred"}, "결과")
        confirmed = count(body["confirmed_count"], "확인 인원")
        basis = string(body["basis_report_id"], "근거 보고 ID")
        note = string(body["note"], "결과 확인 메모")
        with self._transaction() as db:
            incident = self._get(db, iid)
            self._revision(incident, body)
            if incident["status"] == "closed":
                raise APIError(409, "결과 변경은 사유를 입력해 사건을 재개한 뒤 확정하세요.")
            report = next((r for r in incident["reports"] if r["id"] == basis), None)
            if (incident["people_count"] is None or confirmed != incident["people_count"] or report is None
                    or report["kind"] != "field" or report.get("people_count") != confirmed):
                raise APIError(400, "현재 접수 인원과 같은 사건의 현장 보고 인원이 모두 일치해야 결과를 확정할 수 있습니다.")
            if incident["outcome_history"]:
                previous = incident["outcome_history"][-1]
                stale = basis in previous.get("report_ids_at_reopen", [])
                if "report_ids_at_reopen" not in previous and previous.get("reopened_at"):
                    try:
                        stale = datetime.fromisoformat(report["received_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(previous["reopened_at"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        stale = True
                if stale:
                    raise APIError(400, "재개 이후의 새로운 현장 보고가 필요합니다. 과거 완료 근거는 재사용할 수 없습니다.")
            if not _full_confirmation(report, incident["people_count"]):
                raise APIError(400, "현장 원문에 남은 대상이나 미확인 상태가 있습니다. 전체 대상의 안전 확인 근거가 필요합니다.")
            basis_index = incident["reports"].index(report)
            for newer in incident["reports"][basis_index + 1:]:
                raw = NO_RESIDUAL.sub("", newer.get("text", ""))
                if (NEGATIVE_CONFIRMATION.search(raw) or RESIDUAL.search(raw)
                        or any(term in raw for term in CONTACT_TERMS)
                        or newer["kind"] == "field" and not _full_confirmation(newer, confirmed)
                        or newer["kind"] == "correction" and any(k in newer for k in ("people_count", "location"))):
                    raise APIError(400, "선택한 현장 근거 이후 새 미확인 정보가 있습니다. 최신 현장 확인이 필요합니다.")
            last_correction = max((i for i, r in enumerate(incident["reports"]) if r["kind"] == "correction" and "people_count" in r), default=-1)
            if any(r["kind"] == "additional" and "people_count" in r and r["people_count"] != confirmed
                   for r in incident["reports"][last_correction + 1:]):
                raise APIError(400, "추가 신고의 확인 대상 총수가 다릅니다. 인원 정정 근거를 먼저 등록하세요.")
            before = self._before(incident)
            incident["status"] = "closed"
            incident["outcome"] = {"outcome": outcome, "confirmed_count": confirmed, "basis_report_id": basis,
                                   "note": note, "actor": actor, "confirmed_at": now()}
            if incident["assigned_team_id"]:
                team = self._team(db, incident["assigned_team_id"])
                team.update(status="available", incident_id=None)
                self._put(db, "resources", team)
            incident["assigned_team_id"] = None
            return self._save(db, incident, before, "outcome_confirmed", actor, note)

    def reopen(self, iid, body):
        body_fields(body, {"expected_revision", "actor", "reason"}, {"expected_revision", "reason"})
        actor = string(body.get("actor", DEFAULT_ACTOR), "담당자")
        reason = string(body["reason"], "재개 사유")
        with self._transaction() as db:
            incident = self._get(db, iid)
            self._revision(incident, body)
            if incident["status"] != "closed":
                raise APIError(409, "처리 완료 사건만 재개할 수 있습니다.")
            before = self._before(incident)
            self._restore_review(incident, actor, reason)
            return self._save(db, incident, before, "incident_reopened", actor, reason)

    def upload(self, body):
        body_fields(body, {"filename", "content_type", "data_base64"}, {"filename", "content_type", "data_base64"})
        filename = string(body["filename"], "파일명")
        if "/" in filename or "\\" in filename or "\x00" in filename or len(filename) > 255:
            raise APIError(400, "파일명에 경로나 제어 문자를 사용할 수 없습니다.")
        mime = enum(body["content_type"], set(MEDIA), "파일 종류")
        encoded = body["data_base64"]
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_UPLOAD + 2) // 3):
            raise APIError(413, "첨부 파일은 최대 8MiB입니다.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise APIError(400, "첨부 base64 데이터가 잘못되었습니다.") from exc
        if not data or len(data) > MAX_UPLOAD:
            raise APIError(413, "첨부 파일은 비어 있지 않고 최대 8MiB여야 합니다.")
        if not valid_header(data, mime):
            raise APIError(400, "첨부 파일 헤더가 선언된 파일 종류와 일치하지 않습니다.")
        uid = identity("UPL")
        media_type, suffix = MEDIA[mime]
        attachment = {"id": uid, "url": f"/media/uploads/{uid}{suffix}", "filename": filename,
                      "media_type": media_type, "caption": filename, "source": "operator_upload"}
        path = self.media_path(attachment["url"], require_exists=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(data)
            with self._transaction() as db:
                self._put(db, "uploads", attachment)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return attachment

    def allowed_media(self, url):
        path = self.media_path(url)
        with self._transaction() as db:
            allowed = {a["url"] for incident in self._all(db, "incidents") for report in incident["reports"] for a in report["attachments"]}
            allowed.update(item["url"] for item in self._all(db, "uploads"))
        if url not in allowed:
            raise APIError(404, "허용된 첨부 파일이 아닙니다.")
        return path
