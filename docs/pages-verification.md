# 정적 체험판 검증과 배포

사용자의 최종 배포 대상은 Netlify다. 소스·아이디어·작업 과정은 [namojo/hack-test](https://github.com/namojo/hack-test)에 정리하고 사이트는 [namojo-hack-test.netlify.app](https://namojo-hack-test.netlify.app/)에 배포했다. 다음은 실제 완료한 배포와 검증 기록이다.

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

- 코드 배포 commit: [`935423cfcd660d71334cdfb8fe05065b59daa446`](https://github.com/namojo/hack-test/commit/935423cfcd660d71334cdfb8fe05065b59daa446).
- [GitHub Actions 실행 37773325577](https://github.com/namojo/hack-test/actions/runs/37773325577): completed / success. 원격에서도 unittest 78·smoke 28·fixture 20사례/91검사·Node 21개와 정적 빌드 성공. [실제 CI 상태](verification/github-ci.json).
- Netlify 팀: namojo (Andy), 별도 새 사이트 namojo-hack-test. 기존 여섯 사이트는 변경하지 않았다.
- production deploy: `6ac784cf886e9f013f351579`, state ready, context production, CLI 배포. [불변 배포 주소](https://6ac784cf886e9f013f351579--namojo-hack-test.netlify.app/) · [배포 설정](https://app.netlify.com/projects/namojo-hack-test/deploys/6ac784cf886e9f013f351579) · [선별한 배포 상태](verification/netlify-production.json).
- HTTPS 공개 자산 11개는 모두 200. JS·CSS·seed·매체·build-info 10개 SHA는 빌드와 동일하다. HTML은 Netlify가 넣은 호스팅 안내 주석만 제외하면 정확히 동일하다. `.nojekyll`은 Netlify가 공개하지 않는 숨김 제어 파일로 404이며 서비스가 요청하는 자산이 아니다. [자산·헤더 기록](verification/netlify-http.json).
- `Content-Security-Policy`, nosniff, Referrer-Policy가 실제 응답에 있고 seed/build-info는 no-cache다. Python의 로컬 인증서 저장소 오류 후, 인증서 검증을 유지하는 curl로 HTTPS를 확인했다.
- 업무 화면을 가리는 기본 홍보 배지는 이 새 프로젝트에서만 공식 설정으로 껐다. [Netlify 공식 배지 설정 안내](https://docs.netlify.com/manage/projects/powered-by-netlify-badge/).

공개 HTTPS 브라우저에서 신규 사건에 실제 WAV를 첨부해 접수하고, reload 후 dataURI 음성의 10.718초 길이와 재생 상태를 확인했다. 팀 배정→전원 확인 현장 보고→결과 확정→reload→이전 결과 보존 재개·이력을 실제 수행했다. 부분 구조 seed의 완료 제출은 거절되고 입력이 유지됐다. 생성 사진 확대는 1448px 원본이 로드됐다. 390px CSS 뷰포트에서 가로 넘침 없음, 보고 필터 44px, 첨부 필터 동작을 확인하고 크기를 복구했다. 공개 탭의 warning/error 로그는 비어 있다. [공개 브라우저 기록](verification/netlify-browser-flow.json).

![실제 Netlify 공개 대시보드](images/netlify-console.png)

이 이미지는 공개 seed 10사건 상태의 실제 HTTPS 화면이다. 이후 브라우저 검증에서 만든 합성 사건 1건은 검증 브라우저에만 남고 다른 방문자의 seed에는 포함되지 않는다. 후속 문서 커밋은 배포·검증 기록과 화면 증거를 추가하며 제품 코드와 production 빌드는 변경하지 않는다.
