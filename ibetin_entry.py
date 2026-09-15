import json
import logging
from urllib.parse import parse_qs, urlparse

import bot_tracked as runtime
import fantzo_analytics as analytics
import fantzo_live_tv
import ibetin_hub as hub
import private_apk_upload
import trial_live_tv

logger = logging.getLogger(__name__)


def _telegram_start_param(parsed) -> str:
    """Read Telegram Mini App start parameter when Telegram includes it in the request URL."""
    query = parse_qs(parsed.query, keep_blank_values=True)

    for key in ("tgWebAppStartParam", "startapp"):
        value = (query.get(key) or [""])[0].strip().lower()
        if value:
            return value

    raw_init = (query.get("tgWebAppData") or [""])[0]
    if raw_init:
        try:
            init_fields = parse_qs(raw_init, keep_blank_values=True)
            value = (init_fields.get("start_param") or [""])[0].strip().lower()
            if value:
                return value
        except Exception:
            logger.exception("Could not parse Telegram Mini App start parameter")

    return ""


def _news_redirect_page() -> str:
    target = hub.news_url()
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">
<title>IBETIN · News</title>
<script src=\"https://telegram.org/js/telegram-web-app.js\"></script>
<style>html,body{{margin:0;background:#07101c;color:#fff;font-family:Arial,sans-serif}}.w{{padding:28px 18px}}.muted{{color:#91a5bc}}</style>
</head>
<body><div class=\"w\"><b>IBETIN Sports News</b><p class=\"muted\">Opening news…</p></div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); }}
window.location.replace({json.dumps(target)});
</script></body></html>"""


def install_start_param_router() -> None:
    handler_cls = analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_start_param_router", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = urlparse(self.path)
        if parsed.path == hub.HUB_PATH:
            start_param = _telegram_start_param(parsed)
            if start_param:
                logger.info("IBETIN Mini App server start_param=%s", start_param)

                if start_param == "news":
                    hub._send_html(self, 200, _news_redirect_page())
                    return

                if start_param in hub.ALLOWED_SECTIONS:
                    hub._send_html(self, 200, hub._page(start_param))
                    return

            query = parse_qs(parsed.query)
            section = (query.get("section") or [""])[0].strip().lower()
            if section in hub.ALLOWED_SECTIONS:
                hub._send_html(self, 200, hub._page(section))
                return

        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_start_param_router = True
    logger.info("IBETIN Telegram server start-parameter router installed")


def install_client_start_param_router() -> None:
    """Route Main Mini App deep links using Telegram's client-side start_param.

    On some Telegram clients the initial HTTP request is simply /hub and the
    start parameter is exposed only through Telegram.WebApp.initDataUnsafe.
    Injecting this tiny router into every hub page makes each Business-DM deep
    link open its intended Mini App section reliably.
    """
    if getattr(hub, "_ibetin_client_start_router_installed", False):
        return

    original_page = hub._page
    router_script = r"""
<script>
(function () {
  try {
    const tg = window.Telegram && window.Telegram.WebApp;
    const query = new URLSearchParams(window.location.search);
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
    hub._ibetin_client_start_router_installed = True
    logger.info("IBETIN Telegram client start-parameter router installed")


def main() -> None:
    hub.install_on_tracking_handler(analytics)
    install_client_start_param_router()
    install_start_param_router()
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info(
        "Starting IBETIN Mini-App-first bot with client/server start-param routing; LIVE_TV_MODE=%s",
        runtime.LIVE_TV_MODE,
    )
    runtime.app.run()


if __name__ == "__main__":
    main()
