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


def _business_section(url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(url or "")
        query = parse_qs(parsed.query, keep_blank_values=True)
        source = (query.get("source") or [""])[0].strip().lower()
        if parsed.path == "/news":
            return "news", source
        if parsed.path == "/hub":
            return (query.get("section") or [""])[0].strip().lower(), source
    except Exception:
        pass
    return "", ""


def _expect_business_routes(
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
            errors.append(f"{name}/{button.text}: Business launcher must use a URL button")
        if not button.url:
            errors.append(f"{name}/{button.text}: missing URL")
            continue

        parsed = urlparse(button.url)
        if parsed.scheme != "https":
            errors.append(f"{name}/{button.text}: Business URL must be HTTPS")

        section, source = _business_section(button.url)
        if not section:
            errors.append(f"{name}/{button.text}: not an explicit IBETIN section route")
            continue
        if source != "business_dm":
            errors.append(f"{name}/{button.text}: missing source=business_dm")
        actual_sections.add(section)

        if section == "alerts":
            query = parse_qs(parsed.query, keep_blank_values=True)
            if not (query.get("bdm") or [""])[0]:
                errors.append(f"{name}/{button.text}: secure Business alert token missing")

    if expected_sections is not None and actual_sections != expected_sections:
        errors.append(
            f"{name}: sections mismatch; expected {sorted(expected_sections)}, got {sorted(actual_sections)}"
        )
    return len(buttons)


def _restore_main_bot_runtime() -> None:
    """Undo the Mini-App dashboard override after the hub routes are installed.

    bot_tracked already defines the intended IBETIN main-bot menu with distinct
    Sports, Live, Casino, Games, Results, Payments, News, Alerts and Support
    destinations. ibetin_hub installs the web routes but also replaces that main
    menu with the generic dashboard. Restore the tracked UI so the main bot and
    the Business auto-reply remain separate experiences.
    """
    runtime = ibetin_entry.runtime
    app = runtime.app

    app.core.main_keyboard = runtime.premium_main_keyboard
    app.core.join_keyboard = runtime.premium_join_keyboard
    app.core.explore_keyboard = runtime.premium_explore_keyboard
    app.start = runtime.smart_start
    app.configure_telegram_ui = runtime.configure_telegram_ui

    logger.info("IBETIN main bot runtime restored to section-specific menu")


def _install_hub_and_restore_main_ui(analytics_module) -> None:
    _original_hub_install(analytics_module)
    _restore_main_bot_runtime()


def run_navigation_self_test() -> None:
    """Fail startup for code regressions in IBETIN navigation."""
    errors: list[str] = []

    direct_count = _expect_webapps("direct-home", ibetin_entry.runtime.premium_main_keyboard(), errors)
    auto_count = _expect_webapps(
        "direct-autoreply",
        ibetin_entry.runtime.app.fantzo_autoreply.standard_keyboard(),
        errors,
    )

    business_count = _expect_business_routes(
        "business-autoreply",
        business.business_keyboard(123456789),
        errors,
        expected_count=5,
        expected_sections={"home", "live", "news", "alerts", "support"},
    )

    _, business_reminder = reminders._copy_for("general", 1, "business_dm")
    business_reminder_buttons = _buttons(business_reminder)
    business_reminder_count = len(business_reminder_buttons)
    if business_reminder_count != 1:
        errors.append(
            f"business-reminder: expected 1 launcher, got {business_reminder_count}"
        )
    elif business_reminder_buttons:
        button = business_reminder_buttons[0]
        if button.web_app is not None or not button.url:
            errors.append("business-reminder: must use one explicit URL button")
        else:
            section, source = _business_section(button.url)
            if section != "home" or source != "business_dm":
                errors.append(
                    "business-reminder: expected explicit home route with source=business_dm"
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
        "IBETIN navigation self-test PASS: main_bot=%s direct_autoreply=%s "
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
    """Report Telegram Main Mini App capability without coupling Business routing to it."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("IBETIN Telegram capability BLOCKED: BOT_TOKEN missing")
        return False

    try:
        async with Bot(token=token) as bot:
            me = await bot.get_me()
    except Exception as exc:
        logger.warning("IBETIN Telegram capability test could not reach getMe: %s", exc)
        return False

    has_main = bool(getattr(me, "has_main_web_app", False))
    logger.info(
        "IBETIN Telegram capability test PASS: username=@%s has_main_web_app=%s business_routing=explicit",
        me.username or "Ibtnofficialbot",
        has_main,
    )
    return True


_original_hub_install = hub.install_on_tracking_handler
hub.install_on_tracking_handler = _install_hub_and_restore_main_ui


def main() -> None:
    run_navigation_self_test()
    asyncio.run(_telegram_capability_self_test())
    # asyncio.run() closes the temporary loop it creates. python-telegram-bot
    # run_polling() expects a current loop, so provide a fresh one for runtime.
    asyncio.set_event_loop(asyncio.new_event_loop())
    ibetin_entry.main()


if __name__ == "__main__":
    main()
