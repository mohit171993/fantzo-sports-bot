import hmac
import logging
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "").strip()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(400 * 1024 * 1024)))
UPLOAD_PORT = int(os.getenv("UPLOAD_PORT", "8081"))
_started = False

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fantzo Private APK Upload</title>
<style>body{font-family:Arial,sans-serif;background:#11151b;color:#fff;padding:24px}.box{max-width:640px;margin:40px auto;background:#1b2028;padding:24px;border-radius:16px}input,button{width:100%;box-sizing:border-box;padding:14px;margin-top:16px}button{font-weight:700}progress{width:100%;margin-top:16px}.muted{color:#adb6c4}.ok{color:#79e7aa}.err{color:#ff9696}</style></head>
<body><div class="box"><h2>Fantzo Private APK Upload</h2><p class="muted">Select the completed Diamond .apk file. Maximum 400 MB. The file is stored privately and is not executed.</p>
<input id="f" type="file" accept=".apk"><button id="b">Upload APK</button><progress id="p" value="0" max="100" hidden></progress><div id="s"></div></div>
<script>
const f=document.getElementById('f'),b=document.getElementById('b'),p=document.getElementById('p'),s=document.getElementById('s');
const token=(location.hash||'').slice(1);if(!token){s.className='err';s.textContent='Private token missing.';b.disabled=true;}
b.onclick=()=>{const file=f.files[0];if(!file){s.className='err';s.textContent='Choose the APK first.';return;}const x=new XMLHttpRequest();x.open('POST','/upload?name='+encodeURIComponent(file.name));x.setRequestHeader('X-Upload-Token',token);x.setRequestHeader('Content-Type','application/octet-stream');p.hidden=false;b.disabled=true;x.upload.onprogress=e=>{if(e.lengthComputable){p.value=Math.round(e.loaded/e.total*100);s.textContent='Uploading... '+p.value+'%';}};x.onload=()=>{b.disabled=false;s.className=x.status===200?'ok':'err';s.textContent=x.responseText;};x.onerror=()=>{b.disabled=false;s.className='err';s.textContent='Connection interrupted.';};x.send(file);};
</script></body></html>"""


def safe_name(name: str) -> str:
    name = os.path.basename((name or "diamond.apk").strip())
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:180]
    if not name.lower().endswith(".apk"):
        raise ValueError("Only .apk files are allowed")
    return name


class UploadHandler(BaseHTTPRequestHandler):
    def send_text(self, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/":
            self.send_text(200, PAGE, "text/html; charset=utf-8")
        elif urlparse(self.path).path == "/health":
            self.send_text(200, "ok")
        else:
            self.send_text(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/upload":
            self.send_text(404, "Not found")
            return
        supplied = self.headers.get("X-Upload-Token", "")
        if not UPLOAD_TOKEN or not hmac.compare_digest(supplied, UPLOAD_TOKEN):
            self.send_text(403, "Invalid private upload link.")
            return
        try:
            filename = safe_name(parse_qs(parsed.query).get("name", ["diamond.apk"])[0])
            length = int(self.headers.get("Content-Length", "0"))
        except Exception as exc:
            self.send_text(400, str(exc))
            return
        if length <= 0 or length > UPLOAD_MAX_BYTES:
            self.send_text(413, "APK must be between 1 byte and 400 MB.")
            return
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOAD_DIR / filename
        if dest.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = UPLOAD_DIR / f"{dest.stem}_{stamp}.apk"
        temp = dest.with_suffix(".apk.part")
        remaining = length
        try:
            with temp.open("wb") as out:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("Upload ended early")
                    out.write(chunk)
                    remaining -= len(chunk)
            os.replace(temp, dest)
            logger.info("Private APK saved: %s (%s bytes)", dest, length)
            self.send_text(200, f"Upload complete: {dest.name} ({length} bytes)")
        except Exception:
            logger.exception("Private APK upload failed")
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            self.send_text(500, "Upload could not be saved.")

    def log_message(self, format: str, *args) -> None:
        return


def start_upload_server() -> None:
    global _started
    if _started:
        return
    server = ThreadingHTTPServer(("0.0.0.0", UPLOAD_PORT), UploadHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="private-apk-upload").start()
    _started = True
    logger.info("Private APK upload server listening on port %s", UPLOAD_PORT)
