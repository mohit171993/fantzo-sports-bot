import logging
from urllib.parse import parse_qs, urlparse

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


def _expect_business_launcher(name: str, markup, errors: list[str]) -> int:
    buttons = _buttons(markup)
    if len(buttons) != 1:
        errors.append(f"{name}: expected exactly 1 launcher, got {len(buttons)}")
        return len(buttons)
    button = buttons[0]
    if button.web_app is not None:
        errors.append(f"{name}: Business launcher must not use web_app")
    if not _is_telegram_mini_app_link(button.url or ""):
        errors.append(f"{name}: launcher is not a Telegram Mini App deep link")
    return 1


def run_navigation_self_test() -> None:
    """Fail startup if IBETIN navigation regresses to external web links."""
    errors: list[str] = []

    direct_count = _expect_webapps(
        "direct-home", hub.clean_main_keyboard(), errors
    )

    # This module has already been patched by bot_tracked during ibetin_entry
    # import. Testing it here validates the real runtime keyboard, not source
    # code in isolation.
    auto_count = _expect_webapps(
        "direct-autoreply",
        ibetin_entry.runtime.app.fantzo_autoreply.standard_keyboard(),
        errors,
    )

    business_count = _expect_business_launcher(
        "business-autoreply", business.business_keyboard(123456789), errors
    )

    _, business_reminder = reminders._copy_for("general", 1, "business_dm")
    business_reminder_count = _expect_business_launcher(
        "business-reminder", business_reminder, errors
    )

    _, bot_reminder = reminders._copy_for("general", 1, "bot")
    bot_reminder_count = _expect_webapps(
        "direct-reminder", bot_reminder, errors
    )

    alert_count = 0
    alert_count += _expect_webapps(
        "match-alert-live", match_alerts._markup("started"), errors
    )
    alert_count += _expect_webapps(
        "match-alert-final", match_alerts._markup("final"), errors
    )

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


def main() -> None:
    run_navigation_self_test()
    ibetin_entry.main()


if __name__ == "__main__":
    main()
