import json
import threading
import zipfile
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import genymotion_poc as base


def abi_summary():
    apk = Path('/tmp/diamond.apk')
    if not apk.exists():
        return {'status': 'waiting_for_apk'}
    try:
        abi_libs = defaultdict(list)
        with zipfile.ZipFile(apk) as zf:
            for name in zf.namelist():
                parts = name.split('/')
                if len(parts) >= 3 and parts[0] == 'lib' and name.endswith('.so'):
                    abi_libs[parts[1]].append('/'.join(parts[2:]))
        abis = sorted(abi_libs.keys())
        return {
            'status': 'done',
            'apk_size_bytes': apk.stat().st_size,
            'abis': abis,
            'native_lib_counts': {abi: len(abi_libs[abi]) for abi in abis},
            'digitalocean_x86_compatible': bool(set(abis) & {'x86', 'x86_64'}),
            'arm_compatible': bool(set(abis) & {'armeabi-v7a', 'arm64-v8a'}),
        }
    except Exception as exc:
        return {'status': 'failed', 'error': str(exc)[:500]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            payload = b'ok'; code = 200; ctype = 'text/plain'
        elif parsed.path == '/status':
            with base.LOCK:
                safe = {k: v for k, v in base.STATE.items() if not k.startswith('_')}
            payload = json.dumps(safe, indent=2).encode(); code = 200; ctype = 'application/json'
        elif parsed.path == '/abi':
            payload = json.dumps(abi_summary(), indent=2).encode(); code = 200; ctype = 'application/json'
        elif parsed.path == '/open':
            if not base.authorized(self.path):
                payload = b'forbidden'; code = 403; ctype = 'text/plain'
            else:
                with base.LOCK:
                    portal = base.STATE.get('_portal_url'); status = base.STATE.get('status')
                if status == 'ready' and portal:
                    self.send_response(302)
                    self.send_header('Location', portal)
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    return
                payload = b'Diamond cloud session is not ready yet'; code = 503; ctype = 'text/plain'
        else:
            payload = b'Fantzo Diamond Genymotion PoC'; code = 200; ctype = 'text/plain'
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    threading.Thread(target=base.worker, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', base.PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
