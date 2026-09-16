import logging
import os
import re
import threading
import time
from difflib import SequenceMatcher

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import ibetin_ui_start as base
import ibetin_liveline_trial as liveline

logger = logging.getLogger(__name__)

TRIAL_VERSION = "20260916-0901"


def _is_owner_or_admin(user_id: int) -> bool:
    if not user_id:
        return False
    if int(user_id) == int(base.core.ADMIN_USER_ID):
        return True
    try:
        with base.core.db() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM business_connections
                WHERE owner_user_id = ? AND enabled = 1
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
        return bool(row)
    except Exception:
        logger.exception("Could not verify IBETIN Business owner for admin trial")
        return False


def _versioned_trial_url() -> str:
    url = base._mazza_admin_url()
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={TRIAL_VERSION}"


def _trial_markup():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "🏏 OPEN MIRROR TRIAL",
            web_app=WebAppInfo(url=_versioned_trial_url()),
        )]]
    )


# Telegram Android WebView rejects intent:// links. Patch the rendered page
# defensively so no Android intent URL can survive, even if the base page changes.
_original_mirror_page = base._mazza_mirror_page


def _telegram_safe_mirror_page() -> str:
    html = _original_mirror_page()
    play_html = base.escape(base.MAZZA_PLAY_URL, quote=True)

    html = re.sub(
        r'<a class="btn primary" href="intent://[^"]*">🏏 OPEN CRICKET MAZZA APP</a>',
        f'<a class="btn primary" href="{play_html}" target="_blank" rel="noopener noreferrer">🏏 OPEN CRICKET MAZZA</a>',
        html,
        flags=re.IGNORECASE,
    )
    html = html.replace("intent://", "https://play.google.com/store/apps/details?id=com.crics.cricket11#blocked-intent-")
    html = html.replace(
        '<div class="badge">ADMIN ONLY</div>',
        f'<div class="badge">ADMIN ONLY · SAFE {TRIAL_VERSION}</div>',
    )
    html = html.replace(
        "Suggested test: tap TRY DEVICE SCREEN MIRROR → allow full-screen sharing if Telegram/Android offers it → open Cricket Mazza → return here and check whether the preview kept capturing.",
        "Direct screen capture is not supported by Telegram Android WebView on this device. The HTTPS button below is only for opening the Cricket Mazza Play Store page; the actual mirror will require a remote Android relay/source.",
    )
    return html


base._mazza_mirror_page = _telegram_safe_mirror_page


async def _mazza_mirror_command(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat
    if not user or not message or not chat:
        return
    if getattr(chat, "type", "") != "private":
        await message.reply_text("This trial is available only in a private chat with the bot.")
        return
    logger.info("IBETIN Mazza mirror trial accepted user_id=%s", user.id)
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · ADMIN TRIAL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Private test only. Nothing from this screen is visible in the public IBETIN menu.",
        parse_mode="HTML",
        reply_markup=_trial_markup(),
        disable_web_page_preview=True,
    )


