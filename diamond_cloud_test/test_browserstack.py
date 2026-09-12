import io
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import requests
from appium import webdriver
from appium.options.android import UiAutomator2Options
from PIL import Image, ImageChops, ImageStat
from selenium.webdriver.common.by import By

PORT = int(os.getenv("PORT", "8080"))
BS_USER = os.getenv("BROWSERSTACK_USERNAME", "").strip()
BS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY", "").strip()
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
TRIAL_TV_TOKEN = os.getenv("TRIAL_TV_TOKEN", "").strip()
DIAMOND_USERNAME = os.getenv("DIAMOND_USERNAME", "")
DIAMOND_PASSWORD = os.getenv("DIAMOND_PASSWORD", "")

PACKAGE_NAME = "com.diamond.diamondlive"
MAIN_ACTIVITY = "com.sherdle.universal.MainActivity"
MEETING_ACTIVITY = "com.sherdle.universal.custom.CustomMeetingActivity"

RESULT = {
    "status": "starting",
    "provider": "BrowserStack App Automate",
    "purpose": "private Diamond Live Join Meeting capture feasibility test",
    "target_activity": MEETING_ACTIVITY,
    "steps": [],
}
RESULT_LOCK = threading.Lock()


def update(**kwargs):
    with RESULT_LOCK:
        RESULT.update(kwargs)


def step(name, ok=True, detail=None):
    item = {"name": name, "ok": bool(ok)}
    if detail:
        item["detail"] = detail
    with RESULT_LOCK:
        RESULT.setdefault("steps", []).append(item)


def safe_error(exc):
    text = str(exc)
    for secret in (BS_USER, BS_KEY, TRIAL_TV_TOKEN, DIAMOND_USERNAME, DIAMOND_PASSWORD):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:1000]


def download_apk():
    if not TRACKING_BASE_URL or not TRIAL_TV_TOKEN:
        raise RuntimeError("TRACKING_BASE_URL/TRIAL_TV_TOKEN are missing")
    url = f"{TRACKING_BASE_URL}/trial-diamond-apk?t={quote(TRIAL_TV_TOKEN, safe='')}"
    out = Path("/tmp/diamond.apk")
    with requests.get(url, stream=True, timeout=(15, 900)) as r:
        r.raise_for_status()
        with out.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    size = out.stat().st_size
    if size < 1024 * 1024:
        raise RuntimeError(f"Downloaded APK is unexpectedly small: {size} bytes")
    return out, size


def upload_app(apk_path):
    with apk_path.open("rb") as f:
        files = {
            "file": ("diamond.apk", f, "application/vnd.android.package-archive"),
            "custom_id": (None, "fantzo-diamond-live-poc"),
        }
        r = requests.post(
            "https://api-cloud.browserstack.com/app-automate/upload",
            auth=(BS_USER, BS_KEY),
            files=files,
            timeout=900,
        )
    r.raise_for_status()
    data = r.json()
    app_url = data.get("app_url")
    if not app_url:
        raise RuntimeError("BrowserStack upload returned no app_url")
    return app_url


def version_num(value):
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else 0.0


def pick_device():
    r = requests.get(
        "https://api-cloud.browserstack.com/app-automate/devices.json",
        auth=(BS_USER, BS_KEY),
        timeout=60,
    )
    r.raise_for_status()
    devices = [d for d in r.json() if str(d.get("os", "")).lower() == "android"]
    modern = [d for d in devices if version_num(d.get("os_version")) >= 13]
    if not modern:
        modern = devices
    preferred = ["Samsung Galaxy S24", "Samsung Galaxy S23", "Google Pixel 8", "Google Pixel 7"]
    for name in preferred:
        for d in modern:
            if d.get("device") == name:
                return d
    if not modern:
        raise RuntimeError("No Android devices returned by BrowserStack")
    return modern[0]


def current_activity(driver):
    try:
        return driver.current_activity or "unknown"
    except Exception:
        return "unknown"


