#!/usr/bin/env python3
"""Build the synthetic browser demo for a static host, without using the user's DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service.store import Store, valid_header
from scripts.judge_pages import write_public_pages

PRODUCT = 'rescue-synthetic-static-v1'
UI_FILES = ('index.html', 'app.js', 'style.css', 'pages-store.js')
MEDIA = {'flood-entrance.png': 'image/png', 'flood-stairwell.png': 'image/png',
         'call-isolated.wav': 'audio/wav', 'call-proxy.wav': 'audio/wav',
         'parking-pillar-dark.png': 'image/png', 'parking-stair-flood.png': 'image/png',
         'parking-call-noisy.wav': 'audio/wav', 'parking-call-enhanced.wav': 'audio/wav'}
SPATIAL_FILES = ('index.html', 'app.js', 'style.css', 'assets/floor-model.json',
                 'assets/analysis.json', 'assets/report.json', 'assets/provenance.json',
                 'assets/synthetic-report.png', 'assets/walkthrough.mp4',
                 'assets/walkthrough-poster.png', 'assets/walkthrough.ko.vtt',
                 'assets/walkthrough.json')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, mode: str = 'offline', include_routes: bool = True) -> dict:
    if mode not in ('offline', 'cloud'):
        raise ValueError('빌드 모드는 offline 또는 cloud여야 합니다.')
    # Refuse replacing source directories, ancestors, symlinks or unrelated artifacts.
    if output.is_symlink():
        raise ValueError('출력 경로는 심볼릭 링크일 수 없습니다.')
    output = output.absolute().resolve()
    protected = [ROOT, *(ROOT / name for name in ('web', 'data', 'service', 'scripts', '.git', '.harness', '_workspace'))]
    if any(output == p or output in p.parents or p in output.parents for p in protected[1:]) or output == ROOT or output in ROOT.parents:
        raise ValueError('소스 및 사용자 데이터 경로에 빌드할 수 없습니다.')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        marker = output / 'build-info.json'
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('product') != PRODUCT:
            raise ValueError('기존 출력은 이 빌더의 산출물이어야 합니다. 별도 빈 디렉터리를 사용하세요.')
    seed_path = ROOT / 'data' / 'seed.json'
    original = json.loads(seed_path.read_text(encoding='utf-8'))
    if original.get('synthetic') is not True or not original.get('incidents'):
        raise ValueError('공개 초기 자료는 비어 있지 않은 합성 사건 목록이어야 합니다.')
    if any(i.get('synthetic') is not True for i in original['incidents']):
        raise ValueError('합성 사건만 공개할 수 있습니다.')
    # The temporary database is seeded only from data/seed.json, never workspace.sqlite3.
    with tempfile.TemporaryDirectory(prefix='rescue-pages-seed-') as temp:
        bundle = Store(Path(temp) / 'seed.sqlite3', seed_path).list_incidents()
    bundle['synthetic'] = True
    html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
    if not include_routes:
        html = re.sub(r'\s*<a\b[^>]*data-local-only="routes"[^>]*>.*?</a>', '', html, flags=re.S)
    html = re.sub(r'<script\s+src=[\"\']/cloud-client\.js[\"\']\s+defer\s*>\s*</script>\s*', '', html)
    html, css_count = re.subn(r'href=[\"\']/style\.css[\"\']', 'href="style.css"', html)
    scripts = '<script src="pages-store.js" defer></script>\n  '
    if mode == 'cloud':
        scripts += '<script src="cloud-client.js" defer></script>\n  '
        html = html.replace('<html lang="ko">', '<html lang="ko" data-service-mode="cloud">')
    scripts += '<script src="app.js" defer></script>'
    html, app_count = re.subn(r'<script\s+src=[\"\']/app\.js[\"\']\s+defer\s*>\s*</script>', scripts, html)
    if css_count != 1 or app_count != 1:
        raise ValueError('업무 HTML의 CSS·app defer 참조를 확인하세요.')
    source_paths = [ROOT / 'web' / f for f in UI_FILES] + [seed_path, ROOT / 'service' / 'store.py', ROOT / 'service' / 'attention.py', Path(__file__).resolve()]
    source_paths.append(ROOT / 'scripts' / 'judge_pages.py')
    source_paths += [ROOT / 'web/spatial' / f for f in SPATIAL_FILES]
    if mode == 'cloud':
        source_paths.append(ROOT / 'web' / 'cloud-client.js')
    if (ROOT / 'docs/verification/ai-live.json').exists():
        source_paths.append(ROOT / 'docs/verification/ai-live.json')
    source_paths += [ROOT / 'data' / 'media' / name for name in (*MEDIA, 'provenance.json')]
    route_sources = {
        'routes/index.html': ROOT / 'web/routes/index.html',
        'routes/app.js': ROOT / 'web/routes/app.js',
        'routes/style.css': ROOT / 'web/routes/style.css',
        'routes/engine.js': ROOT / 'service/route-engine.js',
        'routes/network.json': ROOT / 'data/routing/network.json',
        'routes/flood-history.json': ROOT / 'data/routing/flood-history.json',
    } if include_routes else {}
    source_paths += list(route_sources.values())
    if any(not p.is_file() or p.is_symlink() for p in source_paths):
        raise ValueError('공개 allowlist 소스는 실제 일반 파일이어야 합니다.')
    for name, mime in MEDIA.items():
        if not valid_header((ROOT / 'data' / 'media' / name).read_bytes(), mime):
            raise ValueError(f'합성 매체 헤더가 잘못되었습니다: {name}')
    provenance = json.loads((ROOT / 'data' / 'media' / 'provenance.json').read_text(encoding='utf-8'))
    if provenance.get('synthetic') is not True:
        raise ValueError('매체 출처의 합성 표시가 필요합니다.')
    git = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False)
    info = {'product': PRODUCT, 'synthetic': True, 'built_at': datetime.now(timezone.utc).isoformat(),
            'git_commit': git.stdout.strip() if git.returncode == 0 else None,
            'storage': 'supabase-configured-at-runtime' if mode == 'cloud' else 'visitor-localStorage',
            'mode': mode, 'incident_count': len(original['incidents']), 'report_count': sum(len(i['reports']) for i in original['incidents']),
            'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in source_paths}}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.rescue-pages-build-', dir=output.parent))
    backup = None
    try:
        public = write_public_pages(stage, ROOT, bundle, mode)
        if '<!-- judge-snapshot -->' in html:
            html = html.replace('<!-- judge-snapshot -->', public['snapshot'])
        else:
            html = html.replace('<div id="view">', public['snapshot'] + '<div id="view">')
        (stage / 'index.html').write_text(html, encoding='utf-8')
        for name in UI_FILES[1:]:
            shutil.copyfile(ROOT / 'web' / name, stage / name)
        if route_sources:
            (stage / 'routes').mkdir()
            for name, source in route_sources.items():
                shutil.copyfile(source, stage / name)
            info['route_page'] = 'routes/index.html'
            info['route_data_license'] = 'ODbL 1.0 — https://opendatacommons.org/licenses/odbl/1-0/'
            info['flood_history_license'] = '공공누리 1유형 — 서울특별시'
            info['flood_history_source'] = 'https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do'
        if mode == 'cloud':
            shutil.copyfile(ROOT / 'web' / 'cloud-client.js', stage / 'cloud-client.js')
        # Only the model, synthetic report and UI are public; original drawing stays local.
        for name in SPATIAL_FILES:
            target = stage / 'spatial' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'web/spatial' / name, target)
        (stage / 'seed.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (stage / 'media').mkdir()
        for name in (*MEDIA, 'provenance.json'):
            shutil.copyfile(ROOT / 'data' / 'media' / name, stage / 'media' / name)
        (stage / '.nojekyll').write_text('', encoding='utf-8')
        if not include_routes:
            # Strip all navigation into excluded route assets, including shared shell pages.
            for document in stage.rglob('*.html'):
                content = document.read_text(encoding='utf-8')
                content = re.sub(r'<a\b[^>]*href=[\"\'](?:\.\./|/)?routes/[^\"\']*[\"\'][^>]*>.*?</a>', '', content, flags=re.S)
                document.write_text(content, encoding='utf-8')
            for filename in ('llms.txt', 'llms-full.txt', 'sitemap.xml'):
                content = (stage / filename).read_text(encoding='utf-8')
                content = re.sub(r'^.*https://namojo-hack-test.netlify.app/routes/.*\n', '', content, flags=re.M) if filename.endswith('.txt') else content.replace('<url><loc>https://namojo-hack-test.netlify.app/routes/</loc></url>', '')
                (stage / filename).write_text(content, encoding='utf-8')
        info['files_sha256'] = {str(p.relative_to(stage)): digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage / 'build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix='.rescue-pages-old-', dir=output.parent))
            backup.rmdir()
            output.rename(backup)
        try:
            stage.rename(output)
        except BaseException:
            if backup is not None:
                backup.rename(output)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
        return {'output': str(output), 'files': sorted([*info['files_sha256'], 'build-info.json']),
                'incident_count': len(original['incidents']), 'report_count': sum(len(i['reports']) for i in original['incidents']), 'git_commit': info['git_commit']}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'pages')
    parser.add_argument('--mode', choices=['offline', 'cloud'], default='offline')
    parser.add_argument('--include-routes', action='store_true', default=True, help='Include route review and public road snapshot; does not publish it')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.mode, include_routes=args.include_routes), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
