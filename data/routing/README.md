# 신림동 도로 스냅샷

`network.json`의 도로 좌표·도로명·통행 태그는 OpenStreetMap에서 추출했다. 다운로드: 2026-10-09.

- © OpenStreetMap contributors.
- 이 추출 데이터베이스의 OSM 부분과 파생 데이터는 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)에 따라 제공한다. [저작권 안내](https://www.openstreetmap.org/copyright).
- [원본 API 영역](https://www.openstreetmap.org/api/0.6/map?bbox=126.923,37.467,126.958,37.489).
- 재생성: 원본 XML을 별도 로컬 파일에 다운로드한 뒤 `python3 -B scripts/build_route_network.py SOURCE.xml` 실행. 원본 SHA-256은 meta.source_sha256에 저장된다.
- `destinations`의 요청 원문과 `closures`의 통제는 합성 훈련 자료다. 실제 피해·통제·수위·신고가 아니다.
- OSM 작성자 계정과 개인 프로필은 추출하지 않는다. 실제 소방서와 시장 같은 공개 시설 위치만 사용한다.
- 도로 유효폭의 현장 확인값은 0개다. 엔진의 도로 등급별 유효폭·속도·회전 비용과 차량 프리셋은 훈련 가정이다. 실제 장비 제원 및 현장 정보가 필요하다.
- 일반 도로 노드의 단순 회전 제한만 포함한다. 현재 추출된 단일 via-node 제한 34개. 신호 체계·임시 제한·회차 공간·차고 내부 및 마지막 건물 접근을 재현하지 않는다.

출동경로 조건과 한계는 [routing-contract.md](../../docs/routing-contract.md)에 기록한다.
