# Codex CLI·OpenAI 해커톤 시연 계약 v2 — 2026-10-09

사용자 변경 요청: API 잔액이 없으므로 ChatGPT로 로그인된 Codex CLI로 가능한 다매체 분석을 실제 시연한다. OpenAI API 모듈은 나중에 키/모델을 설정하여 쓰도록 유지한다. 기존 ai-service-contract.md의 DTO·원문·119·담당자확정·Supabase CAS·완료계약을 그대로 확장한다.

추가 사용자 변경: OpenAI API 크레딧 충전 완료. 실제 API 문자·사진·음성 및 담당자 확인·Supabase 저장을 검증하고 성공하면 공개 Netlify의 AI_PROVIDER=openai를 활성화한다. Codex CLI는 로컬 선택 경로로 유지한다. 이전 잔액 부족 실패와 CLI 실패 기록은 보존하며 새 성공으로 덮어쓰지 않는다.

## 실행 범위

- 공개 Netlify: Supabase 공동 합성 업무, 심사 HTML, 설정/AI 연결 메뉴. API 분석은 기본 비활성(AI_PROVIDER=disabled), OPENAI_API_KEY/OPENAI_MODEL은 서버 설정 후 AI_PROVIDER=openai로 활성화. 실제 키나 OAuth 토큰은 UI/코드/로그/DB에 넣지 않는다. 일반 방문자가 서버 키 설정을 변경할 수 없다.
- 로컬 시연: Node22+ loopback `127.0.0.1:8769`에 `scripts/serve_codex_demo.mjs` 실행. dist/cloud와 동일 업무 화면을 제공하고 CRUD/AI작업/첨부/확정은 같은 Supabase에 저장한다. 브라우저가 로컬 서버에만 같은 출처로 요청한다. Netlify에서 localhost로 몰래 호출하지 않는다. 설정에서 로컬 시연 열기 링크와 설치/실행 안내를 제공한다.
- 로컬 서버는 `--env-stdin` 한 줄 JSON으로 Supabase 환경을 메모리에 받을 수 있고, 그렇지 않으면 서버 환경변수를 사용한다. credentials를 파일/argv/응답으로 출력 금지. 실제 사용자 SQLite와 기존 데이터는 보존.
- Codex CLI는 기존 `codex login status`의 ChatGPT 로그인을 사용한다. 현재 로그인 확인: CLI 0.162.0, Logged in using ChatGPT. 별도 앱의 Sign in with ChatGPT를 구현했다고 부르지 않는다. 로그인 안 되어 있으면 명시적으로 `codex login` 안내. Codex 토큰 파일을 앱이 읽거나 클라우드에 복사하지 않는다.
- 모델은 CLI의 현재 사용자 설정을 상속하며 전역 모델/권한 설정을 변경하지 않는다. 실행은 read-only sandbox, isolated temp cwd, STDIN raw packet, `--output-schema` strict 공통 DTO, 실제 PNG/JPEG `--image`만 허용. 셸 문자열에 신고/파일명을 보간하지 않고 spawn 배열을 사용한다. 도구 실행·파일쓰기·웹탐색을 요청하지 않는다. 타임아웃/버퍼 한도/동시성 제한/실패 시 원문 보존. 실제 CLI 실행 ID/usage/time/inputhash/provider 기록; 확인할 수 없는 model/responseID를 상상하지 않는다.
- 서버 전용 adapter hooks로 API/DB job 생성·claim·finish·confirm을 재사용 가능. HTTP 입력으로 hooks/명령/권한을 선택하거나 바꿀 수 없다. local Codex만 로컬 코드의 고정 실행 경로로 사용. cloud는 localhost dispatch/CLI/토큰을 실행하지 않는다.

## 매체와 검증

문자는 원문, 사진은 실제 바이트를 Codex에 전송한다. 음성은 Codex가 직접 들었다고 주장하지 않는다. 선택적 로컬 Whisper로 실제 WAV/MP3 전사하여 그 결과를 Codex 입력에 넣는다. CLI 어댑터와 local Whisper를 분리한다. root가 프로젝트 전용 .venv-demo와 .cache/whisper에 OpenAI 공식 whisper 모델을 설치·검증할 수 있다. 자동 모델 다운로드는 공식 모델 URL만 사용한다. 데이터/모델/venv는 Git에 포함하지 않는다.

