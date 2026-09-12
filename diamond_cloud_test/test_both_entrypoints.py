import threading
import time
from http.server import ThreadingHTTPServer

from appium import webdriver
from appium.options.android import UiAutomator2Options

import test_join_meeting_v2 as base
import test_join_meeting_ui as ui

base.RESULT.clear()
base.RESULT.update({
    "status": "starting",
    "provider": "BrowserStack App Automate",
    "purpose": "Diamond UI-only: verify both meeting entry buttons",
    "target_activity": base.MEETING,
    "steps": [],
    "entries": {},
})


def make_driver(app_url, device_name, os_version, label):
    opts = UiAutomator2Options()
    opts.set_capability("platformName", "Android")
    opts.set_capability("appium:deviceName", device_name)
    opts.set_capability("appium:platformVersion", os_version)
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
        "buildName": f"diamond-both-entrypoints-{int(time.time())}",
        "sessionName": label,
        "debug": True,
        "video": False,
        "networkLogs": False,
    })
    return webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)


def test_entry(app_url, device_name, os_version, key, terms):
    driver = None
    result = {
        "button_terms": terms,
        "clicked": False,
        "meeting_activity_reached": False,
    }
    try:
        driver = make_driver(app_url, device_name, os_version, f"Diamond {key}")
        result["session_id"] = driver.session_id
        time.sleep(9)

        consent_ok, consent_detail = ui.accept_consent(driver)
        result["consent"] = {"ok": consent_ok, "detail": consent_detail}
        if not consent_ok:
            result["status"] = "privacy_consent_failed"
            result["labels"] = base.visible_labels(driver)
            return result
        time.sleep(6)

        logged, login_detail = base.fill_login(driver)
        result["login"] = {"ok": logged, "detail": login_detail}
        if not logged:
            result["status"] = "login_failed"
            result["labels"] = base.visible_labels(driver)
            return result
        time.sleep(9)

        clicked, detail = base.click_text(driver, terms)
        result["clicked"] = clicked
        result["click_detail"] = detail
        if clicked:
            time.sleep(10)

        result["final_activity"] = base.activity(driver)
        result["labels"] = base.visible_labels(driver)
        result["contexts"] = base.contexts(driver)
        result["meeting_activity_reached"] = "CustomMeetingActivity" in result["final_activity"]
        result["meeting_ui_detected"] = any(
            x in " ".join(result["labels"]).lower()
            for x in ["you are muted", "gallery video", "active speaker", "leave"]
        )
        result["status"] = "meeting_reached" if result["meeting_activity_reached"] else "meeting_not_reached"
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = base.redact(exc)
        return result
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def run_test():
    required = {
        "BROWSERSTACK_USERNAME": base.BS_USER,
        "BROWSERSTACK_ACCESS_KEY": base.BS_KEY,
        "TRACKING_BASE_URL": base.TRACKING_BASE_URL,
        "TRIAL_TV_TOKEN": base.TRIAL_TV_TOKEN,
        "DIAMOND_USERNAME": base.DIAMOND_USERNAME,
        "DIAMOND_PASSWORD": base.DIAMOND_PASSWORD,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        base.update(status="waiting_for_variables", missing_variables=missing)
        return

    try:
        base.update(status="running")
        apk, size = base.download_apk()
        base.step("download_diamond", True, f"{size} bytes")
        app_url = base.upload_app(apk)
        base.step("upload_browserstack", True)
        dev = base.pick_device()
        name, osv = dev.get("device"), str(dev.get("os_version"))
        base.update(device=name, android_version=osv)
        base.step("select_real_device", True, f"{name} / Android {osv}")

        first = test_entry(app_url, name, osv, "1 ALL IN ONE GROUND LINE", ["ALL IN ONE GROUND LINE", "GROUND LINE"])
        with base.RESULT_LOCK:
            base.RESULT["entries"]["all_in_one_ground_line"] = first
        base.step("test_first_entry", first.get("meeting_activity_reached", False), first.get("status"))

        second = test_entry(app_url, name, osv, "2 TV DABBA + Gungi LINE", ["TV DABBA", "GUNGI LINE"])
        with base.RESULT_LOCK:
            base.RESULT["entries"]["tv_dabba_gungi_line"] = second
        base.step("test_second_entry", second.get("meeting_activity_reached", False), second.get("status"))

        both = first.get("meeting_activity_reached") and second.get("meeting_activity_reached")
        same_activity = first.get("final_activity") == second.get("final_activity") == base.MEETING
        base.update(
            status="both_entrypoints_confirmed" if both else "entrypoint_verification_incomplete",
            both_open_custom_meeting_activity=bool(both and same_activity),
        )
    except Exception as exc:
        base.step("failure", False, base.redact(exc))
        base.update(status="failed", error=base.redact(exc))


def main():
    threading.Thread(target=run_test, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", base.PORT), base.Handler).serve_forever()


if __name__ == "__main__":
    main()
