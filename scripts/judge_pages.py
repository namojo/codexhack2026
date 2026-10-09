"""Public, human and machine readable project documentation, from synthetic seed only."""
from html import escape as esc
import json
from pathlib import Path

SITE = 'https://namojo-hack-test.netlify.app'
REPO = 'https://github.com/namojo/codexhack2026'
LINKS = [('about', '서비스 개요'), ('guide', '이용법'), ('references', '근거와 한계'), ('judge', '심사 안내'), ('spatial', '건물 공간정보')]
REFERENCES = [
    ('소방청: 119 다매체 신고', 'https://www.nfa.go.kr/nfa/news/pressrelease/press/?cntId=2097&mode=view&pageIdx=2&searchCondition=all',
     '문자·사진, 신고 앱, 영상통화 등으로 신고할 수 있다는 공개 채널 구성을 참고했다. 내부 접수 시스템이나 실제 신고 API를 제공받은 프로젝트는 아니다.'),
    ('소방청: 재난 시 신고 폭주와 다매체 활용', 'https://www.nfa.go.kr/nfa/news/pressrelease/press/?cntId=1902&mode=view&pageIdx=1&searchCondition=all',
     '재난 시 신고 집중으로 대응이 어려워지고 사진·영상이 현장 상황과 출동지점 파악을 돕는다는 문제 설명을 참고했다. 본 서비스의 대응 시간 개선을 검증한 자료는 아니다.'),
    ('미국 NTIA: AI and Next Generation 9-1-1', 'https://www.ntia.gov/sites/default/files/ai-and-ng-9-1-1-fact-sheet.pdf',
     'AI를 긴급 대응의 의사결정 지원 도구로 다루며 신고 분류와 가상 훈련 시나리오 등의 활용 방향을 소개한다. 미국 9-1-1의 맥락이며 한국 119 도입 실적이나 우리 모델 성능 근거로 전용하지 않는다.'),
    ('OpenAI: 이미지 분석', 'https://developers.openai.com/api/docs/guides/images-vision',
     '텍스트와 실제 이미지 입력을 함께 분석하는 API 구현 근거. 사진에서 관찰한 위험과 신고자가 말한 위험을 구분하고 정확한 주소·GPS·피해 인원을 사진만으로 확정하지 않는다.'),
    ('OpenAI: 음성 전사', 'https://developers.openai.com/api/docs/guides/speech-to-text',
     '실제 음성 파일의 전사 API 구현 근거. 합성 음성 대본과 실제 ASR 결과를 구분하고 잘못 들린 층·호수와 인원은 담당자가 원음을 대조한다.'),
    ('OpenAI: Structured Outputs', 'https://developers.openai.com/api/docs/guides/structured-outputs',
     'JSON schema에 맞춘 구조화 출력 구현 근거. 스키마 일치는 사실의 정확성을 보장하지 않으며 근거·ID 검증과 담당자 확인이 추가로 필요하다.'),
    ('Supabase: Row Level Security', 'https://supabase.com/docs/guides/database/postgres/row-level-security',
     'DB 접근 제한 구현 근거. 서버 전용 서비스 키를 사용하고 브라우저에 키를 노출하지 않는다. 사건 및 감사 이력을 revision 비교 후 원자적으로 갱신한다.'),
    ('Netlify: Functions 실행 제한', 'https://docs.netlify.com/build/functions/configuration/?fn-language=js',
     '긴 분석을 background function과 DB 작업 상태 조회로 분리하는 구현 근거. 대기 화면이 최종 완료를 의미하지 않으며 실제 ready/failed 상태를 확인한다.'),
]
FIELDS = [
    ('접수 정보', '접수번호, 수신 시각, 마지막 갱신 시각, 처리 상태'),
    ('신고자·연락처', '표시 이름, 회신 채널, 전화번호, 구조 대상과의 관계'),
    ('현장 위치', '주소·랜드마크, 층·호수, 접근 위치, GPS, 출처, 확인 상태'),
    ('상황', '원문 메시지, 요약, 재난 분류, 발생 시각'),
    ('구조 대상', '구조 필요 인원, 부상·의식·호흡·고립 상태'),
    ('현장 위험', '신고된 위험, 사진 관찰 위험, 추가 확인 위험'),
    ('첨부 자료', '실제 사진·음성, 촬영 정보가 있을 때 그 출처, 실제 음성 전사'),
    ('담당자 검토', '누락 정보, 우선 검토 경고, 확인·수정 이력'),
]
INTRO = '아직 여기는 문자·사진·전화 음성이 섞여 들어오는 재난 신고에서, 아직 확인되지 않은 구조 요청을 놓치지 않도록 접수담당자의 분석·인계·추적을 돕는 AI 상황실 콘솔입니다.'
BOUNDARY = '모든 사례와 첨부는 합성 훈련 자료입니다. 공식 119 시스템·카카오톡·전화망과 연결되지 않으며 실제 신고·출동·의료 판단을 수행하지 않습니다.'
STEPS = [
    ('접수 또는 진행 사건 선택', '신규 사건을 열거나 현장 메뉴에서 진행 중인 사건을 선택합니다. 기존 사건의 원문·현재 인원·위치·진행 이력을 먼저 확인합니다.'),
    ('추가 신고 입력', '합성 메시지와 사진·음성 파일을 넣고 수신 채널·발생 시각·신고자와 대상의 관계를 기록합니다. 전화번호나 GPS가 없으면 미확인으로 남깁니다.'),
    ('AI 분석 요청', '음성은 실제 전사 API, 사진은 실제 이미지 입력으로 분석합니다. 분석 초안은 현재 사건을 바꾸지 않습니다. 연결 실패·지원하지 않는 매체·거절은 화면에 표시합니다.'),
    ('원문과 분석 초안 대조', '119 접수 항목, 위치 출처, 위험 관찰, 중복 후보, 아직 확인할 사람, 현장 인계 메모를 검토합니다. 같은 건물의 다른 세대와 신고자의 GPS를 특히 대조합니다.'),
    ('담당자 확인 후 등록', '제안 값을 수정하고 확인 이유를 남겨 등록합니다. 원문·첨부·AI 실행 메타와 담당자 수정 이력을 함께 보존합니다. 분석 이후 사건이 바뀌면 충돌을 알리고 재분석합니다.'),
    ('현장 진행·처리 결과 확인', '담당팀과 진행 상태는 별도 업무로 기록합니다. 부분 구조, 남은 사람, 근거 없는 완료는 차단합니다. 새 정보가 오면 완료 사건도 다시 확인하고 이전 결과를 보존합니다.'),
]
CSS = '''*{box-sizing:border-box}body{margin:0;color:#203747;background:#f3f6f8;font:16px/1.7 system-ui,-apple-system,sans-serif}a{color:#1e5ca1;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #2e70bd;outline-offset:4px}header{background:#183449;color:white;padding:18px max(24px,calc((100% - 1060px)/2))}header a{color:white}header strong{font-size:22px}nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}nav a{padding:8px 4px;min-height:44px}main{max-width:1060px;margin:32px auto;padding:0 24px}h1{font-size:34px;line-height:1.3;margin:16px 0}h2{font-size:24px;margin:32px 0 12px}h3{font-size:20px;margin:0 0 12px}p{margin:10px 0}article,.panel{background:white;border:1px solid #d5dfe6;border-radius:12px;padding:24px;margin:18px 0}.eyebrow{color:#4b6578;font-size:14px}.lead{font-size:20px}.notice{border-left:4px solid #356aa0;padding:12px 20px;background:#e9f0f7}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid article{margin:0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:12px;text-align:left;border-bottom:1px solid #d5dfe6;vertical-align:top}th{background:#f0f4f7}blockquote{border-left:3px solid #91a9bb;margin:12px 0;padding:0 16px}code{overflow-wrap:anywhere}footer{margin:36px 0;color:#4b6578;font-size:14px}.button{display:inline-flex;align-items:center;min-height:44px;background:#245f9d;color:white;padding:10px 18px;border-radius:6px;text-decoration:none}details summary{cursor:pointer;min-height:44px;padding:8px 0}ul,ol{padding-left:24px}.case-meta{color:#4b6578;font-size:14px}img{max-width:100%;height:auto}audio{max-width:100%;width:360px}@media(max-width:640px){.grid{grid-template-columns:1fr}h1{font-size:28px}main{padding:0 16px}article,.panel{padding:18px}nav{gap:6px 12px}}'''