def fill_login(driver):
    if not DIAMOND_USERNAME or not DIAMOND_PASSWORD:
        return False, "Diamond credentials are not configured"

    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass

    try:
        edits = driver.find_elements(By.CLASS_NAME, "android.widget.EditText")
        if len(edits) >= 2:
            edits[0].clear()
            edits[0].send_keys(DIAMOND_USERNAME)
            edits[1].clear()
            edits[1].send_keys(DIAMOND_PASSWORD)
            candidates = driver.find_elements(
                By.XPATH,
                "//*[contains(translate(@text,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'LOGIN') "
                "or contains(translate(@text,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'SIGN IN') "
                "or contains(translate(@content-desc,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'LOGIN') "
                "or contains(translate(@content-desc,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'SIGN IN')]",
            )
            for el in candidates:
                try:
                    el.click()
                    return True, "native login fields"
                except Exception:
                    pass
    except Exception:
        pass

    try:
        contexts = driver.contexts
        for ctx in contexts:
            if "WEBVIEW" not in str(ctx).upper():
                continue
            driver.switch_to.context(ctx)
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            if len(inputs) < 2:
                continue
            user_input = None
            pass_input = None
            for field in inputs:
                typ = (field.get_attribute("type") or "").lower()
                name = ((field.get_attribute("name") or "") + " " + (field.get_attribute("placeholder") or "")).lower()
                if typ == "password" and pass_input is None:
                    pass_input = field
                elif user_input is None and any(k in name for k in ("user", "email", "mobile", "login", "account")):
                    user_input = field
            if user_input is None:
                user_input = inputs[0]
            if pass_input is None:
                pass_input = inputs[1]
            user_input.clear()
            user_input.send_keys(DIAMOND_USERNAME)
            pass_input.clear()
            pass_input.send_keys(DIAMOND_PASSWORD)
            buttons = driver.find_elements(By.CSS_SELECTOR, "button,input[type=submit],a")
            for el in buttons:
                label = ((el.text or "") + " " + (el.get_attribute("value") or "")).strip().lower()
                if "login" in label or "log in" in label or "sign in" in label:
                    el.click()
                    driver.switch_to.context("NATIVE_APP")
                    return True, "webview login fields"
            driver.switch_to.context("NATIVE_APP")
    except Exception:
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass

    return False, "login fields/button were not detected"


def click_text(driver, terms):
    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass

    for term in terms:
        upper = term.upper()
        xpath = (
            "//*[contains(translate(@text,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')," + json.dumps(upper) + ") "
            "or contains(translate(@content-desc,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')," + json.dumps(upper) + ")]"
        )
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                try:
                    el.click()
                    return True, f"native:{term}"
                except Exception:
                    pass
        except Exception:
            pass

    try:
        for ctx in driver.contexts:
            if "WEBVIEW" not in str(ctx).upper():
                continue
            driver.switch_to.context(ctx)
            for term in terms:
                nodes = driver.find_elements(
                    By.XPATH,
                    "//*[contains(translate(normalize-space(.),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
                    + json.dumps(term.upper())
                    + ")]",
                )
                for node in nodes[:10]:
                    try:
                        node.click()
                        driver.switch_to.context("NATIVE_APP")
                        return True, f"webview:{term}"
                    except Exception:
                        pass
    finally:
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass
    return False, "no matching UI element detected"


def open_meeting_activity(driver):
    before = current_activity(driver)
    try:
        driver.start_activity(PACKAGE_NAME, MEETING_ACTIVITY)
        time.sleep(6)
        after = current_activity(driver)
        if "CustomMeetingActivity" in after:
            return True, f"direct activity launch: {after}"
        return False, f"direct start returned activity {after}; previous {before}"
    except Exception as exc:
        direct_error = safe_error(exc)

    clicked, detail = click_text(driver, ["JOIN MEETING", "MEETING", "JOIN"])
    if clicked:
        time.sleep(6)
        after = current_activity(driver)
        return True, f"UI navigation {detail}; activity={after}"

    return False, f"direct activity failed: {direct_error}; UI fallback: {detail}"


def attempt_join(driver):
    clicked, detail = click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN", "START MEETING", "ENTER MEETING"])
    if clicked:
        time.sleep(10)
        return True, f"{detail}; activity={current_activity(driver)}"
    return False, detail


def crop_center(image):
    w, h = image.size
    left = int(w * 0.15)
    right = int(w * 0.85)
    top = int(h * 0.20)
    bottom = int(h * 0.80)
    return image.crop((left, top, right, bottom)).convert("RGB")


