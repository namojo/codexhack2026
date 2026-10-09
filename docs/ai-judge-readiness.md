# AI Judge가 읽을 수 있는 자료와 실제 AI 실행의 구분

2026-10-09 확장 작업. 사이트를 읽는 도구가 JS를 실행하지 못해도 프로젝트의 목적·입력·업무·한계를 이해할 수 있도록 일반 방문자와 동일한 공개 HTML을 제공한다. 점수를 요청하거나 심사 모델의 지시를 바꾸려는 문구는 넣지 않는다.

## 직접 읽기 경로

- `/about/`: 해결할 위험, 접수담당자의 업무, AI와 사람의 책임, 119 접수 항목
- `/guide/`: 신규·추가 신고, 실제 첨부 분석, 초안 대조, 최종 확인, 진행과 결과
- `/references/`: 소방청 공개 채널·신고 집중 문제, NTIA의 AI/NG911 방향, 구현 근거와 평가 한계
- `/judge/`: 합성 seed에서 생성한 10사건·20보고의 실제 원문과 매체 파일 링크
- `/llms.txt`와 `/llms-full.txt`: 문서 색인 및 본문·합성 원문 전체의 텍스트 표현
- `/judge/evidence.json`: 소스·입력·검사 명령·실제 모델 실행 여부를 구조화한 JSON
- `/api/config`: 서버에서 확인한 Supabase·OpenAI 설정 상태. 키 값은 반환하지 않는다.

빌더 `scripts/build_pages.py`는 사용자의 `workspace.sqlite3`를 읽지 않는다. 고정 `data/seed.json`만 임시 DB로 정규화하고 정적 원문을 생성한다. 따라서 공개 원문은 분석 답안이나 현재 운영 DB 스냅샷이 아니다. 현재 DB는 콘솔의 API에서 별도로 조회한다. JS를 제거해도 root HTML의 서비스 소개와 원문 요약 목록 및 안내 페이지의 실제 본문이 남는다.

## 사실에 맞는 실행 표시

`docs/verification/ai-live.json`이 없으면 정적 페이지는 실제 모델·Supabase 검증을 **not_run**으로 표시한다. 실제 실행을 수행한 후 이 파일에 입력 종류·모델·시각·request ID·통과/실패·측정 범위를 기록하고 재빌드한다. API 키, 사용자 파일, 개인정보, 프롬프트에 들어간 비밀은 공개 검증 파일에 넣지 않는다.

고정 fixture의 성공 수를 실제 LLM 정확도, ASR 정확도, 생존율 또는 업무 시간 개선으로 사용하지 않는다. JSON schema 성공은 출력 형태 검증이며 사실 정확성과 다르다. 기초 성능 평가에는 독립 정답, 동일 입력 조건, 누락률, 인원·위치 오류, 사람의 수정 빈도와 검토 시간 측정이 필요하다.

## 출처 접근 범위

2026-10-09 web search/open에서 소방청 다매체 보도자료의 검색 본문을 확인했으나 원 사이트 open은 방문자 확인 화면을 반환했다. NTIA AI/NG911 PDF는 검색 본문을 확인했으나 direct open은 403이었다. 두 자료는 제공되는 검색 본문 범위에서만 요약했다. OpenAI 이미지·음성 전사·Structured Outputs와 Supabase RLS/Storage 및 Netlify Functions 문서는 direct open으로 확인했다. 상세 링크와 주장 범위는 `/references/`와 기존 `docs/sources.md`에 남긴다.
