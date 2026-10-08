# 상황실 업무 콘솔 계약 v2

## 목표와 소유권
신고 접수, 사건 대조, 현장 진행, 처리 결과, 수정 이력을 실제로 조작하는 로컬 업무 콘솔이다. 공식 119 제품·내부 양식을 복제했다고 주장하지 않는다. 전부 가상 사례이며 외부 신고 전송 없음.
이번 service-v2 런 소유권이 v1 소유권보다 우선한다. backend=service/ 및 scripts/serve.py, frontend=web/ (web/replay/ 제외), seed=data/seed.json 및 docs/service-workflows.md, QA=tests/test_service_qa.py 및 지정 검증 산출물. main=이 계약·미디어 파일·문서·장부·통합. 동료 변경을 되돌리지 않고 재귀 위임하지 않는다.

## API
Python 표준 라이브러리 SQLite. Store(db_path, seed_path=ROOT/data/seed.json)라는 service.store.Store 공개 클래스를 제공한다. 데이터는 첫 시작에만 seed를 불러오며 모든 변경은 트랜잭션·감사 기록으로 저장한다. 수정 시 expected_revision 불일치는 409. JSON 오류 {error: 한국어 문장}; 성공은 사건 객체 또는 명시된 객체. 기본 담당자 '상황실 김담당'은 가상 사용자.
- GET /api/incidents -> {incidents:[요약 또는 전체 사건], resources:[팀]}
- GET /api/incidents/:id -> 전체 사건
- POST /api/incidents -> 새 사건. body {title,category,location,priority,summary,people_count,channel,text,actor,attachments:[]}. required title, location, text. 채널 voice/sms/mms/app/video_call/web/field, category flood/fire/rescue/medical/other, priority urgent/high/normal. 반환201.
- POST /api/incidents/:id/reports -> {expected_revision,channel,actor,text,kind:'additional'|'field'|'correction',people_count?:정수,location?:문자열,attachments:[]}. 원문 불변 추가; 인원/위치 정정은 명시 기록. 완료된 사건에 새 정보가 들어오면 자동 reviewing으로 재개하고 사유 기록. 반환200.
- PATCH /api/incidents/:id -> {expected_revision,actor,reason,title?,location?,priority?,people_count?}. 수정 이유 필수, revision 증가, 기존 값 audit 보존. 완료 사건에 중요 인원/위치 변경이면 reviewing.
- POST /api/incidents/:id/progress -> {expected_revision,actor,status:'dispatched'|'on_scene'|'rescuing'|'reviewing',team_id?:문자열,note}. 팀은 resources.id, 현재 사건에 배정된 팀만 사용할 수 있다. 종료된 사건이면 progress 거절 (먼저 reopen). note 필수.
- POST /api/incidents/:id/outcome -> {expected_revision,actor,outcome:'rescued'|'self_evacuated'|'transferred',confirmed_count:정수,basis_report_id:문자열,note}. 인원은 현재 people_count와 같고 해당 사건 field report의 people_count와 같아야 한다. 부분 구조는 완료 불가. 확인 대상 요청 총수와 연결 근거 확인 전 완료 불가. 완료 상태 closed, 결과·시각 저장. 팀 해제.
- POST /api/incidents/:id/reopen -> {expected_revision,actor,reason}. closed만 reviewing으로; 결과는 outcome_history로 보존하고 current outcome=null. 사유 필수.
- POST /api/uploads -> JSON {filename,content_type,data_base64}. PNG/JPEG/WAV/MP3/MP4,최대8MiB,실제 파일 헤더 확인,서버가 생성한 ID 파일명. {id,url:'/media/uploads/...',filename,media_type:'image'|'audio'|'video',caption,source:'operator_upload'} 반환201. 첨부는 업로드 응답 또는 아래 seed 형식. 상대 URL은 /media/ 아래 실제 허용 파일만. 읽을 수 없는/누락 첨부는 입력 거절.
- GET /media/... -> allowlist 경로, Content-Type와 Content-Length. WAV 재생 가능.
- GET /replay/ 및 /api/bundle -> v1 재생 검증 도구. 기존 make_handler(bundle) 인터페이스/테스트 유지. 신규 make_service_handler(store,bundle)로 CLI 서비스 제공.

