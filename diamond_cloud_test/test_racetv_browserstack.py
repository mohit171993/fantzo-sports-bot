import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests
from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By

PORT = int(os.getenv("PORT", "8080"))
BS_USER = os.getenv("BROWSERSTACK_USERNAME", "").strip()
BS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY", "").strip()
RACE_USER = os.getenv("RACETV_USERNAME", "").strip()
RACE_PASS = os.getenv("RACETV_PASSWORD", "").strip()

XAPK_URL = "https://d.apkpure.net/b/XAPK/tk.racetv.live?nc=arm64-v8a&sv=23&versionCode=5"
STATE = {"status": "starting", "target": "Race TV Android app", "steps": []}
LOCK = threading.Lock()


def redact(value):
    s = str(value)
    for secret in (BS_USER, BS_KEY, RACE_USER, RACE_PASS):
        if secret:
            s = s.replace(secret, "[REDACTED]")
    return s[:1000]


def update(**kwargs):
    with LOCK:
        STATE.update(kwargs)


def step(name, ok=True, detail=None):
    item = {"name": name, "ok": bool(ok)}
    if detail is not None:
        item["detail"] = redact(detail)[:500]
    with LOCK:
        STATE.setdefault("steps", []).append(item)


def upload_xapk():
    r = requests.post(
        "https://api-cloud.browserstack.com/app-automate/upload",
        auth=(BS_USER, BS_KEY),
        files={"url": (None, XAPK_URL)},
        timeout=240,
    )
    r.raise_for_status()
    data = r.json()
    app_url = data.get("app_url")
    if not app_url:
        raise RuntimeError("BrowserStack upload did not return app_url")
    return app_url


def choose_device():
    r = requests.get(
        "https://api-cloud.browserstack.com/app-automate/devices.json",
        auth=(BS_USER, BS_KEY),
        timeout=60,
    )
    r.raise_for_status()
    devices = [d for d in r.json() if str(d.get("os", "")).lower() == "android"]
    preferred = ["Samsung Galaxy S24", "Samsung Galaxy S23", "Google Pixel 8", "Google Pixel 7"]
    for name in preferred:
        for d in devices:
            if d.get("device") == name:
                return d
    if not devices:
        raise RuntimeError("No Android device available")
    return devices[0]


def session_url(session_id):
    try:
        r = requests.get(
            f"https://api.browserstack.com/automate/sessions/{session_id}.json",
            auth=(BS_USER, BS_KEY),
            timeout=20,
        )
        if r.ok:
            obj = r.json().get("automation_session", {})
            return obj.get("browser_url") or obj.get("public_url")
    except Exception:
        pass
    return None


def make_driver(app_url, device, os_version):
    opts = UiAutomator2Options()
    opts.set_capability("platformName", "Android")
    opts.set_capability("appium:deviceName", device)
    opts.set_capability("appium:platformVersion", os_version)
    opts.set_capability("appium:automationName", "UiAutomator2")
    opts.set_capability("appium:app", app_url)
    opts.set_capability("appium:autoGrantPermissions", True)
    opts.set_capability("appium:newCommandTimeout", 240)
    opts.set_capability("bstack:options", {
        "userName": BS_USER,
        "accessKey": BS_KEY,
        "projectName": "Fantzo Race TV PoC",
        "buildName": f"racetv-{int(time.time())}",
        "sessionName": "Race TV login and webview inspection",
        "debug": True,
        "video": True,
        "networkLogs": False,
    })
    return webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)


def visible_texts(driver, limit=80):
    out = []
    seen = set()
    try:
        for el in driver.find_elements(By.XPATH, "//*[@text]"):
            try:
                txt = (el.get_attribute("text") or "").strip()
            except Exception:
                txt = ""
            if txt and txt not in seen:
                seen.add(txt)
                out.append(txt[:140])
                if len(out) >= limit:
                    break
    except Exception:
        pass
    return out


def click_text(driver, terms):
    for term in terms:
        xpath = f"//*[contains(translate(@text,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{term.lower()}')]"
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    return term
        except Exception:
            continue
    return None


