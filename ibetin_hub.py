import hashlib
import hmac
import json
import logging
import os
import time
from html import escape
from string import Template
from urllib.parse import parse_qs, parse_qsl, quote, urlparse

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.ext import CommandHandler

import bot as core
import ibetin_match_alerts as match_alerts

logger = logging.getLogger(__name__)

HUB_PATH = "/hub"
PREFS_PATH = "/hub/api/preferences"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

IBETIN_HOME_URL = os.getenv("IBETIN_HOME_URL", "https://ibetin.com").strip().rstrip("/")
IBETIN_SPORTS_URL = os.getenv("IBETIN_SPORTS_URL", f"{IBETIN_HOME_URL}/line").strip()
IBETIN_LIVE_URL = os.getenv("IBETIN_LIVE_URL", f"{IBETIN_HOME_URL}/live").strip()
IBETIN_CASINO_URL = os.getenv("IBETIN_CASINO_URL", f"{IBETIN_HOME_URL}/casino").strip()
IBETIN_GAMES_URL = os.getenv("IBETIN_GAMES_URL", f"{IBETIN_HOME_URL}/games").strip()
IBETIN_RESULTS_URL = os.getenv("IBETIN_RESULTS_URL", f"{IBETIN_HOME_URL}/results").strip()
IBETIN_PAYMENT_URL = os.getenv(
    "IBETIN_PAYMENT_URL", f"{IBETIN_HOME_URL}/information/payment"
).strip()
IBETIN_SUPPORT_URL = os.getenv(
    "IBETIN_SUPPORT_URL", f"{IBETIN_HOME_URL}/information/contacts"
).strip()

SECTION_TARGETS = {
    "sports": IBETIN_SPORTS_URL,
    "live": IBETIN_LIVE_URL,
    "casino": IBETIN_CASINO_URL,
    "games": IBETIN_GAMES_URL,
    "results": IBETIN_RESULTS_URL,
    "payments": IBETIN_PAYMENT_URL,
    "support": IBETIN_SUPPORT_URL,
}
SECTION_LABELS = {
    "sports": "Sports",
    "live": "Live",
    "casino": "Live Casino",
    "games": "Games",
    "results": "Results",
    "payments": "Payments",
    "support": "Support",
}
ALLOWED_SECTIONS = {"home", "alerts", "settings", *SECTION_TARGETS.keys()}


def _public_base_url() -> str:
    value = (
        os.getenv("TRACKING_BASE_URL", "").strip()
        or os.getenv("RAILWAY_STATIC_URL", "").strip()
        or os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    )
    if not value:
        value = "https://ibetin-app-production.up.railway.app"
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def hub_url(section: str = "home") -> str:
    section = (section or "home").strip().lower()
    if section not in ALLOWED_SECTIONS:
        section = "home"
    return f"{_public_base_url()}{HUB_PATH}?section={quote(section, safe='')}"


def news_url() -> str:
    return f"{_public_base_url()}/news?category=latest"


def webapp_button(label: str, section: str = "home") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=hub_url(section)))


def news_button(label: str = "📰 SPORTS NEWS") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=news_url()))


def clean_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [webapp_button("⚡ OPEN IBETIN", "home")],
            [
                news_button("📰 NEWS"),
                webapp_button("🔴 LIVE", "live"),
            ],
            [
                webapp_button("🔔 MY ALERTS", "alerts"),
                webapp_button("🛟 SUPPORT", "support"),
            ],
        ]
    )


