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
    "purpose": "Diamond exact consent -> login -> SKY -> Join Meeting -> capture test",
    "target_activity": base.MEETING,
    "steps": [],
})

CONSENT_ID = f"{base.PACKAGE}:id/privacy_accept_button"
SHEET_ID = f"{base.PACKAGE}:id/design_bottom_sheet"


def consent_state(driver):
    try:
        els = driver.find_elements(By.ID, CONSENT_ID)
        visible = [e for e in els if e.is_displayed()]
        if not visible:
            return {"present": False}
        el = visible[0]
        info = {"present": True, "rect": el.rect}
        for attr in ("class", "enabled", "clickable", "focusable", "selected"):
            try:
                info[attr] = el.get_attribute(attr)
            except Exception:
                pass
        return info
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
        return True, "privacy sheet already absent"

    try:
        el = next(e for e in driver.find_elements(By.ID, CONSENT_ID) if e.is_displayed())
    except Exception as exc:
        return False, f"accept button not located: {base.redact(exc)}"

    attempts = []
    try:
        el.click()
        attempts.append("element.click")
    except Exception as exc:
        attempts.append(f"element.click error={base.redact(exc)}")
    time.sleep(3)
    state = consent_state(driver)
    if not state.get("present"):
        base.update(consent_control_after=state)
        return True, "; ".join(attempts)

    try:
        rect = el.rect
        x = int(rect["x"] + rect["width"] / 2)
        y = int(rect["y"] + rect["height"] / 2)
        driver.execute_script("mobile: tap", {"x": x, "y": y})
        attempts.append(f"mobile:tap@{x},{y}")
    except Exception as exc:
        attempts.append(f"mobile:tap error={base.redact(exc)}")
    time.sleep(3)
    state = consent_state(driver)
    if not state.get("present"):
        base.update(consent_control_after=state)
        return True, "; ".join(attempts)

    # If the control is disabled until the disclosure is read, scroll the sheet and retry.
    try:
        driver.execute_script("mobile: scroll", {"direction": "down"})
        attempts.append("mobile:scroll-down")
        time.sleep(2)
    except Exception as exc:
        attempts.append(f"scroll error={base.redact(exc)}")

    try:
        el = next(e for e in driver.find_elements(By.ID, CONSENT_ID) if e.is_displayed())
        rect = el.rect
        x = int(rect["x"] + rect["width"] / 2)
        y = int(rect["y"] + rect["height"] / 2)
        driver.execute_script("mobile: tap", {"x": x, "y": y})
        attempts.append("tap-after-scroll")
    except Exception as exc:
        attempts.append(f"tap-after-scroll error={base.redact(exc)}")
    time.sleep(4)
    state = consent_state(driver)
    base.update(consent_control_after=state)
    return not state.get("present"), "; ".join(attempts)


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
            "projectName": "Fantzo Diamond Cloud PoC",
            "buildName": f"diamond-exact-consent-{int(time.time())}",
            "sessionName": "Diamond SKY Join exact consent",
            "debug": True,
            "video": True,
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

        # User-described path: open SKY, then Join Meeting.
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
        base.update(meeting_activity_reached=reached, meeting_activity=base.activity(driver), meeting_labels=base.visible_labels(driver))
        if reached:
            join2, join2_detail = base.click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN", "START MEETING", "ENTER MEETING"])
            base.step("meeting_screen_join_attempt", join2, join2_detail)
            if join2:
                time.sleep(15)

        first = driver.get_screenshot_as_png(); time.sleep(7); second = driver.get_screenshot_as_png()
        metrics = base.capture_metrics(first, second)
        base.update(final_activity=base.activity(driver), final_labels=base.visible_labels(driver), capture_metrics=metrics)
        base.step("capture_compare", True, metrics["verdict"])

        if reached and metrics["verdict"] == "changing_pixels_capture_likely_works":
            base.update(status="meeting_reached_capture_works")
        elif reached and metrics["verdict"] == "likely_black_or_secure_surface":
            base.update(status="meeting_reached_capture_black")
        elif reached:
            base.update(status="meeting_reached_capture_inconclusive")
        elif not sky:
            base.update(status="sky_not_found_after_consent")
        elif not join:
            base.update(status="sky_opened_join_not_found")
        else:
            base.update(status="join_clicked_meeting_activity_not_reached")
    except Exception as exc:
        base.step("failure", False, base.redact(exc)); base.update(status="failed", error=base.redact(exc))
    finally:
        if driver is not None:
            try: driver.quit()
            except Exception: pass


def main():
    threading.Thread(target=run_test, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", base.PORT), base.Handler).serve_forever()


if __name__ == "__main__":
    main()
