# 공개 검증 근거

실행 장부 전체는 컴퓨터별 경로와 임시 산출물을 포함하므로 로컬에 보존한다. 여기에는 검토에 필요한 실제 로그와 실패 요약을 선별했다.

- server-v6-unittest.log: 실제 71개 unittest, exit 0
- server-v6-smoke.log: 실제 28개 smoke, exit 0
- server-v6-fixture.log: 실제 20사례/91 assertions, exit 0
- server-v6-dom-mock.log: 기존 15개 모의 검사, exit 0. 실제 브라우저가 아니다.
- service-v5-failure.json: 모의/회귀는 통과했지만 실제 자원 배정 UX는 실패한 기록. v6에서 수정했다.

이전 단계의 원래 코드와 현재 정적 어댑터 확장을 구분한다. 추가 검사는 [배포 검증](../pages-verification.md)에 기록한다.

정적 공개판의 첫 실패와 수정 후 독립 결과도 보존했다. `static-v1-failure.*`는 실제 실패이며 `static-v2-*`는 수정 후 재실행한 검사다. `static-browser-flow.json`은 메인의 실제 UI 흐름, `original-state-preserved.json`은 원본 DB 읽기 전용 대조 결과다.

`netlify-*`는 실제 공개 HTTP·브라우저·배포의 선별 근거다. `github-ci.json`은 성공한 원격 Actions의 단계 상태다. 배포 토큰이나 원본 사용자 DB는 포함하지 않는다.
