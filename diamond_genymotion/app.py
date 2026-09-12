import json
import os
import re
import subprocess
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
import xml.etree.ElementTree as ET

PORT = int(os.getenv("PORT", "8080"))
GENY_TOKEN = os.getenv("GENYMOTION_API_TOKEN", "").strip()
RECIPE_UUID = os.getenv("GENYMOTION_RECIPE_UUID", "").strip()
POC_TOKEN = os.getenv("GENYMOTION_POC_TOKEN", "").strip()
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
TRIAL_TV_TOKEN = os.getenv("TRIAL_TV_TOKEN", "").strip()
DIAMOND_USERNAME = os.getenv("DIAMOND_USERNAME", "")
DIAMOND_PASSWORD = os.getenv("DIAMOND_PASSWORD", "")

PACKAGE = "com.diamond.diamondlive"
MAIN = "com.sherdle.universal.MainActivity"
MEETING = "com.sherdle.universal.custom.CustomMeetingActivity"
INSTANCE_NAME = "fantzo-diamond-poc"

STATE = {
    "status": "starting",
    "purpose": "private Fantzo -> Genymotion Android -> Diamond Button 1 PoC",
    "steps": [],
}
LOCK = threading.Lock()
ADB = "/tmp/platform-tools/adb"


def update(**kwargs):
    with LOCK:
        STATE.update(kwargs)


def step(name, ok=True, detail=None):
    item = {"name": name, "ok": bool(ok)}
    if detail is not None:
        item["detail"] = str(detail)[:1000]
    with LOCK:
        STATE.setdefault("steps", []).append(item)


def redact(value):
    text = str(value)
    for secret in (GENY_TOKEN, POC_TOKEN, TRIAL_TV_TOKEN, DIAMOND_USERNAME, DIAMOND_PASSWORD):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:2000]


