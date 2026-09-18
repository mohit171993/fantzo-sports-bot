import asyncio
import json
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


def _business_start(url: str) -> str:
    try:
        parsed = urlparse(url or "")
        query = parse_qs(parsed.query, keep_blank_values=True)
        start = (query.get("startapp") or [""])[0].strip().lower()
        if not start:
            return ""

        if parsed.scheme == "https" and parsed.netloc.lower() in {"t.me", "telegram.me"}:
            return start
        if parsed.scheme == "tg" and parsed.netloc == "resolve":
            return start
    except Exception:
        pass
    return ""


def _expect_business_mini_app_links(
    name: str,
    markup,
    errors: list[str],
    expected_count: int,
    expected_sections: set[str],
) -> int:
    buttons = _buttons(markup)
    if len(buttons) != expected_count:
        errors.append(f"{name}: expected {expected_count} launcher(s), got {len(buttons)}")

    actual: set[str] = set()
    for button in buttons:
        if button.web_app is not None:
            errors.append(f"{name}/{button.text}: Business message cannot use web_app")
        if not button.url:
            errors.append(f"{name}/{button.text}: missing URL")
            continue
        if "JOIN CHANNEL" in (button.text or "").upper():
            if "t.me/ibetinoffcial" not in button.url:
                errors.append(f"{name}/{button.text}: wrong channel URL")
            continue
        start = _business_start(button.url)
        if not start:
            errors.append(f"{name}/{button.text}: not a Telegram Main Mini App deep link")
            continue
        actual.add(start)

    if actual != expected_sections:
        errors.append(
            f"{name}: startapp mismatch; expected {sorted(expected_sections)}, got {sorted(actual)}"
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


def _redirect_target(section: str) -> str:
    section = (section or "").strip().lower()
    targets = {
        "home": hub.IBETIN_HOME_URL,
        "sports": hub.IBETIN_SPORTS_URL,
        "live": hub.IBETIN_LIVE_URL,
        "liveline": f"{hub._public_base_url()}/liveline",
        "casino": hub.IBETIN_CASINO_URL,
        "games": hub.IBETIN_GAMES_URL,
        "results": hub.IBETIN_RESULTS_URL,
        "payments": hub.IBETIN_PAYMENT_URL,
        "support": hub.IBETIN_SUPPORT_URL,
        "news": hub.news_url(),
    }
    return targets.get(section, "")


def _send_redirect(handler, target: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", target)
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _launcher_page() -> str:
    """White, zero-dashboard launcher used only when start_param is client-side.

    The old /hub home dashboard was the black screen visible in Telegram. This
    launcher never renders that dashboard: it immediately routes to the final
    IBETIN destination once Telegram exposes start_param.
    """
    targets = {
        "home": hub.IBETIN_HOME_URL,
        "sports": hub.IBETIN_SPORTS_URL,
        "live": hub.IBETIN_LIVE_URL,
        "liveline": f"{hub._public_base_url()}/liveline",
        "casino": hub.IBETIN_CASINO_URL,
        "games": hub.IBETIN_GAMES_URL,
        "results": hub.IBETIN_RESULTS_URL,
        "payments": hub.IBETIN_PAYMENT_URL,
        "support": hub.IBETIN_SUPPORT_URL,
        "news": hub.news_url(),
    }
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">
<meta http-equiv=\"Cache-Control\" content=\"no-store, no-cache, must-revalidate\">
<title>IBETIN</title>
<script src=\"https://telegram.org/js/telegram-web-app.js\"></script>
<style>
html,body{{margin:0;min-height:100%;background:#fff;color:#142033;font-family:Arial,sans-serif}}
main{{display:flex;min-height:70vh;align-items:center;justify-content:center;padding:24px;text-align:center}}
.logo{{font-size:24px;font-weight:900;letter-spacing:.8px}}
.status{{margin-top:10px;color:#718096;font-size:13px}}
.spin{{width:26px;height:26px;margin:18px auto 0;border:3px solid #e6eaf0;border-top-color:#1d5fd0;border-radius:50%;animation:s .75s linear infinite}}
@keyframes s{{to{{transform:rotate(360deg)}}}}
</style>
</head>
<body><main><div><div class=\"logo\">IBETIN</div><div class=\"status\">Opening inside Telegram…</div><div class=\"spin\"></div></div></main>
<script>
(function() {{
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {{ try {{ tg.ready(); tg.expand(); }} catch(e) {{}} }}
  const q = new URLSearchParams(window.location.search);
  let start = String(q.get('tgWebAppStartParam') || q.get('startapp') || '').trim().toLowerCase();
  if (!start && tg && tg.initDataUnsafe) start = String(tg.initDataUnsafe.start_param || '').trim().toLowerCase();
  if (!start && tg && tg.initData) start = String(new URLSearchParams(tg.initData).get('start_param') || '').trim().toLowerCase();
  const targets = {json.dumps(targets)};
  if (start === 'alerts' || start === 'settings') {{
    window.location.replace('/hub?section=' + encodeURIComponent(start) + (window.location.hash || ''));
    return;
  }}
  window.location.replace(targets[start] || targets.home);
}})();
</script></body></html>"""


def _install_native_mini_app_server_router() -> None:
    """Route Main Mini App deep links before the old black /hub dashboard renders."""
    handler_cls = ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_native_mini_app_router", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = urlparse(self.path)
        if parsed.path == hub.HUB_PATH:
            query = parse_qs(parsed.query, keep_blank_values=True)
            section = (query.get("section") or [""])[0].strip().lower()
            start_param = ibetin_entry._telegram_start_param(parsed)

            if start_param:
                logger.info("IBETIN native Mini App start_param=%s", start_param)
                target = _redirect_target(start_param)
                if target:
                    _send_redirect(self, target)
                    return
                if start_param in {"alerts", "settings"}:
                    hub._send_html(self, 200, hub._page(start_param))
                    return

            if section:
                target = _redirect_target(section)
                if target:
                    logger.info("IBETIN direct Mini App section=%s", section)
                    _send_redirect(self, target)
                    return
                if section in {"alerts", "settings"}:
                    hub._send_html(self, 200, hub._page(section))
                    return

            # Bare Main Mini App URL: wait only for Telegram client start_param,
            # then leave immediately. Never render the black command-center home.
            hub._send_html(self, 200, _launcher_page())
            return

        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_native_mini_app_router = True
    logger.info("IBETIN native Mini App no-black-screen router installed")


def _install_noop_client_router() -> None:
    """Server/launcher routing replaces the old page-rewriting JS router."""
    logger.info("IBETIN legacy client start-param router disabled")


def run_navigation_self_test() -> None:
    errors: list[str] = []

    main_markup = ibetin_entry.runtime.premium_main_keyboard()
    main_count = _expect_webapps("main-bot", main_markup, errors)
    main_texts = [button.text for button in _buttons(main_markup)]
    if not any("WATCH IBETIN LIVE LINE" in (text or "") for text in main_texts):
        errors.append("main bot missing WATCH IBETIN LIVE LINE")
    direct_auto_count = _expect_webapps(
        "direct-autoreply",
        ibetin_entry.runtime.app.fantzo_autoreply.standard_keyboard(),
        errors,
    )

    business_count = _expect_business_mini_app_links(
        "business-autoreply",
        business.business_keyboard(123456789),
        errors,
        expected_count=3,
        expected_sections={"home", "liveline"},
    )

    _, business_reminder = reminders._copy_for("general", 1, "business_dm")
    business_reminder_buttons = _buttons(business_reminder)
    business_reminder_count = len(business_reminder_buttons)
    if business_reminder_count != 1:
        errors.append(f"business-reminder: expected 1 launcher, got {business_reminder_count}")
    elif _business_start(business_reminder_buttons[0].url or "") != "home":
        errors.append("business-reminder: must launch Telegram Main Mini App startapp=home")

    _, bot_reminder = reminders._copy_for("general", 1, "bot")
    bot_reminder_count = _expect_webapps("direct-reminder", bot_reminder, errors)

    alert_count = 0
    alert_count += _expect_webapps("match-alert-live", match_alerts._markup("started"), errors)
    alert_count += _expect_webapps("match-alert-final", match_alerts._markup("final"), errors)

    news_buttons = _buttons(news.launcher_keyboard())
    if not news_buttons or news_buttons[0].web_app is None or news_buttons[0].url:
        errors.append("news-launcher: primary News button is not a web_app")

    if _redirect_target("home") != hub.IBETIN_HOME_URL:
        errors.append("home redirect target invalid")
    if _redirect_target("live") != hub.IBETIN_LIVE_URL:
        errors.append("live redirect target invalid")
    if _redirect_target("support") != hub.IBETIN_SUPPORT_URL:
        errors.append("support redirect target invalid")

    if errors:
        raise RuntimeError("IBETIN navigation self-test FAILED: " + " | ".join(errors))

    logger.info(
        "IBETIN navigation self-test PASS: main_bot=%s direct_autoreply=%s "
        "business_native_mini_app=%s business_reminder=%s direct_reminder=%s "
        "match_alerts=%s black_home_dashboard=disabled",
        main_count,
        direct_auto_count,
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
        "IBETIN Telegram capability test PASS: username=@%s has_main_web_app=%s business_links=main_mini_app",
        me.username or "Ibtnofficialbot",
        has_main,
    )
    return True


_original_hub_install = hub.install_on_tracking_handler
hub.install_on_tracking_handler = _install_hub_and_restore_main_ui

# Replace the old black-dashboard start routing with native Main Mini App routing.
ibetin_entry.install_start_param_router = _install_native_mini_app_server_router
ibetin_entry.install_client_start_param_router = _install_noop_client_router


def main() -> None:
    run_navigation_self_test()
    asyncio.run(_telegram_capability_self_test())
    asyncio.set_event_loop(asyncio.new_event_loop())
    ibetin_entry.main()


if __name__ == "__main__":
    main()
