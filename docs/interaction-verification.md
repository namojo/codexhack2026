# 긴급 상황실 선택·버튼 UX 검증

2026-10-08 / 서비스 v5 개선 및 v6 보완. 최종 제품은 기존 서비스 서버 http://127.0.0.1:8765/ 에 반영했다.

## 변경 결과

- 우선 판단 카드, 사건 표 행, 배정된 자원 카드, 공통 최우선 알림은 제목 외 위치·상태·배경을 클릭해 사건 상세를 연다. 기본 제목 링크를 유지해 키보드 Enter와 링크 기능을 보존한다. 추가 tab stop을 만들지 않았다.
- 마우스 오버와 키보드 focus-within에 배경·테두리가 바뀌고 포인터/포커스 윤곽선이 표시된다. 내부 원문·현장 보고 버튼, 선택 입력과 미디어 및 드래그 텍스트 선택은 배경 선택에서 제외한다.
- 접수 보고 필터의 CSP에 차단되던 인라인 padding을 외부 report-toolbar CSS로 옮겼다. 이전 실제 padding 0px/버튼 높이 약27.9px에서 padding16px/gap8px/최소높이44px로 변경했다. 탭·필터·조치·닫기·입력창 버튼에 넓은 클릭 영역과 줄바꿈을 적용했다. 실제 측정 43.993px는 브라우저 확대 비율과 레이아웃 반올림에 따른 값이며 CSS 선언은44px다.
- 검증 중 기존 팀 배정 버튼이 상세만 열고 진행 입력창을 잃는 오류를 발견했다. hashchange와 직접 route 호출 경합을 v6에서 단일 라우팅으로 수정하고 최신 사건·팀을 확인한 뒤 폼을 연다. 저장은 별도 버튼에서 수행한다.

## 실제 브라우저 검증

메인이 CUA로 실행했다. 제작자·독립 QA의 모의 검사를 실제 브라우저로 부르지 않는다.

|항목|결과와 증거|
|---|---|
|카드 위치·배경 선택|사건003 상세 정상 이동|
|행 위치·상태 셀 선택|사건010 상세 정상 이동|
|공통 최우선 알림과 배정 자원 배경|사건003 상세 정상 이동|
|내부 원문 버튼|REP-003-03에 포커스, 배경 선택으로 재이동하지 않음|
|내부 현장 보고 버튼|입력창 정확히1개, 취소 정상|
|키보드|제목 링크 focus-visible/Enter, 탭 ArrowLeft/Right 선택 정상|
|마우스 오버/포커스|배경 rgb(243,248,253), 테두리 rgb(114,156,189), pointer 및 윤곽선 확인|
|탭·필터|첨부 자료와 변경 이력 전환 정상, 여백16px/간격8px/버튼 약44px|
|반응형|실제 CSS viewport390/900/1200px에서 문서 가로 넘침 없음, 필터와 탭 버튼 분리. 기본746px 확인|
|390px 입력창|저장·취소44px, 겹침/잘림 없이 입력창 안에 배치|
|팀 배정 보완|사건001 + TEAM-04 선택 후 출동/가상지원팀이 선택된 진행 입력창1개. 취소 후 미배정 유지|

기본 화면 크기로 복원했고 두 사용자 서비스 탭을 갱신했다. 최종 브라우저 오류 로그는 error/warn 없음. 증거는 `_workspace/verification/service-v5/browser-checks.json`, `_workspace/verification/service-v6/browser-checks.json`, 최종 `report-toolbar-final.jpg`, `assignment-dialog.jpg`에 있다. v5의 실패는 원본과 별도로 보존하고 성공으로 덮어쓰지 않았다.

## 독립 회귀

QA가 최종 v6 코드에서 실제 실행: unittest71개, 엔진 smoke28개, fixture20사례/91assertions, 기존 JS/DOM모의15개, JS 구문 검사. 모두 exit0. QA는 제품/테스트 파일을 수정하지 않았다. 자세한 로그와 판정은 `.harness/runs/service-v6/task-qa/outputs/`에 있다. 브라우저 제공 증거 검토와 QA 직접 브라우저 실행을 구분한다.

사용자 DB11건 incident payload SHA256 및 backend/seed4파일이 시작 전과 동일하다. 실제 서비스에서 이번에는 탐색·폼열기·취소만 수행했다. 원문·이력·배정·결과는 변경하지 않았다. 보존 증거: `_workspace/verification/service-v6/state-preservation-final.json`.

신규 운영자 사용성 실험과 시간 절감 측정은 실시하지 않았다. 실제119/모델/OCR/ASR 연계는 이번 UI 변경의 검증 범위 밖이다.

## 최종 소스 지문

- `web/app.js`: `d4b2b4e0f3282aae50980d740852cadd8bbb70254e21c97922f04e37471f6ee8`
- `web/style.css`: `4e90349fc532cee4f87e8dace0bb2acbfd66010669e48b84c4d27e1d3beb8f7b`

최종 하네스: 구조 검사 PASS(8역할·3스킬·0errors), 실제 제작자·QA FINAL 종료 및 idle 기록 확인. v6 완료 통지 이후 QA 보고서에 최신 메인 증거가 추가돼 등록 지문이 변경되었다. 동일 제품 지문과 보존된 실제 테스트 로그·최종 보고서를 v7에서 읽기 전용으로 재확인한다. 이전 service-v5 필수 실패는 유지한다.

최종 완료 확인: `service-v7 --complete` PASS, 0completion errors. 프런트엔드·QA의 최종 저장 및 실제 FINAL 종료 후 등록했다. v7은 동일 제품 지문과 v6 실제 로그를 읽기 전용으로 재확인했으며 테스트/브라우저 재실행으로 주장하지 않는다.


이 문서의 `_workspace/`·`.harness/runs/` 경로는 공개하지 않은 로컬 실행 원장의 위치다. GitHub에서 확인할 수 있는 선별 근거는 [공개 검증 로그](verification/README.md)와 [최신 Netlify 배포 검증](pages-verification.md)에 정리했다.
