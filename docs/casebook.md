# 합성 사례집

20개 결정적 사건 재생 사례다. 모든 인물·장소·좌표·미디어는 synthetic이다. fixture_analysis는 인간작성 분석이며 실제 LLM·OCR·ASR 실행 결과가 아니다. 영상·사진은 텍스트 설명, 영상통화는 모의 전사다. 원문 이벤트와 분석 제안, 담당자 결정은 분리되어 있다.

검증은 최종 상태뿐 아니라 `after`로 지정한 위험한 중간 상태를 검사한다. 아래 기대결과는 검증 목표이며, 실제 통과 여부는 새 실행 산출물의 checks/passed에서 확인한다. fixture PASS는 실제 모델 정확도나 생존율·시간 절감을 입증하지 않는다.

| 사례 ID | 상황과 기대결과 | 발표 포인트 |
|---|---|---|
| [same-building](../scenarios/same-building.json) | 같은 건물의 다른 가구: 원본 두 카드 유지; 모호한 보고로 A 완료 금지; 모호한 보고는 확인 대기; 모호한 보고로 B 완료 금지; 가구 특정 확인 질문; A만 사람 확정; B 미확정 유지; B 인원 보존 | E3에서 두 카드와 가구 특정 질문을 보인 뒤 E5에서 A만 완료되고 B가 남는 장면. |
| [partial-rescue](../scenarios/partial-rescue.json) | 부분 구조는 전체 완료가 아니다: 부분 구조 인원 대조; 부분 구조 미완료; 부분 보고 확인 대기; 2명 완료 승인 거절; 원래 요청 인원 유지; 전체 근거 후 완료; 보고는 revision 유지 | 2명 구조 보고와 3명 접수의 차이를 강조하고 전체 보고와 담당자 결정 후만 닫는다. |
| [proxy-gps](../scenarios/proxy-gps.json) | 대리 신고자의 GPS: 대상 텍스트 위치 유지; 신고자와 대상 위치 확인; GPS만으로 완료 금지; 접수 최초 버전 | GPS subject=reporter를 근거 패널에서 보여주고 대상 위치와 분리한다. |
| [manual-duplicate-link](../scenarios/manual-duplicate-link.json) | 중복 후보는 사람이 연결: 중복 후보 수동 검토; 자동 병합 없는 두 카드; 담당자 연결 관계; 연결 후에도 두 원본; 연결이 완료가 아님; 관련 원본도 미완료 | E3 두 카드 → E4 canonical_id 관계를 보여주며 실제 합쳐 삭제하지 않는다. |
| [late-location](../scenarios/late-location.json) | 늦게 도착한 옛 위치: 새 위치 반영; 위치 변경 버전; 늦은 옛 위치 덮기 금지; 위치 사건 시각 유지; 무시한 위치는 버전 유지; 옛 위치 이력 표시 | received_at과 occurred_at을 나란히 읽고 E3 후에도 301호가 유지되는지 보인다. |
| [unreadable-photo](../scenarios/unreadable-photo.json) | 읽을 수 없는 사진: 첨부 해석 불가 확인; 이미 접수된 인원 유지; 사진만으로 완료 금지; 읽지 못한 첨부는 수정 아님 | 실제 이미지 대신 텍스트 미디어 설명과 readable=false임을 밝힌다. |
| [old-video-new-text](../scenarios/old-video-new-text.json) | 오래된 영상보다 새로운 문자: 새 문자 위치; 옛 영상 덮기 금지; 실제 새 정보만 버전 증가; 옛 영상 촬영 시각 확인 | 텍스트 설명 영상의 captured_at과 새 문자의 시각을 대조한다. 영상 인식 성능을 시연하는 것이 아니다. |
| [video-call-transcript](../scenarios/video-call-transcript.json) | 영상통화 모의 전사: 전사에 기재된 두 명; 영상 해석은 접수 상태; 영상통화만으로 완료 금지 | transcript_source=fixture를 직접 보여주고 실제 영상통화 연결·ASR은 실행하지 않았다고 말한다. |
| [multilingual-typo](../scenarios/multilingual-typo.json) | 외국어와 오타가 섞인 문자: 원문 두 명 추출; 위치 표기 정리; 번역만으로 완료 금지 | 정규화된 카드 옆 원문을 확인한다. 이 픽스처는 실제 번역 모델 성능 증거가 아니다. |
| [self-evacuated](../scenarios/self-evacuated.json) | 자력 대피의 담당자 확인: 인계 진술만으로 미확정; 담당자 대조 후 완료; 구조와 구분된 완료 종류 | E2는 AI 제안과 확인 대기, E3는 담당자 결정으로 완료. outcome을 구조 완료와 구분해서 읽는다. |
| [team-transfer](../scenarios/team-transfer.json) | 다른 팀 인계의 담당자 확인: 인계 진술만으로 미확정; 담당자 대조 후 완료; 구조와 구분된 완료 종류 | E2는 AI 제안과 확인 대기, E3는 담당자 결정으로 완료. outcome을 구조 완료와 구분해서 읽는다. |
| [no-response](../scenarios/no-response.json) | 연락 두절은 미확인: 재확인 질문; 무응답 결과 추론 금지; 원래 인원 유지; 무응답은 정보 수정 아님 | 알림 질문과 남아 있는 원문을 보여주며 무응답이 상태 증거가 아니라고 설명한다. |
| [dispatch-not-complete](../scenarios/dispatch-not-complete.json) | 배정은 완료가 아니다: 담당자 배정 상태; 배정 결과 미확정; 배정은 정보 버전 유지 | 배정 상태와 빈 outcome을 함께 보여준다. 실제 출동 명령은 전송하지 않는다. |
| [count-correction-stale](../scenarios/count-correction-stale.json) | 인원 정정 뒤 오래된 완료 승인: 보고만으로 미완료; 명시적 인원 정정; 정정 버전 증가; revision 1 승인 차단; 낡은 승인으로 완료 금지; 새 인원과 버전 확인 후 완료; 보고와 확인은 revision 유지 | E3에서 2→3명·revision 2를 짚고 E4 실패를 보인 뒤 E6에서 새 근거로 완료한다. |
| [prompt-injection-rejected](../scenarios/prompt-injection-rejected.json) | 프롬프트 인젝션으로 만든 분석 거절: 계약 밖 완료 분석 거절; 사용자 명령으로 완료 금지; 기존 카드 보존; 거절된 분석은 정보 변경 없음 | 원문 안의 공격 문장과 분석 resolve 거절을 비교한다. 이는 모델의 인젝션 내성을 측정한 결과가 아니다. |
| [fabricated-evidence](../scenarios/fabricated-evidence.json) | 원문에 없는 근거 인용 거절: 허위 인용 분석 거절; 허위 근거 완료 금지; 거절 전 상태 보존 | 실제 원문과 evidence_quote를 대조해 없는 문장을 거절한다. |
| [missing-analysis](../scenarios/missing-analysis.json) | 누락된 분석의 명시적 거절: 누락 분석 명시 표시; 누락 분석으로 완료 금지; 접수 원본 인원 보존 | 분석 누락과 원문 보존을 보인다. live에서도 fixture fallback이 금지된다. |
| [delivery-failure](../scenarios/delivery-failure.json) | 전송 실패는 안내 완료가 아니다: 미전달 확인 질문; 전송 실패 미확정 유지; 실패는 정보 변경 아님 | 전송 실패 알림을 확인한다. 하네스 밖 메시지를 실제 발송하지 않는다. |
| [normal-completion](../scenarios/normal-completion.json) | 근거를 대조한 정상 완료: 배정 중간 상태; 배정은 완료 아님; 구조 보고도 미확정; 전체 보고도 확인 대기; 담당자 근거 대조 완료; 완료 종류 구조; 정보 불변 버전 | 완료까지 네 단계와 근거 E3, expected_revision 1을 연결해서 보여준다. |
| [post-resolution-update](../scenarios/post-resolution-update.json) | 완료 후 새 정보가 오면 재확인: 초기 완료; 새 정보 후 완료 해제; 새 접수 인원 반영; 새 위치 반영; 새 정보 버전; 완료 후 변경 재확인 | E3 완료를 보여준 뒤 E4에서 미확정으로 다시 열리고 알림이 남는지 본다. |

