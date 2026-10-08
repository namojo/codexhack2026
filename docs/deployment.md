# Netlify 공개 체험판과 로컬 서버판

- 사이트: [아직 여기](https://namojo-hack-test.netlify.app/) (Netlify 팀 namojo)
- 저장소: https://github.com/namojo/hack-test

## 공개 체험판의 저장 범위

Netlify에 정적 HTML/CSS/JS를 배포한다. 기존 Python 서버판과 별도로 `web/pages-store.js`가 합성 seed와 각 방문자의 localStorage를 사용한다. 업무 화면 `web/app.js`는 두 실행 방식이 공유한다.

초기 데이터는 합성 사건 10건, 보고 20건, 대응팀 4개, 생성 PNG 2장과 TTS WAV 2개다. 접수·추가/현장/정정 보고·팀 배정·진행·결과·재개와 이력은 현재 브라우저에 저장된다. 다른 기기나 방문자와 공유되지 않는다. 브라우저 저장 데이터를 지우면 체험 변경 내용도 사라진다.

화면에 저장 범위를 표시한다. 현재 체험판은 공동 상황실 DB나 공식 119 연계를 제공하지 않는다. 실제 개인정보를 입력하지 않고 가상 자료로 체험한다.

공개판에서도 인원·근거·revision·팀 중복 배정 가드를 적용한다. 저장 공간 오류는 저장 실패로 안내하고 입력을 보존한다. 생성 매체 provenance와 모의 전사 표시를 유지한다. 실제 모델·OCR·ASR 결과라고 표시하지 않는다.

## 로컬 서버판 실행

```bash
python3 -B scripts/serve.py --port 8765
```

첫 시작에 seed를 SQLite로 복사한다. 이후 수정은 원문·감사 이력과 함께 DB에 보존한다. 추가 패키지나 API 키 없이 실행하며 기존 사용자 DB를 배포하거나 초기화하지 않는다.

## 정적 빌드와 Netlify 배포

```bash
python3 -B scripts/build_pages.py --output dist/pages
```

이 출력 폴더만 Netlify에 올린다. 사용자 DB, 업로드, 환경 키와 개발 재생기는 포함하지 않는다. 정적 자산과 매체는 상대경로를 사용한다. 현재 Netlify에는 루트에 배포했으며, `/hack-test/` 서브경로는 별도 로컬 미리보기에서 검증했다. 빌드 정보에 소스 SHA와 Git commit을 남긴다.

`.github/workflows/verify.yml`은 제품 변경 때 서비스 검사·엔진 smoke·fixture·브라우저 어댑터 검사 후 빌드한다. 배포는 연결된 Netlify CLI 계정으로 수행한다. 저장소에 배포 토큰을 넣지 않는다. `netlify.toml`에 빌드 명령, 공개 폴더와 보안 헤더를 정의했다.

```bash
netlify deploy --prod --no-build --dir dist/pages --site SITE_ID
```

[Netlify 공식 CLI 안내](https://docs.netlify.com/api-and-cli-guides/cli-guides/get-started-with-cli/)의 정적 폴더 배포 방식을 사용한다. Netlify의 Git 연동을 별도로 설정하는 경우 같은 빌드 명령과 공개 폴더를 사용한다. 이번 배포는 기존 계정 인증으로 수행하며 새 토큰이나 GitHub secret을 만들지 않는다.

최신 사용자 요청에 따라 GitHub Pages 배포는 취소했다. [호스트 변경 결정](netlify-deployment-decision.md)을 보존한다. 실제 commit·CI·Netlify deploy ID·공개 URL·브라우저 검사 결과는 [배포 검증](pages-verification.md)에 기록한다.
