# 침수흔적도 중첩·이력 고려 경로 계약 v1

2026-10-09. docs/routing-contract.md를 유지하고 아래 기능을 추가한다. 서울시 실제 공공 침수흔적도는 합성 신고·가상 통제와 구분한다. 사용자는 조사, 지도 중첩, 추가 경로, Git push·동기화를 요청했다. 외부 사이트 운영 배포는 별도다.

## 데이터와 한계
- 공식 서울 열린데이터광장 OA-15636. 2010~2025 제공 14개 연도 ZIP, 마지막 데이터 갱신 2026-04-27. 공공누리 1유형 출처표시·상업적 이용·변경 가능. 2015·2021은 제공기관이 침수 없는 연도로 안내하여 파일 없음. 2026 자료는 포함하지 않음.
- 원본 PRJ를 읽어 EPSG:5179 미터 좌표에서 계산하고 EPSG:4326 경위도로 표시. F_YR 침수년도로 분류한다. 2022 ZIP의 일부 2023 기록도 2023으로 분류. 같은 연도 폴리곤 합집합으로 중복 제거. 지도 영역으로 자른 실제 기하, 연도만 공개; 개인·피해주소·PNU·원문 자유 텍스트 속성은 출력하지 않는다.
- `data/routing/flood-history.json`: `{schema_version:1,meta:{source_url,provider,license,license_url,years_available,years_in_bbox,years_without_files,network_sha256,nearby_buffer_m:10,risk_penalty_per_year_m:8,sources:[{year,seq,zip_sha256,...}],...},traces:{type:'FeatureCollection',features:[{type:'Feature',properties:{year,source_record_count},geometry:GeoJSON Polygon|MultiPolygon,nearby_geometry:GeoJSON Polygon|MultiPolygon}]},edge_exposure:{[edge_id]:{by_year:[{year,trace_m,nearby_m}],trace_union_m,nearby_union_m}}}`. 0값 구간은 생략 가능. 가까운 영역이 있으나 길이0의 접촉은 노출로 세지 않음.
- 10m 주변(buffer)은 도로 중심선·등록 영역의 위치 불확실성을 고려한 **훈련 가정**이다. 실제 과거 침수 경계를 확대한 관측값이 아니다. 실제 폴리곤과 주변을 색/범례로 구별한다.
- 침수흔적도는 과거 피해 등록 범위. 현재 침수·미래 확률·도로 침수심으로 해석하지 않는다. 미기록 지역 안전 보장 불가. 조사 범위/누락/배수 개선/강우/수위/고도/교량 수직 차이를 보정하지 않는다. F_SHIM을 도로 수심으로 표시하지 않는다.

## 엔진 추가
- `RescueRouting.plan(network,input,floodHistory=null)`로 기존 호환성 유지. 입력 `flood_year:'all'|number` 기본 all. 해당 데이터에 없는 연도는 명시적 입력 오류. 기존 recommended/shortest 결과와 차량/통제/방향/회전 제한을 유지.
- 새 결과 `flood_aware:null|route`, `flood_status:'ok'|'no_route'|'unavailable'`, `flood_message:string`. 데이터 미제공/형식 또는 노출 수치 오류이면 기존 경로는 유지하되 새 경로 unavailable과 사유 표시. 조용히 위험0으로 대체 금지. 필요한 노출값은 유한수·비음수·구간길이 이하(+0.01m 반올림 오차)이고 연도 중복 금지.
- 추가 경로는 기존 차량 권고 비용에 `8 × sum(선택 연도별 nearby_m)` 비용을 더하여 최소화. 반복 침수 연도는 각 연도로 더하되 같은 연도의 면적 겹침은 중복 없음. 비용8은 확률·통계 추정값이 아닌 공개된 훈련 가중치. 통제는 계속 hard exclusion. 과거 침수는 hard exclusion이 아니므로 목적지 접근 잔여 노출이 남을 수 있다.
- 모든 route에 자료가 있을 때 `flood_exposure:{trace_m,nearby_m,year_weighted_m,years:[...],selected_year:'all'|number,buffer_m:10}`. all일 때 trace/nearby는 구간별 합집합 길이, year_weighted는 연도별 nearby 합계. 하나의 연도면 해당 연도 길이. 구간별 표시와 전체 합계는 같은 계산 경로. 권고 비용은 거리를 희생할 수 있고 항상 더 안전하거나 다른 경로가 나온다고 주장하지 않는다.

## 화면·서빙·패키지
- 실제 폴리곤과 주변 10m 표시, 범례·출처·사용조건·데이터 시점·영역 내 기록 연도와 건수 표시. 누적/연도 선택은 표시와 경로 계산에 함께 적용. 지도 표시 끄기는 레이어만 숨기며 경로 계산은 유지한다고 명시.
- 3개 카드: 기존 훈련 추천, 최단 비교, **침수 이력 고려 경로**. 거리와 시간 및 침수흔적 교차/주변 통과 길이로 비교. 새 경로는 명시적 선택 버튼으로 표시. 선택 지도·구간 안내·ARIA와 범례가 일치. unavailable/no_route/자료없는연도/strict/오류 때 이전 새 경로 잔상을 제거.
- `/routes/flood-history.json` 정적 allowlist GET/HEAD만 추가. 경로 우회 금지. 기존 DB·사건업무·AI 콘솔 유지. 정적 빌드 기존 mode='offline'|'cloud' + include_routes 옵션을 모두 유지. include_routes일 때 추가 자료 출처/라이선스와 파일 지문 포함. 기본 공개 빌드 동작 유지.

## 소유권과 검증
backend=service/route-engine.js, scripts/serve.py. frontend=web/routes/ (engine.js 제외). main=실제 공공 데이터, GIS 추출, 계약, scripts/build_pages.py, 통합/Git/문서/실제 브라우저. independent QA=tests/routing_qa.cjs, tests/test_routing_qa.py 및 배정 출력. 다른 동료 변경을 되돌리지 않는다. 재귀 위임 금지.
독립 QA는 합성 폴리곤의 교차·중복·다중연도 및 비용 변화, 잘못된 데이터, strict/통제/회전/폭 조건 일치, 데이터·네트워크 지문/좌표/주소속성 비공개, 실제 3목적지 전체 결과, static GET/HEAD/404, offline/cloud 빌드 호환, 모의 DOM(실제 브라우저 별도)을 검사. 메인은 전체 unittest·fixture replay·하네스와 실제 브라우저의 누적/연도/표시끄기/3경로선택/strict·오류·모바일 및 스크린샷 확인. 실제 현장 운행·예측 확률 검증·실시간 교통·LLM/OCR/ASR 실행은 범위 제외.