def run(cmd, timeout=120, check=True, env=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {redact(p.stdout)}")
    return p.stdout.strip()


def gmsaas(args, timeout=180, json_output=False):
    cmd = ["gmsaas"]
    if json_output:
        cmd += ["--format", "json"]
    cmd += args
    out = run(cmd, timeout=timeout)
    if not json_output:
        return out
    try:
        return json.loads(out)
    except Exception:
        # Some versions may prepend informational text. Recover the JSON object if possible.
        start = out.find("{")
        if start >= 0:
            return json.loads(out[start:])
        raise


def ensure_adb():
    if Path(ADB).exists():
        return
    url = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
    zip_path = "/tmp/platform-tools.zip"
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall("/tmp")
    os.chmod(ADB, 0o755)


def auth_genymotion():
    run(["gmsaas", "auth", "token", GENY_TOKEN], timeout=60)


def list_recipes():
    data = gmsaas(["recipes", "list"], json_output=True)
    recipes = data.get("recipes", []) if isinstance(data, dict) else []
    brief = []
    for r in recipes[:100]:
        brief.append({
            "uuid": r.get("uuid"),
            "name": r.get("name"),
            "android_version": r.get("android_version") or r.get("os_version") or r.get("version"),
            "arch": r.get("arch") or r.get("architecture"),
        })
    return brief


def list_instances():
    data = gmsaas(["instances", "list"], json_output=True)
    return data.get("instances", []) if isinstance(data, dict) else []


def get_or_start_instance():
    for inst in list_instances():
        if inst.get("name") == INSTANCE_NAME and str(inst.get("state", "")).upper() in {"ONLINE", "BOOTING", "CREATING"}:
            return inst.get("uuid"), "reused"
    data = gmsaas(["instances", "start", RECIPE_UUID, INSTANCE_NAME, "--max-run-duration", "60"], timeout=900, json_output=True)
    inst = data.get("instance", {}) if isinstance(data, dict) else {}
    uuid = inst.get("uuid")
    if not uuid:
        raise RuntimeError("Genymotion start did not return an instance UUID")
    return uuid, "started"


def wait_online(instance_uuid, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = gmsaas(["instances", "get", instance_uuid], json_output=True)
        inst = data.get("instance", {}) if isinstance(data, dict) else {}
        state = str(inst.get("state", "")).upper()
        if state == "ONLINE":
            return inst
        time.sleep(5)
    raise RuntimeError("Genymotion instance did not become ONLINE in time")


def adbconnect(instance_uuid):
    data = gmsaas(["instances", "adbconnect", instance_uuid], timeout=180, json_output=True)
    inst = data.get("instance", {}) if isinstance(data, dict) else {}
    serial = inst.get("adb_serial")
    if not serial:
        # Fallback to a subsequent get; some versions omit it from adbconnect output.
        data = gmsaas(["instances", "get", instance_uuid], json_output=True)
        serial = (data.get("instance", {}) if isinstance(data, dict) else {}).get("adb_serial")
    if not serial:
        raise RuntimeError("ADB tunnel connected but no adb_serial was returned")
    return serial


def download_diamond():
    if not TRACKING_BASE_URL or not TRIAL_TV_TOKEN:
        raise RuntimeError("TRACKING_BASE_URL/TRIAL_TV_TOKEN missing")
    url = f"{TRACKING_BASE_URL}/trial-diamond-apk?t={quote(TRIAL_TV_TOKEN, safe='')}"
    out = Path("/tmp/diamond.apk")
    req = urllib.request.Request(url, headers={"User-Agent": "Fantzo-Genymotion-PoC/1.0"})
    with urllib.request.urlopen(req, timeout=900) as src, out.open("wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
    if out.stat().st_size < 10_000_000:
        raise RuntimeError("Diamond APK download was unexpectedly small")
    return out


def adb(serial, args, timeout=120, check=True):
    return run([ADB, "-s", serial] + args, timeout=timeout, check=check)


def adb_shell(serial, *args, timeout=60, check=True):
    return adb(serial, ["shell"] + list(args), timeout=timeout, check=check)


def dump_ui(serial):
    adb_shell(serial, "uiautomator", "dump", "/sdcard/window.xml", timeout=30, check=False)
    xml = adb(serial, ["exec-out", "cat", "/sdcard/window.xml"], timeout=30, check=False)
    if "<hierarchy" not in xml:
        return None
    try:
        return ET.fromstring(xml[xml.find("<hierarchy"):])
    except Exception:
        return None


def bounds_center(bounds):
    nums = [int(x) for x in re.findall(r"\d+", bounds or "")]
    if len(nums) != 4:
        return None
    return ((nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2)


def find_node(root, resource_suffix=None, text_contains=None):
    if root is None:
        return None
    needle = (text_contains or "").lower()
    for node in root.iter("node"):
        rid = node.attrib.get("resource-id", "")
        text = (node.attrib.get("text", "") + " " + node.attrib.get("content-desc", "")).strip()
        if resource_suffix and rid.endswith(resource_suffix):
            return node
        if needle and needle in text.lower():
            return node
    return None


def tap_node(serial, node):
    center = bounds_center(node.attrib.get("bounds", "")) if node is not None else None
    if not center:
        return False
    adb_shell(serial, "input", "tap", str(center[0]), str(center[1]))
    return True


def wait_and_tap(serial, resource_suffix=None, text_contains=None, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        root = dump_ui(serial)
        node = find_node(root, resource_suffix=resource_suffix, text_contains=text_contains)
        if node is not None and tap_node(serial, node):
            return True
        time.sleep(2)
    return False


def safe_input_text(value):
    # Android input text uses %s for spaces. Keep this PoC deliberately conservative.
    return str(value).replace(" ", "%s")


def configure_diamond(serial):
    adb_shell(serial, "am", "force-stop", PACKAGE, check=False)
    adb_shell(serial, "am", "start", "-n", f"{PACKAGE}/{MAIN}")
    time.sleep(8)

    if wait_and_tap(serial, resource_suffix="privacy_accept_button", timeout=12):
        step("accept_privacy", True)
        time.sleep(5)
    else:
        step("accept_privacy", True, "privacy sheet not present")

    root = dump_ui(serial)
    user_node = find_node(root, resource_suffix="username")
    pass_node = find_node(root, resource_suffix="password")
    if user_node is not None and pass_node is not None:
        if not DIAMOND_USERNAME or not DIAMOND_PASSWORD:
            raise RuntimeError("Diamond credentials are not configured")
        tap_node(serial, user_node)
        adb_shell(serial, "input", "keyevent", "KEYCODE_MOVE_END", check=False)
        adb_shell(serial, "input", "text", safe_input_text(DIAMOND_USERNAME))
        tap_node(serial, pass_node)
        adb_shell(serial, "input", "text", safe_input_text(DIAMOND_PASSWORD))
        if not wait_and_tap(serial, resource_suffix="submit", timeout=8):
            wait_and_tap(serial, text_contains="LOGIN", timeout=8)
        step("diamond_login", True)
        time.sleep(10)
    else:
        step("diamond_login", True, "already logged in")

    # Button 1 is the controlled PoC target requested by the user.
    if not wait_and_tap(serial, resource_suffix="first", timeout=20):
        if not wait_and_tap(serial, text_contains="GROUND LINE", timeout=12):
            raise RuntimeError("Button 1 / ALL IN ONE GROUND LINE was not found")
    step("open_button_1", True)
    time.sleep(12)

    focused = adb_shell(serial, "dumpsys", "window", "windows", timeout=30, check=False)
    meeting = "CustomMeetingActivity" in focused
    step("meeting_activity_check", meeting, MEETING if meeting else "CustomMeetingActivity not detected")
    if not meeting:
        raise RuntimeError("Button 1 did not reach CustomMeetingActivity")


def display_url(instance_uuid):
    data = gmsaas(["instances", "display", instance_uuid, "--yes"], json_output=True)
    url = data.get("url") if isinstance(data, dict) else None
    if not url:
        raise RuntimeError("Genymotion did not return a display URL")
    return url


def worker():
    required = {
        "GENYMOTION_API_TOKEN": GENY_TOKEN,
        "GENYMOTION_POC_TOKEN": POC_TOKEN,
        "TRACKING_BASE_URL": TRACKING_BASE_URL,
        "TRIAL_TV_TOKEN": TRIAL_TV_TOKEN,
        "DIAMOND_USERNAME": DIAMOND_USERNAME,
        "DIAMOND_PASSWORD": DIAMOND_PASSWORD,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        update(status="waiting_for_variables", missing_variables=missing)
        return
    try:
        update(status="initializing")
        ensure_adb()
        step("android_platform_tools", True)
        auth_genymotion()
        step("genymotion_auth", True)

        recipes = list_recipes()
        update(recipe_candidates=recipes[:30])
        if not RECIPE_UUID:
            update(status="waiting_for_recipe_uuid")
            return

        instance_uuid, mode = get_or_start_instance()
        update(instance_uuid=instance_uuid)
        step("genymotion_instance", True, mode)
        wait_online(instance_uuid)
        step("instance_online", True)

        serial = adbconnect(instance_uuid)
        update(adb_connected=True)
        step("adb_tunnel", True)

        apk = download_diamond()
        step("download_diamond_apk", True, f"{apk.stat().st_size} bytes")
        adb(serial, ["install", "-r", str(apk)], timeout=900)
        step("install_diamond", True)

        configure_diamond(serial)
        portal = display_url(instance_uuid)
        # Never return the sensitive portal URL from /status.
        with LOCK:
            STATE["_portal_url"] = portal
        update(status="ready", meeting_activity=MEETING, target="Button 1")
    except Exception as exc:
        step("failure", False, redact(exc))
        update(status="failed", error=redact(exc))


def authorized(path):
    if not POC_TOKEN:
        return False
    q = parse_qs(urlparse(path).query)
    return q.get("t", [""])[0] == POC_TOKEN


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif parsed.path == "/status":
            with LOCK:
                safe = {k: v for k, v in STATE.items() if not k.startswith("_")}
            payload = json.dumps(safe, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif parsed.path == "/open":
            if not authorized(self.path):
                payload = b"forbidden"
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
            else:
                with LOCK:
                    portal = STATE.get("_portal_url")
                    status = STATE.get("status")
                if status != "ready" or not portal:
                    payload = b"Diamond cloud session is not ready yet"
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain")
                else:
                    self.send_response(302)
                    self.send_header("Location", portal)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
        else:
            body = """<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Fantzo Diamond Cloud PoC</title>
<style>body{font-family:system-ui;background:#0b1020;color:#fff;padding:28px;max-width:720px;margin:auto}.card{background:#151d33;border-radius:18px;padding:22px}code{color:#8be9fd}</style>
<div class='card'><h2>Fantzo Diamond Cloud PoC</h2><p>Private admin-only Android/WebRTC prototype.</p><p>Status: <code>/status</code></p><p>The public Fantzo menu is unchanged.</p></div>"""
            payload = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
