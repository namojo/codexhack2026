# 5분 데모 대본과 전체 사례 탐색

이 데모는 집중호우 고립의 synthetic 사건 재생이다. `fixture_analysis`는 인간작성 분석이며 실제 LLM·OCR·ASR은 실행하지 않는다. 사진·영상은 텍스트 설명, 영상통화는 모의 전사다. 공식 119 시스템 연결·실제 신고·실제 출동은 없다. 모델 정확도나 생존율·시간 절감 수치를 제시하지 않는다.

## 시작 전 확인

현재 프로젝트 루트에서 `python3 -B scripts/replay.py --all`을 실행하고 새 산출물 디렉터리의 mode/입력 SHA256/checks를 확인한다. 브라우저 데모를 켜는 현재 명령과 URL은 README 및 `python3 -B scripts/serve.py --help`에서 확인한다. 실제 실행 결과가 실패하면 통과했다고 말하지 않는다. 발표자는 fixture 배지와 원문/분석/담당자 결정을 구분하는 화면을 먼저 읽는다.

## 핵심 세 사례, 5분

| 시간 | 조작·확인할 장면 | 말할 문장과 메시지 |
|---|---|---|
| 0:00–0:30 | synthetic·fixture 표시, 사건별 진행과 근거 패널 소개 | “우리는 집중호우 신고와 현장 보고 사이에서 아직 확인하지 못한 요청을 남깁니다. 지금 보이는 분석은 사람이 만든 픽스처입니다.” |
| 0:30–1:45 | `same-building` 선택, 초기화, E1/E2 다음 사건. 카드 R-A 201호3명·R-B 202호2명을 비교. E3에서 모호한 구조 보고와 질문. E4/E5까지 진행 | “같은 건물이어도 두 가구 원문과 ID가 남습니다. 건물에서 세 명 구조했다는 보고는 어느 가구인지 확정하지 못합니다. 담당자가 A 근거를 대조한 뒤에도 B 두 명은 남아 있습니다.” E3 후 A/B outcome=null, E5 후 A resolved·B 미확정을 확인 |
| 1:45–3:00 | `partial-rescue` 선택·초기화. E1 접수3명 → E2 구조2명, 인원 대조 알림. E3 승인 차단 → E4 전체3명 보고 → E5 확인 | “두 명 구조는 세 명 전원 완료가 아닙니다. 두 명으로 닫으려는 승인은 차단됩니다. 전체 근거와 현재 인원을 담당자가 대조해야 완료합니다.” E2/E3 outcome=null, E5만 resolved 확인 |
| 3:00–4:15 | `count-correction-stale` 선택·초기화. E1/E2 접수·보고2명 → E3 인원3명/revision2 → E4 오래된 revision1 결정 → E5/E6 새 근거와 결정 | “접수 인원이 바뀌면 이전 완료 승인도 낡은 정보가 됩니다. 과거 승인으로 닫지 않고 새 근거와 revision2로 대조합니다.” E4 closure_blocked, E6 resolved 확인 |
| 4:15–5:00 | 세 사례 checks/미확정 목록과 원문 근거. 이전 사건/초기화를 한 번 시연 | “증명한 것은 이 합성 입력의 상태 전이와 근거 대조 규칙입니다. 실제 모델 이해력은 별도 live 평가가 필요합니다. 교대 담당자에게는 남은 요청 ID와 확인 질문이 넘어갑니다.” 실제 실행 수와 경로를 읽되 계획 수치를 성과로 부르지 않음 |

각 사례의 최종 화면만 넘기지 말고 지정된 위험한 중간 사건을 멈춰 읽는다. 이전 사건은 과거 snapshot을 보여주는 UI 조작이며 실제 구조 상태를 되돌리는 명령이 아니다. 버튼 이름이 구현과 다르면 사례 선택·다음 사건·이전 사건·초기화·근거 보기라는 기능 기준으로 조작한다.

## 전체 케이스 탐색

발표 뒤 선택 목록에서 20개 사례를 직접 탐색한다. 일반 입력 17개와 오류 주입 3개를 구분해 아래 묶음 순서로 본다. 각 사례의 상세 기대값은 [사례집](casebook.md)과 JSON expectations에 있다.

| 묶음 | 사례 ID | 추가로 확인할 것 |
|---|---|---|
| 요청 보존·완료 인계 | same-building, partial-rescue, manual-duplicate-link, dispatch-not-complete, normal-completion | 두 카드 유지, canonical_id 수동 관계, 배정과 완료 분리, 도착 근거와 담당자 확정 |
| 위치·다매체 시각 | proxy-gps, late-location, unreadable-photo, old-video-new-text, video-call-transcript, multilingual-typo | GPS subject, 발생/수신/촬영 시각, 원문 인용, readable=false, fixture 전사 출처 |
| 결과 종류·새 정보 | self-evacuated, team-transfer, no-response, delivery-failure, count-correction-stale, post-resolution-update | rescued와 자력 대피/인계 구분, 무응답·전송 실패 확인 과제, 정정 이력과 재열림 |
| 오류 주입 output_fault | prompt-injection-rejected, fabricated-evidence, missing-analysis | 계약 밖 kind·없는 인용·누락 분석의 명시적 거절, 기존 카드와 원문 유지. live 정확도 평가 기본 제외 |

## 장애 시에도 같은 사실을 발표

브라우저가 실패하면 CLI 실행 보고의 이벤트 snapshots·checks를 화면에 보이고 브라우저 검증은 NOT_RUN/FAIL로 보고한다. live 공급자·자격증명·네트워크가 없으면 fixture만 발표하고 live는 NOT_RUN이라고 말한다. 어떤 실패도 다른 모드 결과로 숨기거나 실제 OCR/ASR 성공으로 바꾸지 않는다. 공식 출처 접근 한계는 [sources](sources.md)에 기록되어 있다.
