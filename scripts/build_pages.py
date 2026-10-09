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

PRODUCT = 'rescue-synthetic-static-v1'
UI_FILES = ('index.html', 'app.js', 'style.css', 'pages-store.js')
MEDIA = {'flood-entrance.png': 'image/png', 'flood-stairwell.png': 'image/png',
         'call-isolated.wav': 'audio/wav', 'call-proxy.wav': 'audio/wav'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path) -> dict:
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
    if original.get('synthetic') is not True or len(original.get('incidents', [])) != 10 or sum(len(i['reports']) for i in original['incidents']) != 20:
        raise ValueError('공개 초기 자료는 합성 10사건·20보고여야 합니다.')
    if any(i.get('synthetic') is not True for i in original['incidents']):
        raise ValueError('합성 사건만 공개할 수 있습니다.')
    # The temporary database is seeded only from data/seed.json, never workspace.sqlite3.
    with tempfile.TemporaryDirectory(prefix='rescue-pages-seed-') as temp:
        bundle = Store(Path(temp) / 'seed.sqlite3', seed_path).list_incidents()
    bundle['synthetic'] = True
    html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
    # Spatial source drawings are for local review; do not publish them or a broken link.
    html = re.sub(r'\s*<a\b[^>]*data-local-only="spatial"[^>]*>.*?</a>', '', html, flags=re.S)
    html, css_count = re.subn(r'href=[\"\']/style\.css[\"\']', 'href="style.css"', html)
    html, app_count = re.subn(r'<script\s+src=[\"\']/app\.js[\"\']\s+defer\s*>\s*</script>',
                              '<script src="pages-store.js" defer></script>\n  <script src="app.js" defer></script>', html)
    if css_count != 1 or app_count != 1:
        raise ValueError('업무 HTML의 CSS·app defer 참조를 확인하세요.')
    source_paths = [ROOT / 'web' / f for f in UI_FILES] + [seed_path, ROOT / 'service' / 'store.py', ROOT / 'service' / 'attention.py', Path(__file__).resolve()]
    source_paths += [ROOT / 'data' / 'media' / name for name in (*MEDIA, 'provenance.json')]
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
            'storage': 'visitor-localStorage', 'incident_count': 10, 'report_count': 20,
            'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in source_paths}}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.rescue-pages-build-', dir=output.parent))
    backup = None
    try:
        (stage / 'index.html').write_text(html, encoding='utf-8')
        for name in UI_FILES[1:]:
            shutil.copyfile(ROOT / 'web' / name, stage / name)
        (stage / 'seed.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (stage / 'media').mkdir()
        for name in (*MEDIA, 'provenance.json'):
            shutil.copyfile(ROOT / 'data' / 'media' / name, stage / 'media' / name)
        (stage / '.nojekyll').write_text('', encoding='utf-8')
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
                'incident_count': 10, 'report_count': 20, 'git_commit': info['git_commit']}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'pages')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output), ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