async def _admin_with_mazza_trial(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not _is_owner_or_admin(user.id):
        await message.reply_text("This command is restricted.")
        return
    if int(user.id) == int(base.core.ADMIN_USER_ID):
        try:
            await base._original_admin(update, context)
        except Exception:
            logger.exception("Legacy IBETIN admin panel failed")
    logger.info("IBETIN admin mirror trial accepted for authorized owner/admin")
    await message.reply_text(
        "🏏 <b>CRICKET MAZZA MIRROR · TRIAL</b>",
        parse_mode="HTML",
        reply_markup=_trial_markup(),
        disable_web_page_preview=True,
    )


base._mazza_mirror_command = _mazza_mirror_command
base._runtime.app.core.admin = _admin_with_mazza_trial


# Live Line uses a synchronous HTTP handler. urllib's default Python browser
# signature is blocked by Highlightly's Cloudflare policy on Railway (403/1010).
# Use httpx with a normal browser UA, and fall back to Highlightly's documented
# RapidAPI gateway when the direct host is blocked. The existing API key is tried
# on both paths without exposing it to the browser.
def _liveline_highlightly(path: str, params=None, ttl: int = 45):
    api_key = os.getenv("HIGHLIGHTLY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")

    params = params or {}
    cache_key = "liveline:" + liveline.HIGHLIGHTLY_BASE + path + "?" + str(sorted(params.items()))
    cached = liveline._cache_get(cache_key)
    if cached is not None:
        return cached

    common_headers = {
        "x-rapidapi-key": api_key,
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 16; SM-S938B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    endpoints = [
        (
            "Highlightly",
            f"https://sports.highlightly.net{path}",
            common_headers,
        ),
        (
            "RapidAPI",
            f"https://sport-highlights-api.p.rapidapi.com{path}",
            {**common_headers, "x-rapidapi-host": "sport-highlights-api.p.rapidapi.com"},
        ),
    ]

    failures = []
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for label, url, headers in endpoints:
            try:
                response = client.get(url, params=params, headers=headers)
                if 200 <= response.status_code < 300:
                    payload = response.json()
                    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
                    liveline._cache_put(cache_key, data, ttl)
                    logger.info("IBETIN Live Line feed OK via %s", label)
                    return data
                body = response.text[:180].replace("\n", " ")
                failures.append(f"{label} HTTP {response.status_code}: {body}")
            except Exception as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")

    logger.warning("IBETIN Live Line feed failed on both transports: %s", " | ".join(failures))
    raise RuntimeError("Cricket feed connection failed. Direct and fallback providers were unavailable.")


liveline._highlightly = _liveline_highlightly
logger.info("IBETIN Live Line Highlightly transport patched with Cloudflare-safe fallback")


# Roanuz V5 is used only for the private Live Line trial. Highlightly remains
# the fixture/general-data source; Roanuz enriches a matched live game with true
# delivery-level commentary. Project/API keys stay server-side in Railway.
_ROANUZ_BASE = "https://api.sports.roanuz.com/v5"
_roanuz_token = {"value": "", "until": 0.0}
_roanuz_lock = threading.Lock()


def _deep_value(node, names):
    if isinstance(node, dict):
        for name in names:
            value = node.get(name)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return value
        for value in node.values():
            found = _deep_value(value, names)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _deep_value(value, names)
            if found is not None:
                return found
    return None


def _roanuz_auth(force: bool = False) -> str:
    project = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
    api_key = os.getenv("ROANUZ_API_KEY", "").strip()
    if not project or not api_key:
        raise RuntimeError("Roanuz credentials are not configured")

    with _roanuz_lock:
        if not force and _roanuz_token["value"] and _roanuz_token["until"] > time.time() + 60:
            return _roanuz_token["value"]

        url = f"{_ROANUZ_BASE}/core/{project}/auth/"
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.post(url, json={"api_key": api_key}, headers={"Accept": "application/json"})
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Roanuz auth HTTP {response.status_code}")
        payload = response.json()
        token = _deep_value(payload, ("token", "access_token", "accessToken"))
        if not token:
            raise RuntimeError("Roanuz authentication returned no access token")

        # Roanuz access tokens are normally refreshed every 24 hours. Cache for
        # 20 hours and also force-refresh immediately if an API call rejects it.
        _roanuz_token["value"] = str(token)
        _roanuz_token["until"] = time.time() + (20 * 60 * 60)
        return _roanuz_token["value"]


def _roanuz_get(path: str, ttl: int = 10):
    project = os.getenv("ROANUZ_PROJECT_KEY", "").strip()
    if not project:
        raise RuntimeError("ROANUZ_PROJECT_KEY is not configured")
    cache_key = f"roanuz:{path}"
    cached = liveline._cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_ROANUZ_BASE}/cricket/{project}/{path.lstrip('/')}"
    last_status = 0
    for attempt in range(2):
        token = _roanuz_auth(force=(attempt == 1))
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url, headers={"rs-token": token, "Accept": "application/json"})
        last_status = response.status_code
        if 200 <= response.status_code < 300:
            payload = response.json()
            liveline._cache_put(cache_key, payload, ttl)
            return payload
        if response.status_code not in (401, 403):
            break
    raise RuntimeError(f"Roanuz HTTP {last_status}")


def _roanuz_featured_matches():
    cached = liveline._cache_get("roanuz:featured:candidates")
    if cached is not None:
        return cached
    payload = _roanuz_get("featured-matches-2/", ttl=45)
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            key = node.get("key") or node.get("match_key") or node.get("matchKey")
            teams = node.get("teams")
            if key and (teams is not None or node.get("playStatus") is not None or node.get("play_status") is not None):
                marker = str(key)
                if marker not in seen:
                    seen.add(marker)
                    found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    liveline._cache_put("roanuz:featured:candidates", found, 45)
    return found


def _team_names_from_roanuz(match):
    names = []
    teams = match.get("teams") if isinstance(match, dict) else None
    if isinstance(teams, dict):
        ordered = []
        for side in ("a", "b", "home", "away"):
            if side in teams:
                ordered.append(teams.get(side))
        if not ordered:
            ordered = list(teams.values())
        for obj in ordered:
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("shortName") or obj.get("short_name")
            else:
                name = obj
            if name:
                names.append(str(name))
    elif isinstance(teams, list):
        for obj in teams:
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("shortName") or obj.get("short_name")
            else:
                name = obj
            if name:
                names.append(str(name))
    return names[:2]


