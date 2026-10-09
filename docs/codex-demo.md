# ChatGPT 로그인으로 다매체 신고 시연하기

별도 앱의 OAuth 로그인 구현이 아니라, 사용자가 ChatGPT로 로그인한 **Codex CLI를 로컬 분석기로 실행**한다. Netlify 공개 서버는 CLI나 로그인 토큰을 실행·보관하지 않는다. API 잔액과 별도로 Codex 계정의 사용 한도가 적용된다. [공식 비대화형 실행 안내](https://learn.chatgpt.com/docs/non-interactive-mode)를 참고한다.

## 준비

Node 22 이상, Python 3.11 이상, Codex CLI, Supabase 스키마가 필요하다. 공개판과 같은 DB를 사용할 경우 [서버 설정](ai-setup.md)의 SQL을 먼저 설치한다. 기존 DB를 초기화하지 않는다.

```bash
codex login
codex login status
python3 -B scripts/build_pages.py --mode cloud --output dist/ai-preview
```

음성 전사는 선택 설치다. 설치하지 않으면 음성 분석 실패를 표시하며 대본으로 대신하지 않는다. 공식 [OpenAI Whisper](https://github.com/openai/whisper)와 ffmpeg를 사용한다.

```bash
python3 -m venv .venv-demo
.venv-demo/bin/python -m pip install openai-whisper
```

현재 시연 환경에는 Whisper small과 모델 캐시가 설치되어 있다. 다른 컴퓨터에서는 첫 분석 때 공식 모델 다운로드가 발생한다. `.venv-demo/`와 `.cache/`는 Git에 포함하지 않는다.

## 실행

서버 환경에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`를 주입하고 다음을 실행한다. 키는 브라우저에 입력하지 않는다. OpenAI API 키는 Codex 시연에 필요하지 않다.

```bash
AI_PROVIDER=codex_cli LOCAL_WHISPER_MODEL=small \
  node scripts/serve_codex_demo.mjs --static dist/ai-preview --port 8769
```

또는 `--env-stdin`을 추가해 한 줄 JSON을 신뢰할 수 있는 비밀 관리 도구에서 표준 입력으로 전달한다. 서버는 값을 메모리로 받고 출력하지 않는다. 터미널에 직접 입력할 때는 입력 에코를 끄고, 키를 명령 인자·셸 이력·저장소에 넣지 않는다.

[로컬 시연](http://127.0.0.1:8769/#settings)의 설정 화면에서 ChatGPT 로그인과 음성 전사 상태를 확인한다. 제공자 변경은 로컬 세션 쿠키·CSRF·정확한 출처 확인으로 보호되고 다음 작업부터 적용된다. 공개 설정은 읽기 전용이다.

## 발표에서 보여줄 순서

1. 현장 메뉴에서 `INC-20261008-003`을 선택한다. “301호 3명 중 2명 구조, 1명 남음, 302호 전달은 정정”이라는 추가 신고를 분석한다. 남은 인원·위치 정정·현장 전달 사항을 보여준다.
2. 신규 접수에서 `data/media/flood-entrance.png`를 첨부한다. 사진에서 관찰한 침수 위험과 사진으로 확인할 수 없는 주소·인원을 구분한다.
3. `data/media/call-isolated.wav`를 전화 음성으로 접수한다. 실제 Whisper 전사와 위치·인원·보행 어려움 분석을 보여준다. 실제 전사에는 “새봄”을 “세봄”으로 잘못 인식한 사례가 있으므로 담당자가 음성을 다시 듣고 명칭을 확인한다.
4. AI 초안에서 119 항목을 수정하고 검토 사유와 확인을 입력한다. 그때 원문·첨부·AI 분석·담당자 수정·감사 이력이 Supabase에 함께 저장된다.
5. 새로고침하거나 공개판에서 동일 사건을 조회한다. 추가 보고와 수정이 유지되는지 확인한다. 현장 진행은 담당자가 별도로 변경하며 부분 구조를 전원 완료로 처리하지 않는다.

텍스트와 사진은 실제 CLI 입력이다. 음성은 실제 로컬 Whisper 전사 결과가 CLI 입력이다. 사진 생성 프롬프트나 TTS 대본을 관찰·전사 결과로 대신하지 않는다. CLI는 현재 사용자 모델 설정을 상속하고 격리 임시 경로에서 읽기 전용으로 실행한다.

## 나중에 OpenAI API 사용하기

API 잔액 확보 후 서버의 `OPENAI_API_KEY`, `OPENAI_MODEL`을 설정하고 `AI_PROVIDER=openai`로 활성화한다. Netlify는 재배포해야 환경 변경이 적용된다. 로컬 설정에서는 이미 서버에 설정된 API 제공자를 선택할 수 있다. Python `scripts/analyzer_openai.py --service`와 Netlify Responses·음성 전사 모듈은 구현되어 있다. 충전 전 [잔액 부족 실패](verification/openai-credit-failure.json)를 보존하며, 충전 후 [실제 세 사례](verification/openai-funded-passed.json)는 성공했다. 공개 활성화는 관리자의 명시 승인과 재배포가 필요하다.
