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


def _install_business_safe_server_router() -> None:
    """Give explicit Business URLs priority over Telegram's stale start_param.

    Some Telegram clients keep the last Main Mini App start parameter (often
    ``home``) when a normal URL button is opened from a Business message. The
    previous router read that stale value first and sent LIVE/NEWS/etc. back to
    the home dashboard. Business ``section=...&source=business_dm`` must win.
    """
    handler_cls = ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_business_safe_start_router", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = urlparse(self.path)
        if parsed.path == hub.HUB_PATH:
            query = parse_qs(parsed.query, keep_blank_values=True)
            section = (query.get("section") or [""])[0].strip().lower()
            source = (query.get("source") or [""])[0].strip().lower()

            # Critical rule: an explicit Business-DM route is authoritative.
            if source == "business_dm" and section in hub.ALLOWED_SECTIONS:
                logger.info(
                    "IBETIN Business explicit route section=%s (Telegram start_param ignored)",
                    section,
                )
                hub._send_html(self, 200, hub._page(section))
                return

            start_param = ibetin_entry._telegram_start_param(parsed)
            if start_param:
                logger.info("IBETIN Mini App server start_param=%s", start_param)
                if start_param == "news":
                    hub._send_html(self, 200, ibetin_entry._news_redirect_page())
                    return
                if start_param in hub.ALLOWED_SECTIONS:
                    hub._send_html(self, 200, hub._page(start_param))
                    return

            if section in hub.ALLOWED_SECTIONS:
                hub._send_html(self, 200, hub._page(section))
                return

        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_business_safe_start_router = True
    logger.info("IBETIN Business-safe server router installed")


def _install_business_safe_client_router() -> None:
    """Use Telegram start_param only for normal Main Mini App launches."""
    if getattr(hub, "_ibetin_business_safe_client_router", False):
        return

    original_page = hub._page
    router_script = r"""
<script>
(function () {
  try {
    const tg = window.Telegram && window.Telegram.WebApp;
    const query = new URLSearchParams(window.location.search);
    const source = String(query.get('source') || '').trim().toLowerCase();

    // Business buttons already carry the exact destination in section=.
    // Never let stale Main Mini App start_param overwrite it.
    if (source === 'business_dm') return;

    let start = (query.get('tgWebAppStartParam') || '').trim().toLowerCase();
    if (!start && tg && tg.initDataUnsafe) {
      start = String(tg.initDataUnsafe.start_param || '').trim().toLowerCase();
    }
    if (!start && tg && tg.initData) {
      start = String(new URLSearchParams(tg.initData).get('start_param') || '').trim().toLowerCase();
    }

    const allowed = new Set([
      'home', 'live', 'news', 'alerts', 'support', 'sports',
      'casino', 'games', 'results', 'payments', 'settings'
    ]);
    if (!allowed.has(start)) return;

    if (start === 'news') {
      if (window.location.pathname !== '/news') {
        window.location.replace('/news?category=latest');
      }
      return;
    }

    const currentSection = (query.get('section') || 'home').trim().toLowerCase();
    if (window.location.pathname === '/hub' && currentSection === start) return;
    window.location.replace('/hub?section=' + encodeURIComponent(start));
  } catch (e) {
    console.error('IBETIN start-param routing failed', e);
  }
})();
</script>
"""

    def routed_page(section: str) -> str:
        html = original_page(section)
        if "</body>" in html:
            return html.replace("</body>", router_script + "</body>", 1)
        return html + router_script

    hub._page = routed_page
    hub._ibetin_business_safe_client_router = True
    logger.info("IBETIN Business-safe client router installed")


def run_navigation_self_test() -> None:
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
        errors.append(f"business-reminder: expected 1 launcher, got {business_reminder_count}")
    elif business_reminder_buttons:
        button = business_reminder_buttons[0]
        if button.web_app is not None or not button.url:
            errors.append("business-reminder: must use one explicit URL button")
        else:
            section, source = _business_section(button.url)
            if section != "home" or source != "business_dm":
                errors.append("business-reminder: expected explicit home route with source=business_dm")

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
        "IBETIN navigation self-test PASS: main_bot=%s direct_autoreply=%s business=%s "
        "business_reminder=%s direct_reminder=%s match_alerts=%s news_primary=webapp",
        direct_count,
        auto_count,
        business_count,
        business_reminder_count,
        bot_reminder_count,
        alert_count,
    )


async def _telegram_capability_self_test() -> bool:
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

# Replace only the two start-param routers. The rest of ibetin_entry remains unchanged.
ibetin_entry.install_start_param_router = _install_business_safe_server_router
ibetin_entry.install_client_start_param_router = _install_business_safe_client_router


def main() -> None:
    run_navigation_self_test()
    asyncio.run(_telegram_capability_self_test())
    asyncio.set_event_loop(asyncio.new_event_loop())
    ibetin_entry.main()


if __name__ == "__main__":
    main()