## 적용 계약

초기 카드 revision은 1이며 사람 수·위치·필요 정보가 실제 변경될 때만 증가한다. 배정·단순 보고·알림은 revision을 증가시키지 않는다. 같은 건물, 중복 후보, 부분 구조를 이유로 요청 ID를 없애지 않는다. `confirm_outcome`은 도착한 해당 요청의 구조/안전 근거, 현재 접수 인원, 현재 revision을 대조한다. 원문·개별 ID·발생/수신 시각을 보존한다.

일반 사례는 test_kind=input_case, prompt-injection-rejected/fabricated-evidence/missing-analysis는 test_kind=output_fault다. live 정확도 평가에서 output_fault를 기본 제외하고 오류주입 회귀 결과로 따로 표시한다.

거절 사례는 일부러 잘못 작성한 fixture 분석 또는 누락 분석을 담는다. 시나리오 JSON 자체를 손상시킨 것이 아니다. 인젝션 사례는 계약 밖 kind 거절을 증명하는 회귀 사례이며, 실제 모델이 항상 공격을 방어한다는 주장은 하지 않는다.

## 재생과 증거

`python3 -B scripts/replay.py --all`로 전체를 재생하고 실제 실행 명령, 입력 SHA256, mode, 이벤트별 snapshots와 checks가 보존된 새 산출물 경로를 확인한다. 개별 사례와 CLI 인자는 `python3 -B scripts/replay.py --help`에서 현재 구현을 확인한다. live는 해당 이벤트 모델 출력이 누락되면 analysis_rejected로 남겨야 하며 fixture로 보충하지 않는다. 독립 QA·브라우저·live 결과는 각각 별도로 보고한다.
