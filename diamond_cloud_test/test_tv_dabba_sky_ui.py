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
    "purpose": "Diamond UI-only: login -> TV DABBA -> SKY -> Join Meeting",
    "target_activity": base.MEETING,
    "steps": [],
})


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
            "buildName": f"diamond-tv-dabba-sky-{int(time.time())}",
            "sessionName": "TV DABBA to SKY Join Meeting UI-only",
            "debug": True,
            "video": False,
            "networkLogs": False,
        })

        driver = webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)
        base.update(session_id=driver.session_id, device=name, android_version=osv)
        time.sleep(9)
        base.step("launch_main", True, f"activity={base.activity(driver)}")

        consent_ok, consent_detail = ui.accept_consent(driver)
        base.step("accept_privacy_exact", consent_ok, consent_detail)
        if not consent_ok:
            base.update(status="privacy_consent_not_cleared", labels=base.visible_labels(driver))
            return
        time.sleep(7)

        logged, login_detail = base.fill_login(driver)
        base.step("login_attempt", logged, login_detail)
        if logged:
            time.sleep(10)
        base.update(home_activity=base.activity(driver), home_labels=base.visible_labels(driver))
        if not logged:
            base.update(status="login_failed")
            return

        dabba, dabba_detail = base.click_text(driver, ["TV DABBA", "GUNGI LINE"])
        base.step("open_tv_dabba", dabba, dabba_detail)
        if dabba:
            time.sleep(10)
        base.update(tv_dabba_activity=base.activity(driver), tv_dabba_labels=base.visible_labels(driver), tv_dabba_contexts=base.contexts(driver))
        if not dabba:
            base.update(status="tv_dabba_not_found")
            return

        sky, sky_detail = base.click_text(driver, ["SKY"])
        base.step("open_sky", sky, sky_detail)
        if sky:
            time.sleep(10)
        base.update(sky_activity=base.activity(driver), sky_labels=base.visible_labels(driver), sky_contexts=base.contexts(driver))
        if not sky:
            base.update(status="sky_not_found_inside_tv_dabba")
            return

        join, join_detail = base.click_text(driver, ["JOIN MEETING", "JOIN NOW", "JOIN"])
        base.step("click_join_meeting", join, join_detail)
        if join:
            time.sleep(12)
        reached = "CustomMeetingActivity" in base.activity(driver)
        base.update(
            final_activity=base.activity(driver),
            final_labels=base.visible_labels(driver),
            meeting_activity_reached=reached,
        )

        if reached:
            base.update(status="meeting_activity_reached")
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
