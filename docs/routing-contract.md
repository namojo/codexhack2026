# 출동경로 검토 계약 v1

2026-10-09. 신림동 도림천 주변의 합성 구조 요청을 관악소방서에서 접근하는 로컬 웹페이지. 사용자 요청은 기능 구현이며 외부 배포는 포함하지 않는다. 실제 출동·신고·사건 완료 상태를 변경하지 않는다.

## 근거와 계산
- 출발: 관악소방서, 관악로 97. 목적: 신원시장 주변의 공개 도로 위 합성 접근 지점 3곳. 실거주자·특정 가구 신고가 아니다.
- 실제 OpenStreetMap 도로 좌표·도로명·일방통행·통행 태그의 2026-10-09 로컬 스냅샷을 사용한다. © OpenStreetMap contributors, ODbL 출처 및 다운로드 URL을 보존한다. 작성자 계정 정보는 추출하지 않는다.
- 서울시 공개 자료는 신림동의 과거 침수 이력 및 지역 선정 근거다. 현재 침수 범위를 뜻하지 않는다. 현재 교통·수위·공사·주차·유효폭을 조회하지 않는다.
- 하나의 계산 경로: `service/route-engine.js`의 UMD `RescueRouting`을 브라우저와 Node 검사에서 사용한다. 브라우저 `/routes/engine.js`로 제공한다. API 키·외부 타일·추가 모델 호출 없음.
- `data/routing/network.json`: `{schema_version:1,meta:{...},nodes:{id:{lat,lon}},edges:[{id,from,to,way_id,length_m,name,highway,tags,geometry:[[lon,lat],[lon,lat]]}],roads:[{id,name,highway,geometry:[[lon,lat],...]}],waterways:[{name,geometry}],restrictions:[{from_way,via_node,to_way,restriction}],origin:{node_id,name,address,lat,lon,snap_distance_m},destinations:[{id,node_id,name,lat,lon,report,synthetic:true}],closures:[{id,label,edge_ids:[],synthetic:true}]}`. `edges`는 방향별로 만들고 보행로·계단·건설 도로·private/no 통행을 제외한다. 도로 태그 제한은 계산 중에도 검사한다. 국가별 실제 운행 법규를 재현했다고 주장하지 않는다.
- `RescueRouting.plan(network, options)` 옵션: `{destination_id,vehicle_width_m,vehicle_height_m,clearance_m,mode:'training'|'strict',closed_edge_ids:[]}`. 폭 1.5~3.5m, 높이 1.5~4.5m, 좌우 여유 각각 0.1~0.8m. 유한수 및 실제 destination/closure IDs 검사. 결과 `{status:'ok'|'no_route',recommended:null|route,shortest:null|route,rejected:{...},options,...}`. 각 route는 `{edge_ids,node_ids,distance_m,estimated_minutes,turn_count,unknown_width_count,assumed_width_count,steps:[{name,distance_m,...}],geometry:[[lon,lat],...],warnings:[]}`. invalid input throws Error with Korean message.
- 최단 비교는 같은 통제·방향·법적 제한을 적용한 거리 기준이다. 차량 물리 폭 필터를 적용하지 않는 비교임을 명시한다. 권고는 차량 폭 + 양측 여유, 표기된 높이/최대폭 제한을 먼저 검사하고 거리+좁은 길/미확인 길/방향전환 가중치로 선택한다. 권고 경로도 현장 검토가 필요하다.
- OSM `width`는 전체 도로폭일 수 있어 유효 주행폭이나 통행 보증으로 사용하지 않는다. `maxwidth`는 차량폭 제한과 비교한다. `maxheight`는 차량높이와 비교한다. 미해석 제한 태그를 허용으로 간주하지 않는다.
- training 기본: 유효폭은 도로 등급별 **훈련 가정**(primary/trunk 7m, secondary 6m, tertiary 5m, residential/unclassified 3.2m, living_street/service 2.8m, link는 상위 등급)을 쓰고 OSM width가 있으면 더 작은 값으로 제한한다. 실측값·소방차 규격이라고 부르지 않는다. 차량 입력도 훈련 예시이며 실제 장비 제원 입력 가능.
- strict: 현장 검증 유효폭 `tags['rescue:verified_width']` 없으면 제외한다. 현재 공개 스냅샷에 현장 확인값은 없으므로 경로 없음이 정상이다. OSM width만으로 현장 확인값을 만들지 않는다.
- relation 단일 via node 통행제한을 적용한다. 복합 via way 제한은 지원 여부/건수와 한계를 표시한다. 회전 횟수·가중치는 개략이며 차체길이·회전반경·축중·경사·실제 회차 공간을 검증하지 않는다. 도로 밖 직선 연결을 운행 경로로 그리지 않는다.
- 예상 시간은 설정한 고정 훈련 속도와 회전 가중치로 산출하며 실시간 ETA라고 부르지 않는다. 실제 구글맵·네이버지도 링크는 목적지 위치를 확인하는 별도 링크다. 내부 권고나 차량·침수 제한이 외부 지도에 전달되지 않음을 표시한다.

## 화면과 검증
기존 콘솔 메뉴의 출동경로 안내 → 독립 페이지. 입력 폼, 지역 선정 근거·합성 원문, 실제 좌표의 도로 지도, 권고/최단 비교, 구간별 안내, 가상 침수 통제 토글, 출처·한계를 표시한다. 지도 pan/zoom/reset, 경로 선택과 범례, 오류/로딩/경로없음, 모바일·키보드 포커스 지원. strict 전환 후 이전 경로 잔상을 제거한다. 입력 변경 시 재계산하거나 이전 결과임을 표시한다. 원문과 사건 DB 변경 없음.

소유권: backend=`service/route-engine.js`,`scripts/serve.py`; frontend=`web/routes/` (engine.js 제외),`web/index.html`; main=데이터·계약·공개 빌더·문서·장부·실제 브라우저; independent QA=`tests/test_routing_qa.py`,`tests/routing_qa.cjs`, 지정 출력. 동료와 함께 작업하며 다른 변경을 되돌리지 않는다. 재귀 위임 금지.

독립 검사는 최단/차폭 차이, 양측 여유, 높이, 제한 해석 실패, 일방통행·회전제한·통제 회피, strict no route, 입력 오류, 지오메트리 연속, 정적 서빙 allowlist/HEAD/404, 정적 빌드 포함을 확인한다. 전체 unittest·fixture replay·하네스 및 실제 브라우저를 각각 기록한다. 이 검증은 실제 소방차 운행 안전성을 증명하지 않는다.
