import asyncio
import os
import sqlite3
import logging
from datetime import datetime, timezone
from html import escape

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
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8992664481"))
SPORTS_API_BASE = "https://api.sportsapi.app"

FANTZO_HOME = "https://fantzo.com"
FANTZO_LIVE = "https://fantzo.com/en/live"
FANTZO_SLOTS = "https://fantzo.com/en/slots"
FANTZO_REGISTER = "https://fantzo.com/en/registration"

DB_PATH = os.getenv("DB_PATH", "fantzo_bot.db")

TEXT = {
    "en": {
        "welcome": (
            "⚡ <b>Welcome to Fantzo Sports Updates</b>\n\n"
            "Live scores • Fixtures • Results • Sports news\n"
            "Fast updates for cricket, football and more.\n\n"
            "Choose what you want below 👇"
        ),
        "settings": "⚙️ <b>Settings</b>\n\nChoose your language and notification preferences.",
        "explore": "🌐 <b>Explore Fantzo</b>\n\nOpen any Fantzo destination below.",
        "lang_saved": "✅ Language changed to English.",
        "sub_on": "🔔 <b>Updates ON</b>\n\nYou are subscribed to Fantzo sports alerts.",
        "sub_off": "🔕 <b>Updates OFF</b>\n\nYou will no longer receive Fantzo sports alerts.",
    },
    "hi": {
        "welcome": (
            "⚡ <b>Fantzo Sports Updates में आपका स्वागत है</b>\n\n"
            "लाइव स्कोर • फिक्स्चर • रिज़ल्ट • स्पोर्ट्स न्यूज़\n"
            "क्रिकेट, फुटबॉल और अन्य खेलों के तेज़ अपडेट।\n\n"
            "नीचे अपना विकल्प चुनें 👇"
        ),
        "settings": "⚙️ <b>Settings</b>\n\nभाषा और notification preferences चुनें।",
        "explore": "🌐 <b>Explore Fantzo</b>\n\nनीचे से Fantzo destination खोलें।",
        "lang_saved": "✅ भाषा हिंदी कर दी गई है।",
        "sub_on": "🔔 <b>Updates ON</b>\n\nआप Fantzo sports alerts के लिए subscribe हैं।",
        "sub_off": "🔕 <b>Updates OFF</b>\n\nआपको Fantzo sports alerts नहीं मिलेंगे।",
    },
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'en',
                subscribed INTEGER DEFAULT 0,
                created_at TEXT,
                last_seen TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                created_at TEXT
            )
        """)


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
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔴 Live Now", callback_data="live_now"),
            InlineKeyboardButton("🏏 Cricket", callback_data="cricket"),
        ],
        [
            InlineKeyboardButton("⚽ Football", callback_data="football"),
            InlineKeyboardButton("🔎 Find Team", callback_data="find_team"),
        ],
        [
            InlineKeyboardButton("🗓 Upcoming", callback_data="upcoming"),
            InlineKeyboardButton("✅ Results", callback_data="results"),
        ],
        [
            InlineKeyboardButton("🔔 Subscribe", callback_data="subscribe"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
        ],
        [InlineKeyboardButton("🌐 Explore Fantzo", callback_data="explore")],
    ])


def back_keyboard(extra=None) -> InlineKeyboardMarkup:
    rows = extra or []
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def explore_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Fantzo Home", url=FANTZO_HOME)],
        [
            InlineKeyboardButton("🔴 Live", url=FANTZO_LIVE),
            InlineKeyboardButton("📝 Register", url=FANTZO_REGISTER),
        ],
        [InlineKeyboardButton("🎰 Slots", url=FANTZO_SLOTS)],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ])


def subscription_keyboard(current: bool) -> InlineKeyboardMarkup:
    label = "🔕 Turn OFF" if current else "🔔 Turn ON"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data="toggle_sub")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ])


TRANSIENT_STATUS_CODES = (502, 503, 504)


async def _api_get_once(path: str, params=None):
    headers = {"Authorization": f"Bearer {SPORTS_API_KEY}"}
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(f"{SPORTS_API_BASE}{path}", headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload)


async def api_get(path: str, params=None):
    if not SPORTS_API_KEY:
        raise RuntimeError("SPORTS_API_KEY is not configured")
    try:
        return await _api_get_once(path, params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in TRANSIENT_STATUS_CODES:
            logger.info(
                "Transient HTTP %s from %s, retrying once after backoff",
                exc.response.status_code,
                path,
            )
            await asyncio.sleep(1)
            return await _api_get_once(path, params)
        raise
    except httpx.ReadTimeout:
        logger.info("Read timeout from %s, retrying once after backoff", path)
        await asyncio.sleep(1)
        return await _api_get_once(path, params)


def get_match_sport(match):
    sport = (match or {}).get("sport")
    if isinstance(sport, str):
        return sport
    if isinstance(sport, dict):
        return sport.get("name") or sport.get("slug")
    return None


def score_value(score):
    if isinstance(score, dict):
        value = score.get("current")
        return "-" if value is None else str(value)
    return "-" if score is None else str(score)


def fixture_line(match):
    home = escape(str((match.get("home") or {}).get("name") or "Home"))
    away = escape(str((match.get("away") or {}).get("name") or "Away"))
    hs = score_value(match.get("homeScore"))
    aws = score_value(match.get("awayScore"))
    league = (match.get("league") or {}).get("name")
    status = match.get("status") or {}
    status_text = status.get("description") or status.get("type") or "live"
    extra = f"\n<small>{escape(str(league))}</small>" if league else ""
    return f"<b>{home} {hs} – {aws} {away}</b>\n{escape(str(status_text))}{extra}"


def format_live(matches, title):
    if not matches:
        return f"{title}\n\nNo live matches right now."
    lines = [title, ""]
    for match in matches[:12]:
        lines.append(fixture_line(match))
        lines.append("")
    if len(matches) > 12:
        lines.append(f"+ {len(matches) - 12} more live matches")
    return "\n".join(lines).strip()


def format_fixture_list(fixtures, title):
    if not fixtures:
        return f"{title}\n\nNo matches found."
    lines = [title, ""]
    for match in fixtures[:10]:
        home = escape(str((match.get("home") or {}).get("name") or "Home"))
        away = escape(str((match.get("away") or {}).get("name") or "Away"))
        start = match.get("startTime") or ""
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            start = dt.strftime("%d %b %Y, %H:%M UTC")
        except Exception:
            pass
        hs = score_value(match.get("homeScore"))
        aws = score_value(match.get("awayScore"))
        lines.append(f"<b>{home} {hs} – {aws} {away}</b>")
        if start:
            lines.append(escape(str(start)))
        lines.append("")
    return "\n".join(lines).strip()


async def safe_api_message(query, coro, keyboard=None):
    try:
        text = await coro
    except RuntimeError:
        text = "⚠️ Sports API key is not configured yet."
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 401:
            text = "⚠️ Sports API authentication failed. Please check the API key."
        elif code == 429:
            text = "⏳ Sports API request limit reached. Please try again later."
        else:
            text = f"⚠️ Sports data provider returned HTTP {code}."
    except Exception as exc:
        logger.exception("Sports API error: %s", exc)
        text = "⚠️ Sports data is temporarily unavailable. Please try again shortly."
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard or back_keyboard())


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
        "Use /start for the main menu.\n"
        "Use /team TEAMNAME to find a team and view upcoming/recent matches.\n"
        "Use /sports to check the data provider's supported sports.",
        reply_markup=main_keyboard(),
    )


async def sports_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    try:
        sports = await api_get("/v2/sports")
        rows = []
        for sport in sports[:20]:
            name = sport.get("name") or sport.get("slug") or "sport"
            live = sport.get("live", 0)
            rows.append(f"• {escape(str(name)).title()}: {live} live")
        text = "🏟 <b>Sports coverage</b>\n\n" + "\n".join(rows)
    except Exception:
        text = "⚠️ Could not load sports coverage right now."
    await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard())


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    q = " ".join(context.args).strip()
    if not q:
        await update.effective_message.reply_text("Usage: /team India\nExample: /team Arsenal")
        return
    try:
        results = await api_get("/v2/search", {"q": q})
        teams = [r for r in results if r.get("type") == "team"][:5]
        if not teams:
            await update.effective_message.reply_text("No team found. Try another spelling.")
            return
        rows = []
        for team in teams:
            tid = team.get("id")
            name = str(team.get("name") or "Team")[:40]
            rows.append([InlineKeyboardButton(f"🏟 {name}", callback_data=f"team:{tid}")])
        await update.effective_message.reply_text(
            f"🔎 <b>Team search:</b> {escape(q)}",
            parse_mode="HTML",
            reply_markup=back_keyboard(rows),
        )
    except Exception as exc:
        logger.exception("Team search failed: %s", exc)
        await update.effective_message.reply_text("⚠️ Team search is temporarily unavailable.")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    touch_user(update)
    if update.effective_user.id != ADMIN_USER_ID:
        await update.effective_message.reply_text("This command is restricted.")
        return
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        subs = conn.execute("SELECT COUNT(*) c FROM users WHERE subscribed = 1").fetchone()["c"]
        clicks = conn.execute("SELECT COUNT(*) c FROM clicks").fetchone()["c"]
        top = conn.execute(
            "SELECT action, COUNT(*) c FROM clicks GROUP BY action ORDER BY c DESC LIMIT 5"
        ).fetchall()
    top_text = "\n".join(f"• {escape(r['action'])}: {r['c']}" for r in top) or "No activity yet."
    api_state = "✅ configured" if SPORTS_API_KEY else "❌ missing"
    await update.effective_message.reply_text(
        "🛠 <b>Fantzo Admin</b>\n\n"
        f"👥 Users: <b>{total}</b>\n"
        f"🔔 Subscribers: <b>{subs}</b>\n"
        f"📊 Button actions: <b>{clicks}</b>\n"
        f"🏟 Sports API: <b>{api_state}</b>\n\n"
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
        users = conn.execute("SELECT user_id FROM users WHERE subscribed = 1").fetchall()
    sent = failed = 0
    for row in users:
        try:
            await context.bot.send_message(chat_id=row["user_id"], text=message)
            sent += 1
        except Exception:
            failed += 1
    await update.effective_message.reply_text(f"Broadcast complete.\nSent: {sent}\nFailed: {failed}")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    touch_user(update)
    user_id = update.effective_user.id
    action = query.data
    track(user_id, action)
    lang = get_user_lang(user_id)

    if action == "back":
        await query.edit_message_text(TEXT[lang]["welcome"], parse_mode="HTML", reply_markup=main_keyboard())
        return

    if action == "live_now":
        async def load_all():
            matches = await api_get("/v2/livescores")
            return format_live(matches, "🔴 <b>Live Now</b>")
        await safe_api_message(query, load_all())
        return

    if action in ("cricket", "football"):
        sport = action
        icon = "🏏" if sport == "cricket" else "⚽"
        async def load_sport():
            try:
                matches = await api_get("/v2/livescores", {"sport": sport})
            except (httpx.HTTPStatusError, httpx.ReadTimeout) as exc:
                is_transient_status = (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code in TRANSIENT_STATUS_CODES
                )
                is_timeout = isinstance(exc, httpx.ReadTimeout)
                if not (is_transient_status or is_timeout):
                    raise
                logger.info(
                    "Filtered livescores call failed for sport=%s, falling back to unfiltered livescores",
                    sport,
                )
                all_matches = await api_get("/v2/livescores")
                matches = [m for m in all_matches if get_match_sport(m) == sport]
            return format_live(matches, f"{icon} <b>{sport.title()} Live</b>")
        await safe_api_message(query, load_sport(), back_keyboard([
            [InlineKeyboardButton("🔄 Refresh", callback_data=action)],
            [InlineKeyboardButton("🔎 Find Team", callback_data="find_team")],
        ]))
        return

    if action == "find_team":
        await query.edit_message_text(
            "🔎 <b>Find a team</b>\n\nSend a command like:\n<code>/team India</code>\n<code>/team Arsenal</code>\n\nThen choose the team to see upcoming or recent matches.",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if action in ("upcoming", "results"):
        word = "upcoming" if action == "upcoming" else "recent"
        await query.edit_message_text(
            f"🗓 <b>{'Upcoming Matches' if action == 'upcoming' else 'Latest Results'}</b>\n\n"
            f"Use <code>/team TEAMNAME</code>, choose a team, then tap <b>{word.title()}</b>.\n\n"
            "Example: <code>/team India</code>",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if action.startswith("team:"):
        team_id = action.split(":", 1)[1]
        try:
            team = await api_get(f"/v2/teams/{team_id}")
            name = escape(str(team.get("name") or "Team"))
        except Exception:
            name = "Team"
        await query.edit_message_text(
            f"🏟 <b>{name}</b>\n\nChoose match history:",
            parse_mode="HTML",
            reply_markup=back_keyboard([
                [
                    InlineKeyboardButton("🗓 Upcoming", callback_data=f"team_up:{team_id}"),
                    InlineKeyboardButton("✅ Recent", callback_data=f"team_recent:{team_id}"),
                ]
            ]),
        )
        return

    if action.startswith("team_up:") or action.startswith("team_recent:"):
        recent = action.startswith("team_recent:")
        team_id = action.split(":", 1)[1]
        kind = "recent" if recent else "upcoming"
        async def load_team_fixtures():
            fixtures = await api_get(f"/v2/teams/{team_id}/fixtures", {"type": kind, "page": 0})
            title = "✅ <b>Recent Matches</b>" if recent else "🗓 <b>Upcoming Matches</b>"
            return format_fixture_list(fixtures, title)
        await safe_api_message(query, load_team_fixtures(), back_keyboard([
            [InlineKeyboardButton("🔄 Refresh", callback_data=action)]
        ]))
        return

    if action == "explore":
        await query.edit_message_text(TEXT[lang]["explore"], parse_mode="HTML", reply_markup=explore_keyboard(), disable_web_page_preview=True)
        return

    if action == "settings":
        await query.edit_message_text(TEXT[lang]["settings"], parse_mode="HTML", reply_markup=settings_keyboard())
        return

    if action in ("lang_en", "lang_hi"):
        new_lang = "en" if action == "lang_en" else "hi"
        set_language(user_id, new_lang)
        await query.edit_message_text(TEXT[new_lang]["lang_saved"], parse_mode="HTML", reply_markup=back_keyboard())
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

    await query.edit_message_text("Fantzo Sports Updates", reply_markup=back_keyboard())


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
    logger.info("Starting Fantzo Sports Updates bot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
