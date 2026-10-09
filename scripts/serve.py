#!/usr/bin/env python3
"""로컬 합성 업무 콘솔과 기존 읽기 전용 사건 재생 도구."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from replay import load_cases, run_cases
from service.store import Store, APIError, MAX_UPLOAD, media_mime


class BaseHandler(BaseHTTPRequestHandler):
    def respond(self, code, data, mime, extra=None, head=False):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def json_response(self, value, code=200, head=False):
        self.respond(code, json.dumps(value, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', head=head)

    def failure(self, exc):
        self.json_response({'error': str(exc)}, exc.status)

    def log_message(self, fmt, *args):
        print(fmt % args, file=sys.stderr)


def make_handler(bundle):
    """v1 인터페이스와 GET 허용표/POST 501 유지."""
    class Handler(BaseHandler):
        def do_GET(self):
            route = urlparse(self.path).path
            if route == '/api/bundle':
                self.json_response(bundle)
            elif route in {'/', '/index.html', '/app.js', '/style.css'}:
                name = 'index.html' if route == '/' else route.lstrip('/')
                path = ROOT / 'web' / 'replay' / name
                mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[name]
                self.respond(200, path.read_bytes(), mime)
            else:
                self.send_error(404, 'No such route')
    return Handler


def make_service_handler(store, bundle=None, dev_tools=False):
    class Handler(BaseHandler):
        def do_GET(self):
            self._get()

        def do_HEAD(self):
            self._get(head=True)

        def _get(self, head=False):
            try:
                route = urlparse(self.path).path
                if not dev_tools and (route.startswith('/replay') or route == '/api/bundle'):
                    raise APIError(404, '허용된 페이지가 아닙니다.')
                if route == '/api/incidents':
                    self.json_response(store.list_incidents(), head=head)
                elif re.fullmatch(r'/api/incidents/[A-Za-z0-9_-]+', route):
                    self.json_response(store.get_incident(route.rsplit('/', 1)[1]), head=head)
                elif route == '/api/bundle':
                    self.json_response(bundle, head=head)
                elif route.startswith('/media/'):
                    path = store.allowed_media(route)
                    data = path.read_bytes()
                    extra = {'Accept-Ranges': 'bytes'}
                    code = 200
                    range_value = self.headers.get('Range')
                    if range_value:
                        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_value)
                        if not match or not any(match.groups()) or any(len(part) > 18 for part in match.groups()):
                            self.respond(416, b'', media_mime(path), {'Content-Range': f'bytes */{len(data)}'}, head=head)
                            return
                        a, b = match.groups()
                        start = int(a) if a else max(0, len(data) - int(b))
                        end = min(int(b), len(data) - 1) if b and a else len(data) - 1
                        if start >= len(data) or end < start:
                            self.respond(416, b'', media_mime(path), {'Content-Range': f'bytes */{len(data)}'}, head=head)
                            return
                        extra['Content-Range'] = f'bytes {start}-{end}/{len(data)}'
                        data = data[start:end + 1]
                        code = 206
                    self.respond(code, data, media_mime(path), extra, head=head)
                else:
                    if route == '/replay':
                        self.respond(302, b'', 'text/html', {'Location': '/replay/'}, head=head)
                        return
                    files = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/cloud-client.js': ('cloud-client.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/replay/': ('replay/index.html', 'text/html'), '/replay/index.html': ('replay/index.html', 'text/html'), '/replay/app.js': ('replay/app.js', 'text/javascript'), '/replay/style.css': ('replay/style.css', 'text/css')}
                    if route not in files:
                        raise APIError(404, '허용된 페이지가 아닙니다.')
                    filename, mime = files[route]
                    path = ROOT / 'web' / filename
                    if not path.is_file():
                        raise APIError(404, '페이지가 준비되지 않았습니다.')
                    self.respond(200, path.read_bytes(), mime + '; charset=utf-8', head=head)
            except APIError as exc:
                self.failure(exc)
            except (OSError, sqlite3.Error):
                self.failure(APIError(503, '저장소 또는 첨부를 읽을 수 없습니다.'))

        def _body(self):
            if self.headers.get_content_type() != 'application/json':
                raise APIError(415, 'Content-Type application/json이 필요합니다.')
            if self.headers.get('Transfer-Encoding'):
                raise APIError(400, '고정 길이 JSON 요청이 필요합니다.')
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or len(lengths[0]) > 12 or not re.fullmatch(r'\d+', lengths[0]):
                raise APIError(400, '올바른 Content-Length가 필요합니다.')
            size = int(lengths[0])
            if size < 1 or size > 4 * ((MAX_UPLOAD + 2) // 3) + 4096:
                raise APIError(413, '요청 본문이 비어 있거나 허용 크기를 초과했습니다.')
            origin = self.headers.get('Origin')
            if origin:
                try:
                    parsed = urlparse(origin)
                    valid_origin = parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'} and parsed.port == self.server.server_port
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    raise APIError(403, '이 콘솔에서 보낸 요청만 처리할 수 있습니다.')
            try:
                def no_duplicates(pairs):
                    value = {}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError('중복 필드')
                        value[key] = item
                    return value
                def no_constants(value):
                    raise ValueError('유효하지 않은 수치')
                value = json.loads(self.rfile.read(size).decode('utf-8'), object_pairs_hook=no_duplicates, parse_constant=no_constants)
            except (ValueError, UnicodeError):
                raise APIError(400, '올바른 UTF-8 JSON 객체를 입력하세요.')
            if not isinstance(value, dict):
                raise APIError(400, 'JSON 객체가 필요합니다.')
            return value

        def do_POST(self):
            self._mutate('POST')

        def do_PATCH(self):
            self._mutate('PATCH')

        def _mutate(self, method):
            try:
                route = urlparse(self.path).path
                body = self._body()
                code = 200
                if method == 'POST' and route == '/api/incidents':
                    value, code = store.create_incident(body), 201
                elif method == 'POST' and route == '/api/uploads':
                    value, code = store.upload(body), 201
                else:
                    match = re.fullmatch(r'/api/incidents/([A-Za-z0-9_-]+)(?:/(reports|progress|outcome|reopen))?', route)
                    if not match:
                        raise APIError(404, '허용된 API가 아닙니다.')
                    iid, action = match.groups()
                    if method == 'PATCH' and action is None:
                        value = store.update_incident(iid, body)
                    elif method == 'POST' and action:
                        operation = {'reports': store.add_report, 'progress': store.add_progress, 'outcome': store.confirm_outcome, 'reopen': store.reopen}[action]
                        value = operation(iid, body)
                    else:
                        raise APIError(405, '이 경로에서 사용할 수 없는 요청 방식입니다.')
                self.json_response(value, code)
            except APIError as exc:
                self.failure(exc)
            except (OSError, sqlite3.Error):
                self.failure(APIError(503, '저장 작업을 완료하지 못했습니다. 입력을 보존하고 다시 확인하세요.'))
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--report', type=Path, help='저장된 live/fixture 재생 report.json')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'workspace.sqlite3', help='영속 SQLite 사건 저장소')
    parser.add_argument('--seed', type=Path, default=ROOT / 'data' / 'seed.json')
    parser.add_argument('--dev-tools', action='store_true', help='개발 재생기 /replay/ 및 /api/bundle 명시 공개')
    args = parser.parse_args()
    try:
        if args.report and not args.dev_tools:
            raise ValueError('--report를 표시하려면 --dev-tools를 함께 지정하세요')
        bundle = None
        if args.dev_tools:
            bundle = json.loads(args.report.read_text()) if args.report else run_cases(load_cases())
            if bundle.get('synthetic') is not True or not bundle.get('results'):
                raise ValueError('합성 재생 결과만 표시할 수 있습니다')
        store = Store(args.db, args.seed)
        with ThreadingHTTPServer(('127.0.0.1', args.port), make_service_handler(store, bundle, dev_tools=args.dev_tools)) as server:
            suffix = ' / 개발 도구 /replay/' if args.dev_tools else ''
            print(f'아직 여기 업무 콘솔: http://127.0.0.1:{args.port}{suffix}', flush=True)
            server.serve_forever()
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f'FAIL {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
