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

## 서울시 침수흔적도

`flood-history.json`은 [서울 열린데이터광장 OA-15636](https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do)의 공식 SHP 자료를 이 도로망 영역으로 잘라 만든 실제 공개 공간자료다. 제공기관은 서울특별시 물순환안전국 치수안전과. [공공누리 제1유형](https://www.kogl.or.kr/info/licenseType1.do): 출처표시, 상업적 이용·변경 가능. 원본 자료 갱신 2026-04-27, 다운로드 2026-10-09.

2010~2025 제공 14개 연도 ZIP 모두 확인했다. 2015·2021은 제공기관이 침수 없는 연도로 안내해 파일이 없다. 2026 자료는 없다. 이 지도 영역에는 2010/2011/2022/2023/2024 기록이 있다. 원본 파일명 대신 DBF의 `F_YR` 침수년도로 분류한다. 2022 ZIP에 들어 있는 일부 2023 기록은 2023으로 합친다. 주소·PNU·피해 원문 속성은 출력하지 않는다. 다운로드 POST 필드·ZIP SHA256·원본 좌표계·선택/보정 건수는 JSON `meta.sources`에 있다.

PRJ를 읽어 EPSG:5179에서 연도별 폴리곤 합집합 및 도로 중심선 교차 길이를 계산하고 EPSG:4326으로 표시한다. 같은 연도 중복 영역은 한번만 계산한다. 폴리곤은 단순화하지 않는다. 등록 위치와 도로 중심선 차이에 대한 **주변 10m 훈련 가정**은 실제 관측 경계와 별도로 저장·표시한다. 8 × 연도별 주변 통과 길이의 합을 차량 권고 비용에 추가한다. 반복 연도는 비용에 더해지지만 미래 확률을 계산하지 않는다. 현재 통제·수심·안전 보증이 아니다.

재생성에만 GIS 패키지가 필요하다. 일반 서버/브라우저 실행은 추가 패키지 없이 저장된 JSON을 사용한다. 원본 ZIP과 압축 해제 SHP/DBF/PRJ를 연도별 `sources/2022.zip`, `sources/2022/*.shp` 구조로 준비한다. 공식 다운로드는 `meta.sources[*].download_url`에 `post_fields`를 POST하며 압축 해제 전에 ZIP SHA256을 대조한다. Python 가상환경에서 `pip install -r scripts/routing-gis-requirements.txt`, `python scripts/build_flood_history.py --sources /path/to/sources`로 재생성한다. 원본 피해주소 DBF나 전체 ZIP은 Git에 넣지 않는다.