ASR 미설치 시 음성 첨부 분석을 실패/미지원으로 표시하거나 담당자 입력 전사문을 신고 텍스트로 명시하여 시연한다. seed 대본을 실제 ASR로 쓰지 않는다. 실제 ASR을 실행한 경우 transcripts[].model=실제 local whisper 모델 식별자, text=실제 전사 그대로; asr_model 메타와 한계 표시. API 모드의 실제 OpenAI 전사 모듈은 유지한다.

지문은 PostgreSQL jsonb의 중첩 객체 키 재정렬에 불변인 canonical JSON으로 해시한다. 배열순서/원문/매체 ID/인원/위치 값이 바뀌면 달라야 한다. 생성→DB JSONB→background 검증까지 같은 함수를 사용한다. 기존 잘못된 hash 작업은 성공으로 바꾸지 않는다.

## 설정 API / UX

GET /api/config에 기존 필드를 유지하고 additive ai.provider ('codex_cli'|'openai'|'disabled'), ai.enabled, ai.local_demo, ai.asr, ai.login 설명/상태 추가 가능. configured는 키/CLI 설정만 의미하며 실제 실행 성공과 구분.
GET /api/settings는 비밀 없는 provider/current capabilities/설정 방법만 반환 가능. 공용 Netlify에서 키값 입력·쓰기 endpoint 금지.
로컬 POST /api/settings는 provider ('codex_cli'|'openai'|'disabled')만 허용. Origin/Host를 exact loopback 자신의 origin에 묶고 서버 브라우저 세션/CSRF token으로 보호한다. 토큰/키 문자열은 localStorage에도 저장하지 않는다. OpenAI 활성화는 이미 서버에 있는 key/model만 사용. 로컬 로그인 상태 재확인은 read-only codex login status로 제공 가능.
UI #settings 메뉴: 기본 해커톤 실행 방식, Codex CLI ChatGPT 로그인 상태/로컬 시연 실행명령과 열기 링크, API 나중 활성화 안내, 음성 처리 방식/지원 범위, 실제 분석/실패를 구분한다. local demo에서 설정 provider가 바뀌면 다음 분석에만 적용; 기존 초안 provider 메타 유지. 신규/현장 AI 흐름·확정·이력 UI는 기존 그대로이고 provider/실제ASR 표기를 읽기 쉽게 추가한다.

## 소유권

backend: service/, scripts/analyzer_openai.py, scripts/analyzer_codex.mjs, scripts/serve_codex_demo.mjs, scripts/transcribe_local.py, netlify/functions/, supabase/, web/pages-store.js. frontend: web/app.js/index.html/style.css/cloud-client.js. QA: tests/test_ai_service.py, tests/ai_service_qa.cjs, tests/codex_demo_qa.cjs와 전용 QA 산출물. root: 공통 계약/빌더/문서/실제 로컬 환경 설치/서버 실행·브라우저·배포/CI/통합. 동료 변경 되돌리지 않으며 재귀 위임 금지.

검증은 독립 모의검사와 실제 CLI/사진/음성/Supabase/브라우저를 구분한다. 사용자 API 잔액0이므로 실제OpenAI 성공 검사는 요구하지 않으며 구현·모의 계약검사 및 429 실측을 유지. 새 기본 시연의 실제 CLI 분석·담당자확정·DB 보존은 root가 실행한다.

## v2 검증과 제한된 재생성

충전 이후 실제 OpenAI 성공도 root가 검증한다. 모델이 실제 원문과 다른 인용을 만들어 검증에 실패하면 검증 규칙을 완화하지 않는다. 필요시 동일 원문·실제 전사·사진·허용 출처 목록과 오류를 다시 모델에 제공하여 최대 한 번 재생성할 수 있다. 최초 실패 응답은 격리된 임시 경로에서만 다루고 키/원시 로그를 공개하지 않는다. 마지막 응답도 동일 검증에 실패하면 작업은 failed이며 담당자 직접 입력·명시적 재분석을 안내한다. 재생성이 있었으면 실제 횟수·실행 ID·usage를 메타에 기록하고 전체 작업의 실행 시간·출력 한도를 유지한다. 실제 전사문을 정규화하거나 fixture로 채우지 않는다.

설정 직접 진입에서도 연결된 workspace 목록을 불러오고 다른 업무 메뉴 이동 때 빈 목록으로 오인하지 않게 한다. 연결 실패는 빈 목록과 구분하며 재시도를 제공한다. 로컬과 공개 설정에서 동일 업무 접근을 검증한다.