def _clean_team_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    value = re.sub(r"\b(cricket|club|team)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _name_similarity(left: str, right: str) -> float:
    a, b = _clean_team_name(left), _clean_team_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.92
    return SequenceMatcher(None, a, b).ratio()


def _find_roanuz_match_key(detail) -> str:
    match = detail.get("match") if isinstance(detail, dict) else {}
    if not isinstance(match, dict):
        return ""
    home = ((match.get("home") or {}).get("name") if isinstance(match.get("home"), dict) else "") or ""
    away = ((match.get("away") or {}).get("name") if isinstance(match.get("away"), dict) else "") or ""
    if not home or not away:
        return ""

    best_key, best_score = "", 0.0
    for candidate in _roanuz_featured_matches():
        names = _team_names_from_roanuz(candidate)
        if len(names) < 2:
            continue
        direct = (_name_similarity(home, names[0]) + _name_similarity(away, names[1])) / 2
        reverse = (_name_similarity(home, names[1]) + _name_similarity(away, names[0])) / 2
        score = max(direct, reverse)
        if score > best_score:
            best_score = score
            best_key = str(candidate.get("key") or candidate.get("match_key") or candidate.get("matchKey") or "")
    if best_score >= 0.68:
        logger.info("IBETIN Live Line matched Highlightly game to Roanuz key=%s confidence=%.2f", best_key, best_score)
        return best_key
    logger.info("IBETIN Live Line found no safe Roanuz match mapping; best confidence=%.2f", best_score)
    return ""


def _roanuz_timeline(match_key: str):
    payload = _roanuz_get(f"match/{match_key}/ball-by-ball/", ttl=5)
    balls = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            comment = node.get("comment") or node.get("commentary") or node.get("text") or node.get("description")
            over_str = node.get("over_str") or node.get("overStr")
            ball_no = node.get("ball")
            over_no = node.get("over")
            if comment and (over_str is not None or ball_no is not None or over_no is not None):
                marker = str(node.get("key") or node.get("id") or f"{over_str}:{ball_no}:{comment}")
                if marker not in seen:
                    seen.add(marker)
                    text = re.sub(r"<[^>]+>", "", str(comment)).strip()
                    display_over = over_str
                    if display_over is None and over_no is not None:
                        try:
                            display_over = f"{max(int(over_no) - 1, 0)}.{ball_no or ''}".rstrip(".")
                        except Exception:
                            display_over = f"{over_no}.{ball_no or ''}".rstrip(".")
                    balls.append({
                        "over": str(display_over or ball_no or "Ball"),
                        "commentary": text,
                        "runs": node.get("runs"),
                        "wicket": node.get("wicket") or node.get("wicket_type"),
                        "updated": node.get("updated") or node.get("updatedAt") or "",
                    })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return balls[-30:]


_original_match_detail = liveline._match_detail


def _match_detail_with_roanuz(match_id: str):
    detail = _original_match_detail(match_id)
    if not os.getenv("ROANUZ_PROJECT_KEY", "").strip() or not os.getenv("ROANUZ_API_KEY", "").strip():
        return detail
    try:
        match_key = _find_roanuz_match_key(detail)
        if match_key:
            timeline = _roanuz_timeline(match_key)
            if timeline:
                detail["timeline"] = timeline
                detail["timelineSource"] = "Roanuz"
                detail["roanuzMatchKey"] = match_key
                logger.info("IBETIN Live Line loaded %s Roanuz ball events for match=%s", len(timeline), match_key)
    except Exception as exc:
        # Never break the existing scorecard if Roanuz is unavailable or the
        # user's current plan does not include the selected match.
        logger.warning("IBETIN Roanuz enrichment unavailable: %s", exc)
    return detail


liveline._match_detail = _match_detail_with_roanuz
logger.info("IBETIN Live Line Roanuz ball-by-ball enrichment installed")


def _probe_roanuz():
    try:
        _roanuz_auth()
        featured = _roanuz_featured_matches()
        logger.info("IBETIN Roanuz authentication PASS; featured match candidates=%s", len(featured))
    except Exception as exc:
        logger.warning("IBETIN Roanuz authentication/feed probe FAILED: %s", exc)


if os.getenv("ROANUZ_PROJECT_KEY", "").strip() and os.getenv("ROANUZ_API_KEY", "").strip():
    threading.Thread(target=_probe_roanuz, name="ibetin-roanuz-probe", daemon=True).start()


# Install the new Live Line V1 as a hidden private preview. This adds only
# /liveline and its signed admin web routes; it does not touch the public menu.
liveline.install()

logger.info("IBETIN Mazza mirror trial enabled for direct private chat; /admin stays restricted")
logger.info("IBETIN Mazza launcher hard-patched to HTTPS; trial version=%s", TRIAL_VERSION)
logger.info("IBETIN Live Line V1 preview bootstrap installed")

if __name__ == "__main__":
    base.ibetin_start.main()
