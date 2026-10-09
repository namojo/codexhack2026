#!/usr/bin/env python3
"""Clip official Seoul annual flood traces and calculate road exposure offline.
Requires pyshp, pyproj, shapely only for rebuilding; runtime serves plain JSON.
Raw SHP properties (addresses/PNU/free text) are never exported.
"""
from __future__ import annotations
import argparse, hashlib, json, warnings
from pathlib import Path

DATASET = 'https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do'
DOWNLOAD = 'https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false'
YEARS = {2010:4,2011:5,2012:6,2013:7,2014:8,2016:9,2017:10,2018:11,2019:12,2020:13,2022:30,2023:31,2024:32,2025:103}
BUFFER_M = 10


def build(source_dir: Path, network_path: Path, output: Path) -> dict:
    import shapefile
    from pyproj import CRS, Transformer
    from shapely import make_valid
    from shapely.geometry import box, shape, mapping, LineString, Polygon, MultiPolygon
    from shapely.ops import transform, unary_union
    network_bytes = network_path.read_bytes()
    network = json.loads(network_bytes)
    bbox = network['meta']['bbox']
    if isinstance(bbox, dict): bbox = [bbox[k] for k in ('west','south','east','north')]
    geographic_clip = box(*bbox)
    to_metric = Transformer.from_crs(4326,5179,always_xy=True)
    to_wgs = Transformer.from_crs(5179,4326,always_xy=True)
    metric_clip = transform(to_metric.transform, geographic_clip)
    yearly, features, sources = {}, [], []
    by_record_year = {year: [] for year in YEARS}
    for year, seq in YEARS.items():
        zpath = source_dir/f'{year}.zip'
        files = list((source_dir/str(year)).rglob('*.shp'))
        if not zpath.is_file() or len(files)!=1:raise ValueError(f'{year}: one extracted SHP and original ZIP required')
        p = files[0]
        crs = CRS.from_wkt(p.with_suffix('.prj').read_text())
        projected = Transformer.from_crs(crs,5179,always_xy=True)
        raw = shapefile.Reader(str(p),encoding='cp949')
        selected, repaired, ignored = [], 0, 0
        # Geometry and F_YR only: never export damage addresses or free-text properties.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for sr in raw.iterShapeRecords(fields=['F_YR']):
                s = sr.shape
                record_year = int(str(sr.record.as_dict()['F_YR']).strip())
                if record_year not in YEARS:raise ValueError(f'Unsupported record year: {record_year}')
                g = transform(projected.transform, shape(s.__geo_interface__))
                if not g.intersects(metric_clip):continue
                if not g.is_valid:g=make_valid(g);repaired+=1
                if not isinstance(g,(Polygon,MultiPolygon)):
                    geoms=[part for part in getattr(g,'geoms',[]) if isinstance(part,(Polygon,MultiPolygon))]
                    if not geoms:ignored+=1;continue
                    g=unary_union(geoms)
                clipped=g.intersection(metric_clip)
                if not clipped.is_empty and clipped.area>0:
                    selected.append(clipped)
                    by_record_year[record_year].append(clipped)
        sources.append({'year':year,'seq':seq,'download_url':DOWNLOAD,'post_fields':{'infId':'OA-15636','seq':str(seq),'infSeq':'1'},'zip_sha256':hashlib.sha256(zpath.read_bytes()).hexdigest(),'zip_bytes':zpath.stat().st_size,'original_crs':crs.to_string(),'original_record_count':len(raw),'selected_record_count':len(selected),'repaired_geometry_count':repaired,'ignored_nonpolygon_count':ignored})
    for year, selected in by_record_year.items():
        merged=unary_union(selected)
        nearby=merged.buffer(BUFFER_M).intersection(metric_clip) if selected else merged
        yearly[year]=(merged,nearby)
        if selected:
            features.append({'type':'Feature','properties':{'year':year,'source_record_count':len(selected)},'geometry':mapping(transform(to_wgs.transform,merged)), 'nearby_geometry':mapping(transform(to_wgs.transform,nearby))})
    all_exact=unary_union([g for g,_ in yearly.values()])
    all_near=unary_union([g for _,g in yearly.values()])
    exposure={}
    for e in network['edges']:
        line=transform(to_metric.transform,LineString(e['geometry']))
        entries=[]
        for year,(g,nearby) in yearly.items():
            if g.is_empty or not line.intersects(nearby):continue
            exact=min(e['length_m'],line.intersection(g).length)
            near=min(e['length_m'],line.intersection(nearby).length)
            if near>0.001:entries.append({'year':year,'trace_m':round(exact,3),'nearby_m':round(near,3)})
        if entries:
            exposure[e['id']]={'by_year':entries,'trace_union_m':round(min(e['length_m'],line.intersection(all_exact).length),3),'nearby_union_m':round(min(e['length_m'],line.intersection(all_near).length),3)}
    result={'schema_version':1,'meta':{'title':'서울시 연도별 침수흔적도 — 신림 도로망 영역','source_url':DATASET,'provider':'서울특별시 물순환안전국 치수안전과','license':'공공누리 제1유형 (출처표시, 상업적 이용·변경 가능)','license_url':'https://www.kogl.or.kr/info/licenseType1.do','downloaded_at':'2026-10-09','dataset_updated_at':'2026-04-27','bbox':bbox,'years_available':list(YEARS),'years_without_files':[2015,2021],'no_file_reason':'서울시 자료 안내에서 침수 없는 연도로 명시','years_in_bbox':[f['properties']['year'] for f in features],'network_sha256':hashlib.sha256(network_bytes).hexdigest(),'nearby_buffer_m':BUFFER_M,'calculation_crs':'EPSG:5179','display_crs':'EPSG:4326','year_grouping':'DBF F_YR 침수년도 사용 (2022 ZIP 안의 2023 기록도 2023으로 분류); 같은 연도 중복은 합집합','risk_penalty_per_year_m':8,'method':'연도별 폴리곤 합집합과 도로 중심선의 교차 길이. 같은 연도 중복은 한번 계산. 주변 10m 포함 길이의 연도별 합계 × 8을 기존 차량 권고 비용에 더함. 확률 또는 현재 통제 아님.','limitations':['과거 피해 등록 범위이며 미래 확률·현재 침수·도로 침수심을 뜻하지 않습니다.','침수 기록이 없는 곳도 안전을 보장하지 않습니다.','10m 주변 범위는 위치 불확실성을 고려한 훈련 가정이며 실제 침수 경계 확대를 뜻하지 않습니다.','연도별 조사 범위·방법·신고 누락과 방재시설 변경을 보정하지 않습니다.','수직 위치를 모델링하지 않아 교량·지하차도 높이 차이를 판별하지 않습니다.'],'sources':sources},'traces':{'type':'FeatureCollection','features':features},'edge_exposure':exposure}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    return {'output':str(output),'years_in_bbox':result['meta']['years_in_bbox'],'selected_records':{s['year']:s['selected_record_count'] for s in sources},'exposed_directed_edges':len(exposure),'bytes':output.stat().st_size}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',type=Path,required=True);p.add_argument('--network',type=Path,default=Path('data/routing/network.json'));p.add_argument('--output',type=Path,default=Path('data/routing/flood-history.json'));a=p.parse_args();print(json.dumps(build(a.sources,a.network,a.output),ensure_ascii=False))
