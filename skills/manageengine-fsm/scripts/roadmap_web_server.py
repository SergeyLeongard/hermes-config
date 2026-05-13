#!/usr/bin/env python3
import base64
import json
import os
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path('/home/sadmin/.hermes/skills/manageengine-fsm')
ROADMAP_MD = BASE_DIR / 'manageengine-telegram-monitor-ROADMAP.md'
ROADMAP_JSON = BASE_DIR / 'roadmap.json'
BUILD_SCRIPT = BASE_DIR / 'scripts' / 'build_roadmap_json.py'

ADMIN_USER = os.environ.get('HERMES_ROADMAP_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('HERMES_ROADMAP_ADMIN_PASS', '123')


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = path.split('?', 1)[0].split('#', 1)[0]
        rel = clean.lstrip('/') or 'graph.html'
        return str(BASE_DIR / rel)

    def _is_authorized(self) -> bool:
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Basic '):
            return False
        try:
            raw = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8')
        except Exception:
            return False
        return raw == f'{ADMIN_USER}:{ADMIN_PASS}'

    def _require_auth(self) -> bool:
        if self._is_authorized():
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Hermes Roadmap Admin"')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'unauthorized'}).encode('utf-8'))
        return False

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/auth-check'):
            if not self._require_auth():
                return
            self._send_json({'ok': True})
            return
        if self.path.startswith('/api/roadmap.md'):
            if not self._require_auth():
                return
            try:
                text = ROADMAP_MD.read_text(encoding='utf-8')
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
                return
            self._send_json({'ok': True, 'content': text})
            return
        return super().do_GET()

    def do_PUT(self):
        if not self.path.startswith('/api/roadmap.md'):
            self._send_json({'error': 'not found'}, status=404)
            return
        if not self._require_auth():
            return

        try:
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode('utf-8'))
            content = str(data.get('content', ''))
            ROADMAP_MD.write_text(content, encoding='utf-8')

            proc = subprocess.run(
                ['/usr/bin/env', 'python3', str(BUILD_SCRIPT)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                self._send_json({'error': 'build_failed', 'stderr': proc.stderr}, status=500)
                return
            self._send_json({'ok': True, 'stdout': proc.stdout.strip()})
        except Exception as exc:
            self._send_json({'error': str(exc)}, status=500)


def main():
    os.chdir(BASE_DIR)
    server = ThreadingHTTPServer(('0.0.0.0', 8888), Handler)
    print('Hermes roadmap web server on :8888')
    server.serve_forever()


if __name__ == '__main__':
    main()
