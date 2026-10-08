# 공통 계약 v1

## 범위와 의미
집중호우로 고립된 주택·다세대 건물의 신고와 현장 보고를 대조한다. 판정은 미확인/불일치의 발견이며 구조 우선순위·의료 처치·대피 경로는 생성하지 않는다. 공식 119 내부 API나 데이터 형식을 추정해 구현하지 않는다.

공개 채널을 참고한 모의 입력: `sms` 문자, `mms` 사진/영상 첨부 문자, `app` 위치 포함 신고, `video_call` 영상통화의 모의 기록, `web` 인터넷 신고. `field` 현장 보고, `operator` 담당자 결정, `system` 전송·무응답 이벤트는 하네스가 추가한 운영 입력이다.

## 파일과 소유권
- 메인: 이 계약, README, AGENTS, 프로젝트 로컬 역할·스킬, scripts/, web/, docs/architecture.md, docs/evaluation.md, 실행 계획과 통합 기록.
- 엔진 워커: `rescue/` 전체. Python 표준 라이브러리만 사용.
- 사례 워커: `scenarios/`, `docs/proposal.md`, `docs/casebook.md`, `docs/demo-script.md`, `docs/sources.md`.
- QA: `tests/`와 지정된 검증 결과. 제품 코드 수정 금지.

## 시나리오 JSON
`scenarios/<id>.json`:
```json
{
  "schema_version": 1,
  "id": "same-building",
  "title": "같은 건물의 다른 가구",
  "synthetic": true,
  "description": "검증할 위험과 상황",
  "channels": ["sms", "field"],
  "events": [],
  "fixture_analysis": {},
  "expectations": [],
  "demo_notes": "발표에서 확인할 장면"
}
```
`fixture_analysis`는 이벤트 ID → 분석 객체의 매핑이다. 검증 기대값과 분리하며, **수작업으로 작성한 분석 결과**이지 실제 모델 출력이 아니다. 실시간 모델 입력에는 이 매핑과 expectations를 보내지 않는다.

## 원본 이벤트
필수: `id`, `channel`, `actor`, `occurred_at`, `received_at`, `text`. 시각은 시간대가 있는 ISO 8601. 도착 순서와 사건 시각은 다를 수 있다.
선택: `request_id`(접수 단계에서 부여한 개별 요청 ID), `candidate_request_ids`(담당자가 제공한 후보), `building_id`, `attachments`, `location`, `decision`.

첨부는 `id`, `media_type`(`image`/`video`), `description`, `transcript`(선택), `transcript_source`(`fixture`/`human`/`model`), `captured_at`, `readable`를 가진다. 실제 사진·영상·음성 인식은 필수 구현 범위가 아니다. 텍스트로 설명한 미디어는 화면에 그 사실을 표시한다. 모델 분석의 evidence_quote는 text 또는 attachment.description/transcript에 존재해야 한다.

위치 메타데이터: `latitude`, `longitude`, `accuracy_m`, `captured_at`, `subject`(`reporter`/`victim`/`unknown`). 앱 GPS가 신고자 위치인지 구조 대상 위치인지 구분한다. 좌표를 새로 만들어내지 않는다.

## 분석 객체
```json
{"event_id":"E1","observations":[
  {"kind":"request","request_ids":["R-A"],"people_count":3,
   "location_text":"2층","needs":["고립"],"evidence_quote":"2층에 세 명 있어요"}
]}
```
`kind` enum:
- `request`: 새 요청 또는 같은 ID의 추가 신고. 요청 ID별 카드를 유지한다.
- `location_update`: 당사자/현장 출처의 위치 변경 진술. 늦게 도착한 옛 진술로 현재 위치를 덮지 않는다.
- `count_correction`: 기존 인원 정정. 묵시적 덮어쓰기 대신 정정 이력을 보존한다.
- `rescue_report`: 구조 보고. `people_count`와 request_ids가 있어도 완료는 담당자 결정 전까지 금지.
- `safe_report`: 자력 대피/다른 팀 인계 진술. 구조 완료와 구분하여 담당자 확인 대상으로 둔다.
- `duplicate_candidate`: `request_ids` 두 개 이상. 자동 병합 금지.
- `unreadable_media`, `location_conflict`, `no_response`, `delivery_failure`: 확인할 문제를 기록한다. 완료/사망/확정 위치로 추론하지 않는다.

선택 필드: `people_count`(0 이상의 정수, bool 불가), `location_text`, `needs`(문자열 배열), `evidence_quote`(필수·빈 문자열 불가). 알 수 없는 필드는 오류로 처리한다. 모든 request_ids는 해당 시점까지 접수된 ID 또는 현재 이벤트의 request_id에 속해야 한다. event_id가 원본과 다르거나 근거가 원문에 없으면 분석 거절. 거절해도 원본 접수와 기존 상태를 보존하며 `analysis_rejected` 알림을 남긴다.

