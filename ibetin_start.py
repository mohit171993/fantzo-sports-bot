import asyncio
import logging
import os
from urllib.parse import parse_qs, urlparse

from telegram import Bot

import ibetin_entry
import fantzo_business as business
import fantzo_reminders as reminders
import ibetin_hub as hub
import ibetin_match_alerts as match_alerts
import ibetin_news as news

logger = logging.getLogger(__name__)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _is_telegram_mini_app_link(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if "startapp" not in query:
            return False
        if parsed.scheme in {"http", "https"}:
            return parsed.netloc.lower() in {
                "t.me",
                "www.t.me",
                "telegram.me",
                "www.telegram.me",
            }
        return parsed.scheme == "tg" and parsed.netloc.lower() == "resolve"
    except Exception:
        return False


def _startapp_value(url: str) -> str:
    try:
        return (parse_qs(urlparse(url).query, keep_blank_values=True).get("startapp") or [""])[0]
    except Exception:
        return ""


def _mini_app_link_kind(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        parts = [part for part in parsed.path.split("/") if part]
        return "direct" if len(parts) >= 2 else "main"
    query = parse_qs(parsed.query, keep_blank_values=True)
    return "direct" if (query.get("appname") or [""])[0] else "main"


def _expect_webapps(name: str, markup, errors: list[str]) -> int:
    buttons = _buttons(markup)
    if not buttons:
        errors.append(f"{name}: no buttons")
        return 0
    for button in buttons:
        if button.web_app is None:
            errors.append(f"{name}/{button.text}: not a web_app button")
        if button.url:
            errors.append(f"{name}/{button.text}: unexpected url button")
    return len(buttons)


def _expect_business_launchers(
    name: str,
    markup,
    errors: list[str],
    expected_count: int,
    expected_sections: set[str] | None = None,
) -> int:
    buttons = _buttons(markup)
    if len(buttons) != expected_count:
        errors.append(f"{name}: expected {expected_count} launcher(s), got {len(buttons)}")
    actual_sections: set[str] = set()
    for button in buttons:
        if button.web_app is not None:
            errors.append(f"{name}/{button.text}: Business launcher must not use web_app")
        if not _is_telegram_mini_app_link(button.url or ""):
            errors.append(f"{name}/{button.text}: launcher is not a Telegram Mini App deep link")
        actual_sections.add(_startapp_value(button.url or ""))
    if expected_sections is not None and actual_sections != expected_sections:
        errors.append(
            f"{name}: startapp sections mismatch; expected {sorted(expected_sections)}, got {sorted(actual_sections)}"
        )
    return len(buttons)


def run_navigation_self_test() -> None:
    """Fail startup for code regressions in IBETIN navigation."""
    errors: list[str] = []

    direct_count = _expect_webapps("direct-home", hub.clean_main_keyboard(), errors)
    auto_count = _expect_webapps(
        "direct-autoreply",
        ibetin_entry.runtime.app.fantzo_autoreply.standard_keyboard(),
        errors,
    )

    business_count = _expect_business_launchers(
        "business-autoreply",
        business.business_keyboard(123456789),
        errors,
        expected_count=5,
        expected_sections={"home", "live", "news", "alerts", "support"},
    )

    _, business_reminder = reminders._copy_for("general", 1, "business_dm")
    business_reminder_count = _expect_business_launchers(
        "business-reminder",
        business_reminder,
        errors,
        expected_count=1,
    )

    _, bot_reminder = reminders._copy_for("general", 1, "bot")
    bot_reminder_count = _expect_webapps("direct-reminder", bot_reminder, errors)

    alert_count = 0
    alert_count += _expect_webapps("match-alert-live", match_alerts._markup("started"), errors)
    alert_count += _expect_webapps("match-alert-final", match_alerts._markup("final"), errors)

    news_buttons = _buttons(news.launcher_keyboard())
    if not news_buttons or news_buttons[0].web_app is None or news_buttons[0].url:
        errors.append("news-launcher: primary News button is not a web_app")

    if not hub.hub_url("home").startswith("https://"):
        errors.append("hub home URL is not HTTPS")
    if not hub.news_url().startswith("https://"):
        errors.append("news URL is not HTTPS")

    if errors:
        raise RuntimeError("IBETIN navigation self-test FAILED: " + " | ".join(errors))

    logger.info(
        "IBETIN navigation self-test PASS: direct_home=%s direct_autoreply=%s "
        "business=%s business_reminder=%s direct_reminder=%s match_alerts=%s "
        "news_primary=webapp",
        direct_count,
        auto_count,
        business_count,
        business_reminder_count,
        bot_reminder_count,
        alert_count,
    )


async def _telegram_capability_self_test() -> bool:
    """Report whether Telegram can resolve the configured Business launcher."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("IBETIN Telegram capability BLOCKED: BOT_TOKEN missing")
        return False

    link = business.telegram_mini_app_url("home")
    kind = _mini_app_link_kind(link)

    try:
        async with Bot(token=token) as bot:
            me = await bot.get_me()
    except Exception as exc:
        logger.warning("IBETIN Telegram capability test could not reach getMe: %s", exc)
        return False

    has_main = bool(getattr(me, "has_main_web_app", False))
    if kind == "main" and not has_main:
        logger.error(
            "IBETIN Telegram capability BLOCKED: @%s has_main_web_app=false. "
            "Business launcher is structurally correct but Telegram cannot open it as a Main Mini App "
            "until the Main Mini App is configured for this bot in BotFather.",
            me.username or business.IBETIN_BOT_USERNAME,
        )
        return False

    logger.info(
        "IBETIN Telegram capability test PASS: username=@%s mini_app_link=%s has_main_web_app=%s",
        me.username or business.IBETIN_BOT_USERNAME,
        kind,
        has_main,
    )
    return True


def main() -> None:
    run_navigation_self_test()
    asyncio.run(_telegram_capability_self_test())
    # asyncio.run() closes the temporary loop it creates. python-telegram-bot
    # run_polling() expects a current loop, so provide a fresh one for runtime.
    asyncio.set_event_loop(asyncio.new_event_loop())
    ibetin_entry.main()


if __name__ == "__main__":
    main()