def capture_metrics(png1, png2):
    a = crop_center(Image.open(io.BytesIO(png1)))
    b = crop_center(Image.open(io.BytesIO(png2)))
    gray_a = a.convert("L")
    gray_b = b.convert("L")
    hist_a = gray_a.histogram()
    hist_b = gray_b.histogram()
    pixels = a.size[0] * a.size[1]
    black_a = sum(hist_a[:20]) / max(1, pixels)
    black_b = sum(hist_b[:20]) / max(1, pixels)
    diff = ImageChops.difference(gray_a, gray_b)
    mean_diff = float(ImageStat.Stat(diff).mean[0])
    if black_a > 0.78 and black_b > 0.78 and mean_diff < 1.8:
        verdict = "likely_black_or_secure_surface"
    elif mean_diff > 3.0 and max(black_a, black_b) < 0.90:
        verdict = "changing_pixels_capture_likely_works"
    else:
        verdict = "inconclusive"
    return {
        "center_black_ratio_first": round(black_a, 4),
        "center_black_ratio_second": round(black_b, 4),
        "center_mean_pixel_change": round(mean_diff, 3),
        "verdict": verdict,
    }


def run_test():
    missing = [
        name
        for name, value in (
            ("BROWSERSTACK_USERNAME", BS_USER),
            ("BROWSERSTACK_ACCESS_KEY", BS_KEY),
            ("TRACKING_BASE_URL", TRACKING_BASE_URL),
            ("TRIAL_TV_TOKEN", TRIAL_TV_TOKEN),
        )
        if not value
    ]
    if missing:
        update(status="waiting_for_variables", missing_variables=missing)
        return

    driver = None
    try:
        update(status="running")
        apk, size = download_apk()
        step("download_existing_diamond_apk", True, f"{size} bytes")

        app_url = upload_app(apk)
        step("upload_to_real_device_cloud", True)

        device = pick_device()
        device_name = device.get("device")
        os_version = str(device.get("os_version"))
        step("select_real_android_device", True, f"{device_name} / Android {os_version}")

        options = UiAutomator2Options()
        options.set_capability("platformName", "Android")
        options.set_capability("appium:deviceName", device_name)
        options.set_capability("appium:platformVersion", os_version)
        options.set_capability("appium:automationName", "UiAutomator2")
        options.set_capability("appium:app", app_url)
        options.set_capability("appium:appPackage", PACKAGE_NAME)
        options.set_capability("appium:appActivity", MAIN_ACTIVITY)
        options.set_capability("appium:autoGrantPermissions", True)
        options.set_capability("appium:newCommandTimeout", 180)
        options.set_capability(
            "bstack:options",
            {
                "userName": BS_USER,
                "accessKey": BS_KEY,
                "projectName": "Fantzo Diamond Cloud PoC",
                "buildName": f"diamond-join-meeting-{int(time.time())}",
                "sessionName": "Diamond CustomMeetingActivity capture test",
                "debug": True,
                "video": True,
                "networkLogs": False,
            },
        )

        driver = webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=options)
        session_id = driver.session_id
        update(session_id=session_id, device=device_name, android_version=os_version)
        step("launch_diamond_live", True, f"activity={current_activity(driver)}")
        time.sleep(12)

        logged_in, login_detail = fill_login(driver)
        if DIAMOND_USERNAME and DIAMOND_PASSWORD:
            step("automatic_login_attempt", logged_in, login_detail)
            time.sleep(12)
        else:
            step("automatic_login_attempt", False, "credentials not configured; continuing with activity-only test")

        meeting_opened, meeting_detail = open_meeting_activity(driver)
        step("open_custom_meeting_activity", meeting_opened, meeting_detail)
        if meeting_opened:
            time.sleep(8)

        joined, join_detail = attempt_join(driver)
        step("join_meeting_button_attempt", joined, join_detail)
        if joined:
            time.sleep(15)

        first = driver.get_screenshot_as_png()
        time.sleep(7)
        second = driver.get_screenshot_as_png()
        metrics = capture_metrics(first, second)
        update(
            capture_metrics=metrics,
            final_activity=current_activity(driver),
            meeting_activity_opened=meeting_opened,
            join_button_clicked=joined,
        )
        step("meeting_screen_capture_comparison", True, metrics["verdict"])

        if not meeting_opened:
            update(status="meeting_activity_not_reached")
        elif metrics["verdict"] == "likely_black_or_secure_surface":
            update(status="meeting_reached_capture_blocked_or_black")
        elif metrics["verdict"] == "changing_pixels_capture_likely_works":
            update(status="meeting_reached_capture_works")
        elif not DIAMOND_USERNAME or not DIAMOND_PASSWORD:
            update(status="meeting_test_inconclusive_login_may_be_needed")
        else:
            update(status="meeting_reached_capture_inconclusive")
    except Exception as exc:
        update(status="failed", error=safe_error(exc))
        step("test_failure", False, safe_error(exc))
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            payload = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif self.path.startswith("/result"):
            with RESULT_LOCK:
                payload = json.dumps(RESULT, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            payload = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    threading.Thread(target=run_test, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
