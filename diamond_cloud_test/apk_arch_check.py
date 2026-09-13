import json
import os
import threading
import urllib.request
import zipfile
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

PORT = int(os.getenv('PORT','8080'))
BASE = os.getenv('TRACKING_BASE_URL','').rstrip('/')
TOKEN = os.getenv('TRIAL_TV_TOKEN','')
STATE = {'status':'starting'}
LOCK = threading.Lock()


def set_state(**kw):
    with LOCK:
        STATE.update(kw)


def worker():
    if not BASE or not TOKEN:
        set_state(status='failed', error='missing internal APK source variables')
        print('ABI_CHECK ' + json.dumps(STATE, sort_keys=True), flush=True)
        return
    try:
        url = f"{BASE}/trial-diamond-apk?t={quote(TOKEN, safe='')}"
        apk = Path('/tmp/diamond.apk')
        req = urllib.request.Request(url, headers={'User-Agent':'Fantzo-ABI-Check/1.0'})
        with urllib.request.urlopen(req, timeout=900) as src, apk.open('wb') as dst:
            while True:
                b = src.read(1024*1024)
                if not b:
                    break
                dst.write(b)
        if apk.stat().st_size < 10_000_000:
            raise RuntimeError('APK download unexpectedly small')
        abi_libs = defaultdict(list)
        with zipfile.ZipFile(apk) as zf:
            for n in zf.namelist():
                parts = n.split('/')
                if len(parts) >= 3 and parts[0] == 'lib' and n.endswith('.so'):
                    abi_libs[parts[1]].append('/'.join(parts[2:]))
        summary = {
            abi: {
                'native_lib_count': len(libs),
                'sample_libs': sorted(libs)[:20],
                'has_media_endpoint': any(x.endswith('libmedia_endpoint.so') for x in libs),
            }
            for abi, libs in sorted(abi_libs.items())
        }
        result = {
            'status':'done',
            'apk_size_bytes':apk.stat().st_size,
            'abis':list(summary.keys()),
            'native_libraries':summary,
            'digitalocean_x86_compatible':bool(set(summary) & {'x86','x86_64'}),
            'arm_compatible':bool(set(summary) & {'armeabi-v7a','arm64-v8a'}),
        }
        set_state(**result)
        print('ABI_CHECK ' + json.dumps(result, sort_keys=True), flush=True)
    except Exception as e:
        set_state(status='failed', error=str(e)[:1000])
        print('ABI_CHECK ' + json.dumps(STATE, sort_keys=True), flush=True)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/health'):
            body=b'ok'; ct='text/plain'; code=200
        elif self.path.startswith('/status'):
            with LOCK:
                body=json.dumps(STATE, indent=2).encode()
            ct='application/json'; code=200
        else:
            body=b'Fantzo Diamond APK ABI check'; ct='text/plain'; code=200
        self.send_response(code)
        self.send_header('Content-Type',ct)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*a):
        return

threading.Thread(target=worker, daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
