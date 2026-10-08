---
name: rescue-orchestrator
description: "아직 여기 프로젝트의 소방청 다매체 신고 기반 합성 사례 추가, 해커톤 데모 재생, 구조 인계 불일치 검증, 모델 출력 비교와 이전 결과의 부분 재실행에 사용한다. 실제 긴급 신고·출동·의료 판단은 수행하지 않는다."
---

# 아직 여기 오케스트레이터

## 목표와 완료 기준
공개된 다매체 채널을 입력 모델로 삼아 합성 구조 요청과 현장 보고를 재생한다. 제안서, 사례집, 실행 가능한 Python 엔진·CLI·브라우저 데모, 독립 QA, 재현 가능한 증거를 만든다. fixture와 live를 구분한다.

## 시작할 때
1. AGENTS.md, docs/contract.md, docs/sources.md, README.md와 최근 .harness/runs/ 기록을 읽는다. 없는 파일은 아직 생성 전으로 취급한다.
2. 메인은 공통 계약·scripts/·web/·설정·통합을 소유한다. rescue_engine_worker는 rescue/, scenario_designer는 scenarios/ 및 계약에 지정한 문서, rescue_qa는 tests/와 지정된 QA outputs/만 수정한다. rescue_reviewer는 읽기 전용이다.
3. 모델·추론 설정은 부모를 상속한다. 현재 런타임에 프로젝트 역할이 노출되지 않으면 정의를 읽어 builtin worker/default로 대체한 사실을 기록한다. 읽기 전용 리뷰어에게 파일 쓰기를 요구하지 않는다.

## 실행·작업 수명
1. 실제 cwd가 프로젝트인지 확인한다. `.agents/skills/harness/references/runtime-guide.md`의 첫 대기 자식 생성 점검을 따른다. 스키마와 실제 ID를 확인한 뒤 성공한 자식을 첫 작업에 재사용한다. 부모 스레드 오류로 ID가 없으면 추가 spawn을 중단하고 메인의 순차 작업과 네이티브 미실행을 분리해 기록한다.
2. `python3 -B .agents/skills/harness/scripts/run.py --project . init --plan-file .harness/plan-template.json --run-id NEW_ID`로 새 실행을 만든다. NEW_ID는 사용하지 않은 실행 ID로 바꾼다.
3. ready 상태와 쓰기 소유권을 확인한 후 start로 실제 ID를 등록하고 최신 input.md를 전달한다. 엔진과 사례는 독립 병렬 작업, QA는 양쪽 결과 등록 이후 실행한다. 자식의 추가 위임은 금지한다.
4. 중요 발견·질문·답변·차단·인계는 communication.py log로 기록하고 실제 collaboration 도구로 전달한다. recorded/sent/received를 구분하며 event ID로 연결한다. 로컬 기록만으로 전송 성공을 주장하지 않는다.
5. 결과는 run_id/task_id/status/summary/artifacts/checks/issues JSON으로 등록한다. 필수 checks의 실제 근거가 있어야 completed다. 제품 수정은 해당 워커, QA는 검증만 한다. 수정·재검증은 기본 최대 2회다.
6. 반환된 실제 유휴 상태를 별도로 관찰하고 run.py agent로 기록한다. 중단 요청만으로 소유권을 재배정하지 않는다.

## 사례 추가·분석
- docs/contract.md를 먼저 읽고 합성 출처·채널·발생/도착 시각·원문·fixture_analysis·중간/최종 expectations를 각각 작성한다.
- 같은 건물의 다른 가구, 대리 신고의 신고자 GPS, 늦은 위치, 읽을 수 없는 첨부, 연락 두절, 다른 팀 인계, 부분 구조, 잘못된 모델 출력과 오래된 완료 승인 중 영향받는 사례를 포함한다.
- fixture_analysis는 수작업 분석. 실제 모델에는 원본 이벤트와 직전 상태만 주고 fixture 및 expectations를 노출하지 않는다. live 분석 실패는 원문 보존·분석 거절로 나타내며 fixture fallback 금지.
- 모델 평가는 동일 사건 재생에서 fixture/live 결과를 따로 저장한다. 통과한 fixture assertions를 LLM 정확도 수치로 부르지 않는다. 시간 절감은 사람 비교 실험 없이는 미측정이다.

## 검증
- `python3 -B scripts/replay.py --all`로 전체 사례를 재생하고 새 artifacts/ 실행 경로를 보존한다.
- `python3 -B -m unittest discover -s tests -v`로 독립 경계면 검사를 실행한다.
- `python3 -B .agents/skills/harness/scripts/validate.py --project .`로 역할·스킬·포인터를 검사한다.
- `python3 -B .agents/skills/harness/scripts/validate.py --project . --run RUN_ID --complete`로 해당 실행 결과와 지문을 검사한다.
- 웹 데모는 실제 브라우저에서 사례 선택·다음 사건·되돌리기·초기화·근거 보기·결과를 확인한다. curl 성공을 브라우저 PASS로 부르지 않는다.

## 후속·오류
기존 실행을 덮어쓰지 않는다. `run.py resume --run OLD_ID --new-run NEW_ID`로 입력 변경의 영향을 받는 작업과 소비자를 재실행한다. 목표·소유권·acceptance 변경은 새 plan-file도 전달한다. 구조 검증·사건 재생·실제 모델·실제 브라우저·네이티브 실행을 각각 PASS/FAIL/NOT_RUN으로 보고한다. 미해결 필수 실패는 완료를 막는다.
