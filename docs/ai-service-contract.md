# AI 서비스 확장 계약 v1 — 2026-10-09

이 계약은 이번 구현의 고정 입력이다. 기존 docs/contract.md, service-contract.md의 원문 보존·동시성·완료 근거 계약을 유지한다. 모든 입력은 synthetic이며 공식 119·카카오톡·전화 시스템 연동을 주장하지 않는다. 카카오톡 메시지는 수동 합성 접수 채널로 제공한다.

## 배포와 저장

Netlify Functions(Node 22, native fetch)에서 같은 출처 /api/를 처리한다. Supabase Postgres에 사건/보고/검토 초안/감사/팀/첨부 메타데이터를 영속 저장하고 Storage의 비공개 버킷에 업로드 바이트를 저장한다. MVP는 revision이 있는 workspace JSON 문서를 단일 DB 행에서 CAS RPC로 원자 갱신해도 된다. 원문과 개별 ID 및 이력은 문서에 남고, 분석 작업은 별도 행으로 저장한다. SQL migration은 재실행 가능하고 기존 데이터 삭제/자동 초기화 금지. RLS와 revoke로 anon/authenticated의 직접 테이블 쓰기·RPC 실행을 막고 server service-role만 접근한다. 서비스 키와 OpenAI 키는 서버 환경변수만 사용한다.

기본 공개 사이트는 합성 자료를 공유하는 해커톤 데모이다. 모든 신규 분석에 synthetic:true가 필요하며 일일 AI 분석 수를 서버 DB에서 제한한다(기본 20회, AI_DAILY_LIMIT 설정 가능). 분석 제한은 원문을 잃게 하거나 AI 결과를 위조하지 않는다. DB/키 미설정이면 API가 명시적 503을 반환한다. 화면의 별도 '합성 사례 둘러보기'만 기존 visitor localStorage 오프라인 모드로 들어간다. 실제 AI 실패에 fixture를 조용히 대체하지 않는다.

root는 빌더/Netlify 설정/공개 문서/공통 계약과 통합을 소유한다. backend는 service/, scripts/analyzer_openai.py, netlify/functions/, supabase/, web/pages-store.js 및 backend 전용 검사 산출물을 소유한다. frontend는 web/app.js, index.html, style.css, cloud-client.js 및 frontend 산출물. QA는 tests/test_ai_*.py, tests/ai_*.cjs와 전용 QA 산출물만 소유한다. 기존 seed와 사용자 SQLite는 root 승인 없이 수정하지 않는다.

## API

기존 CRUD의 요청/응답 및 revision 충돌 409를 유지한다. backend는 새 intake119 필드를 추가 허용한다. /api/uploads 응답의 첨부 ID/논리 URL을 유지하고 클라우드는 /api/media/<upload-id> 같은 서버 프록시를 사용해 비공개 파일을 읽는다. frontend safeMedia가 이 경로를 허용한다. seed의 /media/ 파일은 기존 경로다. 공개 호스트 업로드는 Netlify body 한계에 맞춰 최대 3MiB(실제 헤더 검증)를 명시한다. 오프라인/로컬 8MiB 계약은 보존한다.

- GET /api/config → {storage:'supabase'|'unconfigured',ai:{configured:boolean,model:string|null},synthetic:true,offline_available:true}. 비밀/키 값 금지. 본문 API 오류 {error,code?}.
- POST /api/ai/analyses → {synthetic:true,incident_id:null|id,expected_revision:null|int,report:{channel,actor,text,kind:'initial'|'additional'|'field',attachments:[],occurred_at?:string},intake119?:object}. 사건 ID가 있으면 revision 필수. 업로드는 먼저 성공해야 한다. 반환 202 {id,status:'queued',incident_id,expected_revision,created_at}. AI 작업 생성은 사건을 변경하지 않는다.
- GET /api/ai/analyses/<id> → {id,status:'queued'|'running'|'ready'|'failed'|'confirmed',incident_id,expected_revision,created_at,updated_at,report,intake119?,analysis:null|Analysis,execution:{mode:'live',model?,asr_model?,input_sha256?,response_id?,usage?,started_at?,completed_at?},error:null|string}. raw report text와 첨부 그대로 보존. 상태/메타는 실제 실행 기준. 실패 시 초안 확정 불가.
- POST /api/ai/analyses/<id>/confirm → {synthetic:true,actor,expected_revision:null|int,reason,changes:{title?,category?,location?,people_count?,priority?,summary?,intake119?}}. 사용자가 검토/수정한 값을 신규 접수 또는 추가 보고와 **한 트랜잭션**으로 반영한다. 분석에 입력했던 사건·revision과 다른 확인은 409. confirmed 재요청은 중복 등록하지 않고 기존 결과를 반환(idempotent). 기존 사건에서는 원문 보고 추가와 허용 필드 변경/검토 기록만 가능하고 AI로 팀배정·진행상태·완료 결과·사건 병합 변경 금지. 완료 사건의 새 보고는 reviewing으로 재개하고 이전 결과 보존. 실제 AI/ASR 정보는 확정 report.ai_analysis 메타에 연결. 반환 {incident,analysis_id}.

장시간 분석은 DB 작업 상태+Netlify background function으로 처리해 폴링한다. 공개 background 엔드포인트는 서버 HMAC 서명 검증, 작업 ID/입력hash 결속, 중복실행 원자claim, 시간초과 failed 처리. 클라이언트가 단순 ID로 모델 실행을 호출할 수 없다. background 트리거 실패도 작업 failed로 기록한다. 주어진 매체 처리 불가/모델 거절/네트워크 실패를 드러낸다.

## Analysis DTO (frontend와 Python/Node 공통)

