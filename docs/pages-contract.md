# GitHub Pages 공개 배포 계약

사용자 요청: 현재 아이디어·작업 과정을 GitHub namojo 계정에 정리하고 https://namojo.github.io/hack-test/ 에 사이트를 배포한다. 기존 로컬 SQLite DB 및 업로드는 변경·배포하지 않는다. 공개초기데이터는 synthetic seed10사건20보고와 생성PNG/WAV4개다. 공개 저장소는 namojo/hack-test(현재없음), 공개 Pages는 Actions로 생성한다.

## 기능과 경계
Pages는 정적 파일 호스팅이므로 기존 Python 서버판을 보존하고 공개판에 브라우저 저장 어댑터를 제공한다. 신규 사건·추가/현장/정정 보고·담당팀/진행·근거 결과확정·재개·수정 이력·매체확대/재생을 체험할 수 있다. 저장은 방문자의 localStorage이며 공동상황실/서버동기화가 아니다. 작은 합성배지와 브라우저체험 안내, 저장범위 안내, GitHub 프로젝트 소개 링크를 제공한다. 실제119/AI모델 연결없음. 하단 개발검증기는 공개하지 않는다.

## 소유권
- pages(backend builtin fallback /root/engine): web/pages-store.js + scripts/build_pages.py만. 다른 backend/seed파일 변경금지.
- frontend(/root/cases): web/app.js,index.html,style.css. adapter파일은다른작업자소유.
- QA(/root/qa): tests/test_pages_qa.py, tests/pages_qa.cjs 및 해당run QAoutputs. 제품파일변경금지.
- main: 이계약, 문서/작업과정정리, .github/workflows, 공개파일선별/지문/통합/브라우저/게시. 동료변경되돌리기/재귀위임금지, 모델설정상속.

## 어댑터 인터페이스
배포HTML에만 pages-store.js를 app.js보다앞서 defer주입한다(로컬HTML에는자동활성화없음). window.RescuePages.request(path,{method=GET,body}) -> Promise 객체 혹은한국어메시지+status 오류. app의api()가 window.RescuePages 존재때 request를호출, 없으면기존fetch. init은 상대 seed.json 로드, 기본경로 /hack-test/ 기준매체URL정규화, path별localStoragekey와버전. 병렬mutation직렬화/매번최신storage/revision검사; transaction은복제후검증/저장성공후반영(오류시무변경). quota오류무저장명시, 조용한휘발저장금지.

현재 service/store.py와service/attention.py 계약에동등한 주요가드: 필수문자열/정수/열거, revision409, 다른사건팀배정409, 부분구조/이전재개근거/다른사건근거/인원충돌 결과차단, 완료후새보고자동재개/이전결과보존, 원문불변, 최신규칙attention(근거substring 및 담당우선도불변). 연락/위치/인원정정후과거경보해소. API GET/POST/PATCH paths는 service계약과동일. attachment 업로드는브라우저저장범위/형식/헤더검증, 외부URL거절, 업로드dataURL보존/refresh재생. 저장공간용량오류는유저입력보존과오류안내.

build_pages.py --output dist/pages: 기존web UI3개+adapter,seed.json,media4파일및provenance, .nojekyll과build정보만출력. 결과HTML app/css/js 모두상대경로, 기존media루트경로는공개base와맞게어댑터정규화. 사용자DB/uploads, 개발replay, 하네스journal/계정키등은정적사이트에포함하지않음. 빌드출력은로컬전용ignore. 미디어는allowlist만복사, sourceSHA와gitcommit buildinfo.

## 검증
QA는주요mutation과revision/팀경합/부분완료/정정/재개/미디어/저장오류경계및Python판과대표case연속상태 비교, build서브경로/공개파일검사. 기존unittest/engine smoke/replay회귀유지. 메인이 /hack-test/ base의실제브라우저에서신규접수→첨부→배정→현장→완료차단→정상완료→정정재개/이력→reload보존, 모바일필터와미디어확대/재생을확인한다. 출판후GitHubActions성공및공개URL HTML/자산/실제브라우저동작확인한다. 검사실행과재사용범위/실제모델미실행을명시하고 모든저장및nativeFINAL후result등록.