전체 사건 필드:
{id,title,category,location,priority,status,summary,people_count,revision,created_at,updated_at,assigned_team_id:null|id,synthetic:true,reports:[],progress:[],audit:[],outcome:null|{},outcome_history:[],checks:[]}
report={id,channel,actor,text,kind,people_count?:int,location?:str,received_at,occurred_at,attachments:[]}
attachment={id,url,filename,media_type,caption,source:'ai_generated'|'tts_synthetic'|'operator_upload',transcript?:str}. transcript는 합성 대본/담당자 원문; 실제 ASR/OCR 실행 아님.
progress={id,status,team_id,note,actor,created_at}
audit={id,action,actor,reason,created_at,before,after}
checks=[{id,level:'warning'|'info',title,detail,report_ids:[]}]. 서버가 규칙으로 생성하는 확인 사항: 부분 구조 인원 불일치, 동일 건물 다른 세대, 위치 정정/신고자 GPS, 연락 두절, 미확정 결과. AI 호출 없으면 화면에 '규칙 기반 대조' 표시. AI 임의 점수/순위 금지. 담당자가 우선도를 지정한다.
status received/dispatched/on_scene/rescuing/reviewing/closed. 상태값 human label 접수/출동/현장 도착/구조 진행/확인 필요/처리 완료.
resources={id,name,type,status:'available'|'assigned',incident_id:null|id,crew_count}. 동시 배정 차단.

## Seed
{synthetic:true,resources:[...],incidents:[전체 사건]}. 8건 이상, 서로 다른 현재 상태, 문자·음성·사진·앱·현장보고 포함, 시각과 원문 일관성. ID INC-20261008-001부터. media URLs /media/flood-entrance.png, /media/flood-stairwell.png, /media/call-isolated.wav, /media/call-proxy.wav. 메인이 생성 예정. 사진 생성·TTS 대본과 seed caption 일치 필요. 사진은 flooded entrance / stairwell, 음성은 아래 대본. 최소2개 완료 사례 결과를 열람할 수 있도록.
음성1: "물 때문에 밖으로 나갈 수 없어요. 가상동 새봄빌라 이층 이백일호예요. 어머니와 저, 두 명이고요. 어머니는 걷기 어려우세요. 일층 입구로 물이 들어와요."
음성2: "저는 다른 곳에 있는 아들입니다. 어머니가 가상동 푸른빌라 삼층 삼백이호에 혼자 계세요. 제 휴대폰 위치는 어머니 집이 아니에요. 연락이 끊겨서 대신 신고합니다."

## UX acceptance
정상 첫화면은 업무 대시보드. 검색·상태/채널 필터·미처리/확인 필요/완료·가용팀 확인. 사건 상세는 원문·실제 사진/오디오·추가 신고/현장보고·근거 대조·담당팀/진행·결과/변경 이력. 사건 생성, 진행 수정, 추가 정보, 결과 확정, 잘못된 완료 차단, 수정 및 재개가 UI에서 동작한다. 브라우저 reload와 서버 restart 뒤 보존. 결과 수정은 이유를 넣어 재개 후 재확정하여 과거 결과를 보존한다.
마이크/사진 아이콘만으로 첨부인 척 하지 않는다. 실제 img/audio와 원문 제공. 접근성 label/focus/dialog Esc/한국어 오류/live toast, 폼 입력 보존, 취소 가능, 빈 상태. 데스크탑 업무 밀도·스크롤·모바일 대응. 고정 합성 배지는 작게 1개; 화면 전체를 발표 문구로 채우지 않는다. 안내에 공식 119 연계없음을 명시.
