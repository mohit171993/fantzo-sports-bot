import hmac
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APK = Path('/out/fantzo-tv-trial.apk')
TOKEN = os.getenv('DOWNLOAD_TOKEN', '').strip()
PORT = int(os.getenv('PORT', '8080'))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        supplied = parse_qs(parsed.query).get('t', [''])[0]
        if parsed.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            return
        if parsed.path != '/fantzo-tv-trial.apk':
            self.send_response(404)
            self.end_headers()
            return
        if not TOKEN or not hmac.compare_digest(supplied, TOKEN):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Invalid trial link')
            return
        if not APK.exists():
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'APK is still building')
            return
        size = APK.stat().st_size
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', 'attachment; filename="fantzo-tv-trial.apk"')
        self.send_header('Content-Length', str(size))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        with APK.open('rb') as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
    def log_message(self, format, *args):
        return

ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
