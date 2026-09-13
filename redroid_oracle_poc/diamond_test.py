#!/usr/bin/env python3
import os, re, subprocess, time, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

SERIAL = os.getenv("ANDROID_SERIAL", "127.0.0.1:5555")
BASE = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
TOKEN = os.getenv("TRIAL_TV_TOKEN", "").strip()
USERNAME = os.getenv("DIAMOND_USERNAME", "")
PASSWORD = os.getenv("DIAMOND_PASSWORD", "")
PACKAGE = "com.diamond.diamondlive"
MAIN = "com.sherdle.universal.MainActivity"
MEETING = "com.sherdle.universal.custom.CustomMeetingActivity"
APK = Path("/tmp/diamond.apk")


def run(args, timeout=120, check=True):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(p.stdout[-2000:])
    return p.stdout.strip()


def adb(*args, timeout=120, check=True):
    return run(["adb", "-s", SERIAL, *args], timeout=timeout, check=check)


def shell(*args, timeout=60, check=True):
    return adb("shell", *args, timeout=timeout, check=check)


def dump_ui():
    shell("uiautomator", "dump", "/sdcard/window.xml", check=False)
    xml = adb("exec-out", "cat", "/sdcard/window.xml", check=False)
    if "<hierarchy" not in xml:
        return None
    return ET.fromstring(xml[xml.find("<hierarchy"):])


def find_node(root, suffix=None, contains=None):
    if root is None:
        return None
    needle = (contains or "").lower()
    for n in root.iter("node"):
        rid = n.attrib.get("resource-id", "")
        label = (n.attrib.get("text", "") + " " + n.attrib.get("content-desc", "")).strip()
        if suffix and rid.endswith(suffix):
            return n
        if needle and needle in label.lower():
            return n
    return None


def tap(node):
    nums = [int(x) for x in re.findall(r"\d+", node.attrib.get("bounds", ""))]
    if len(nums) != 4:
        return False
    x, y = (nums[0] + nums[2]) // 2, (nums[1] + nums[3]) // 2
    shell("input", "tap", str(x), str(y))
    return True


def wait_tap(suffix=None, contains=None, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        n = find_node(dump_ui(), suffix=suffix, contains=contains)
        if n is not None and tap(n):
            return True
        time.sleep(2)
    return False


def input_text(value):
    value = value.replace(" ", "%s")
    shell("input", "text", value)


def main():
    missing = [k for k,v in {
        "TRACKING_BASE_URL": BASE,
        "TRIAL_TV_TOKEN": TOKEN,
        "DIAMOND_USERNAME": USERNAME,
        "DIAMOND_PASSWORD": PASSWORD,
    }.items() if not v]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))

    print("[1/8] Checking Android")
    adb("get-state")
    print("Android", shell("getprop", "ro.build.version.release"), shell("getprop", "ro.product.cpu.abi"))

    print("[2/8] Downloading private Diamond APK")
    url = f"{BASE}/trial-diamond-apk?t={quote(TOKEN, safe='')}"
    req = urllib.request.Request(url, headers={"User-Agent":"Fantzo-ReDroid-PoC/1.0"})
    with urllib.request.urlopen(req, timeout=900) as src, APK.open("wb") as dst:
        while True:
            b = src.read(1024*1024)
            if not b: break
            dst.write(b)
    if APK.stat().st_size < 10_000_000:
        raise RuntimeError("Downloaded APK is unexpectedly small")

    print("[3/8] Installing Diamond")
    adb("install", "-r", str(APK), timeout=900)

    print("[4/8] Launching Diamond")
    shell("am", "force-stop", PACKAGE, check=False)
    shell("am", "start", "-n", f"{PACKAGE}/{MAIN}")
    time.sleep(8)

    print("[5/8] Handling first-run privacy")
    if wait_tap(suffix="privacy_accept_button", timeout=15):
        time.sleep(5)

    print("[6/8] Logging in if needed")
    root = dump_ui()
    user = find_node(root, suffix="username")
    passwd = find_node(root, suffix="password")
    if user is not None and passwd is not None:
        tap(user); input_text(USERNAME)
        tap(passwd); input_text(PASSWORD)
        if not wait_tap(suffix="submit", timeout=8):
            wait_tap(contains="LOGIN", timeout=8)
        time.sleep(10)
    else:
        print("Login fields not present; assuming session already logged in")

    print("[7/8] Opening Button 1: ALL IN ONE GROUND LINE")
    if not wait_tap(suffix="first", timeout=20):
        if not wait_tap(contains="GROUND LINE", timeout=15):
            raise RuntimeError("Button 1 was not found")
    time.sleep(12)

    print("[8/8] Verifying meeting activity")
    windows = shell("dumpsys", "window", "windows", check=False)
    if "CustomMeetingActivity" not in windows:
        raise RuntimeError("Button 1 did not reach CustomMeetingActivity")

    shot = "/tmp/diamond-meeting.png"
    with open(shot, "wb") as f:
        p = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"], stdout=f)
        if p.returncode:
            raise RuntimeError("Unable to capture meeting screenshot")

    print("SUCCESS")
    print("Meeting activity:", MEETING)
    print("Screenshot:", shot)
    print("Next test: inspect whether the meeting video surface renders normally. No DRM/capture bypass is attempted.")


if __name__ == "__main__":
    main()
