# 해커톤 대표 사건 계약

모든 신고·사람·위험·현장 사진·음성은 synthetic이다. 공식 신고·출동 연결 없음. 기존 사용자 DB와 GitHub의 경로 구현을 지우거나 초기화하지 않는다. AI 초안/실제 모델 결과/수작업 seed/담당자 확정을 구분한다.

## 대표 사례
- 대표 사건 ID INC-20261009-100, demo_featured:true. 제목 '태풍 침수 지하주차장 · 여성 3명 중 1명 미구조'. 가상동 한빛길 31 한빛복합센터 B2, 기둥 B2-C07 인근(확인 필요). 층·기둥은 신고자 진술과 사진 후보이며 좌표/공식 건물 DB 연결로 확정하지 않는다.
- 여성3명=고령 여성1/여자아이1/성인 여성1. 현장팀이 앞의2명 구조, 성인1명 잔류. people_count=3/status=rescuing; 원문 보고의 구조2와 미구조1을 분리, 완료 차단 유지. 새 전원 구조 field 근거와 담당자 확인 전 outcome=null.
- 신규 가상 자원 TEAM-DEMO01 4명, 대표 사건에만 배정. 기존 팀 배정 보존.
- 중복 후보 사건 INC-20261009-101, 미배정·people_count=null. 바깥 가족 신고와 SNS 문자 원문2개를 보존하고 동일인 여부 사람 확인. 자동 병합/추가 출동/인원 차감 금지.
- 신고 폭주 배경은 태풍·폭우·해일(허리케인 등 자연재해의 국제적 적용 맥락); 실제 재난 통계·임의 효과 수치 없음.
- 원문 수신→문자→잡음 음성→어두운 사진→중복 재신고→현장2명구조→성인여성 추가문자→현장 진입 사진의 시계열. main 최소7보고, duplicate2보고. 실제 발생·접수 시각, 보고ID, 원문, 진행이력 유지.

## 실제 매체 경로 (root 생성, 계약만 먼저 제공)
- /media/parking-pillar-dark.png: 저조도 침수 지하주차장, 비상등, 물 튀긴 렌즈/약한 흔들림, 'B2'/'C07' 기둥 표기. 원문에 표시 후보를 넣되 눈으로 본 생성 결과와 실제 모델 해석을 별도 검증한다.
- /media/parking-stair-flood.png: 동일 훈련의 침수 통로/계단 입구 현장 관찰. 사람·실제주소·소방기관 로고 없음.
- /media/parking-call-noisy.wav: 실제 TTS 목소리에 생성 강우·저주파·물소리 잡음이 섞인 합성 PCM WAV.
- /media/parking-call-enhanced.wav: 위 noisy파일을 실제 DSP로 처리한 비교용 WAV. 깨끗한 대본/원음을 복구 결과인 척 사용하지 않는다. 보장된 화자분리/의미복구/실제모델ASR이 아니다.
- 대본: '여기는 가상동 한빛복합센터 지하 이층 주차장이에요. 기둥 씨 공 칠 근처에 여자 세 명이 있어요. 할머니와 여자아이, 저예요. 비상등만 켜져 있고 물이 계속 들어와요. 계단으로 나갈 수 없어요.'
- attachment는 기존 계약 id/url/filename/media_type/caption/source/transcript만; source 이미지ai_generated/음성tts_synthetic, transcript는 합성 대본이라는 캡션. 실제 ASR은 별도 실행 기록/AI초안에 저장. 생성provenance 원본hash/처리알고리즘/대본 보존.

## 노출·메뉴
진행 사건/대시보드 대표 사건을 제일 앞에 배치하되 실제 긴급도를 조작하는 점수 없음. '발표 대표 사례' 표시로 정렬 이유 명확화. 상세에서 시간순 자료, 잡음원본/처리비교 실제audio, 부분구조 미확인 인원/시급한 이유/다음확인 액션. 기존 AI 분석·담당자 등록·진행·결과 기능 재사용.
공간정보 /spatial/ 과 GitHub 최신 /routes/는 별도 메뉴. 공간목업(더포엠 역삼), 경로(관악→신림 OSM/과거침수)는 대표 가상 B2건물과 자동 좌표연결/실시간 최적출동했다고 주장하지 않는다. route network·flood-history·engine 원문/조건/불가검사 보존.

## 미래 과제
현장캠/CCTV/기상/지자체3D건물/공공데이터/현재통제·침수정보 통합. Codex가 정기 수집·정규화·출처/라이선스/관측시각/좌표계/버전/품질검토 이력을 누적하고 새 데이터와 분석 개선을 재평가. 학습 완료나 무검토 자동수집을 현재 구현으로 주장하지 않는다. 영상프레임분석·화자분리·실제3D대응은 현재 미구현 범위를 명시. 연구출처는 적용가능성과 논문 자체평가를 구분하며 우리서비스 구난효과 증명으로 바꾸지 않는다.

## 소유권
root=이 계약/미디어·provenance/scripts빌더·judge/연구·ToDo/기존공유DB에append/브라우저/배포. backend=service/store.py·attention.py/web/pages-store.js 및 seed media검증/선택명시 demo_flag정렬. frontend=web/app.js·index.html·style.css/spatial/index.html/routes UI shell 통일, route engine/data무수정. seed=data/seed.json 및 docs/hackathon-case.md·hackathon-demo-script.md. QA=tests/전용산출물 제품무수정. 동료변경되돌리지않고 재귀위임금지.
