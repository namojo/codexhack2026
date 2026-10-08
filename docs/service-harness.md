# 서비스 업무 검증 하네스

기본 업무 화면은 `web/`, 서버와 영속 상태는 `service/` 및 `scripts/serve.py`, 초기 사례는 `data/seed.json`, 실제 합성 첨부는 `data/media/`다. 재생 검증기와 엔진은 `web/replay/`, `rescue/`, `scenarios/`로 남아 있다.

service-v2는 기존 네이티브 작업자를 최신 입력 패킷과 명시한 새 소유권으로 재사용했다. builtin 역할 재사용을 새 프로젝트 역할이 자동 로딩된 것으로 주장하지 않는다. 다음 작업은 `.agents/skills/service-operations/SKILL.md`와 프로젝트 역할 `service_backend`, `service_frontend`, `service_seed`, `service_qa`를 사용한다. 역할 미노출 시 정의를 읽어 builtin worker로 대체하고 실제 ID를 장부에 기록한다.

## 실행/검증
- 업무 UI: `python3 -B scripts/serve.py --port 8765`
- API/영속/회귀: `python3 -B -m unittest discover -s tests -v`
- 결정적 재생: `python3 -B scripts/replay.py --all`
- 구조: `python3 -B .agents/skills/harness/scripts/validate.py --project .`
- 장부: `python3 -B .agents/skills/harness/scripts/validate.py --project . --run service-v3 --complete`

별도 새 컨텍스트의 QA 작업자를 기본으로 한다. 이번 service-v3에서는 새 작업자 생성이 thread limit로 실패해 메인이 제품 제작자와 별도로 테스트를 작성하고 seed·미디어 관계 및 브라우저를 검증했다. 기존 seed 작업자는 타인이 만든 backend/frontend 테스트 실행과 결과 기록만 맡았다. 이 실행자의 seed 자체검증을 독립 seed QA라고 부르지 않는다. 브라우저 검증은 신규 접수→추가 보고/첨부→배정/진행→결과 차단→올바른 근거 확정→재개/정정→이력→새로고침 보존 흐름을 수행한다. API 검사를 브라우저 PASS로 부르지 않는다. 썸네일 표시·이미지 확대·음성 재생을 따로 관찰하고 이력이 바뀐 화면 증거를 저장한다.

원본 seed를 덮어쓰거나 사용자 DB를 자동 초기화하지 않는다. 검증은 임시 DB를 쓰며 실제 브라우저 시연에서 입력한 테스트 사건도 가상 사건으로 남긴다. 입력/결과/소유권이 바뀌면 과거 승인 지문을 그대로 통과라고 보고하지 않고 새 런에서 재검증한다.

## service-v4 판단·조치 개선

현재 실행은 `service-v4`다. seed를 변경하지 않고 backend/frontend 및 별도 QA 세 작업으로 구성했다. 기존 실제 유휴 작업자를 최신 패킷과 프로젝트 역할 정의로 재사용했다. QA는 이번 backend/frontend 구현에 참여하지 않았으며 과거 자기 seed 제작의 독립 검증은 주장하지 않는다. 실제 브라우저는 메인이 수행한다. 전체71 tests·28 engine smoke·20fixture/91기대값·15모의DOM 및 메인 브라우저 증거는 [판단·조치 검증](attention-verification.md)에 있다. 현재 장부 검사는 `python3 -B .agents/skills/harness/scripts/validate.py --project . --run service-v4 --complete`이며 0 completion errors로 통과했다. 기존 v3 기록과 source도 보존한다.
