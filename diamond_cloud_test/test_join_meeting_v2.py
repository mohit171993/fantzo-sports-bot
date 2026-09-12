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

PACKAGE = "com.diamond.diamondlive"
MAIN = "com.sherdle.universal.MainActivity"
MEETING = "com.sherdle.universal.custom.CustomMeetingActivity"

RESULT = {
    "status": "starting",
    "provider": "BrowserStack App Automate",
    "purpose": "Diamond SKY -> Join Meeting -> capture feasibility test",
    "target_activity": MEETING,
    "steps": [],
}
LOCK = threading.Lock()


def update(**kwargs):
    with LOCK:
        RESULT.update(kwargs)


def step(name, ok, detail=None):
    item = {"name": name, "ok": bool(ok)}
    if detail is not None:
        item["detail"] = str(detail)[:1500]
    with LOCK:
        RESULT.setdefault("steps", []).append(item)


def redact(text):
    text = str(text)
    for secret in (BS_USER, BS_KEY, TRIAL_TV_TOKEN, DIAMOND_USERNAME, DIAMOND_PASSWORD):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:1500]


def download_apk():
    url = f"{TRACKING_BASE_URL}/trial-diamond-apk?t={quote(TRIAL_TV_TOKEN, safe='')}"
    out = Path("/tmp/diamond.apk")
    with requests.get(url, stream=True, timeout=(15, 900)) as r:
        r.raise_for_status()
        with out.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    return out, out.stat().st_size


def upload_app(path):
    with path.open("rb") as f:
        r = requests.post(
            "https://api-cloud.browserstack.com/app-automate/upload",
            auth=(BS_USER, BS_KEY),
            files={
                "file": ("diamond.apk", f, "application/vnd.android.package-archive"),
                "custom_id": (None, "fantzo-diamond-live-join-poc"),
            },
            timeout=900,
        )
    r.raise_for_status()
    app_url = r.json().get("app_url")
    if not app_url:
        raise RuntimeError("BrowserStack did not return app_url")
    return app_url


def version_num(value):
    m = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(m.group(0)) if m else 0.0


def pick_device():
    r = requests.get(
        "https://api-cloud.browserstack.com/app-automate/devices.json",
        auth=(BS_USER, BS_KEY), timeout=60,
    )
    r.raise_for_status()
    devices = [d for d in r.json() if str(d.get("os", "")).lower() == "android"]
    modern = [d for d in devices if version_num(d.get("os_version")) >= 13] or devices
    for wanted in ("Samsung Galaxy S24", "Samsung Galaxy S23", "Google Pixel 8", "Google Pixel 7"):
        for d in modern:
            if d.get("device") == wanted:
                return d
    if not modern:
        raise RuntimeError("No Android real device available")
    return modern[0]


def activity(driver):
    try:
        return driver.current_activity or "unknown"
    except Exception:
        return "unknown"


def contexts(driver):
    try:
        return [str(x) for x in driver.contexts]
    except Exception:
        return []


def visible_labels(driver, limit=50):
    labels = []
    try:
        driver.switch_to.context("NATIVE_APP")
        src = driver.page_source
        for attr in ("text", "content-desc", "resource-id"):
            for value in re.findall(rf'{attr}="([^"]+)"', src):
                value = re.sub(r"\s+", " ", value).strip()
                if value and value not in labels and len(value) <= 120:
                    labels.append(value)
                    if len(labels) >= limit:
                        return labels
    except Exception:
        pass
    return labels


def click_text(driver, terms):
    lower = "abcdefghijklmnopqrstuvwxyz"
    upperalpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass

    for term in terms:
        t = term.upper()
        xp = (
            f"//*[contains(translate(@text,'{lower}','{upperalpha}'),{json.dumps(t)}) "
            f"or contains(translate(@content-desc,'{lower}','{upperalpha}'),{json.dumps(t)})]"
        )
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
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
                t = term.upper()
                xp = (
                    f"//*[contains(translate(normalize-space(.),'{lower}','{upperalpha}'),{json.dumps(t)})]"
                )
                for el in driver.find_elements(By.XPATH, xp)[:15]:
                    try:
                        if el.is_displayed():
                            el.click()
                            driver.switch_to.context("NATIVE_APP")
                            return True, f"webview:{term}"
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass
    return False, "not found"


