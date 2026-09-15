import logging
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import bot_tracked as tracked
import fantzo_growth as growth

logger = logging.getLogger(__name__)
_installed = False
MAX_HOME_FAVOURITES = 3
MAX_SCREEN_FAVOURITES = 8


def _parse_favourite(value: str):
    parts = str(value or "").split(":", 2)
    if len(parts) != 3:
        return None
    sport, team_id, team_name = parts
    sport = sport.strip().lower()
    team_id = team_id.strip()
    team_name = team_name.strip()
    if sport not in {"cricket", "football"} or not team_id or not team_name:
        return None
    return {
        "sport": sport,
        "team_id": team_id,
        "team_name": team_name,
        "icon": "🏏" if sport == "cricket" else "⚽",
    }


def get_favourites(user_id: int, limit: int = MAX_SCREEN_FAVOURITES):
    growth.ensure_tables()
    with tracked.app.core.db() as conn:
        rows = conn.execute(
            """
            SELECT value, alerts_enabled
            FROM user_favourites
            WHERE user_id = ? AND kind = 'team'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(user_id), int(limit)),
        ).fetchall()

    items = []
    for row in rows:
        parsed = _parse_favourite(row["value"])
        if not parsed:
            continue
        parsed["alerts_enabled"] = bool(row["alerts_enabled"])
        items.append(parsed)
    return items


def remove_favourite(user_id: int, sport: str, team_id: str) -> bool:
    growth.ensure_tables()
    prefix = f"{sport}:{team_id}:"
    with tracked.app.core.db() as conn:
        cur = conn.execute(
            """
            DELETE FROM user_favourites
            WHERE user_id = ? AND kind = 'team' AND value LIKE ?
            """,
            (int(user_id), prefix + "%"),
        )
        removed = int(cur.rowcount or 0) > 0
    if removed:
        try:
            growth.track(user_id, "unfavourite_team", prefix.rstrip(":"))
        except Exception:
            logger.exception("Could not track Fantzo unfavourite")
    return removed


def _short_name(name: str, size: int = 24) -> str:
    name = str(name or "Team").strip()
    return name if len(name) <= size else name[: size - 1] + "…"


def personalized_home_keyboard(user_id: int) -> InlineKeyboardMarkup:
    favourites = get_favourites(user_id, MAX_HOME_FAVOURITES)
    base_rows = [list(row) for row in tracked.premium_main_keyboard().inline_keyboard]

    rows = [[InlineKeyboardButton(
        f"⭐ MY FANTZO{f' · {len(favourites)} TEAM' if len(favourites) == 1 else (f' · {len(favourites)} TEAMS' if favourites else '')}",
        callback_data="my_fantzo",
    )]]

    for item in favourites:
        rows.append([
            InlineKeyboardButton(
                f"{item['icon']} {_short_name(item['team_name'])}",
                callback_data=f"myteam:{item['sport']}:{item['team_id']}",
            )
        ])

    rows.extend(base_rows)
    return InlineKeyboardMarkup(rows)


def personalized_home_text(user_id: int, lang: str) -> str:
    text = tracked.app.core.TEXT[lang]["welcome"]
    favourites = get_favourites(user_id, MAX_HOME_FAVOURITES)
    if favourites:
        names = " · ".join(
            f"{item['icon']} {escape(_short_name(item['team_name'], 20))}"
            for item in favourites
        )
        return text + f"\n\n⭐ <b>Your teams</b>\n{names}"
    return text + "\n\n⭐ Follow a team once and Fantzo will personalise this screen for you."


async def personalized_show_home(update, context) -> None:
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return

    tracked.app.core.touch_user(update)
    lang = tracked.app.core.get_user_lang(user.id)
    text = personalized_home_text(user.id, lang)
    keyboard = personalized_home_keyboard(user.id)
    banner_file_id = tracked.app.get_banner_file_id()

    if banner_file_id:
        try:
            await message.reply_photo(
                photo=banner_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception as exc:
            logger.warning("Personalized Fantzo banner send failed; using text: %s", exc)

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


def _my_fantzo_keyboard(user_id: int) -> InlineKeyboardMarkup:
    favourites = get_favourites(user_id)
    rows = []
    for item in favourites:
        rows.append([
            InlineKeyboardButton(
                f"{item['icon']} {_short_name(item['team_name'], 22)}",
                callback_data=f"myteam:{item['sport']}:{item['team_id']}",
            ),
            InlineKeyboardButton(
                "✕",
                callback_data=f"unfav:{item['sport']}:{item['team_id']}",
            ),
        ])

    rows.extend([
        [InlineKeyboardButton("🔎 FIND ANOTHER TEAM", callback_data="find_team")],
        [InlineKeyboardButton("🔔 MATCH ALERTS", callback_data="subscribe")],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])
    return InlineKeyboardMarkup(rows)


def _my_fantzo_text(user_id: int) -> str:
    favourites = get_favourites(user_id)
    alerts_on = tracked.app.core.is_subscribed(user_id)
    if not favourites:
        return (
            "⭐ <b>MY FANTZO</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "You are not following a team yet.\n\n"
            "Search for a team, open it, and tap <b>FOLLOW TEAM + ALERTS</b>. "
            "Your teams will then appear at the top of your Fantzo home screen.\n\n"
            f"🔔 Match alerts: <b>{'ON' if alerts_on else 'OFF'}</b>"
        )

    lines = [
        "⭐ <b>MY FANTZO</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"Following <b>{len(favourites)}</b> team{'s' if len(favourites) != 1 else ''}",
        f"🔔 Match alerts: <b>{'ON' if alerts_on else 'OFF'}</b>",
        "",
    ]
    for item in favourites:
        lines.append(f"{item['icon']} {escape(item['team_name'])}")
    lines.extend(["", "Tap a team for upcoming and recent matches. Use ✕ to remove it."])
    return "\n".join(lines)


async def _replace_screen(query, context, text: str, keyboard: InlineKeyboardMarkup) -> None:
    # If the current message is the home banner, replace it with a normal text
    # message so every existing callback continues to work exactly as before.
    if query.message and (query.message.photo or query.message.document or query.message.video):
        chat_id = query.message.chat_id
        try:
            await query.message.delete()
        except Exception:
            logger.exception("Could not remove Fantzo media message during personalization navigation")
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        return

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def _show_my_fantzo(update, context) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    await query.answer()
    tracked.app.core.touch_user(update)
    growth.track(user.id, "engagement", "my_fantzo")
    await _replace_screen(query, context, _my_fantzo_text(user.id), _my_fantzo_keyboard(user.id))


async def _show_my_team(update, context, sport: str, team_id: str) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    favourite = next(
        (x for x in get_favourites(user.id) if x["sport"] == sport and x["team_id"] == team_id),
        None,
    )
    if not favourite:
        await query.answer("That team is no longer in My Fantzo.", show_alert=True)
        await _replace_screen(query, context, _my_fantzo_text(user.id), _my_fantzo_keyboard(user.id))
        return

    await query.answer()
    growth.track(user.id, "engagement", f"my_team:{sport}:{team_id}")
    text = (
        f"{favourite['icon']} <b>{escape(favourite['team_name'])}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Your followed team. What would you like to check?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗓 Upcoming", callback_data=f"team_up:{sport}:{team_id}"),
            InlineKeyboardButton("✅ Recent", callback_data=f"team_recent:{sport}:{team_id}"),
        ],
        [InlineKeyboardButton("⭐ MY FANTZO", callback_data="my_fantzo")],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])
    await _replace_screen(query, context, text, keyboard)


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    growth.ensure_tables()
    original_router = tracked.app.core.callback_router
    tracked.app.show_home = personalized_show_home

    async def personalization_router(update, context):
        query = update.callback_query
        user = update.effective_user
        action = query.data if query else ""

        if query and user and action == "my_fantzo":
            await _show_my_fantzo(update, context)
            return

        if query and user and action.startswith("myteam:"):
            parts = action.split(":", 2)
            if len(parts) == 3:
                await _show_my_team(update, context, parts[1], parts[2])
                return

        if query and user and action.startswith("unfav:"):
            parts = action.split(":", 2)
            if len(parts) == 3:
                removed = remove_favourite(user.id, parts[1], parts[2])
                await query.answer("Removed from My Fantzo." if removed else "Team was already removed.")
                await _replace_screen(query, context, _my_fantzo_text(user.id), _my_fantzo_keyboard(user.id))
                return

        if query and user and action == "back":
            await query.answer()
            tracked.app.core.touch_user(update)
            lang = tracked.app.core.get_user_lang(user.id)
            await _replace_screen(
                query,
                context,
                personalized_home_text(user.id, lang),
                personalized_home_keyboard(user.id),
            )
            return

        await original_router(update, context)

    tracked.app.core.callback_router = personalization_router
    logger.info("Fantzo user personalization installed: My Fantzo + favourite-team home shortcuts")
