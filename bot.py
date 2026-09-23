import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
HIGHLIGHTLY_API_KEY = os.getenv("HIGHLIGHTLY_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8992664481"))

HIGHLIGHTLY_API_BASE = "https://sports.highlightly.net"
APP_TIMEZONE = ZoneInfo("Asia/Dubai")

FANTZO_HOME = "https://fantzo.com"
FANTZO_LIVE = "https://fantzo.com/en/live"

DB_PATH = os.getenv("DB_PATH", "fantzo_bot.db")

DIVIDER = "━━━━━━━━━━━━━━━━━━"

TEXT = {
    "en": {
        "welcome": (
            "⚡ <b>FANTZO SPORTS HUB</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🏟 <b>Live action. Fast updates. One place.</b>\n\n"
            "🏏 Cricket scores & fixtures\n"
            "⚽ Football scores & fixtures\n"
            "🔥 Featured live action\n"
            "🔔 Match alerts\n\n"
            "🎯 Follow the game here — then explore more on <b>Fantzo</b>.\n\n"
            "Choose your next move 👇"
        ),
        "settings": (
            "⚙️ <b>FANTZO SETTINGS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Choose your language and notification preferences."
        ),
        "explore": (
            "✨ <b>EXPLORE FANTZO</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Ready to go beyond scores?\n\n"
            "🌐 Visit Fantzo\n"
            "🔴 Explore live action\n"
            "📝 Create your account"
        ),
        "join": (
            "🚀 <b>JOIN FANTZO</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Create your Fantzo account and explore the full experience.\n\n"
            "No exaggerated promises — just direct access to Fantzo."
        ),
        "lang_saved": "✅ Language changed to English.",
        "sub_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "You are subscribed to Fantzo sports alerts.\n"
            "We’ll keep the updates useful and relevant."
        ),
        "sub_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "You will no longer receive Fantzo sports alerts."
        ),
    },
    "hi": {
        "welcome": (
            "⚡ <b>FANTZO SPORTS HUB</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🏟 <b>लाइव एक्शन • तेज़ अपडेट • एक ही जगह</b>\n\n"
            "🏏 क्रिकेट स्कोर और फिक्स्चर\n"
            "⚽ फुटबॉल स्कोर और फिक्स्चर\n"
            "🔥 Featured live action\n"
            "🔔 Match alerts\n\n"
            "🎯 गेम को यहाँ follow करें और फिर <b>Fantzo</b> explore करें।\n\n"
            "अपना विकल्प चुनें 👇"
        ),
        "settings": (
            "⚙️ <b>FANTZO SETTINGS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "भाषा और notification preferences चुनें।"
        ),
        "explore": (
            "✨ <b>EXPLORE FANTZO</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Scores से आगे बढ़ना चाहते हैं?\n\n"
            "🌐 Fantzo खोलें\n"
            "🔴 Live section देखें\n"
            "📝 Account बनाएं"
        ),
        "join": (
            "🚀 <b>JOIN FANTZO</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Fantzo account बनाकर पूरा experience explore करें।"
        ),
        "lang_saved": "✅ भाषा हिंदी कर दी गई है।",
        "sub_on": (
            "🔔 <b>MATCH ALERTS ON</b>\n\n"
            "अब आपको Fantzo sports alerts मिलेंगे।"
        ),
        "sub_off": (
            "🔕 <b>MATCH ALERTS OFF</b>\n\n"
            "अब आपको Fantzo sports alerts नहीं मिलेंगे।"
        ),
    },
}


CRICKET_LIVE_STATES = {
    "in play",
    "stumps",
    "lunch",
    "innings break",
    "drinks",
    "timeout",
    "tea",
    "match delayed",
}
FOOTBALL_LIVE_STATES = {
    "first half",
    "second half",
    "extra time",
    "break time",
    "half time",
    "penalties",
    "interrupted",
}
FINISHED_STATES = {
    "finished",
    "finished after extra time",
    "finished after penalties",
    "finished after over time",
}
UPCOMING_STATES = {
    "scheduled",
    "not started",
    "to be announced",
}
TRANSIENT_STATUS_CODES = {502, 503, 504}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'en',
                subscribed INTEGER DEFAULT 0,
                created_at TEXT,
                last_seen TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                created_at TEXT
            )
            """
        )


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def touch_user(update: Update):
    user = update.effective_user
    if not user:
        return
    with db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_seen=excluded.last_seen
            """,
            (user.id, user.username, user.first_name, now_iso(), now_iso()),
        )


