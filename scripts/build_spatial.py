#!/usr/bin/env python3
"""Refresh the offline spatial page from preserved model outputs; no model calls."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'web/spatial/index.html'
def build():
    assets=PAGE.parent/'assets'
    raw=json.loads((assets/'floor-model.json').read_text())
    analysis=json.loads((assets/'analysis.json').read_text())
    report=json.loads((assets/'report.json').read_text())
    assert report['synthetic'] and analysis['synthetic']
    assert len(raw['floor']['units'])==7
    assert analysis['ground_truth_used'] is False
    for e in analysis['text_evidence']:
        assert e['quote'] in report['text'], e
    assert analysis['candidates'][0]['space_id']=='main_room'
    data={'floor_model':raw,'analysis':analysis,'report':report,'display_evidence':[
        '원문: “3층 B타입 3호 라인”이라는 지정으로 세대 후보를 제한합니다. 사진으로 확인한 층·호실은 아닙니다.',
        '원문: “주방을 지나 큰 창문과 회색 커튼 옆”이라는 진술이 창 인접 주공간을 가리킵니다.',
        '사진: 큰 창·회색 커튼·주방이 보입니다. 사람이 보이지 않아 인원과 정확 위치는 확인되지 않았습니다.',
        '도면: 3호의 외벽 창 안쪽에 넓은 주공간, 중간에 주방 설비, 복도 측에 현관이 있습니다.'
    ]}
    html=PAGE.read_text()
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    html,count=re.subn(r'(<script id="spatial-data" type="application/json">).*?(</script>)',lambda m:m[1]+encoded+m[2],html,flags=re.S)
    assert count==1
    PAGE.write_text(html)
    print(json.dumps({'page':str(PAGE),'model':'gpt-6.1-sol','units':7,'synthetic':True,'live_calls':0},ensure_ascii=False))
if __name__=='__main__':build()