{
  "summary": "한국어 짧은 상황 요약",
  "proposed_changes": {"title": null, "category": null, "location": null, "people_count": null, "priority": null, "summary": null},
  "intake119": {
    "reporter": {"display_name": null, "reply_channel": null, "phone": null, "relationship": null},
    "location": {"address_landmark": null, "floor_unit": null, "access_point": null, "gps": null, "source": null, "verification": "unverified"},
    "situation": {"category": null, "occurred_at": null, "summary": null},
    "rescue": {"people_count": null, "injury": null, "consciousness": null, "breathing": null, "isolation": null},
    "hazards": {"reported": [], "observed": [], "unconfirmed": []},
    "review": {"missing_information": [], "priority_warnings": []}
  },
  "evidence": [{"field": "location", "source_id": "input|既存reportID|attachmentID", "quote": "텍스트/전사에서 실제 인용", "observation": null, "type": "text|audio_transcript|image_observation"}],
  "duplicate_candidates": [{"incident_id": "기존 사건 ID", "report_id": null, "reason": "근거", "needs_human_confirmation": true}],
  "person_overlap": [{"source_ids": [], "reason": "중복 요구조자일 가능성", "needs_human_confirmation": true}],
  "remaining_people": {"count": null, "basis": "확인된 사람과 미확인 사람을 구분", "needs_human_confirmation": true},
  "authenticity": {"status": "unverified", "signals": [], "questions": []},
  "handoff": ["현장에 전달할 위치/접근/위험/미확인 인원"],
  "missing_information": [],
  "urgent_reasons": [],
  "transcripts": [{"attachment_id": "id", "text": "실제 ASR 결과", "model": "실제로 사용한 ASR 모델"}],
  "limitations": []
}

모든 정의된 키를 strict JSON schema로 요구하고 알 수 없는 값은 null/빈 배열로 표시한다. 119 접수번호/접수시각/갱신시각/처리 상태는 DB 값이며 AI가 생성하지 않는다. 실제 전화번호/주소를 새로운 값으로 상상하지 않는다. AI의 gps는 {latitude,longitude}|null이며 신고자 GPS를 구조 대상 위치로 확정하지 않는다. 위 enum/null 값은 기존 API category/priority와 동일하다. backend가 스키마 파일(service/ai_schema.json)을 제공하며 frontend는 이 DTO로 표시한다.

사진은 실제 image 입력으로 Responses API에 전송한다. 음성은 실제 파일을 /audio/transcriptions로 먼저 전사한다. seed transcript/caption을 실제 ASR/vision 결과로 사용하지 않는다. 영상은 본 MVP에서 직접 분석하지 않으며 미지원 사항으로 표시한다. media URL/파일 경로는 서버가 등록한 첨부만 허용한다(임의 외부 fetch/SSRF 금지). 모델과 전사 모델은 환경변수 OPENAI_MODEL, OPENAI_TRANSCRIBE_MODEL(기본 gpt-4o-mini-transcribe). OPENAI_API_KEY 미설정 즉시 fail, fixture fallback 없음. replay CLI 기존 packet/observations 계약은 유지하며 새 service 모드의 공통 DTO를 추가한다.

신고 텍스트·사진 속 지시는 데이터로만 취급한다. evidence 인용은 input/기존 보고/실제 전사에 있는 부분문자열이어야 한다. 사진관찰은 attachment ID와 observation으로 표시하고 임의 OCR 인용/촬영시각/GPS/부상상태를 확정하지 않는다. 후보 ID와 source ID는 서버 입력 allowlist에서 검증한다. 근거 없는/알 수 없는 ID·필드·가짜 인용 결과를 거부한다. AI가 진실/허위 여부를 판정했다는 상태 금지. 위치/인원 자동 병합·차감·완료 금지. residual 텍스트의 남은 사람/미확인/부정 근거로 완료할 수 없는 가드는 Node/SQLite 모두 유지한다.

## UX와 검증

하단 메뉴: /about/ 서비스 개요, /guide/ 이용법, /references/ 근거와 한계, /judge/ 심사 안내. root가 이 HTML과 /llms.txt, /llms-full.txt, /sitemap.xml, /robots.txt, /judge/evidence.json을 생성한다. HTML의 실제 본문/직접 링크는 JS 없이 읽힌다. frontend index에는 본문 소개 및 직접 링크를 보존하고 root 빌더가 JS 전 화면에 seed 요약 표를 삽입한다. 실행 여부와 fixture/live 미실행은 솔직히 표시한다. repo 링크는 namojo/codexhack2026.

현장 메뉴는 진행 사건을 쉽게 선택하고 '추가 신고·현장 정보 AI 분석'으로 원문·사진·음성 접수 → 분석 대기/오류 → 119 추출·전사·근거·중복후보·인원 미확인·인계메모 검토 → 수정 → 담당자 확인 등록. 신규 접수도 같은 흐름. 기존 수동 접수/보고는 유지하고 'AI 없이 담당자 직접 입력'을 명시한다. 결과/진행은 별도 담당자 업무. AI 초안 새로고침/조회로 복구, 입력은 오류/취소 후 보존, stale 분석은 재분석 안내, polling 정리, 모바일 버튼 ≥44px/카드 전체 선택/중첩 클릭 충돌 방지.

검사는 모의 API 계약/오류/보안 경계와 실제 live 호출을 구분한다. Supabase 실제 SQL 설치·영속·CAS와 실제 LLM text/image/ASR 호출은 인증 후 검증한다. 자격증명 부재는 not_run으로 남긴다. 기존 unittest/replay/pages QA 회귀 유지. 실제 브라우저는 root가 수행한다. 사용자 SQLite/실제 Netlify 기존 데이터 삭제 금지.