## 사람의 결정
`channel=operator`이며 `actor`가 비어 있지 않은 이벤트에만 decision을 허용한다.
```json
{"kind":"confirm_outcome","request_id":"R-A","outcome":"rescued",
 "confirmed_count":3,"basis_event_ids":["E3"],"expected_revision":1}
```
`confirm_outcome`은 해당 요청의 현재 revision과 일치해야 하며, 기재된 근거가 이미 도착한 `rescue_report`/`safe_report`에 해당하고 해당 요청을 후보에 포함해야 한다. 확인 인원은 현재 접수 인원과 일치해야 한다. 불일치하면 `closure_blocked` 알림과 원문을 보존한다. 인원을 모르면 확정하지 않는다. `outcome`은 `rescued`, `self_evacuated`, `transferred`.
`dispatch`: request_id를 받아 배정 사실만 기록한다.
`reopen`: request_id와 reason을 받아 완료된 요청을 다시 확인 상태로 전환한다.
`link_duplicate`: request_id와 related_request_id를 받아 담당자가 연결한다. 원본 두 카드·ID를 보존하고 canonical_id로 관계만 기록한다. 이미 완료된 카드에 열린 카드를 연결하거나 서로 다른 known 인원을 연결하면 거절한다. 연결 자체로 완료되지 않는다.

revision: 카드의 사람 수/위치/필요 정보가 실제로 바뀔 때에만 증가한다. 접수 첫 버전은 1. 단순 재전송·배정·구조 보고·알림은 증가시키지 않는다. 완료 후 새 위치·인원·도움 요청이 들어오면 다시 확인 상태로 열고 `post_resolution_update`를 표시한다.

## 엔진 출력과 파이썬 경계
`rescue.engine.replay(scenario: dict, mode: str = "fixture", analyses: dict | None = None) -> dict`.
`mode`는 `fixture` 또는 `live`. `live`에서 누락된 모델 출력은 분석 거절로 남기며 fixture fallback 금지. 이벤트는 배열의 수신 순서로 처리하고 received_at은 비감소해야 한다. occurred_at은 received_at 이후일 수 없다.

출력:
```json
{"scenario_id":"same-building","mode":"fixture","synthetic":true,
 "snapshots":[{"event_id":"E1","requests":{},"alerts":[],"audit":[]}],
 "final":{"event_id":"E5","requests":{},"alerts":[],"audit":[]},
 "checks":[],"passed":true,"metrics":{}}
```
카드 필수: `id`, `building_id`, `people_count`, `location_text`, `location_occurred_at`, `needs`, `status`(`open`/`dispatched`/`awaiting_confirmation`/`resolved`), `revision`, `outcome`(미확정은 null), `canonical_id`, `evidence_event_ids`. 알림에는 코드와 근거가 들어간다.
알림 필수 필드: `code`, `request_ids`, `event_ids`, `message`, `question`, `active`(bool). 해결된 알림도 active=false로 이력을 보존한다.
예상 코드: `ambiguous_match`, `count_unreconciled`, `duplicate_review`, `unreadable_media`, `location_conflict`, `no_response`, `delivery_failure`, `analysis_rejected`, `closure_blocked`, `post_resolution_update`, `late_location_ignored`.

구현·산출물의 사용자 대상 문장은 한국어로 작성한다.

## 기대값 DSL (누락된 assertion은 실패)
`expectations`는 아래 객체 배열이다. `after`가 생략되면 final, 있으면 해당 event snapshot을 검사한다.
- `{"after":"E2","path":"requests.R-A.status","equals":"open","label":"출동 전 열린 요청"}`
- `{"path":"alerts","contains_code":"count_unreconciled","active":true,"label":"인원 대조 경고"}`
- `{"path":"alerts","not_contains_code":"analysis_rejected","label":"분석 유효"}`
- `{"path":"requests","length":2,"label":"두 원본 카드 유지"}`
- `{"path":"requests.R-A.evidence_event_ids","contains":"E1","label":"접수 근거 유지"}`
체크 결과: `label`, `passed`(bool), `expected`, `actual`, `after`.
metrics: `events`, `requests`, `resolved`, `unresolved`, `active_alerts`, `rejected_analyses`, `blocked_closures`. 실제 생존율/시간절감 수치를 만들어내지 않는다.

## 재현성·평가
실행에 seed를 요구하지 않는 결정적 사건 재생. 매 실행 새 출력 디렉터리를 만들고 입력 SHA256·모드·실행 명령·테스트 결과를 보존한다. 최종 상태뿐 아니라 위험한 중간 전이를 assertions로 검사한다. fixture와 live 결과를 섞어 통과율을 계산하지 않는다.
