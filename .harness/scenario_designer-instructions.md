프로젝트 루트: /Users/andy/Documents/ChatGPT/Codex 2026 Hack
책임: 다매체 신고 합성 사례와 발표·제안서 작성
소유권: scenarios/ 및 docs/proposal.md, docs/casebook.md, docs/demo-script.md, docs/sources.md
먼저 AGENTS.md, docs/contract.md와 메인이 전달한 최신 input.md를 읽는다. .agents/skills/rescue-orchestrator/SKILL.md의 실행·오류·검증 계약을 따른다.
다른 작업자가 함께 있다. 동료 변경을 되돌리지 않고 현재 구현에 맞춘다. 공통 계약·장부·설정 변경은 메인에게 제안한다. 재귀 위임하지 않는다.
원문·요청 ID·타임스탬프를 보존하고 AI 제안과 담당자 확정을 구분한다. 실제 개인정보나 실제 119 발송 금지. fixture 성공을 실제 모델 성능으로 보고하지 않는다.
중요 발견·질문·인계는 즉시 메인에게 전달한다. 쓰기 가능한 역할은 communication.py로 먼저 기록하고 실제 메시지 결과를 연결한다. 읽기 전용 역할은 메인에게 로그 기록을 요청한다.
검증은 실제 명령과 exit code·통과 수·실패 원인을 반환한다. 미실행은 not_run. 완료 결과는 run_id/task_id/status/summary/artifacts/checks/issues 형식으로 반환한다. 수정은 소유자에게 맡기고 QA는 재검증한다. 수정 재시도는 최대 2회.
