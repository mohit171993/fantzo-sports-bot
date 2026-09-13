import json
import re
import threading
import time
import zipfile
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import genymotion_poc as base

ABI_STATE = {'status': 'starting'}
ABI_LOCK = threading.Lock()


def set_abi(**kwargs):
    with ABI_LOCK:
        ABI_STATE.update(kwargs)


def apk_abi_summary():
    apk = Path('/tmp/diamond.apk')
    if not apk.exists():
        return None
    abi_libs = defaultdict(list)
    try:
        with zipfile.ZipFile(apk) as zf:
            for name in zf.namelist():
                parts = name.split('/')
                if len(parts) >= 3 and parts[0] == 'lib' and name.endswith('.so'):
                    abi_libs[parts[1]].append('/'.join(parts[2:]))
    except zipfile.BadZipFile:
        return None
    abis = sorted(abi_libs.keys())
    if not abis:
        return None
    return {
        'source': 'apk_zip',
        'apk_size_bytes': apk.stat().st_size,
        'abis': abis,
        'native_lib_counts': {abi: len(abi_libs[abi]) for abi in abis},
        'digitalocean_x86_compatible': bool(set(abis) & {'x86', 'x86_64'}),
        'arm_compatible': bool(set(abis) & {'armeabi-v7a', 'arm64-v8a'}),
    }


def package_manager_abi(instance_uuid):
    serial = base.adbconnect(instance_uuid)
    dump = base.adb_shell(serial, 'dumpsys', 'package', base.PACKAGE, timeout=60, check=False)
    primary = None
    secondary = None
    m = re.search(r'primaryCpuAbi=([^\s]+)', dump or '')
    if m and m.group(1).lower() != 'null':
        primary = m.group(1)
    m = re.search(r'secondaryCpuAbi=([^\s]+)', dump or '')
    if m and m.group(1).lower() != 'null':
        secondary = m.group(1)
    installed = [x for x in (primary, secondary) if x]
    return {
        'source': 'android_package_manager',
        'primary_cpu_abi': primary,
        'secondary_cpu_abi': secondary,
        'installed_abis': installed,
        'digitalocean_x86_compatible': bool(set(installed) & {'x86', 'x86_64'}),
        'arm_compatible': bool(set(installed) & {'armeabi-v7a', 'arm64-v8a'}),
    }


def abi_worker():
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            apk_result = apk_abi_summary()
            if apk_result:
                set_abi(status='done', **apk_result)
                return
            with base.LOCK:
                instance_uuid = base.STATE.get('instance_uuid')
            if instance_uuid:
                pm_result = package_manager_abi(instance_uuid)
                if pm_result.get('installed_abis'):
                    set_abi(status='done', **pm_result)
                    return
            set_abi(status='waiting_for_installed_app')
        except Exception as exc:
            set_abi(status='retrying', error=str(exc)[:500])
        time.sleep(5)
    set_abi(status='failed', error='ABI diagnostic timed out')


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
            with ABI_LOCK:
                safe = dict(ABI_STATE)
            payload = json.dumps(safe, indent=2).encode(); code = 200; ctype = 'application/json'
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
    threading.Thread(target=abi_worker, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', base.PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