def table(rows):
    return '<div class="table-wrap"><table><thead><tr><th>접수 항목</th><th>MVP 내용</th></tr></thead><tbody>' + ''.join(f'<tr><th>{esc(a)}</th><td>{esc(b)}</td></tr>' for a, b in rows) + '</tbody></table></div>'


def page(slug, title, body):
    nav = ''.join(f'<a href="/{s}/"'+(' aria-current="page"' if slug == s else '')+f'>{t}</a>' for s, t in LINKS)
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | 아직 여기</title><meta name="description" content="{esc(INTRO)}"><link rel="canonical" href="{SITE}/{slug}/"><link rel="stylesheet" href="/public-guide.css"></head><body><header><a href="/"><strong>아직 여기</strong></a><nav aria-label="서비스 안내"><a href="/">상황실 콘솔</a>{nav}</nav></header><main><p class="eyebrow">Track 1 · AI for Safety &amp; Resilience · 합성 데이터 프로젝트</p><h1>{esc(title)}</h1>{body}<footer>{esc(BOUNDARY)}<br><a href="{REPO}">GitHub 소스와 검증 기록</a> · <a href="/llms.txt">llms.txt</a> · <a href="/judge/evidence.json">검증 정보 JSON</a></footer></main></body></html>'''


def case_html(i):
    reports = []
    for r in i['reports']:
        media = []
        for a in r.get('attachments', []):
            url = a.get('url', '')
            if url not in ['/media/flood-entrance.png', '/media/flood-stairwell.png', '/media/call-isolated.wav', '/media/call-proxy.wav']:
                continue
            media.append(f'<a href="{url}">{esc(a.get("filename", a["id"]))} 실제 합성 파일</a>')
        reports.append(f'<details open><summary>{esc(r["id"])} · {esc(r["channel"])} · {esc(r["kind"])} · 원문 보기</summary><p class="case-meta">접수 {esc(r.get("received_at", ""))} / 발생 {esc(r.get("occurred_at", "미확인"))}</p><blockquote>{esc(r["text"])}</blockquote><p>{" · ".join(media)}</p></details>')
    return f'<article id="{esc(i["id"])}"><h3>{esc(i["title"])}</h3><p class="case-meta">{esc(i["id"])} · {esc(i["status"])} · {esc(i["priority"])} · {esc(str(i.get("people_count")))}명</p><p>{esc(i["location"])}</p><p>{esc(i.get("summary", ""))}</p>{"".join(reports)}<a href="/#incident/{esc(i["id"])}">콘솔에서 사건 열기 →</a></article>'


def write_public_pages(stage: Path, root: Path, bundle: dict, mode: str) -> dict:
    # No user's local DB, uploads, secrets or unverified performance numbers are published.
    live_path = root / 'docs/verification/ai-live.json'
    live = json.loads(live_path.read_text()) if live_path.exists() else {'status': 'not_run', 'reason': 'OpenAI·Supabase 연결 정보 등록 후 실제 호출 검증 예정', 'runs': []}
    live_text = ('실제 모델 호출 기록은 아래 검증 JSON과 GitHub에서 확인할 수 있습니다. '+live.get('reason','')) if live.get('status') == 'passed' else live.get('reason', '실제 OpenAI 분석·Supabase 영속 검증은 아직 실행하지 못했습니다. API 키와 DB 연결 전까지 기존 합성 사례 체험과 실행 준비 상태를 구분합니다.')
    about = f'<p class="lead">{esc(INTRO)}</p><div class="notice">{esc(BOUNDARY)}</div><h2>줄이려는 위험</h2><p>신고 폭주 중 같은 건물·가구에 대한 여러 신고가 섞이면 사람을 중복 집계하거나, 부분 구조 뒤 남은 사람을 놓치거나, 갱신된 위치가 현장에 전달되지 않을 수 있습니다. 아직 여기는 원문을 보존하며 이 불일치와 미확인 요청을 담당자에게 드러냅니다.</p><div class="grid"><article><h3>AI가 정리하는 내용</h3><p>음성 전사, 사진 위험 관찰, 문자에서 위치·인원·상황 추출, 중복 후보와 확인 질문, 현장 인계 메모를 제안합니다.</p></article><article><h3>담당자가 확정하는 내용</h3><p>개별 요구조자의 관계, 위치 출처, 제안된 인원·우선도, 진행 상태, 현장 근거와 처리 결과를 확인하고 변경 이유를 남깁니다.</p></article></div><h2>119 접수 항목에 맞춘 MVP</h2><p>다음은 프로젝트가 저장하려는 항목입니다. 공식 소방청 내부 DB 스키마라는 의미는 아닙니다.</p>{table(FIELDS)}<h2>해커톤 실행 방식</h2><p>공유 업무 상태는 Supabase에 저장됩니다. 실제 분석 시연은 ChatGPT로 로그인한 로컬 Codex CLI가 문자와 실제 사진을 분석하며, 음성은 로컬 Whisper가 전사한 결과를 전달합니다. Netlify 공개 서버는 Codex를 실행하지 않습니다. 콘솔의 AI 설정에서 로컬 시연 안내를 확인할 수 있습니다. OpenAI API 서버 분석과 로컬 Codex 시연을 지원합니다. 현재 연결 상태는 콘솔 설정에서 확인합니다.</p><h2>실행 상태</h2><p>{esc(live_text)}</p><p><a class="button" href="/">상황실 콘솔 열기</a> <a href="/guide/">이용 순서 확인</a></p>'
    guide = '<p class="lead">접수부터 추가 신고, AI 초안 검토, 현장 확인까지</p><ol>'+''.join(f'<li><h2>{esc(a)}</h2><p>{esc(b)}</p></li>' for a,b in STEPS)+'</ol><h2>반드시 구분할 상태</h2><ul><li>AI 분석 대기는 사건 접수 확정이나 출동 완료가 아닙니다.</li><li>DB 연결 실패 시 합성 사례 둘러보기는 이 브라우저에만 저장하는 별도 모드입니다.</li><li>분석 실패 시 담당자 직접 입력을 선택할 수 있습니다. fixture를 실제 AI 결과로 표시하지 않습니다.</li><li>사진·음성 원문을 열어 초안의 주소·층·호수·인원과 비교합니다.</li><li>진행·구조 완료는 현장 보고에 근거하여 별도로 처리합니다.</li></ul><h2>AI 연결 설정</h2><p>콘솔의 AI 설정에서 로컬 Codex CLI 시연을 엽니다. 시연 서버가 실행되어 있어야 하며 codex login의 ChatGPT 인증을 사용합니다. 음성 전사와 위치는 담당자가 원문과 대조합니다. 공개 사이트에서는 현장 정보에서 사건을 선택하고 추가 신고·현장 정보 AI 분석을 실행합니다. 현재 연결 상태는 콘솔 설정에서 확인할 수 있습니다.</p><h2>해커톤 시연 경로</h2><p>동일 건물의 다른 세대, 대리 신고의 GPS, 연락 두절, 부분 구조, 완료 이후 새 정보의 다섯 사례를 /judge/에서 원문으로 읽고 콘솔에서 비교하세요. 전용 분석 초안 ID가 있으면 새로고침 뒤에도 조회하여 검토할 수 있습니다.</p>'
    references = '<p class="lead">공개 자료가 뒷받침하는 활용 방향과, 우리가 아직 검증해야 할 효과</p><p>AI 활용의 목적은 원문을 구조화하고 미확인 요청을 드러내 접수담당자의 판단을 돕는 것입니다. 기존 시스템의 실제 운영 성과나 생명 구조 효과를 이미 달성했다는 주장은 하지 않습니다.</p>'+''.join(f'<article><h2><a href="{esc(url)}">{esc(title)}</a></h2><p>{esc(body)}</p></article>' for title,url,body in REFERENCES)+'<h2>효과 평가 계획</h2><div class="table-wrap"><table><tr><th>확인하려는 효과</th><th>측정할 내용</th></tr><tr><td>접수 내용 파악</td><td>주소·층·호수·인원 추출의 실제 모델 정확도, 전사 오류, 담당자 수정 빈도</td></tr><tr><td>인계 누락 감소</td><td>남은 사람·위치 정정·미확인 위험이 초안에 포함되는지</td></tr><tr><td>업무 도움</td><td>동일 원문에 대한 수동 대조 대비 검토 소요 시간과 누락률</td></tr><tr><td>잘못된 확정 방지</td><td>부분 구조·다른 사건 근거·오래된 revision·가짜 인용 차단</td></tr></table></div><p>하네스의 결정적 재생 성공은 위 실제 모델 정확도와 업무 시간 개선을 증명하지 않습니다. 수행 여부와 측정 결과를 검증 기록에 구분합니다.</p>'
    evidence = {'project': '아직 여기', 'synthetic': True, 'official_119_connected': False, 'repository': REPO, 'site': SITE, 'build_mode': mode, 'live_verification': live, 'readable_without_javascript': True,
                'dataset': {'incidents': len(bundle['incidents']), 'reports': sum(len(i['reports']) for i in bundle['incidents']), 'source': REPO+'/blob/main/data/seed.json', 'actual_media': ['/media/flood-entrance.png','/media/flood-stairwell.png','/media/call-isolated.wav','/media/call-proxy.wav']},
                'code': {'codex_demo': REPO+'/blob/main/scripts/serve_codex_demo.mjs','codex_analyzer': REPO+'/blob/main/scripts/analyzer_codex.mjs','python_analyzer': REPO+'/blob/main/scripts/analyzer_openai.py','server_functions': REPO+'/tree/main/netlify/functions','database_migrations': REPO+'/tree/main/supabase/migrations','contract': REPO+'/blob/main/docs/ai-service-contract.md'},
                'checks': {'fixture': {'scope': '결정적 합성 재생; 실제 모델 정확도 아님','command': 'python3 -B scripts/replay.py --all'}, 'service': {'command': 'python3 -B -m unittest discover -s tests -v','scope': '업무/동시성/근거 경계; 실행 기록은 GitHub 참조'}},
                'current_runtime_status': SITE+'/api/config', 'reference_urls': [r[1] for r in REFERENCES]}
    judge = f'<p class="lead">프로젝트 이해와 검증을 위한 공개 읽기 경로</p><p>이 페이지는 모든 방문자에게 동일하게 공개되며 자바스크립트 실행이나 로그인 없이 서비스 목적과 합성 원문을 읽을 수 있습니다.</p><div class="notice">{esc(live_text)}</div><h2>읽는 순서</h2><ol><li><a href="/about/">문제·사용자·119 접수 항목과 AI 역할</a></li><li><a href="/guide/">AI 분석 → 담당자 확인 → 사건 갱신 흐름</a></li><li><a href="/references/">공개 근거, 한계와 효과 측정 계획</a></li><li><a href="{REPO}">GitHub 구현·하네스·검증 로그</a></li><li><a href="/judge/evidence.json">실제 실행 여부와 소스 링크 JSON</a> · <a href="/api/config">현재 서버 연결 상태 JSON</a></li></ol><h2>작동을 확인할 사례</h2><p>아래 {len(bundle["incidents"])}건·{sum(len(i["reports"]) for i in bundle["incidents"])}개 보고는 매 빌드 때 data/seed.json에서 생성됩니다. AI가 만들어낸 분석 결과 표가 아니라 테스트 입력인 합성 신고 원문입니다. 실제 사진·WAV 링크를 포함합니다.</p>'+''.join(case_html(i) for i in bundle['incidents'])+'<h2>판단의 근거</h2><p>실제 모델은 API 실행 정보, 전사, 이미지 관찰과 출처 인용을 분석 초안에 남깁니다. 원문과 맞지 않는 인용·후보 ID는 서버가 거부하며 담당자 확인 전에 사건을 변경하지 않습니다. 중복 후보와 잔여 인원은 미확인 대상으로 남기고 완료 결정은 현장 보고에 따릅니다.</p>'
    live_details = '<h2>실제 AI 실행과 담당자 검토 기록</h2><p>공개 서버에서 모델을 실행했다는 의미가 아닙니다. 로컬 Codex CLI/Whisper 시연 결과를 모든 방문자가 읽을 수 있도록 공개합니다.</p>'
    for run in live.get('runs', []):
        job = run.get('job', {})
        analysis = job.get('analysis') or run.get('analysis') or {}
        execution = job.get('execution') or run.get('execution') or {}
        if not analysis:
            continue
        live_details += '<article><h3>'+esc(run.get('case', '합성 실제 분석'))+'</h3><p>상태 '+esc(run.get('status', '미확인'))+' · 제공자 '+esc(execution.get('provider', '미확인'))+' · 전사 '+esc(execution.get('asr_model', '해당 없음'))+'</p><p>'+esc(analysis.get('summary', ''))+'</p>'
        remaining = analysis.get('remaining_people') or {}
        live_details += '<p>남은 인원 제안: '+esc(str(remaining.get('count')))+' · '+esc(remaining.get('basis', ''))+'</p><p>현장 전달: '+esc(' / '.join(analysis.get('handoff', [])))+'</p>'
        for t in analysis.get('transcripts', []):
            live_details += '<blockquote>실제 전사 ('+esc(t.get('model', ''))+'): '+esc(t.get('text', ''))+'</blockquote>'
        for ev in analysis.get('evidence', []):
            if ev.get('type') == 'image_observation':
                live_details += '<p>사진 관찰 ['+esc(ev.get('source_id', ''))+']: '+esc(ev.get('observation', ''))+'</p>'
        live_details += '<p>한계: '+esc(' / '.join(analysis.get('limitations', [])))+'</p></article>'
    spatial = json.loads((root / 'web/spatial/assets/analysis.json').read_text())
    spatial_report = json.loads((root / 'web/spatial/assets/report.json').read_text())
    spatial_info = {'url': SITE+'/spatial/', 'mode': 'preserved-model-analysis-static-view', 'new_model_call_on_view': False, 'synthetic_report': spatial_report, 'analysis': spatial, 'assumptions': '3~16층 동일 평면 반복; 1~2층 내부·실제 층고·현장 상태 미확인', 'original_drawing_redistributed': False}
    evidence['spatial'] = spatial_info
    spatial_html = '<h2>건물 공간정보와 신고 위치 후보</h2><p><a class="button" href="/spatial/">전체 건물·층·평면 보기</a></p><p>공개 도면과 합성 사진·문자를 읽은 사전 모델 분석을 공간 후보로 확인합니다. 보기 전환은 모델을 새로 호출하거나 사건 상태를 변경하지 않습니다. 3~16층 동일 평면은 표시 가정이며 실제 사람 위치·진입 안전은 미확정입니다. 원본 도면은 출처 링크에서 대조합니다.</p><blockquote>'+esc(spatial_report['text'])+'</blockquote>'
    about += spatial_html
    guide += spatial_html
    judge += live_details + spatial_html
    (stage / 'public-guide.css').write_text(CSS, encoding='utf-8')
    for slug,title,body in [('about','서비스 개요',about),('guide','이용법',guide),('references','근거와 한계',references),('judge','심사 안내',judge)]:
        (stage / slug).mkdir(exist_ok=True)
        (stage / slug / 'index.html').write_text(page(slug,title,body),encoding='utf-8')
    (stage / 'judge/evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    llms = f'# 아직 여기\n\n> {INTRO}\n\n{BOUNDARY}\n\n## Public documentation\n\n'+''.join(f'- [{title}]({SITE}/{slug}/)\n' for slug,title in LINKS)+f'- [Full text]({SITE}/llms-full.txt)\n- [Evidence JSON]({SITE}/judge/evidence.json)\n- [Runtime configuration]({SITE}/api/config)\n- [GitHub]({REPO})\n\n## Execution boundary\n\n{live_text}\nFixtures are synthetic test inputs, not real LLM output. Human confirmation is required; AI does not authenticate emergency reports, merge persons or declare rescue completion.\n'
    (stage / 'llms.txt').write_text(llms,encoding='utf-8')
    full = llms+'\n## Workflow\n\n'+ '\n'.join(f'{n+1}. {a}: {b}' for n,(a,b) in enumerate(STEPS))+'\n\n## Intake fields\n\n'+'\n'.join(f'- {a}: {b}' for a,b in FIELDS)+'\n\n## Sources and limits\n\n'+'\n'.join(f'- {a}: {c} ({b})' for a,b,c in REFERENCES)+'\n\n## Synthetic source cases\n'
    for i in bundle['incidents']:
        full += f'\n### {i["id"]}: {i["title"]}\nLocation: {i["location"]}\nStatus: {i["status"]}\nPeople reported: {i.get("people_count")}\n'
        for r in i['reports']:
            full += f'\n- {r["id"]} ({r["channel"]}, {r["kind"]}, {r.get("received_at", "")}): {r["text"]}\n'
            for a in r.get('attachments',[]):
                full += f'  Attachment {a["id"]}: {a.get("url", "")} (synthetic; supplied transcript is not actual ASR)\n'
    full += '\n## Spatial report and preserved model analysis\n' + json.dumps(spatial_info, ensure_ascii=False, indent=2) + '\n'
    full += '\n## Actual local AI execution records\n' + json.dumps(live, ensure_ascii=False, indent=2) + '\n'
    (stage / 'llms-full.txt').write_text(full,encoding='utf-8')
    (stage / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nDisallow: /api/ai/\nDisallow: /api/media/\nSitemap: {SITE}/sitemap.xml\n',encoding='utf-8')
    (stage / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{SITE}{p}</loc></url>' for p in ['/',*[f'/{s}/' for s,_ in LINKS]])+'</urlset>',encoding='utf-8')
    # This semantic preview is visible to everyone, and remains readable if JS cannot load.
    snapshot = f'<section id="judge-snapshot" class="static-snapshot"><h2>아직 여기 · 합성 신고 원문</h2><p>{esc(INTRO)} <a href="/judge/">서비스와 사례 전체 읽기</a></p><p>{esc(live_text)}</p><ul>'+''.join(f'<li><a href="/judge/#{esc(i["id"])}">{esc(i["title"])}</a> — {esc(i["location"])} · {esc(i.get("summary", ""))}</li>' for i in bundle['incidents'])+'</ul></section>'
    return {'snapshot':snapshot,'evidence':evidence}