def track(user_id: int, action: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO clicks(user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action, now_iso()),
        )


def get_user_lang(user_id: int) -> str:
    with db() as conn:
        row = conn.execute(
            "SELECT language FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["language"] if row and row["language"] in TEXT else "en"


def is_subscribed(user_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT subscribed FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return bool(row["subscribed"]) if row else False


def set_subscription(user_id: int, value: bool):
    with db() as conn:
        conn.execute(
            "UPDATE users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
            (1 if value else 0, now_iso(), user_id),
        )


def set_language(user_id: int, lang: str):
    with db() as conn:
        conn.execute(
            "UPDATE users SET language = ?, last_seen = ? WHERE user_id = ?",
            (lang, now_iso(), user_id),
        )


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
                InlineKeyboardButton("🔥 Featured", callback_data="trending"),
            ],
            [
                InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
                InlineKeyboardButton("⚽ Football", callback_data="football"),
            ],
            [
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
                InlineKeyboardButton("✅ Results", callback_data="results"),
            ],
            [
                InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
                InlineKeyboardButton("🔔 Match Alerts", callback_data="subscribe"),
            ],
            [
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
                InlineKeyboardButton("🚀 Join Fantzo", callback_data="join_fantzo"),
            ],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        ]
    )


def back_keyboard(extra=None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append([InlineKeyboardButton("⬅️ Back to Home", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def explore_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✨ Open Fantzo", url=FANTZO_HOME)],
            [InlineKeyboardButton("🔴 Live Section", url=FANTZO_LIVE)],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✨ Visit Fantzo", url=FANTZO_HOME)],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
                InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def subscription_keyboard(current: bool) -> InlineKeyboardMarkup:
    label = "🔕 Turn Alerts OFF" if current else "🔔 Turn Alerts ON"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data="toggle_sub")],
            [InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def score_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=action),
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
            ],
            [
                InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
                InlineKeyboardButton("🚀 Join Fantzo", callback_data="join_fantzo"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def empty_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Check Again", callback_data=action),
                InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
            ],
            [
                InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
            ],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def promo_footer() -> str:
    return (
        f"\n\n{DIVIDER}\n"
        "⚡ <b>FANTZO</b> • Follow the action. Explore more."
    )


async def _highlightly_get_once(path: str, params=None):
    headers = {"x-rapidapi-key": HIGHLIGHTLY_API_KEY}
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{HIGHLIGHTLY_API_BASE}{path}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            logger.info("Highlightly requests remaining: %s", remaining)
        payload = response.json()
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


async def highlightly_get(path: str, params=None):
    if not HIGHLIGHTLY_API_KEY:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured")
    try:
        return await _highlightly_get_once(path, params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in TRANSIENT_STATUS_CODES:
            logger.warning(
                "Highlightly HTTP %s from %s; retrying once",
                exc.response.status_code,
                path,
            )
            await asyncio.sleep(1)
            return await _highlightly_get_once(path, params)
        raise
    except (httpx.ReadTimeout, httpx.ConnectTimeout):
        logger.warning("Highlightly timeout from %s; retrying once", path)
        await asyncio.sleep(1)
        return await _highlightly_get_once(path, params)


def _state_description(match) -> str:
    state = (match or {}).get("state") or {}
    if isinstance(state, dict):
        return str(state.get("description") or "").strip()
    return str(state or "").strip()


def _is_live(match, sport: str) -> bool:
    state = _state_description(match).casefold()
    states = CRICKET_LIVE_STATES if sport == "cricket" else FOOTBALL_LIVE_STATES
    return state in states


def _team_name(match, side: str) -> str:
    obj = (match or {}).get(f"{side}Team") or (match or {}).get(side) or {}
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("displayName") or side.title())
    return str(obj or side.title())


def _cricket_team_score(match, side: str):
    state = (match or {}).get("state") or {}
    teams = state.get("teams") if isinstance(state, dict) else None
    if isinstance(teams, dict):
        team_state = teams.get(side) or {}
        if isinstance(team_state, dict):
            score = team_state.get("score")
            info = team_state.get("info")
            if score and info:
                return f"{score} ({info})"
            if score:
                return str(score)
    return None


def _generic_score(match):
    state = (match or {}).get("state") or {}
    if not isinstance(state, dict):
        return None
    score = state.get("score")
    if isinstance(score, dict):
        current = score.get("current")
        if isinstance(current, dict):
            home = current.get("home")
            away = current.get("away")
            if home is not None or away is not None:
                return f"{home if home is not None else '-'} - {away if away is not None else '-'}"
        if current is not None:
            return str(current)
    elif score is not None:
        return str(score)
    return None


def _league_name(match) -> str:
    league_obj = (match or {}).get("league") or {}
    if isinstance(league_obj, dict):
        return str(league_obj.get("name") or "")
    return str(league_obj or "")


def highlightly_match_card(match, sport: str, index: int | None = None) -> str:
    home = escape(_team_name(match, "home"))
    away = escape(_team_name(match, "away"))
    state = (match or {}).get("state") or {}
    status = escape(_state_description(match) or "Live")
    league = escape(_league_name(match))
    icon = "🏏" if sport == "cricket" else "⚽"

    lines = []
    if index is not None:
        lines.append(f"{icon} <b>MATCH {index}</b>")

    if sport == "cricket":
        home_score = _cricket_team_score(match, "home")
        away_score = _cricket_team_score(match, "away")
        if home_score or away_score:
            lines.append(f"<b>{home}</b>  {escape(str(home_score or '-'))}")
            lines.append(f"<b>{away}</b>  {escape(str(away_score or '-'))}")
        else:
            lines.append(f"<b>{home}</b>  vs  <b>{away}</b>")
            combined = _generic_score(match)
            if combined:
                lines.append(f"📊 {escape(combined)}")
    else:
        combined = _generic_score(match)
        if combined:
            lines.append(f"<b>{home}</b>  {escape(combined)}  <b>{away}</b>")
        else:
            lines.append(f"<b>{home}</b>  vs  <b>{away}</b>")

    if league:
        lines.append(f"🏆 {league}")
    lines.append(f"⏱ {status}")

    if isinstance(state, dict):
        report = state.get("report")
        if report:
            lines.append(f"📣 {escape(str(report))}")

    return "\n".join(lines)


def _match_datetime(match):
    raw = (match or {}).get("startDate") or (match or {}).get("startTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def format_match_list(
    matches,
    title: str,
    sport: str,
    empty_text: str,
    promotional: bool = True,
) -> str:
    if not matches:
        text = (
            f"{title}\n"
            f"{DIVIDER}\n\n"
            "😴 <b>Nothing live here at the moment.</b>\n\n"
            f"{empty_text}\n\n"
            "Try upcoming fixtures, search a team, or explore Fantzo while you wait."
        )
        return text + (promo_footer() if promotional else "")

    lines = [title, DIVIDER, ""]
    for idx, match in enumerate(matches[:8], start=1):
        lines.append(highlightly_match_card(match, sport, idx))
        if idx != min(len(matches), 8):
            lines.append("")
            lines.append("· · ·")
            lines.append("")

    if len(matches) > 8:
        lines.append("")
        lines.append(f"➕ {len(matches) - 8} more matches available")

    if promotional:
        lines.append("")
        lines.append("🎯 <b>Enjoying the action?</b> Explore the full Fantzo experience.")
        lines.append(promo_footer())

    return "\n".join(lines).strip()


def format_featured(cricket_matches, football_matches) -> str:
    picks = []
    for match in cricket_matches[:3]:
        picks.append(("cricket", match))
    for match in football_matches[:3]:
        picks.append(("football", match))

    if not picks:
        return (
            "🔥 <b>FEATURED NOW</b>\n"
            f"{DIVIDER}\n\n"
            "No live featured matches right now.\n\n"
            "Check upcoming fixtures or explore Fantzo."
            + promo_footer()
        )

    lines = [
        "🔥 <b>FEATURED NOW</b>",
        DIVIDER,
        "",
        "<i>A quick selection from matches currently live.</i>",
        "",
    ]
    for idx, (sport, match) in enumerate(picks[:5], start=1):
        lines.append(highlightly_match_card(match, sport, idx))
        if idx != min(len(picks), 5):
            lines.extend(["", "· · ·", ""])

    lines.extend(
        [
            "",
            "✨ <b>More action is one tap away on Fantzo.</b>",
            promo_footer(),
        ]
    )
    return "\n".join(lines).strip()


async def get_sport_matches_for_date(sport: str, date_text: str):
    data = await highlightly_get(
        f"/{sport}/matches",
        {
            "date": date_text,
            "timezone": "Asia/Dubai",
            "limit": 100,
        },
    )
    return data if isinstance(data, list) else []


async def get_live_matches(sport: str):
    today = datetime.now(APP_TIMEZONE).date().isoformat()
    matches = await get_sport_matches_for_date(sport, today)
    return [m for m in matches if isinstance(m, dict) and _is_live(m, sport)]


async def search_teams(sport: str, name: str):
    data = await highlightly_get(
        f"/{sport}/teams",
        {"name": name, "limit": 5, "offset": 0},
    )
    if isinstance(data, list):
        return data[:5]
    return []


async def get_team(sport: str, team_id: str):
    data = await highlightly_get(f"/{sport}/teams/{team_id}")
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


async def get_team_matches(sport: str, team_id: str, recent: bool):
    home_call = highlightly_get(
        f"/{sport}/matches",
        {"homeTeamId": team_id, "timezone": "Asia/Dubai", "limit": 50, "offset": 0},
    )
    away_call = highlightly_get(
        f"/{sport}/matches",
        {"awayTeamId": team_id, "timezone": "Asia/Dubai", "limit": 50, "offset": 0},
    )
    home_data, away_data = await asyncio.gather(home_call, away_call)

    combined = []
    seen = set()
    for item in list(home_data or []) + list(away_data or []):
        if not isinstance(item, dict):
            continue
        match_id = str(item.get("id") or "")
        key = match_id or repr(
            (
                item.get("startDate"),
                _team_name(item, "home"),
                _team_name(item, "away"),
            )
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)

    now = datetime.now(timezone.utc)
    selected = []
    for match in combined:
        state = _state_description(match).casefold()
        dt = _match_datetime(match)
        if recent:
            if state in FINISHED_STATES or (
                dt and dt < now and state not in UPCOMING_STATES
            ):
                selected.append(match)
        else:
            if state in UPCOMING_STATES or (dt and dt >= now):
                selected.append(match)

    selected.sort(
        key=lambda m: _match_datetime(m) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=recent,
    )
    return selected[:10]


async def safe_api_message(query, coro, keyboard=None):
    try:
        text = await coro
    except RuntimeError:
        text = (
            "⚠️ <b>Sports data is not configured yet.</b>\n\n"
            "Please try again shortly."
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            text = "⚠️ Sports data authentication failed."
        elif code == 429:
            text = "⏳ Sports data limit reached. Please try again later."
        elif code == 400:
            text = "⚠️ Sports provider rejected this request. Please try again shortly."
        else:
            text = f"⚠️ Sports data provider returned HTTP {code}."
        logger.warning("Highlightly request failed with HTTP %s", code)
    except Exception as exc:
        logger.exception("Sports API error: %s", exc)
        text = "⚠️ Sports data is temporarily unavailable. Please try again shortly."

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard or back_keyboard(),
        disable_web_page_preview=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    lang = get_user_lang(update.effective_user.id)
    await update.effective_message.reply_text(
        TEXT[lang]["welcome"],
        parse_mode="HTML",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    await update.effective_message.reply_text(
        "⚡ <b>Fantzo Quick Guide</b>\n\n"
        "• /start — premium home menu\n"
        "• /team TEAMNAME — find cricket or football teams\n"
        "• /sports — check sports coverage\n\n"
        "Use the buttons for the fastest experience.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def sports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    api_state = "✅ Connected" if HIGHLIGHTLY_API_KEY else "❌ Missing API key"
    text = (
        "🏟 <b>FANTZO SPORTS COVERAGE</b>\n"
        f"{DIVIDER}\n\n"
        "🏏 Cricket — live scores, teams and fixtures\n"
        "⚽ Football — live scores, teams and fixtures\n\n"
        f"Data connection: <b>{api_state}</b>\n\n"
        "✨ Explore Fantzo for more."
    )
    await update.effective_message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    q = " ".join(context.args).strip()
    if not q:
        await update.effective_message.reply_text(
            "🔎 <b>Find a Team</b>\n\n"
            "Usage: <code>/team India</code>\n"
            "Example: <code>/team Arsenal</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    try:
        cricket_results, football_results = await asyncio.gather(
            search_teams("cricket", q),
            search_teams("football", q),
            return_exceptions=True,
        )

        rows = []
        if not isinstance(cricket_results, Exception):
            for team in cricket_results[:3]:
                tid = team.get("id")
                if tid is None:
                    continue
                name = str(team.get("name") or "Team")[:38]
                rows.append(
                    [
                        InlineKeyboardButton(
                            f"🏏 {name}",
                            callback_data=f"team:cricket:{tid}",
                        )
                    ]
                )

        if not isinstance(football_results, Exception):
            for team in football_results[:3]:
                tid = team.get("id")
                if tid is None:
                    continue
                name = str(team.get("name") or "Team")[:38]
                rows.append(
                    [
                        InlineKeyboardButton(
                            f"⚽ {name}",
                            callback_data=f"team:football:{tid}",
                        )
                    ]
                )

        if not rows:
            await update.effective_message.reply_text(
                "😕 <b>No team found.</b>\n\nTry another spelling.",
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
            return

        rows.append(
            [
                InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore"),
                InlineKeyboardButton("🚀 Join Fantzo", callback_data="join_fantzo"),
            ]
        )

        await update.effective_message.reply_text(
            f"🔎 <b>SEARCH RESULTS</b>\n"
            f"{DIVIDER}\n\n"
            f"Looking for: <b>{escape(q)}</b>\n\n"
            "Choose a team 👇",
            parse_mode="HTML",
            reply_markup=back_keyboard(rows),
        )
    except Exception as exc:
        logger.exception("Team search failed: %s", exc)
        await update.effective_message.reply_text(
            "⚠️ Team search is temporarily unavailable.",
            reply_markup=main_keyboard(),
        )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return

    with db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        subs = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE subscribed = 1"
        ).fetchone()["c"]
        clicks = conn.execute("SELECT COUNT(*) c FROM clicks").fetchone()["c"]
        top = conn.execute(
            "SELECT action, COUNT(*) c FROM clicks "
            "GROUP BY action ORDER BY c DESC LIMIT 8"
        ).fetchall()

    top_text = (
        "\n".join(f"• {escape(r['action'])}: {r['c']}" for r in top)
        or "No activity yet."
    )
    api_state = "✅ configured" if HIGHLIGHTLY_API_KEY else "❌ missing"
    await update.effective_message.reply_text(
        "🛠 <b>FANTZO ADMIN</b>\n"
        f"{DIVIDER}\n\n"
        f"👥 Users: <b>{total}</b>\n"
        f"🔔 Subscribers: <b>{subs}</b>\n"
        f"📊 Button actions: <b>{clicks}</b>\n"
        f"🏟 Highlightly API: <b>{api_state}</b>\n\n"
        f"<b>Top actions</b>\n{top_text}\n\n"
        "Broadcast: <code>/broadcast your message</code>",
        parse_mode="HTML",
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return

    message = " ".join(context.args).strip()
    if not message:
        await update.effective_message.reply_text("Usage: /broadcast your message")
        return

    with db() as conn:
        users = conn.execute(
            "SELECT user_id FROM users WHERE subscribed = 1"
        ).fetchall()

    sent = failed = 0
    for row in users:
        try:
            await context.bot.send_message(
                chat_id=row["user_id"],
                text=message,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✨ Explore Fantzo", url=FANTZO_HOME)]]
                ),
            )
            sent += 1
        except Exception:
            failed += 1

    await update.effective_message.reply_text(
        f"Broadcast complete.\nSent: {sent}\nFailed: {failed}"
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    touch_user(update)

    user_id = update.effective_user.id
    action = query.data
    track(user_id, action)
    lang = get_user_lang(user_id)

    if action == "back":
        await query.edit_message_text(
            TEXT[lang]["welcome"],
            parse_mode="HTML",
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if action == "explore":
        await query.edit_message_text(
            TEXT[lang]["explore"],
            parse_mode="HTML",
            reply_markup=explore_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if action == "join_fantzo":
        await query.edit_message_text(
            TEXT[lang]["join"],
            parse_mode="HTML",
            reply_markup=join_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if action == "live_now":
        async def load_all():
            cricket_result, football_result = await asyncio.gather(
                get_live_matches("cricket"),
                get_live_matches("football"),
                return_exceptions=True,
            )
            if isinstance(cricket_result, Exception) and isinstance(
                football_result, Exception
            ):
                raise cricket_result

            sections = ["🔴 <b>LIVE NOW</b>", DIVIDER, ""]
            total_live = 0

            if not isinstance(cricket_result, Exception):
                total_live += len(cricket_result)
                sections.append(
                    format_match_list(
                        cricket_result,
                        "🏏 <b>CRICKET</b>",
                        "cricket",
                        "No live cricket matches right now.",
                        promotional=False,
                    )
                )
            else:
                sections.append("🏏 <b>CRICKET</b>\n\nTemporarily unavailable.")

            sections.extend(["", DIVIDER, ""])

            if not isinstance(football_result, Exception):
                total_live += len(football_result)
                sections.append(
                    format_match_list(
                        football_result,
                        "⚽ <b>FOOTBALL</b>",
                        "football",
                        "No live football matches right now.",
                        promotional=False,
                    )
                )
            else:
                sections.append("⚽ <b>FOOTBALL</b>\n\nTemporarily unavailable.")

            sections.extend(
                [
                    "",
                    f"📡 Live matches found: <b>{total_live}</b>",
                    "🎯 Follow the scores here, then explore more on Fantzo.",
                    promo_footer(),
                ]
            )
            return "\n".join(sections).strip()

        await safe_api_message(query, load_all(), score_keyboard("live_now"))
        return

    if action == "trending":
        async def load_featured():
            cricket_result, football_result = await asyncio.gather(
                get_live_matches("cricket"),
                get_live_matches("football"),
                return_exceptions=True,
            )
            cricket_matches = (
                [] if isinstance(cricket_result, Exception) else cricket_result
            )
            football_matches = (
                [] if isinstance(football_result, Exception) else football_result
            )
            if isinstance(cricket_result, Exception) and isinstance(
                football_result, Exception
            ):
                raise cricket_result
            return format_featured(cricket_matches, football_matches)

        await safe_api_message(query, load_featured(), score_keyboard("trending"))
        return

    if action in ("cricket", "football"):
        sport = action
        icon = "🏏" if sport == "cricket" else "⚽"

        async def load_sport():
            matches = await get_live_matches(sport)
            return format_match_list(
                matches,
                f"{icon} <b>{sport.upper()} LIVE</b>",
                sport,
                f"No live {sport} matches right now.",
            )

        await safe_api_message(query, load_sport(), score_keyboard(action))
        return

    if action == "find_team":
        await query.edit_message_text(
            "🔎 <b>FIND YOUR TEAM</b>\n"
            f"{DIVIDER}\n\n"
            "Type a command like:\n\n"
            "<code>/team India</code>\n"
            "<code>/team Arsenal</code>\n\n"
            "Then choose the team to see upcoming or recent matches.\n\n"
            "✨ You can explore Fantzo anytime from the menu.",
            parse_mode="HTML",
            reply_markup=back_keyboard(
                [[InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore")]]
            ),
        )
        return

    if action in ("upcoming", "results"):
        word = "upcoming" if action == "upcoming" else "recent"
        heading = "UPCOMING MATCHES" if action == "upcoming" else "LATEST RESULTS"
        icon = "🗓" if action == "upcoming" else "✅"
        await query.edit_message_text(
            f"{icon} <b>{heading}</b>\n"
            f"{DIVIDER}\n\n"
            f"Search a team with <code>/team TEAMNAME</code>, choose it, then tap <b>{word.title()}</b>.\n\n"
            "Example: <code>/team India</code>\n\n"
            "🎯 Follow the action and keep Fantzo one tap away.",
            parse_mode="HTML",
            reply_markup=back_keyboard(
                [
                    [InlineKeyboardButton("🔎 Find Team", callback_data="find_team")],
                    [
                        InlineKeyboardButton(
                            "✨ Explore Fantzo", callback_data="explore"
                        ),
                        InlineKeyboardButton(
                            "🚀 Join Fantzo", callback_data="join_fantzo"
                        ),
                    ],
                ]
            ),
        )
        return

    if action.startswith("team:"):
        parts = action.split(":", 2)
        if len(parts) != 3:
            await query.edit_message_text(
                "Please search for the team again using /team TEAMNAME.",
                reply_markup=back_keyboard(),
            )
            return

        _, sport, team_id = parts
        icon = "🏏" if sport == "cricket" else "⚽"
        try:
            team = await get_team(sport, team_id)
            name = escape(str(team.get("name") or "Team"))
        except Exception:
            name = "Team"

        await query.edit_message_text(
            f"{icon} <b>{name}</b>\n"
            f"{DIVIDER}\n\n"
            "What would you like to check?",
            parse_mode="HTML",
            reply_markup=back_keyboard(
                [
                    [
                        InlineKeyboardButton(
                            "🗓 Upcoming",
                            callback_data=f"team_up:{sport}:{team_id}",
                        ),
                        InlineKeyboardButton(
                            "✅ Recent",
                            callback_data=f"team_recent:{sport}:{team_id}",
                        ),
                    ],
                    [InlineKeyboardButton("✨ Explore Fantzo", callback_data="explore")],
                ]
            ),
        )
        return

    if action.startswith("team_up:") or action.startswith("team_recent:"):
        recent = action.startswith("team_recent:")
        parts = action.split(":", 2)
        if len(parts) != 3:
            await query.edit_message_text(
                "Please search for the team again using /team TEAMNAME.",
                reply_markup=back_keyboard(),
            )
            return

        _, sport, team_id = parts
        icon = "🏏" if sport == "cricket" else "⚽"

        async def load_team_fixtures():
            fixtures = await get_team_matches(sport, team_id, recent)
            title = (
                f"{icon} ✅ <b>RECENT MATCHES</b>"
                if recent
                else f"{icon} 🗓 <b>UPCOMING MATCHES</b>"
            )
            return format_match_list(
                fixtures,
                title,
                sport,
                "No matches found.",
            )

        await safe_api_message(query, load_team_fixtures(), score_keyboard(action))
        return

    if action == "settings":
        await query.edit_message_text(
            TEXT[lang]["settings"],
            parse_mode="HTML",
            reply_markup=settings_keyboard(),
        )
        return

    if action in ("lang_en", "lang_hi"):
        new_lang = "en" if action == "lang_en" else "hi"
        set_language(user_id, new_lang)
        await query.edit_message_text(
            TEXT[new_lang]["lang_saved"],
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if action == "subscribe":
        current = is_subscribed(user_id)
        await query.edit_message_text(
            TEXT[lang]["sub_on"] if current else TEXT[lang]["sub_off"],
            parse_mode="HTML",
            reply_markup=subscription_keyboard(current),
        )
        return

    if action == "toggle_sub":
        new_value = not is_subscribed(user_id)
        set_subscription(user_id, new_value)
        await query.edit_message_text(
            TEXT[lang]["sub_on"] if new_value else TEXT[lang]["sub_off"],
            parse_mode="HTML",
            reply_markup=subscription_keyboard(new_value),
        )
        return

    await query.edit_message_text(
        "⚡ Fantzo Sports Hub",
        reply_markup=back_keyboard(),
    )


def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("sports", sports_command))
    app.add_handler(CommandHandler("team", team_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(callback_router))

    logger.info("Starting Fantzo Premium Sports Hub with Highlightly")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
