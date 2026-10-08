# 정적 체험판 검증과 배포

사용자의 최종 배포 대상은 Netlify다. 소스·아이디어·작업 과정은 [namojo/hack-test](https://github.com/namojo/hack-test)에 정리하고 사이트는 [namojo-hack-test.netlify.app](https://namojo-hack-test.netlify.app/)에 게시한다. 배포 후 commit·deploy ID·공개 브라우저 확인을 아래에 추가한다.

## 실제 실행한 검사

| 검사 | 수정 후 결과 | 근거 |
|---|---|---|
| 독립 Node 어댑터 | 21/21, exit 0 | [로그](verification/static-v2-node.log) |
| 전체 unittest | 78/78, exit 0 | [로그](verification/static-v2-unittest.log) |
| 엔진 smoke | 28/28, exit 0 | [로그](verification/static-v2-smoke.log) |
| 합성 fixture | 20/20 사례·91/91검사, exit 0 | [로그](verification/static-v2-fixture.log) |
| 기존 JS/DOM 모의 | 15개, exit 0 | [로그](verification/static-v2-dom-mock.log) |
| 하네스 구조·pages-v2 완료 | 각각 0 errors, exit 0 | 실제 등록한 결과와 동결 산출물 확인 |

[독립 QA 보고서](verification/static-v2-independent-report.md)와 [결과 요약](verification/static-v2-result.json)을 보존했다. 제작자의 자체 검사는 upload 16개·adapter 36개·build 12개이며 독립 검사와 구분한다.

## 발견한 실패와 수정

pages-v1은 Node 18/20, exit 1이었다. 실제 제공 PNG·WAV를 업로드한 뒤 사건에 연결할 때 큰 dataURL에 일반 URL 문자열 20,000자 제한이 적용됐다. [실패 로그](verification/static-v1-failure.log)와 [실패 결과](verification/static-v1-failure.json)를 보존했다.

v2는 payload를 uploads에 한 번 저장하고 보고에는 논리 첨부 URL을 기록한다. 등록된 URL만 매체로 해석한다. 실제 계단 PNG와 WAV를 5MiB 제한의 모의 저장소에서 연결·다중 보고·재로드해 원본 매체와 일치함을 확인했다. 두 번째 큰 PNG는 한국어 오류·507로 거절되며 저장 상태가 byte-identical이다. 이 5MiB는 검사의 명시적 제한이며 모든 브라우저의 실제 quota를 측정한 수치가 아니다. schema1 등록 dataURL과 과거 보고는 초기화하지 않고 읽을 수 있다.

## 메인의 실제 브라우저 확인

`/hack-test/` 서브경로에서 신규 가상 사건 접수→새로고침 보존→팀 배정→현장 보고→부분 구조 완료 제출 거절→정상 전원 확인·완료→이전 결과 보존 재개→변경 이력을 확인했다. 인원 수는 같지만 원문에 잔여 대상이 있는 보고도 실제 제출 시 거절됐다.

수정 후 실제 WAV 파일을 추가 정보로 업로드·등록하고 reload 후 재생했다. 기존 v1 사건·원문·이전 처리 결과를 그대로 읽었다. 합성 사진 확대는 1448px 원본이 로드됐으며 음성은 네이티브 재생 뒤 currentTime 5.67초를 확인했다. 카드 제목 밖 배경 클릭으로 사건 상세에 진입했다. 351px CSS 뷰포트에서 가로 넘침 없음·필터 버튼 44px·첨부 필터 동작을 확인하고 임시 크기를 복구했다. [브라우저 기록](verification/static-browser-flow.json)은 초기 v1 흐름과 수정 후 v2 첨부 경로를 구분한다. 후자는 새로운 음성 등록까지 실제 수행했으며 수정 후 큰 PNG의 UI 재업로드는 재실행하지 않았다. 큰 PNG의 등록·재로드·quota는 독립 어댑터 테스트로 확인했다.

원본 SQLite 11사건의 payload SHA와 보존 대상 backend·seed SHA를 읽기 전용으로 대조했다. 변경 0개다. [보존 결과](verification/original-state-preserved.json). 공개 초기 seed는 사용자 DB와 별개로 10사건·20보고다.

## 동작 범위와 제한

아홉 단계 대표 상태 변화는 Python과 정적 어댑터가 일치했다. 다만 공개판은 같은 인원 수라도 현장 원문에 잔여·부정·무응답 내용이 있으면 완료를 추가 차단한다. 보존된 Python 서버판은 같은 인원일 때 이 원문 경계를 허용한다. 완전한 동일 구현이라고 주장하지 않는다.

공개판 변경은 각 방문자의 브라우저에만 저장되며 공유·서버 동기화가 아니다. 실제 모델·OCR·ASR·공식 119 연계·운영자 성과 측정은 미실행이다. fixture 통과는 AI 정확도의 증거가 아니다.

## 공개 배포 확인

배포 완료 후 실제 코드 commit, GitHub Actions, Netlify deploy ID, HTTPS 자산·헤더와 공개 화면 검증을 기록한다.
