# 배포 호스트 변경 — 최신 사용자 요청

사용자는 GitHub 정리와 GitHub Pages 배포를 요청한 뒤, 서비스 배포 호스트를 **Netlify의 내 계정**으로 변경했다. GitHub 문서·소스 공개는 유지하고 서비스는 Netlify에 배포한다. GitHub Pages는 활성화하지 않는다.

pages-v1, pages-store.js, build_pages.py라는 이름은 정적 페이지 어댑터와 빌드의 내부 명칭으로 유지했다. API·소유권·브라우저 저장·안전 가드·실제 검증 범위는 동일하다. 상대경로로 호스팅 루트와 `/hack-test/` 서브경로를 지원한다. 기존 입력 계약과 실행 이력을 뒤에서 수정하지 않는다.

QA는 구현 기능을 검증한다. 메인은 GitHub 게시, Netlify CLI 배포, 공개 URL과 호스팅 헤더를 확인한다. 연결된 Netlify CLI 계정의 팀 slug는 `namojo`, 표시 이름은 Andy다. 기존 여섯 사이트와 관계없는 새 프로젝트를 생성한다.

사용자 SQLite·업로드·환경 키·컴퓨터별 장부를 공개하지 않는다. 공개 사이트의 방문자 저장은 각 브라우저에만 한정되며 공유 DB가 아니다. 최종 URL·배포 ID·실제 검증은 [배포 검증](pages-verification.md)에 남긴다.
