import threading
import time
from http.server import ThreadingHTTPServer

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By

import test_join_meeting_v2 as base

base.RESULT.clear()
base.RESULT.update({
    "status": "starting",
    "provider": "BrowserStack App Automate",
    "purpose": "Diamond UI-only consent -> login -> SKY -> Join Meeting test",
    "target_activity": base.MEETING,
    "steps": [],
})

CONSENT_ID = f"{base.PACKAGE}:id/privacy_accept_button"


def consent_state(driver):
    try:
        els = [e for e in driver.find_elements(By.ID, CONSENT_ID) if e.is_displayed()]
        if not els:
            return {"present": False}
        el = els[0]
        out = {"present": True, "rect": el.rect}
        for attr in ("class", "enabled", "clickable", "focusable"):
            try:
                out[attr] = el.get_attribute(attr)
            except Exception:
                pass
        return out
    except Exception as exc:
        return {"present": True, "error": base.redact(exc)}


def accept_consent(driver):
    try:
        driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass
    before = consent_state(driver)
    base.update(consent_control_before=before)
    if not before.get("present"):
        return True, "already absent"

    el = next(e for e in driver.find_elements(By.ID, CONSENT_ID) if e.is_displayed())
    attempts = []
    try:
        el.click(); attempts.append("element.click")
    except Exception as exc:
        attempts.append("element.click failed: " + base.redact(exc))
    time.sleep(3)
    if not consent_state(driver).get("present"):
        base.update(consent_control_after={"present": False})
        return True, "; ".join(attempts)

    try:
        r = el.rect
        x = int(r["x"] + r["width"] / 2)
        y = int(r["y"] + r["height"] / 2)
        driver.execute_script("mobile: tap", {"x": x, "y": y})
        attempts.append(f"mobile:tap@{x},{y}")
    except Exception as exc:
        attempts.append("mobile:tap failed: " + base.redact(exc))
    time.sleep(4)
    after = consent_state(driver)
    base.update(consent_control_after=after)
    return not after.get("present"), "; ".join(attempts)


def run_test():
    required = {
        "BROWSERSTACK_USERNAME": base.BS_USER,
        "BROWSERSTACK_ACCESS_KEY": base.BS_KEY,
        "TRACKING_BASE_URL": base.TRACKING_BASE_URL,
        "TRIAL_TV_TOKEN": base.TRIAL_TV_TOKEN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        base.update(status="waiting_for_variables", missing_variables=missing)
        return

    driver = None
    try:
        base.update(status="running")
        apk, size = base.download_apk(); base.step("download_diamond", True, f"{size} bytes")
        app_url = base.upload_app(apk); base.step("upload_browserstack", True)
        dev = base.pick_device(); name, osv = dev.get("device"), str(dev.get("os_version"))
        base.step("select_real_device", True, f"{name} / Android {osv}")

        opts = UiAutomator2Options()
        opts.set_capability("platformName", "Android")
        opts.set_capability("appium:deviceName", name)
        opts.set_capability("appium:platformVersion", osv)
        opts.set_capability("appium:automationName", "UiAutomator2")
        opts.set_capability("appium:app", app_url)
        opts.set_capability("appium:appPackage", base.PACKAGE)
        opts.set_capability("appium:appActivity", base.MAIN)
        opts.set_capability("appium:autoGrantPermissions", True)
        opts.set_capability("appium:newCommandTimeout", 240)
        opts.set_capability("bstack:options", {
            "userName": base.BS_USER,
            "accessKey": base.BS_KEY,
            "projectName": "Fantzo Diamond UI PoC",
            "buildName": f"diamond-ui-{int(time.time())}",
            "sessionName": "Diamond SKY Join Meeting UI-only",
            "debug": True,
            "video": False,
            "networkLogs": False,
        })

        driver = webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)
        base.update(session_id=driver.session_id, device=name, android_version=osv)
        time.sleep(9)
        base.step("launch_main", True, f"activity={base.activity(driver)}")
        base.update(initial_labels=base.visible_labels(driver))

        consent_ok, consent_detail = accept_consent(driver)
        base.step("accept_privacy_exact", consent_ok, consent_detail)
        if not consent_ok:
            base.update(status="privacy_consent_not_cleared", current_labels=base.visible_labels(driver))
            return
        time.sleep(8)
        base.update(after_consent_activity=base.activity(driver), after_consent_labels=base.visible_labels(driver), after_consent_contexts=base.contexts(driver))

        logged, login_detail = base.fill_login(driver)
        base.step("login_attempt", logged, login_detail)
        if logged:
            time.sleep(10)
        base.update(after_login_activity=base.activity(driver), after_login_labels=base.visible_labels(driver))

        sky, sky_detail = base.click_text(driver, ["SKY"])
        base.step("open_sky", sky, sky_detail)
        if sky:
            time.sleep(9)
        base.update(after_sky_activity=base.activity(driver), after_sky_labels=base.visible_labels(driver))

        join, join_detail = base.click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN"])
        base.step("click_join_meeting", join, join_detail)
        if join:
            time.sleep(12)

        reached = "CustomMeetingActivity" in base.activity(driver)
        base.update(
            meeting_activity_reached=reached,
            final_activity=base.activity(driver),
            final_labels=base.visible_labels(driver),
        )

        if reached:
            base.update(status="meeting_activity_reached")
        elif not sky:
            base.update(status="sky_not_found_after_consent")
        elif not join:
            base.update(status="sky_opened_join_not_found")
        else:
            base.update(status="join_clicked_meeting_activity_not_reached")
    except Exception as exc:
        base.step("failure", False, base.redact(exc))
        base.update(status="failed", error=base.redact(exc))
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def main():
    threading.Thread(target=run_test, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", base.PORT), base.Handler).serve_forever()


if __name__ == "__main__":
    main()
