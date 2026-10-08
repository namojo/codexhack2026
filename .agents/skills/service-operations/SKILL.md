---
name: service-operations
description: "아직 여기 상황실 콘솔의 합성 다매체 사례, 접수·추가정보·진행·결과·정정 업무, 실제 첨부와 영속 상태를 확장하고 검증하는 절차. 공식 119 접수·출동을 수행하지 않는다."
---
# 서비스 업무 오케스트레이터

## 입력과 판단
AGENTS.md, docs/service-contract.md, docs/service-design-brief.md, docs/service-harness.md, README.md를 읽는다. 이 스킬의 서비스 업무에는 v2 계약 소유권이 기존 v1 재생 소유권보다 우선한다. docs/contract.md는 보존된 재생 엔진 계약이다. 합성 자료만 사용하고 실제 개인정보·신고 발송 금지. 규칙 기반 대조, 실제 모델 분석, 담당자 결정을 구분한다. 실제 생성한 이미지/WAV도 실제 피해 자료나 OCR/ASR 결과라 부르지 않는다.

## 역할과 수명
서비스 변경에는 service_backend(service/·scripts/serve.py), service_frontend(web/·web/replay/ 제외), service_seed(data/seed.json·배정 문서), 독립 service_qa(tests/·배정 QA산출물)를 위임한다. 메인은 공통 계약, 생성 미디어·provenance, 통합, 브라우저 검증을 소유한다. 제작자는 QA를 겸하지 않는다. 서로의 변경을 되돌리지 않고 자식의 재귀 위임은 금지한다. 모델 설정 상속. 역할 미노출 시 정의를 읽고 builtin 대체 기록.
`.agents/skills/harness/references/runtime-guide.md`를 따라 새 run의 ready→실제 유휴/대기 자식→start(실제 ID)→최신 input.md 전달→result→실제 유휴 확인→agent idle 순서를 준수한다. 중요 발견과 메시지는 communication.py recorded→실제 네이티브 전달→sent/received 연결. 재사용 때 최신 소유권을 읽게 한다. 입력·결과 지문이 변경되면 새 런에서 영향 작업과 소비자 재검증. 장부를 실제 네이티브 실행 증거로 대체하지 않는다.

## 사례와 미디어
새 사례는 접수부터 완료까지 원문·발생/접수 시각·채널·각각의 가구/사건ID를 보존한다. 새 seed는 이미 저장된 DB를 자동 덮어쓰지 않는다. 이미지·오디오·영상 첨부라면 실제 파일, MIME, 캡션, source, 대본/생성프롬프트 provenance가 필요하다. 변경으로 참조가 깨지면 실패다. 개인이 올린 파일은 파일헤더/크기/경로를 검증하고 raw 신고원문을 덮어쓰지 않는다.

## 완료 검사
- 임시 DB 독립 QA: 신규 접수, 추가 정보, 인원·위치 정정, 팀배정경합, 진행변경, 부분구조 완료차단, 근거 없는/다른사건/오래된revision 차단, 정상완료, 신규정보 자동재개, 결과정정 및 이전결과이력, reload/restart 보존, 업로드·정적경로 검증.
- 실제 브라우저: 검색·필터·상세→사진확대/음성재생→신규접수→추가보고→진행→결과→수정/재개. 오류 후 입력보존·취소·빈상태·모바일검사. API 성공을 브라우저 검증으로 부르지 않는다.
- 기존 엔진 회귀: unittest 전체 및 replay --all. fixture 통과는 AI 성능 증거 아님.
- 하네스 구조+새run --complete. 실패/미실행/권한 제한은 정확히 구분. 필수 실패가 남으면 완료하지 않는다. 브라우저 화면 증거와 테스트수/exit code/미실행 범위를 docs에 기록한다.
사용자 DB 삭제·초기화는 수행하지 않는다. 공유 운영 배포나 실제 신고 연동은 별도의 요청과 검토가 필요하다.
