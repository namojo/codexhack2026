# GitHub 저장소 관리

현재 프로젝트의 주 저장소는 [namojo/codexhack2026](https://github.com/namojo/codexhack2026)이다. 2026-10-09 사용자 요청으로 연결했다.

| 항목 | 연결 |
|---|---|
| 기본 원격 `origin` | `https://github.com/namojo/codexhack2026.git` |
| 작업 브랜치 | `main`, `origin/main` 추적 |
| 이전 원격 `previous-origin` | `https://github.com/namojo/hack-test.git` |
| 서비스 URL | https://namojo-hack-test.netlify.app/ |

대상 저장소의 초기 커밋 `97eecb7c792c52c5c1c3a94d34a39f6057671c3b`와 Apache 2.0 LICENSE를 현재 프로젝트의 기존 커밋 이력과 병합했다. 이전 저장소를 삭제하거나 강제 푸시하지 않았다. 소스·합성 자료·아이디어·작업 과정·검증 문서와 GitHub Actions를 새 저장소에서 관리한다.

## 일반 작업

```bash
git status
git pull --ff-only
git switch -c codex/작업명
# 수정하고 관련 검사를 실행한다.
git add <수정한-파일>
git commit -m "변경 내용"
git push -u origin codex/작업명
```

새 브랜치의 Pull Request는 `namojo/codexhack2026`의 `main`을 대상으로 만든다. `.github/workflows/verify.yml`은 PR과 main의 제품 변경에서 Python·상태 엔진·합성 사례·브라우저 어댑터를 검사하고 정적 빌드를 확인한다.

사용자 SQLite·업로드·환경 키·컴퓨터별 실행 장부는 계속 `.gitignore`로 제외한다. 공개 자료는 합성 데이터만 사용한다. 서비스의 배포 주소와 저장 범위는 [배포 안내](deployment.md)를 따른다. 현재 Netlify 공개 배포는 CLI로 수행하며 GitHub push 자체가 Netlify 배포를 실행하지 않는다. 저장소 연결 작업에서 사이트의 운영 설정이나 방문자 데이터를 변경하지 않았다.

이전 `hack-test` Actions·배포 증거와 당시 계약은 역사 기록으로 남긴다. 새 작업과 PR의 대상은 `origin`의 `codexhack2026`이다.