def fill_login(driver):
    if not DIAMOND_USERNAME or not DIAMOND_PASSWORD:
        return False, "credentials not configured"

    try:
        driver.switch_to.context("NATIVE_APP")
        edits = [e for e in driver.find_elements(By.CLASS_NAME, "android.widget.EditText") if e.is_displayed()]
        if len(edits) >= 2:
            edits[0].clear(); edits[0].send_keys(DIAMOND_USERNAME)
            edits[1].clear(); edits[1].send_keys(DIAMOND_PASSWORD)
            ok, how = click_text(driver, ["LOGIN", "LOG IN", "SIGN IN", "SUBMIT"])
            return ok, f"native fields; {how}"
    except Exception:
        pass

    try:
        for ctx in driver.contexts:
            if "WEBVIEW" not in str(ctx).upper():
                continue
            driver.switch_to.context(ctx)
            inputs = [e for e in driver.find_elements(By.CSS_SELECTOR, "input") if e.is_displayed()]
            if len(inputs) >= 2:
                user = inputs[0]
                password = next((e for e in inputs if (e.get_attribute("type") or "").lower() == "password"), inputs[1])
                user.clear(); user.send_keys(DIAMOND_USERNAME)
                password.clear(); password.send_keys(DIAMOND_PASSWORD)
                for selector in ("button", "input[type=submit]", "a"):
                    for el in driver.find_elements(By.CSS_SELECTOR, selector):
                        label = ((el.text or "") + " " + (el.get_attribute("value") or "")).upper()
                        if any(x in label for x in ("LOGIN", "LOG IN", "SIGN IN", "SUBMIT")):
                            el.click(); driver.switch_to.context("NATIVE_APP")
                            return True, "webview fields"
    except Exception:
        pass
    finally:
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass
    return False, "login controls not detected"


def start_meeting_activity(driver):
    try:
        driver.execute_script(
            "mobile: startActivity",
            {"intent": MEETING, "package": PACKAGE},
        )
        time.sleep(7)
        return "CustomMeetingActivity" in activity(driver), activity(driver)
    except Exception as exc:
        return False, redact(exc)


def crop_center(image):
    w, h = image.size
    return image.crop((int(w * .12), int(h * .16), int(w * .88), int(h * .84))).convert("RGB")


def capture_metrics(a_bytes, b_bytes):
    a = crop_center(Image.open(io.BytesIO(a_bytes))).convert("L")
    b = crop_center(Image.open(io.BytesIO(b_bytes))).convert("L")
    ha, hb = a.histogram(), b.histogram()
    pixels = max(1, a.size[0] * a.size[1])
    black_a = sum(ha[:20]) / pixels
    black_b = sum(hb[:20]) / pixels
    diff = float(ImageStat.Stat(ImageChops.difference(a, b)).mean[0])
    if black_a > .78 and black_b > .78 and diff < 1.8:
        verdict = "likely_black_or_secure_surface"
    elif diff > 3.0 and max(black_a, black_b) < .90:
        verdict = "changing_pixels_capture_likely_works"
    else:
        verdict = "inconclusive"
    return {
        "black_ratio_first": round(black_a, 4),
        "black_ratio_second": round(black_b, 4),
        "mean_pixel_change": round(diff, 3),
        "verdict": verdict,
    }


