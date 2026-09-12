import hashlib
import json
import logging
import os
import re
import threading
import zipfile
from pathlib import Path

from androguard.core.apk import APK

logger = logging.getLogger(__name__)

APK_PATH = Path(os.getenv("APK_ANALYSIS_PATH", "/data/uploads/diamond.apk"))
REPORT_PATH = Path(os.getenv("APK_REPORT_PATH", "/data/uploads/diamond_report.json"))
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
_started = False

MEDIA_PATTERNS = {
    "WebView": [b"android/webkit/WebView", b"Landroid/webkit/WebView;"],
    "ExoPlayer": [b"com/google/android/exoplayer2", b"ExoPlayer"],
    "Media3": [b"androidx/media3", b"androidx.media3"],
    "VLC": [b"org/videolan/libvlc", b"libvlc"],
    "FFmpeg": [b"ffmpeg", b"avcodec", b"libavformat"],
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _component_name(package: str, raw: str | None) -> str:
    if not raw:
        return ""
    if raw.startswith("."):
        return package + raw
    if "." not in raw:
        return package + "." + raw
    return raw


def _manifest_components(apk: APK):
    root = apk.get_android_manifest_xml()
    package = apk.get_package() or ""
    app = root.find("application") if root is not None else None
    result = {"activities": [], "services": [], "receivers": [], "providers": []}
    deep_links = []
    if app is None:
        return result, deep_links

    mapping = {
        "activity": "activities",
        "activity-alias": "activities",
        "service": "services",
        "receiver": "receivers",
        "provider": "providers",
    }
    for tag, bucket in mapping.items():
        for node in app.findall(tag):
            raw_name = node.get(ANDROID_NS + "name")
            exported = node.get(ANDROID_NS + "exported")
            has_filter = bool(node.findall("intent-filter"))
            is_exported = exported == "true" or (exported is None and has_filter)
            name = _component_name(package, raw_name)
            if is_exported:
                result[bucket].append(name)

            for intent in node.findall("intent-filter"):
                actions = [a.get(ANDROID_NS + "name") for a in intent.findall("action") if a.get(ANDROID_NS + "name")]
                categories = [c.get(ANDROID_NS + "name") for c in intent.findall("category") if c.get(ANDROID_NS + "name")]
                for data in intent.findall("data"):
                    item = {
                        "component": name,
                        "actions": actions,
                        "categories": categories,
                        "scheme": data.get(ANDROID_NS + "scheme"),
                        "host": data.get(ANDROID_NS + "host"),
                        "port": data.get(ANDROID_NS + "port"),
                        "path": data.get(ANDROID_NS + "path"),
                        "pathPrefix": data.get(ANDROID_NS + "pathPrefix"),
                        "pathPattern": data.get(ANDROID_NS + "pathPattern"),
                        "mimeType": data.get(ANDROID_NS + "mimeType"),
                    }
                    if any(item.get(k) for k in ("scheme", "host", "path", "pathPrefix", "pathPattern", "mimeType")):
                        deep_links.append(item)
    for k in result:
        result[k] = sorted(set(x for x in result[k] if x))
    return result, deep_links


def _scan_media_and_domains(apk_path: Path):
    found = {k: False for k in MEDIA_PATTERNS}
    domains = set()
    url_re = re.compile(rb"https?://([A-Za-z0-9.-]+)")
    interesting_libs = []
    total_scanned = 0
    max_total = 160 * 1024 * 1024
    allowed_prefixes = ("classes", "assets/", "res/raw/", "lib/")

    with zipfile.ZipFile(apk_path) as zf:
        for info in zf.infolist():
            name = info.filename
            low = name.lower()
            if low.startswith("lib/") and low.endswith(".so"):
                if any(x in low for x in ("vlc", "ffmpeg", "avcodec", "avformat", "player", "media", "codec")):
                    interesting_libs.append(name)
            if not low.startswith(allowed_prefixes):
                continue
            if info.file_size <= 0 or info.file_size > 80 * 1024 * 1024:
                continue
            try:
                with zf.open(info) as fh:
                    carry = b""
                    while total_scanned < max_total:
                        chunk = fh.read(1024 * 1024)
                        if not chunk:
                            break
                        total_scanned += len(chunk)
                        data = carry + chunk
                        for label, patterns in MEDIA_PATTERNS.items():
                            if not found[label] and any(p.lower() in data.lower() for p in patterns):
                                found[label] = True
                        for m in url_re.finditer(data):
                            host = m.group(1).decode("ascii", "ignore").lower().strip(".")
                            if host and len(host) < 200:
                                domains.add(host)
                        carry = data[-512:]
                    if total_scanned >= max_total:
                        break
            except Exception:
                continue

    safe_domains = sorted(
        d for d in domains
        if d and not any(s in d for s in ("googleapis.com", "google.com", "gstatic.com", "firebase", "crashlytics", "facebook.com", "doubleclick.net"))
    )[:80]
    return found, sorted(set(interesting_libs))[:80], safe_domains


def build_report() -> dict:
    if not APK_PATH.exists():
        return {"error": "APK not found", "path": str(APK_PATH)}

    apk = APK(str(APK_PATH))
    components, deep_links = _manifest_components(apk)
    media, libs, domains = _scan_media_and_domains(APK_PATH)

    report = {
        "file": {
            "path": str(APK_PATH),
            "size_bytes": APK_PATH.stat().st_size,
            "sha256": _sha256(APK_PATH),
        },
        "package": apk.get_package(),
        "version_name": apk.get_androidversion_name(),
        "version_code": apk.get_androidversion_code(),
        "min_sdk": apk.get_min_sdk_version(),
        "target_sdk": apk.get_target_sdk_version(),
        "main_activity": apk.get_main_activity(),
        "exported_components": components,
        "deep_links": deep_links,
        "media_technology_signals": media,
        "interesting_native_libraries": libs,
        "public_domains_found": domains,
        "notes": [
            "Static inspection only; APK was not executed.",
            "Only domain names are reported from embedded URLs; paths, query strings, tokens and credentials are intentionally omitted.",
            "This report does not attempt to bypass authentication, DRM, licensing, or protected media controls.",
        ],
    }
    return report


def analyze_to_file() -> None:
    try:
        report = build_report()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Static APK report written to %s", REPORT_PATH)
    except Exception as exc:
        logger.exception("Static APK analysis failed: %s", exc)
        try:
            REPORT_PATH.write_text(json.dumps({"error": str(exc)}, indent=2), encoding="utf-8")
        except Exception:
            pass


def start_background_analysis() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=analyze_to_file, daemon=True, name="apk-static-analysis").start()