def _verify_init_data(init_data: str) -> dict:
    if not BOT_TOKEN or not init_data:
        raise ValueError("Telegram authentication is unavailable")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise ValueError("Missing Telegram signature")

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
    ).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram signature")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise ValueError("Invalid Telegram auth date") from exc

    if auth_date <= 0 or abs(int(time.time()) - auth_date) > 86400:
        raise ValueError("Telegram session expired")

    try:
        user = json.loads(fields.get("user", "{}"))
        user_id = int(user.get("id"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Telegram user is unavailable") from exc

    if user_id <= 0:
        raise ValueError("Telegram user is unavailable")
    return user


def _ensure_user(user: dict) -> int:
    user_id = int(user["id"])
    username = str(user.get("username") or "")
    first_name = str(user.get("first_name") or "")
    now = core.now_iso()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (user_id, username, first_name, now, now),
        )
    return user_id


def _get_preferences(user_id: int) -> dict:
    with core.db() as conn:
        row = conn.execute(
            "SELECT subscribed, language FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    prefs = {
        "subscribed": bool(row["subscribed"]) if row else False,
        "language": (
            str(row["language"])
            if row and str(row["language"]) in {"en", "hi"}
            else "en"
        ),
    }
    prefs.update(match_alerts.get_preferences(int(user_id)))
    return prefs


def _set_preferences(user_id: int, payload: dict) -> dict:
    if "subscribed" in payload:
        value = bool(payload["subscribed"])
        core.set_subscription(user_id, value)
        try:
            core.track(user_id, "mini_alerts_on" if value else "mini_alerts_off")
        except Exception:
            logger.exception("Could not track IBETIN alert preference")

    if "language" in payload:
        language = str(payload["language"]).lower()
        if language not in {"en", "hi"}:
            raise ValueError("Unsupported language")
        core.set_language(user_id, language)
        try:
            core.track(user_id, f"mini_language_{language}")
        except Exception:
            logger.exception("Could not track IBETIN language preference")

    if "cricket_alerts" in payload or "football_alerts" in payload:
        match_alerts.set_preferences(
            user_id,
            cricket_alerts=(
                bool(payload.get("cricket_alerts"))
                if "cricket_alerts" in payload
                else None
            ),
            football_alerts=(
                bool(payload.get("football_alerts"))
                if "football_alerts" in payload
                else None
            ),
        )
        try:
            core.track(user_id, "mini_alert_sports_updated")
        except Exception:
            logger.exception("Could not track IBETIN sport alert preference")

    return _get_preferences(user_id)


def _home_cards() -> str:
    cards = [
        ("🏆", "Sports", "Matches & markets", hub_url("sports")),
        ("🔴", "Live", "Live action", hub_url("live")),
        ("📰", "Sports News", "Fresh India-focused updates", news_url()),
        ("🎰", "Live Casino", "Casino section", hub_url("casino")),
        ("🎮", "Games", "Browse games", hub_url("games")),
        ("📊", "Results", "Latest results", hub_url("results")),
        ("💳", "Payments", "Payment information", hub_url("payments")),
        ("🛟", "Support", "Official help", hub_url("support")),
        ("🔔", "My Alerts", "Notification controls", hub_url("alerts")),
        ("⚙️", "Settings", "Language & preferences", hub_url("settings")),
    ]
    return "".join(
        (
            f'<a class="tile" href="{escape(url, quote=True)}">'
            f'<span class="ico">{icon}</span>'
            f'<span class="tile-copy"><b>{escape(title)}</b>'
            f'<small>{escape(subtitle)}</small></span></a>'
        )
        for icon, title, subtitle, url in cards
    )


PAGE_TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>$title</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{box-sizing:border-box}
:root{--bg:#07101c;--card:#0e1b2b;--card2:#101f31;--line:#20334b;--text:#f7f9fc;--muted:#91a5bc;--soft:#b8c6d6}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,Arial,Helvetica,sans-serif}
body{padding-bottom:84px}
.wrap{max-width:760px;margin:0 auto;padding:15px 14px 28px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.brand{font-size:18px;font-weight:950;letter-spacing:.8px}
.pill{border:1px solid var(--line);border-radius:999px;padding:6px 9px;color:var(--muted);font-size:10px;font-weight:900}
.hero{background:linear-gradient(145deg,#13253a,#0b1726);border:1px solid #29415e;border-radius:24px;padding:21px 18px;box-shadow:0 14px 40px rgba(0,0,0,.22)}
.hero .eyebrow{font-size:11px;font-weight:900;letter-spacing:1.2px;color:#9fb5ca;margin-bottom:8px}
.hero h1{font-size:26px;line-height:1.08;margin:0 0 8px}
.hero p{margin:0;color:var(--soft);font-size:14px;line-height:1.5}
.quick{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.tile{display:flex;align-items:center;gap:11px;min-height:78px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:13px;text-decoration:none;color:var(--text)}
.tile:active{transform:scale(.985)}
.ico{font-size:25px;flex:0 0 32px;text-align:center}
.tile-copy{display:flex;min-width:0;flex-direction:column;gap:4px}
.tile-copy b{font-size:13px}
.tile-copy small{font-size:10.5px;line-height:1.3;color:var(--muted)}
.section{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:16px}
.section h2{font-size:17px;margin:0 0 7px}
.section p{color:var(--soft);line-height:1.5;font-size:13px;margin:0}
.row{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:15px;padding-top:15px;border-top:1px solid var(--line)}
.switch{position:relative;width:58px;height:32px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;border-radius:999px;background:#31445a;transition:.18s}
.slider:before{content:"";position:absolute;width:24px;height:24px;left:4px;top:4px;background:white;border-radius:50%;transition:.18s}
.switch input:checked + .slider{background:#2d7d5a}
.switch input:checked + .slider:before{transform:translateX(26px)}
.status{margin-top:10px;font-size:12px;color:var(--muted)}
select{width:100%;margin-top:12px;padding:13px 12px;border-radius:13px;background:var(--card2);color:var(--text);border:1px solid #2b425e;font-size:15px}
.primary{display:block;width:100%;border:0;border-radius:14px;padding:14px 16px;margin-top:14px;background:#f7f9fc;color:#07101c;font-weight:950;text-align:center;text-decoration:none;font-size:14px}
.loading{display:flex;align-items:center;gap:10px;color:var(--soft)}
.dot{width:10px;height:10px;border-radius:50%;background:#f7f9fc;animation:pulse 1s infinite alternate}
@keyframes pulse{to{opacity:.25}}
.note{font-size:11px!important;color:#7e93aa!important;margin-top:10px!important}
.nav{position:fixed;left:0;right:0;bottom:0;background:rgba(7,16,28,.96);backdrop-filter:blur(14px);border-top:1px solid #1e3046;padding:9px 12px max(9px,env(safe-area-inset-bottom));display:flex;justify-content:center;gap:6px;z-index:20}
.nav a{flex:1;max-width:160px;text-align:center;text-decoration:none;color:#94a8bd;font-size:10px;font-weight:900;padding:7px 4px;border-radius:11px}
.nav a strong{display:block;color:#eef3f8;font-size:17px;margin-bottom:2px}
.toast{position:fixed;left:50%;bottom:92px;transform:translate(-50%,16px);opacity:0;pointer-events:none;background:#f7f9fc;color:#07101c;border-radius:999px;padding:9px 13px;font-size:11px;font-weight:900;transition:.2s;z-index:30}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media(max-width:390px){.quick{gap:8px}.tile{padding:11px;min-height:74px}.tile-copy b{font-size:12px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><div class="brand">IBETIN</div><div class="pill">TELEGRAM MINI APP</div></div>
  $content
</div>
<nav class="nav">
  <a href="$home_url"><strong>⌂</strong>Home</a>
  <a href="$news_url"><strong>📰</strong>News</a>
  <a href="$alerts_url"><strong>🔔</strong>Alerts</a>
  <a href="$support_url"><strong>🛟</strong>Support</a>
</nav>
<div id="toast" class="toast"></div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  try { tg.setHeaderColor('#07101c'); tg.setBackgroundColor('#07101c'); } catch (e) {}
}
const initData = tg ? (tg.initData || '') : '';
function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(window.__ibetinToast);
  window.__ibetinToast = setTimeout(() => el.classList.remove('show'), 1800);
}
async function prefs(payload) {
  const response = await fetch('$prefs_path', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(Object.assign({initData:initData}, payload))
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not save preference');
  return data;
}
$script
</script>
</body>
</html>"""
)


def _page(section: str) -> str:
    section = section if section in ALLOWED_SECTIONS else "home"
    script = ""

    if section == "home":
        content = f"""
        <section class="hero">
          <div class="eyebrow">YOUR IBETIN COMMAND CENTER</div>
          <h1>Everything important. One clean screen.</h1>
          <p>Sports, live action, news, account help and personal alerts — all from inside Telegram.</p>
        </section>
        <div class="quick">{_home_cards()}</div>
        <section class="section">
          <h2>Designed for speed</h2>
          <p>No crowded bot menus. Use the dashboard above, or the four shortcuts at the bottom.</p>
          <p class="note">🔞 18+ • Play responsibly • T&Cs apply</p>
        </section>
        """
    elif section == "alerts":
        content = """
        <section class="hero">
          <div class="eyebrow">PERSONAL NOTIFICATIONS</div>
          <h1>My Match Alerts</h1>
          <p>Choose which sports you want IBETIN to notify you about.</p>
        </section>
        <section class="section">
          <h2>Telegram alerts</h2>
          <p>Your choices are saved directly to your IBETIN bot profile.</p>
          <div class="row">
            <div><b>Match notifications</b><div class="status" id="alertStatus">Checking your preference…</div></div>
            <label class="switch"><input id="alertsToggle" type="checkbox" disabled><span class="slider"></span></label>
          </div>
          <div class="row">
            <div><b>🏏 Cricket</b><div class="status">Toss, start, innings break and result alerts</div></div>
            <label class="switch"><input id="cricketToggle" type="checkbox" disabled><span class="slider"></span></label>
          </div>
          <div class="row">
            <div><b>⚽ Football</b><div class="status">Start, half-time and result alerts</div></div>
            <label class="switch"><input id="footballToggle" type="checkbox" disabled><span class="slider"></span></label>
          </div>
          <p class="note">Cricket is the default. Football is optional. You can change this anytime.</p>
        </section>
        """
        script = """
const toggle = document.getElementById('alertsToggle');
const cricketToggle = document.getElementById('cricketToggle');
const footballToggle = document.getElementById('footballToggle');
const status = document.getElementById('alertStatus');

function applyAlertState(data) {
  toggle.checked = !!data.subscribed;
  cricketToggle.checked = data.cricket_alerts !== false;
  footballToggle.checked = !!data.football_alerts;
  toggle.disabled = false;
  cricketToggle.disabled = false;
  footballToggle.disabled = false;
  status.textContent = data.subscribed ? 'Alerts are ON' : 'Alerts are OFF';
}

async function loadAlerts() {
  if (!initData) {
    status.textContent = 'Open this Mini App from @ibtnofficialbot to manage alerts.';
    return;
  }
  try {
    applyAlertState(await prefs({action:'get'}));
  } catch (e) {
    status.textContent = e.message;
  }
}

toggle.addEventListener('change', async () => {
  toggle.disabled = true;
  try {
    const data = await prefs({action:'set', subscribed:toggle.checked});
    applyAlertState(data);
    toast(data.subscribed ? 'Match alerts enabled' : 'Match alerts disabled');
  } catch (e) {
    toggle.checked = !toggle.checked;
    status.textContent = e.message;
    toast('Could not save');
    toggle.disabled = false;
  }
});

cricketToggle.addEventListener('change', async () => {
  cricketToggle.disabled = true;
  try {
    applyAlertState(await prefs({action:'set', cricket_alerts:cricketToggle.checked}));
    toast('Cricket alert preference saved');
  } catch (e) {
    cricketToggle.checked = !cricketToggle.checked;
    toast('Could not save');
    cricketToggle.disabled = false;
  }
});

footballToggle.addEventListener('change', async () => {
  footballToggle.disabled = true;
  try {
    applyAlertState(await prefs({action:'set', football_alerts:footballToggle.checked}));
    toast('Football alert preference saved');
  } catch (e) {
    footballToggle.checked = !footballToggle.checked;
    toast('Could not save');
    footballToggle.disabled = false;
  }
});

loadAlerts();
"""
    elif section == "settings":
        content = """
        <section class="hero">
          <div class="eyebrow">YOUR PREFERENCES</div>
          <h1>Settings</h1>
          <p>Keep your IBETIN bot language synced with the Mini App.</p>
        </section>
        <section class="section">
          <h2>Language</h2>
          <select id="language" disabled>
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
          </select>
          <div class="status" id="languageStatus">Checking your preference…</div>
        </section>
        """
        script = """
const language = document.getElementById('language');
const languageStatus = document.getElementById('languageStatus');
async function loadSettings() {
  if (!initData) {
    languageStatus.textContent = 'Open this Mini App from @ibtnofficialbot to manage settings.';
    return;
  }
  try {
    const data = await prefs({action:'get'});
    language.value = data.language || 'en';
    language.disabled = false;
    languageStatus.textContent = 'Synced with your bot profile';
  } catch (e) {
    languageStatus.textContent = e.message;
  }
}
language.addEventListener('change', async () => {
  language.disabled = true;
  try {
    const data = await prefs({action:'set', language:language.value});
    language.value = data.language || 'en';
    languageStatus.textContent = 'Saved to your bot profile';
    toast('Language saved');
  } catch (e) {
    languageStatus.textContent = e.message;
    toast('Could not save');
  } finally {
    language.disabled = false;
  }
});
loadSettings();
"""
    else:
        label = SECTION_LABELS[section]
        target = SECTION_TARGETS[section]
        content = f"""
        <section class="hero">
          <div class="eyebrow">IBETIN MINI APP</div>
          <h1>{escape(label)}</h1>
          <p>Opening {escape(label)} inside this Telegram Mini App…</p>
        </section>
        <section class="section">
          <div class="loading"><span class="dot"></span><b>Loading secure IBETIN section</b></div>
          <a class="primary" href="{escape(target, quote=True)}">CONTINUE INSIDE TELEGRAM</a>
        </section>
        """
        script = f"""
setTimeout(() => {{
  window.location.replace({json.dumps(target)});
}}, 180);
"""

    return PAGE_TEMPLATE.safe_substitute(
        title=escape(f"IBETIN · {SECTION_LABELS.get(section, section.title())}"),
        content=content,
        home_url=escape(hub_url("home"), quote=True),
        news_url=escape(news_url(), quote=True),
        alerts_url=escape(hub_url("alerts"), quote=True),
        support_url=escape(hub_url("support"), quote=True),
        prefs_path=PREFS_PATH,
        script=script,
    )


def _send_html(handler, status: int, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def _send_json(handler, status: int, payload: dict) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _handle_preferences_post(handler) -> None:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if length <= 0 or length > 16384:
            raise ValueError("Invalid request")
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
        user = _verify_init_data(str(payload.get("initData") or ""))
        user_id = _ensure_user(user)
        action = str(payload.get("action") or "get").lower()
        if action == "set":
            preferences = _set_preferences(user_id, payload)
        elif action == "get":
            preferences = _get_preferences(user_id)
        else:
            raise ValueError("Unsupported action")
        _send_json(handler, 200, {"ok": True, **preferences})
    except ValueError as exc:
        _send_json(handler, 401, {"ok": False, "error": str(exc)})
    except Exception:
        logger.exception("Could not process IBETIN Mini App preferences")
        _send_json(handler, 500, {"ok": False, "error": "Could not save preference"})


def _install_clean_runtime_ui() -> None:
    import bot_persistent as app

    app.core.TEXT["en"]["welcome"] = (
        "⚡ <b>IBETIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Your sports & entertainment command center.</b>\n\n"
        "Everything opens inside Telegram. Use the clean shortcuts below or open the full Mini App.\n\n"
        "🔞 18+ • Play responsibly • T&Cs apply"
    )
    app.core.TEXT["hi"]["welcome"] = (
        "⚡ <b>IBETIN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>आपका sports & entertainment command center.</b>\n\n"
        "सभी विकल्प Telegram के अंदर खुलते हैं। नीचे quick shortcuts चुनें या पूरा Mini App खोलें।\n\n"
        "🔞 18+ • जिम्मेदारी से खेलें • T&Cs लागू"
    )

    app.core.main_keyboard = clean_main_keyboard
    app.core.join_keyboard = clean_main_keyboard
    app.core.explore_keyboard = clean_main_keyboard

    def one_button(label: str, section: str = "home") -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[webapp_button(label, section)]])

    try:
        app.fantzo_autoreply._website_keyboard = lambda: one_button("⚡ OPEN IBETIN", "home")
        app.fantzo_autoreply._sports_keyboard = lambda: one_button("🏆 OPEN SPORTS", "sports")
        app.fantzo_autoreply._account_keyboard = lambda: one_button("⚡ OPEN IBETIN", "home")
        app.fantzo_autoreply._support_keyboard = lambda: one_button("🛟 OPEN SUPPORT", "support")
    except Exception:
        logger.exception("Could not simplify IBETIN assistant keyboards")

    try:
        app.fantzo_business._welcome_buttons = lambda: InlineKeyboardMarkup(
            [[webapp_button("⚡ OPEN IBETIN", "home")], [news_button("📰 SPORTS NEWS")]]
        )
        app.fantzo_business._fantzo_button = (
            lambda source, label="⚡ OPEN IBETIN": one_button(label, "home")
        )
    except Exception:
        logger.exception("Could not simplify IBETIN business keyboards")

    original_start = app.start

    async def clean_start(update, context) -> None:
        arg = context.args[0].lower() if context.args else ""
        if arg == "stopreminders":
            await original_start(update, context)
            return

        try:
            cleanup = await update.effective_message.reply_text(
                "Updating IBETIN…", reply_markup=ReplyKeyboardRemove()
            )
            await cleanup.delete()
        except Exception:
            pass
        await app.show_home(update, context)

    app.start = clean_start

    original_configure = app.configure_telegram_ui

    async def clean_configure_telegram_ui(application) -> None:
        await original_configure(application)
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Open IBETIN"),
                BotCommand("news", "Sports news"),
                BotCommand("live", "Live section"),
                BotCommand("alerts", "My match alerts"),
                BotCommand("support", "Support"),
            ]
        )
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Open IBETIN",
                web_app=WebAppInfo(url=hub_url("home")),
            )
        )

        async def alerts_command(update, context) -> None:
            message = update.effective_message
            if not message:
                return
            await message.reply_text(
                "🔔 <b>MY MATCH ALERTS</b>\n\nManage your Telegram sports notifications inside the IBETIN Mini App.",
                parse_mode="HTML",
                reply_markup=one_button("🔔 MANAGE ALERTS", "alerts"),
            )

        application.add_handler(CommandHandler("alerts", alerts_command))

    app.configure_telegram_ui = clean_configure_telegram_ui


def install_on_tracking_handler(analytics_module) -> None:
    handler_cls = analytics_module.TrackingHandler
    if getattr(handler_cls, "_ibetin_hub_installed", False):
        return

    previous_get = handler_cls.do_GET
    previous_post = getattr(handler_cls, "do_POST", None)

    def patched_get(self):
        parsed = urlparse(self.path)
        if parsed.path == HUB_PATH:
            section = parse_qs(parsed.query).get("section", ["home"])[0]
            section = section if section in ALLOWED_SECTIONS else "home"
            try:
                _send_html(self, 200, _page(section))
            except Exception:
                logger.exception("Could not render IBETIN Mini App")
                _send_html(self, 500, "<h3>IBETIN Mini App could not load.</h3>")
            return
        previous_get(self)

    def patched_post(self):
        parsed = urlparse(self.path)
        if parsed.path == PREFS_PATH:
            _handle_preferences_post(self)
            return
        if previous_post:
            previous_post(self)
            return
        self.send_response(404)
        self.end_headers()

    handler_cls.do_GET = patched_get
    handler_cls.do_POST = patched_post
    handler_cls._ibetin_hub_installed = True

    _install_clean_runtime_ui()
    logger.info("IBETIN premium Mini App installed at %s", HUB_PATH)