def try_login(driver):
    time.sleep(8)
    # Handle common consent/onboarding screens first.
    click_text(driver, ["i agree", "agree", "accept", "continue", "ok"])
    time.sleep(3)

    edits = [e for e in driver.find_elements(By.CLASS_NAME, "android.widget.EditText") if e.is_displayed()]
    if len(edits) < 2:
        return False, f"visible edit fields={len(edits)}"

    edits[0].click()
    edits[0].clear()
    edits[0].send_keys(RACE_USER)
    edits[1].click()
    edits[1].clear()
    edits[1].send_keys(RACE_PASS)

    term = click_text(driver, ["login", "log in", "sign in", "submit", "enter", "continue"])
    if not term:
        # Fallback: click the first visible enabled button after filling credentials.
        for el in driver.find_elements(By.CLASS_NAME, "android.widget.Button"):
            try:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    term = "first visible button"
                    break
            except Exception:
                pass
    if not term:
        return False, "no submit control found"
    return True, term


def safe_webview_url(driver):
    contexts = []
    try:
        contexts = list(driver.contexts)
    except Exception:
        return contexts, None
    for ctx in contexts:
        if str(ctx).startswith("WEBVIEW"):
            try:
                driver.switch_to.context(ctx)
                raw = driver.current_url or ""
                p = urlparse(raw)
                safe = f"{p.scheme}://{p.netloc}{p.path}" if p.scheme and p.netloc else None
                driver.switch_to.context("NATIVE_APP")
                return contexts, safe
            except Exception:
                try:
                    driver.switch_to.context("NATIVE_APP")
                except Exception:
                    pass
    return contexts, None


def worker():
    missing = [k for k, v in {
        "BROWSERSTACK_USERNAME": BS_USER,
        "BROWSERSTACK_ACCESS_KEY": BS_KEY,
        "RACETV_USERNAME": RACE_USER,
        "RACETV_PASSWORD": RACE_PASS,
    }.items() if not v]
    if missing:
        update(status="waiting_for_variables", missing_variables=missing)
        return

    driver = None
    try:
        update(status="uploading_racetv")
        app_url = upload_xapk()
        step("upload_racetv_xapk", True, "BrowserStack accepted public arm64 XAPK")

        d = choose_device()
        device = d.get("device")
        os_version = str(d.get("os_version"))
        update(device=device, android_version=os_version)
        step("select_real_android_device", True, f"{device} / Android {os_version}")

        driver = make_driver(app_url, device, os_version)
        update(status="app_open", session_id=driver.session_id)
        burl = session_url(driver.session_id)
        if burl:
            update(browserstack_session_url=burl)
        time.sleep(12)

        before = visible_texts(driver)
        update(initial_labels=before[:30])
        step("app_launched", True, f"visible labels={len(before)}")

        logged, detail = try_login(driver)
        step("login_submit", logged, detail)
        if not logged:
            update(status="login_ui_not_detected", final_labels=visible_texts(driver)[:40])
            return

        time.sleep(12)
        labels = visible_texts(driver)
        activity = None
        try:
            activity = driver.current_activity
        except Exception:
            pass
        contexts, web_url = safe_webview_url(driver)

        text_blob = " ".join(labels).lower()
        login_words = ["username", "password", "login", "sign in"]
        still_login_like = sum(1 for x in login_words if x in text_blob) >= 2
        app_opened = not still_login_like

        update(
            status="login_success_likely" if app_opened else "login_result_unclear",
            login_success_likely=app_opened,
            final_activity=activity,
            final_labels=labels[:50],
            contexts=contexts,
            webview_url=web_url,
        )
        step("post_login_ui", app_opened, activity)
        if web_url:
            step("webview_endpoint_detected", True, web_url)

        # Conservative navigation probe: only tap clearly-labelled Live/Channels controls.
        clicked = click_text(driver, ["live", "channels", "channel"])
        if clicked:
            time.sleep(8)
            post_labels = visible_texts(driver)
            contexts2, web_url2 = safe_webview_url(driver)
            update(
                live_navigation_clicked=clicked,
                live_labels=post_labels[:50],
                live_contexts=contexts2,
                live_webview_url=web_url2,
            )
            step("open_live_or_channels", True, clicked)
        else:
            step("open_live_or_channels", False, "No explicit Live/Channels control found")

    except Exception as exc:
        step("failure", False, redact(exc))
        update(status="failed", error=redact(exc))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            body = b"ok"
            ctype = "text/plain"
        else:
            with LOCK:
                body = json.dumps(STATE, indent=2).encode()
            ctype = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


threading.Thread(target=worker, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
