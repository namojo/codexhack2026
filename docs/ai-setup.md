# OpenAI와 Supabase 연결

사이트: https://namojo-hack-test.netlify.app/ · 저장소: https://github.com/namojo/codexhack2026

## 기본 해커톤 시연

OpenAI API 서버 연결 또는 ChatGPT 로그인 Codex CLI의 로컬 실행으로 시연할 수 있다. `codex login` 후 로컬 Node 시연 서버를 실행하고, 콘솔 AI 설정에서 연결 상태와 음성 전사 방식을 확인한다. CLI 인증 정보는 앱이 읽거나 클라우드에 복사하지 않는다. 실행 명령과 검증 결과는 [Codex 시연](codex-demo.md)에 정리한다.

## 서버 환경변수

Netlify의 해당 사이트 Project configuration → Environment variables에 서버 설정을 등록한다. Functions 전용 scope와 Secret 표시는 가능한 요금제에서 사용한다. 현재 Free 계정에서는 이 조합이 거절되어, 사용자의 명시적 승인으로 일반 서버 환경변수를 사용한다. 키는 웹 클라이언트·GitHub·빌드 산출물·검증 로그에 포함하지 않으며 snippet injection에서 참조하지 않는다. 키값을 출력하는 env:list 대신 이름만 조회하고 실제 서버 요청을 검증한다.

|이름|내용|
|---|---|
|`SUPABASE_URL`|선택한 프로젝트의 HTTPS URL|
|`SUPABASE_SERVICE_ROLE_KEY`|서버 전용 service-role/secret key; anon/publishable key는 해당하지 않음|
|`OPENAI_API_KEY`|OpenAI API 프로젝트 키|
|`OPENAI_MODEL`|실제 이미지 입력과 Structured Outputs를 지원하는 사용할 모델 ID|
|`OPENAI_TRANSCRIBE_MODEL`|음성 전사 모델; 기본 `gpt-4o-mini-transcribe`|
|`BACKGROUND_HMAC_SECRET`|서버가 분석 background 요청을 서명하는 비밀; 메인이 Netlify 서버에 생성 등록|
|`AI_PROVIDER`|공개 기본 `disabled`; API 사용 시 `openai`; 로컬 시연 기본 `codex_cli`|

환경변수 이름 목록의 확인은 연결 성공을 의미하지 않는다. 모델 접근 권한·API 요금·DB schema/Storage 권한은 실제 요청으로 검증해야 한다.

## DB 설치

`supabase/migrations/`의 SQL을 선택한 프로젝트의 SQL editor 또는 Supabase CLI migration으로 적용한다. 마이그레이션은 새 프로젝트용 테이블/함수와 비공개 Storage 버킷을 추가하며 기존 사건을 지우거나 덮어쓰지 않는다. 기존 다른 프로젝트를 실수로 선택하지 않도록 프로젝트 ID와 migration 대상을 먼저 대조한다.

브라우저는 Supabase 서비스 키를 알지 못한다. 같은 출처 Netlify API가 입력과 revision을 검증하고 DB CAS/RPC를 호출한다. 최초 workspace는 저장된 행이 없는 경우에만 합성 seed로 시작한다. public/anon의 직접 DB 쓰기와 서비스용 함수 실행은 허용하지 않는다.

## 빌드 및 배포

```sh
python3 -B scripts/build_pages.py --mode cloud --output dist/pages
netlify deploy --no-build --dir dist/pages --functions netlify/functions --site d82092f1-1013-4095-9bb4-ee2920bc72a0
```

미리보기에서 `/api/config`, 정적 문서, 추가 신고 분석/확정과 새로고침 보존을 검증한 후 같은 산출물에 `--prod`로 배포한다. 배포해도 DB/모델 환경변수가 없으면 명시적 연결 오류를 반환한다. '합성 사례 둘러보기'는 별도 localStorage 체험이다.

## 실제 검증 항목

합성 문자, 실제 생성 PNG, 실제 TTS WAV를 각각 모델에 넣는다. WAV 대본을 실제 전사로 대체해 전달하지 않는다. 실제 응답 ID/모델/입력 hash/소요 시간과 오류를 기록한다. 기존 사건에 추가 보고를 확인 등록한 뒤 다른 조회·재시작에서 원문/AI 메타/감사 이력이 보존되는지 확인한다. 두 수정의 CAS 충돌과 오래된 초안 확인 거부, 부분 구조 완료 거부도 검증한다. 실제 호출을 하지 못한 항목은 not_run으로 기록한다.
