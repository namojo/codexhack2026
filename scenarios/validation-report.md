# 사례 담당 검증 기록

실행: rescue-v1 / 작업: cases / 상관 ID: 5798406d6fb945d39371a6044010a686

역할 적용: native builtin worker에서 .codex/agents/scenario_designer.toml을 읽어 적용했다. 추가 위임은 하지 않았다. 사례·배정된 문서만 수정했으며 communication.py는 스킬의 메시지 기록 계약에 따라 호출했다.

## 실제 검사

| 검사 | 결과 | 근거 |
|---|---|---|
| JSON·공통 입력 스키마 | PASS, exit 0, 20/20 | JSON 파싱·필수 루트 필드·synthetic·이벤트 ID 고유성·채널·분석 key·DSL 연산·after 대상 검사. 엔진 replay가 발생/수신 시각·첨부·위치·허용 분석/사람결정 경계를 함께 검증 |
| fixture 엔진 직접 재생 | PASS, exit 0, 20/20 사례·91/91 assertion | 최초 19/20에서 post-resolution-update의 인원변경을 count_correction로 명시하여 수정. 1회 수정 후 20/20 |
| CLI 전체 재생 | PASS, exit 0, 20/20 사례·91/91 assertion | `python3 -B scripts/replay.py --all --output /tmp/rescue-v1-cases-fixture-20261008-0410` |
| 문서 범위 표기 | PASS, exit 0, 4/4 | proposal/casebook/demo-script/sources에 인간작성 분석·LLM/OCR/ASR 미실행 범위 확인 |
| 공개 출처 직접 조회 | 일부 접근 제한 기록 | web open: 정책브리핑2·119홈·119다매체·INSARAG·삼척소방서 성공. nfa cnt1902 방문자 확인. sources.md에 주장 범위·재접근 결과 명시 |
| 독립 QA·실제 브라우저 | NOT_RUN by cases | 메인/QA 담당 통합 범위 |
| live LLM·실제 OCR·ASR | NOT_RUN by cases | 인간작성 fixture 결과와 분리 |

17 input_case / 3 output_fault, 57 이벤트, 중간 38 assertion. 잘못된 분석 출력 3개는 의도적인 오류 주입이고 analysis_rejected가 기대값이다. 해당 분석이 유효하다는 뜻으로 스키마 PASS를 해석하지 않는다.

## 보존 증거

[fixture-replay-evidence.txt](fixture-replay-evidence.txt)는 CLI JSON 보고의 원본 바이트 복사이며 전체 사건 snapshots·checks·입력 SHA256을 포함한다. 원본 실행 경로: /private/tmp/rescue-v1-cases-fixture-20261008-0410/report.json. 생성 시각: 2026-10-08T04:09:33.983120+00:00. mode=fixture, analysis_source=수작업 분석 픽스처.

## 검증 당시 파일 지문

| 경로 | SHA256 |
|---|---|
| docs/contract.md | 68da7b5795e42ac93b8e73c6b8603b630cf36f0922572d07fc326373cf7ac332 |
| rescue/engine.py | b97ad0cfd8bb5bd1dd35bf43f575bdd850178869a413c49542f285e7cf91a2eb |
| scripts/replay.py | d343effe71086eefe3af0231a4c4cccad51494396dc64face67461be7d40ac18 |
| scenarios/count-correction-stale.json | 58462cea179f1a3c25cc35f4ea26a9d2c74ae5fb6482a5b8b5ea0a4a02b361b7 |
| scenarios/delivery-failure.json | 3ec7532f8b1ed8516e51c616a216889fd88fb159403fd7fac72eac6a8fc558b3 |
| scenarios/dispatch-not-complete.json | 62533dae30c056fcc6d8ff29f2564785a1c4277c8be06be0440fb488559f8652 |
| scenarios/fabricated-evidence.json | 1bd49f7472dec576ad2c66ac5fdfb45795efa3e9140ee13b46118c78322c50e2 |
| scenarios/late-location.json | a88050dfb32e32d90ec9a40e1df1883c99d152753f0d0ed6d91e491054871c84 |
| scenarios/manual-duplicate-link.json | b402c7e8ed51a10188abf716da46cb323badd0266c837d754120ba3dc14dbe7b |
| scenarios/missing-analysis.json | 8297c5ea9fab757ec7a0370ffcb0a9f6385ffe2dbea4e120b5ceec389092fdb1 |
| scenarios/multilingual-typo.json | d87d8a3b8f2f79ba072d3265ad7af0bde6208294e22458e0aa975e2f8edf57fd |
| scenarios/no-response.json | 1b4fa4aa440e0cd1de575144b5bd94a8157ed5382bf1d88df8983ee79ca5cd33 |
| scenarios/normal-completion.json | 2b1b63b043cff9b3ba022cb55de2ae88c832008bb4e0c944a55991c7ba7b0941 |
| scenarios/old-video-new-text.json | 7647aaffbda197f40efdf23ab2a42333a85b9ee0a16f24851a55b93836830a9d |
| scenarios/partial-rescue.json | 9d4a3f855002162c831e5641d637d630fb0d00b50df38b9e921eb3663dd957bb |
| scenarios/post-resolution-update.json | 5c516a5435d28718ac6f60689f6c39fd6fcfa8901b027f3e9b068eafc0ee625e |
| scenarios/prompt-injection-rejected.json | d15fbf26db29c39ed24a9c3d7e342e1b42bb6fa9a9029b62b0041d7fe1f1cef6 |
| scenarios/proxy-gps.json | 0624156a9dab8845c1f4a923ed4d8aeb684a6716a90dcb8cbab42d09fdc61e80 |
| scenarios/same-building.json | 1cfa504006009ca5b8f1c01dc94484457d691ca396925722c0522244cfacd5f7 |
| scenarios/self-evacuated.json | 0a80cb2e786da3779d2525248b71e8ab8b65e750ae07fb690b8fb83c468f77d0 |
| scenarios/team-transfer.json | 30b5ad844f145477683c92a7f80589e6b848d0382fc017b40b4a7a790e672633 |
| scenarios/unreadable-photo.json | 73352f1cf08bbd2bb6b4946bd10f2bf85437c7d9ec608beba7f11b71de3e5daf |
| scenarios/video-call-transcript.json | 1f60aaed5d8cffe73e2c2433dec184af1cf8cff354dcb635bd7f82a9f10208a4 |
| docs/proposal.md | be2f58f349a760b0734f414fcce5f2eb0265555e940a5a553098db5c5918ad94 |
| docs/casebook.md | f47ca732a19c113368a855594c57d8a3883ff2a7b30775aafa291c22c555bb54 |
| docs/demo-script.md | 7ba94d89116c7b3fdfabec1f1713bab4189a2de4b6f53e918c475ae0494aefd4 |
| docs/sources.md | d31f87ab38b4b01874d52e595372f7fdf9931c49e6bffe38b138d7b125da13a6 |
| scenarios/fixture-replay-evidence.txt | eaab3b2d0f1ac7d9fc5626a9a205d1079aa8d41a8beca2266345678cb8a0cfb7 |