def run_test():
    required = {
        "BROWSERSTACK_USERNAME": BS_USER,
        "BROWSERSTACK_ACCESS_KEY": BS_KEY,
        "TRACKING_BASE_URL": TRACKING_BASE_URL,
        "TRIAL_TV_TOKEN": TRIAL_TV_TOKEN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        update(status="waiting_for_variables", missing_variables=missing)
        return

    driver = None
    try:
        update(status="running")
        apk, size = download_apk(); step("download_diamond", True, f"{size} bytes")
        app_url = upload_app(apk); step("upload_browserstack", True)
        dev = pick_device(); name, osv = dev.get("device"), str(dev.get("os_version"))
        step("select_real_device", True, f"{name} / Android {osv}")

        opts = UiAutomator2Options()
        opts.set_capability("platformName", "Android")
        opts.set_capability("appium:deviceName", name)
        opts.set_capability("appium:platformVersion", osv)
        opts.set_capability("appium:automationName", "UiAutomator2")
        opts.set_capability("appium:app", app_url)
        opts.set_capability("appium:appPackage", PACKAGE)
        opts.set_capability("appium:appActivity", MAIN)
        opts.set_capability("appium:autoGrantPermissions", True)
        opts.set_capability("appium:newCommandTimeout", 240)
        opts.set_capability("bstack:options", {
            "userName": BS_USER,
            "accessKey": BS_KEY,
            "projectName": "Fantzo Diamond Cloud PoC",
            "buildName": f"diamond-sky-join-{int(time.time())}",
            "sessionName": "SKY Join Meeting capture test",
            "debug": True,
            "video": True,
            "networkLogs": False,
        })
        driver = webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)
        update(session_id=driver.session_id, device=name, android_version=osv)
        time.sleep(12)
        step("launch_main", True, f"activity={activity(driver)}")
        update(initial_contexts=contexts(driver), initial_labels=visible_labels(driver))

        logged, login_detail = fill_login(driver)
        step("login_attempt", logged, login_detail)
        if logged:
            time.sleep(12)
        update(after_login_activity=activity(driver), after_login_labels=visible_labels(driver))

        sky, sky_detail = click_text(driver, ["SKY"])
        step("open_sky", sky, sky_detail)
        if sky:
            time.sleep(10)
        update(after_sky_activity=activity(driver), after_sky_labels=visible_labels(driver))

        join, join_detail = click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN"])
        step("click_join_meeting", join, join_detail)
        if join:
            time.sleep(12)

        reached = "CustomMeetingActivity" in activity(driver)
        if not reached:
            direct, direct_detail = start_meeting_activity(driver)
            step("direct_custom_meeting_fallback", direct, direct_detail)
            reached = direct
        update(meeting_activity_reached=reached, meeting_activity=activity(driver), meeting_labels=visible_labels(driver))

        if reached:
            join2, join2_detail = click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN", "START MEETING", "ENTER MEETING"])
            step("meeting_screen_join_attempt", join2, join2_detail)
            if join2:
                time.sleep(15)

        first = driver.get_screenshot_as_png(); time.sleep(7); second = driver.get_screenshot_as_png()
        metrics = capture_metrics(first, second)
        update(final_activity=activity(driver), capture_metrics=metrics)
        step("capture_compare", True, metrics["verdict"])

        if reached and metrics["verdict"] == "changing_pixels_capture_likely_works":
            update(status="meeting_reached_capture_works")
        elif reached and metrics["verdict"] == "likely_black_or_secure_surface":
            update(status="meeting_reached_capture_black")
        elif reached:
            update(status="meeting_reached_capture_inconclusive")
        else:
            update(status="meeting_not_reached")
    except Exception as exc:
        step("failure", False, redact(exc))
        update(status="failed", error=redact(exc))
    finally:
        if driver is not None:
            try: driver.quit()
            except Exception: pass


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            payload = b"ok"; status = 200; ctype = "text/plain"
        elif self.path.startswith("/result"):
            with LOCK:
                payload = json.dumps(RESULT, indent=2).encode(); status = 200; ctype = "application/json"
        else:
            payload = b"not found"; status = 404; ctype = "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    threading.Thread(target=run_test, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
