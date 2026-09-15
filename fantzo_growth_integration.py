import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import bot_tracked as tracked
import fantzo_growth as growth

logger = logging.getLogger(__name__)
_installed = False


def _favourite_keyboard(sport, team_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ FOLLOW TEAM + ALERTS", callback_data=f"fav:{sport}:{team_id}")],
        [
            InlineKeyboardButton("🗓 Upcoming", callback_data=f"team_up:{sport}:{team_id}"),
            InlineKeyboardButton("✅ Recent", callback_data=f"team_recent:{sport}:{team_id}"),
        ],
        [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
    ])


def install():
    global _installed
    if _installed:
        return
    _installed = True
    growth.ensure_tables()

    original_router = tracked.app.core.callback_router
    original_start = tracked.app.start

    async def growth_start(update, context):
        user = update.effective_user
        if user:
            growth.track(user.id, "bot_open", context.args[0] if context.args else "")
        await original_start(update, context)

    async def growth_router(update, context):
        query = update.callback_query
        user = update.effective_user
        action = query.data if query else ""

        if user and action:
            if action == "live_tv_status":
                growth.track(user.id, "live_tv_open")
            elif action == "join_fantzo":
                growth.track(user.id, "signup_started", "telegram_join")
            else:
                growth.track(user.id, "engagement", action[:120])

        if query and action.startswith("fav:"):
            parts = action.split(":", 2)
            if len(parts) != 3 or not user:
                await query.answer("Please try again.", show_alert=True)
                return
            _, sport, team_id = parts
            try:
                team = await tracked.app.core.get_team(sport, team_id)
                team_name = str(team.get("name") or f"{sport}:{team_id}")
                growth.add_favourite(user.id, f"{sport}:{team_id}:{team_name}")
                tracked.app.core.set_subscription(user.id, True)
                await query.answer(f"Following {team_name}", show_alert=False)
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ FOLLOWING · ALERTS ON", callback_data="subscribe")],
                    [
                        InlineKeyboardButton("🗓 Upcoming", callback_data=f"team_up:{sport}:{team_id}"),
                        InlineKeyboardButton("✅ Recent", callback_data=f"team_recent:{sport}:{team_id}"),
                    ],
                    [InlineKeyboardButton("⬅️ BACK TO HOME", callback_data="back")],
                ]))
            except Exception:
                logger.exception("Could not save Fantzo favourite team")
                await query.answer("Could not follow this team right now.", show_alert=True)
            return

        await original_router(update, context)

        if query and action.startswith("team:"):
            parts = action.split(":", 2)
            if len(parts) == 3:
                try:
                    await query.edit_message_reply_markup(reply_markup=_favourite_keyboard(parts[1], parts[2]))
                except Exception:
                    logger.exception("Could not add favourite-team CTA")

    tracked.app.start = growth_start
    tracked.app.core.callback_router = growth_router
