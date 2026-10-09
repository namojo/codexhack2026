#!/usr/bin/env python3
"""Extract a small public OSM road snapshot; omit contributor identities.
Download source from meta.source_url, then supply the XML path. No network calls.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BBOX = [126.923, 37.467, 126.958, 37.489]
DRIVABLE = {'trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','living_street','service'}
KEEP = {'highway','name','oneway','junction','access','motor_vehicle','motorcar','vehicle','width','maxwidth','maxwidth:physical','maxheight','maxweight','lanes','surface','bridge','tunnel','service','construction'}
LIMIT_PREFIXES = ('access:','vehicle:','motor_vehicle:','motorcar:','width:','maxwidth:','maxheight:','oneway:')

def node_limits(tags):
    return {key:value for key,value in tags.items() if key in {'barrier','access','motor_vehicle','motorcar','vehicle','width','maxwidth','maxheight'} or key.startswith(LIMIT_PREFIXES)}

def distance(a,b):
    la,lb=math.radians(a['lat']),math.radians(b['lat'])
    dlat=lb-la;dlon=math.radians(b['lon']-a['lon'])
    return 6371000*2*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(la)*math.cos(lb)*math.sin(dlon/2)**2)))

def extract(source, output):
    root=ET.parse(source).getroot()
    nodes={};node_tags={}
    for n in root.findall('node'):
        nid=n.attrib['id'];nodes[nid]={'lat':float(n.attrib['lat']),'lon':float(n.attrib['lon'])}
        node_tags[nid]=node_limits({t.attrib['k']:t.attrib['v'] for t in n.findall('tag')})
    def inside(n):return BBOX[0]<=n['lon']<=BBOX[2] and BBOX[1]<=n['lat']<=BBOX[3]
    edges=[];roads=[];waterways=[];ways=set();places={}
    for w in root.findall('way'):
        tags={t.attrib['k']:t.attrib['v'] for t in w.findall('tag')};refs=[n.attrib['ref'] for n in w.findall('nd')]
        if tags.get('name') in ('관악소방서','신원시장'):
            unique=list(dict.fromkeys(refs));places[tags['name']]={'lat':sum(nodes[n]['lat'] for n in unique)/len(unique),'lon':sum(nodes[n]['lon'] for n in unique)/len(unique)}
        geometry=[[nodes[n]['lon'],nodes[n]['lat']] for n in refs if n in nodes]
        if tags.get('waterway') in ('river','stream') and len(geometry)>1:
            waterways.append({'name':tags.get('name','하천'),'geometry':geometry})
        if 'highway' not in tags:continue
        # Drawing also includes non-drivable paths to make exclusions inspectable.
        if len(geometry)>1:roads.append({'id':w.attrib['id'],'name':tags.get('name','이름 없는 길'),'highway':tags['highway'],'geometry':geometry})
        if tags['highway'] not in DRIVABLE:continue
        if any(tags.get(k) in ('no','private') for k in ('access','vehicle','motor_vehicle','motorcar')):continue
        wayid=w.attrib['id'];ways.add(wayid)
        oneway=tags.get('oneway','yes' if tags.get('junction')=='roundabout' else 'no')
        for i,(a,b) in enumerate(zip(refs,refs[1:])):
            if a not in nodes or b not in nodes or not inside(nodes[a]) or not inside(nodes[b]):continue
            length=distance(nodes[a],nodes[b])
            if length<=0:continue
            for u,v,direction in ((a,b,'f'),(b,a,'r')):
                if oneway in ('yes','1','true') and direction=='r':continue
                if oneway=='-1' and direction=='f':continue
                nt={k:v for k,v in tags.items() if k in KEEP or k.startswith(LIMIT_PREFIXES)}
                # Preserve barrier/vehicle limits at both endpoints for conservative screening.
                for n in (u,v):
                    for k,val in node_tags[n].items():nt['node:'+n+':'+k]=val
                edges.append({'id':f'{wayid}:{i}:{direction}','from':u,'to':v,'way_id':wayid,'length_m':round(length,3),'name':tags.get('name','이름 없는 길'),'highway':tags['highway'],'tags':nt,'geometry':[[nodes[u]['lon'],nodes[u]['lat']],[nodes[v]['lon'],nodes[v]['lat']]]})
    used={n for e in edges for n in (e['from'],e['to'])};nodes={k:v for k,v in nodes.items() if k in used}
    restrictions=[];unsupported=0
    for r in root.findall('relation'):
        tags={t.attrib['k']:t.attrib['v'] for t in r.findall('tag')}
        if tags.get('type')!='restriction':continue
        members={m.attrib['role']:m.attrib for m in r.findall('member')}
        if not all(k in members for k in ('from','via','to')):continue
        if members['from']['ref'] not in ways or members['to']['ref'] not in ways:continue
        if members['via']['type']!='node' or tags.get('except') or 'restriction:conditional' in tags:
            unsupported+=1;continue
        restriction=tags.get('restriction',tags.get('restriction:motorcar',''))
        if restriction:restrictions.append({'from_way':members['from']['ref'],'via_node':members['via']['ref'],'to_way':members['to']['ref'],'restriction':restriction})
    # Approach locations are road nodes, not an invented straight drive to a building.
    incoming={e['to'] for e in edges};outgoing={e['from'] for e in edges}
    def nearest(point,major=False):
        pool={e['from'] for e in edges if not major or e['highway'] in {'primary','secondary','tertiary','residential'}} & incoming & outgoing
        nid=min(pool,key=lambda n:distance(point,nodes[n]));return nid,distance(point,nodes[nid])
    origin_place=places['관악소방서'];on,od=nearest(origin_place,True)
    origin={'node_id':on,'name':'관악소방서 인근 도로 출발점','address':'서울 관악구 관악로 97','station_location':origin_place,**nodes[on],'snap_distance_m':round(od,1),'note':'소방서 부지 중심에서 가까운 도로 노드로 연결. 실제 차고 출입 동선은 미확인.'}
    specs=[('market','신원시장 주변 합성 접근 지점',{'lat':37.4813,'lon':126.9282},'SYN-ROUTE-001 · 신원시장 주변에 물이 차올라 이동이 어려운 가상 주민 2명이 접근 지원을 요청했습니다.'),('north','신원시장 북측 합성 접근 지점',{'lat':37.4823,'lon':126.9281},'SYN-ROUTE-002 · 도림천 인근 북측 공개 도로의 가상 고립 요청입니다. 현장 위치는 훈련용입니다.'),('east','신원시장 동측 합성 접근 지점',{'lat':37.4808,'lon':126.9300},'SYN-ROUTE-003 · 동측 골목 주변 가상 주민 1명이 이동 지원을 요청했습니다.')]
    destinations=[]
    for id,name,p,report in specs:
        nid,d=nearest(p);destinations.append({'id':id,'node_id':nid,'name':name,**nodes[nid],'report':report,'synthetic':True,'snap_distance_m':round(d,1)})
    local=[e for e in edges if e['highway'] in {'service','living_street','residential'} and 37.4802<=nodes[e['from']]['lat']<=37.4826 and 126.9278<=nodes[e['from']]['lon']<=126.9294]
    ids=[e['id'] for e in local if e['name'].startswith('신원로')]
    # One local synthetic control area, not a statement about current water levels.
    closures=[{'id':'market-flood','label':'시장 인근 골목 침수 통제 (가상)','edge_ids':ids,'synthetic':True,'description':'훈련용 통제입니다. 실제 침수 관측·도로 통제 자료가 아닙니다.'}]
    meta={'downloaded_at':'2026-10-09','source':'OpenStreetMap API 0.6','source_url':'https://www.openstreetmap.org/api/0.6/map?bbox='+','.join(map(str,BBOX)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'attribution':'© OpenStreetMap contributors','license':'ODbL 1.0','license_url':'https://www.openstreetmap.org/copyright','bbox':BBOX,'real_time_traffic':False,'verified_effective_width_count':0,'unsupported_restriction_count':unsupported,'place_locations':places,'limitations':['공개 도로망은 현장 유효폭·주차·침수·회차 공간을 검증하지 않습니다.','차고 출입구와 최종 건물 진입은 미확인입니다.','태그가 없는 실제 통행제한과 복합 via-way 제한은 재현하지 못합니다.']}
    value={'schema_version':1,'meta':meta,'nodes':nodes,'edges':edges,'roads':roads,'waterways':waterways,'restrictions':restrictions,'origin':origin,'destinations':destinations,'closures':closures}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'nodes':len(nodes),'edges':len(edges),'roads':len(roads),'restrictions':len(restrictions),'unsupported_restrictions':unsupported,'origin':origin,'destinations':destinations,'closure_edges':len(ids)},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,default=ROOT/'data/routing/network.json');args=p.parse_args();extract(args.source,args.output)
