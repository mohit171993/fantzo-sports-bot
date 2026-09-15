import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs, urlparse

import bot as core
import bot_tracked as runtime
import fantzo_analytics as analytics
import fantzo_live_tv
import ibetin_hub as hub
import private_apk_upload
import trial_live_tv

logger = logging.getLogger(__name__)

BUSINESS_ALERTS_API = "/business/api/alerts"
BUSINESS_TOKEN_MAX_TTL = 31 * 24 * 60 * 60


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
    """Keep start-param routing for normal Main Mini App launches.

    Telegram Business shortcuts no longer depend on this mechanism; they use
    explicit IBETIN URLs because some Telegram clients drop Business startapp
    parameters completely.
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


def _verify_business_alert_token(token: str) -> int:
    if not hub.BOT_TOKEN or not token:
        raise ValueError("Invalid alert link")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid alert link")

    try:
        user_id = int(parts[0])
        expires_at = int(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid alert link") from exc

    if user_id <= 0:
        raise ValueError("Invalid alert link")

    now = int(time.time())
    if expires_at < now:
        raise ValueError("This alert link has expired. Send a new message to IBETIN for a fresh link.")
    if expires_at > now + BUSINESS_TOKEN_MAX_TTL:
        raise ValueError("Invalid alert link")

    payload = f"{user_id}.{expires_at}"
    expected = hmac.new(
        hub.BOT_TOKEN.encode("utf-8"),
        f"ibetin-business-alerts:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, parts[2]):
        raise ValueError("Invalid alert link")
    return user_id


def _ensure_business_user(user_id: int) -> None:
    now = core.now_iso()
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, created_at, last_seen)
            VALUES (?, '', '', ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen
            """,
            (user_id, now, now),
        )


def _business_alert_page(token: str) -> str:
    token_json = json.dumps(token)
    home_url = json.dumps(f"{hub._public_base_url()}/hub?section=home&source=business_dm")
    support_url = json.dumps(f"{hub._public_base_url()}/hub?section=support&source=business_dm")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">
<meta name=\"referrer\" content=\"no-referrer\">
<meta http-equiv=\"Cache-Control\" content=\"no-store, no-cache, must-revalidate\">
<title>IBETIN · My Match Alerts</title>
<script src=\"https://telegram.org/js/telegram-web-app.js\"></script>
<style>
*{{box-sizing:border-box}}:root{{--bg:#07101c;--card:#0e1b2b;--line:#20334b;--text:#f7f9fc;--muted:#91a5bc;--soft:#b8c6d6}}
html,body{{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,Arial,Helvetica,sans-serif}}
body{{padding-bottom:82px}}.wrap{{max-width:760px;margin:0 auto;padding:15px 14px 28px}}.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}.brand{{font-size:18px;font-weight:950;letter-spacing:.8px}}.pill{{border:1px solid var(--line);border-radius:999px;padding:6px 9px;color:var(--muted);font-size:10px;font-weight:900}}
.hero{{background:linear-gradient(145deg,#13253a,#0b1726);border:1px solid #29415e;border-radius:24px;padding:21px 18px}}.eyebrow{{font-size:11px;font-weight:900;letter-spacing:1.2px;color:#9fb5ca;margin-bottom:8px}}h1{{font-size:26px;line-height:1.08;margin:0 0 8px}}.hero p,.section p{{color:var(--soft);font-size:13px;line-height:1.5;margin:0}}
.section{{margin-top:14px;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:16px}}.section h2{{font-size:17px;margin:0 0 7px}}.row{{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:15px;padding-top:15px;border-top:1px solid var(--line)}}.status{{margin-top:6px;font-size:12px;color:var(--muted)}}
.switch{{position:relative;width:58px;height:32px}}.switch input{{opacity:0;width:0;height:0}}.slider{{position:absolute;inset:0;border-radius:999px;background:#31445a;transition:.18s}}.slider:before{{content:'';position:absolute;width:24px;height:24px;left:4px;top:4px;background:#fff;border-radius:50%;transition:.18s}}.switch input:checked + .slider{{background:#2d7d5a}}.switch input:checked + .slider:before{{transform:translateX(26px)}}.note{{font-size:11px!important;color:#7e93aa!important;margin-top:12px!important}}
.nav{{position:fixed;left:0;right:0;bottom:0;background:rgba(7,16,28,.97);border-top:1px solid #1e3046;padding:10px 14px;display:flex;gap:8px;justify-content:center}}.nav a{{flex:1;max-width:240px;text-align:center;text-decoration:none;color:#eef3f8;background:#0e1b2b;border:1px solid #20334b;border-radius:12px;padding:11px;font-size:12px;font-weight:900}}
</style>
</head>
<body>
<div class=\"wrap\">
  <div class=\"top\"><div class=\"brand\">IBETIN</div><div class=\"pill\">TELEGRAM</div></div>
  <section class=\"hero\"><div class=\"eyebrow\">PERSONAL NOTIFICATIONS</div><h1>My Match Alerts</h1><p>Turn IBETIN Telegram sports notifications on or off for your account.</p></section>
  <section class=\"section\"><h2>Telegram alerts</h2><p>Your choice is saved directly to your IBETIN profile.</p><div class=\"row\"><div><b>Sports notifications</b><div class=\"status\" id=\"status\">Checking your preference…</div></div><label class=\"switch\"><input id=\"toggle\" type=\"checkbox\" disabled><span class=\"slider\"></span></label></div><p class=\"note\">You can change this anytime. No password or OTP is required.</p></section>
</div>
<nav class=\"nav\"><a id=\"home\" href=\"#\">⌂ Home</a><a id=\"support\" href=\"#\">🛟 Support</a></nav>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{ tg.ready(); tg.expand(); try {{ tg.setHeaderColor('#07101c'); tg.setBackgroundColor('#07101c'); }} catch(e) {{}} }}
const token = {token_json};
const toggle = document.getElementById('toggle');
const status = document.getElementById('status');
document.getElementById('home').href = {home_url};
document.getElementById('support').href = {support_url};
async function request(action, subscribed) {{
  const payload = {{token:token, action:action}};
  if (typeof subscribed === 'boolean') payload.subscribed = subscribed;
  const response = await fetch({json.dumps(BUSINESS_ALERTS_API)}, {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not save preference');
  return data;
}}
async function load() {{
  try {{
    const data = await request('get');
    toggle.checked = !!data.subscribed;
    toggle.disabled = false;
    status.textContent = data.subscribed ? 'Alerts are ON' : 'Alerts are OFF';
  }} catch(e) {{ status.textContent = e.message; }}
}}
toggle.addEventListener('change', async () => {{
  toggle.disabled = true;
  try {{
    const data = await request('set', toggle.checked);
    toggle.checked = !!data.subscribed;
    status.textContent = data.subscribed ? 'Alerts are ON' : 'Alerts are OFF';
  }} catch(e) {{
    toggle.checked = !toggle.checked;
    status.textContent = e.message;
  }} finally {{ toggle.disabled = false; }}
}});
load();
</script>
</body></html>"""


def install_business_alerts_router() -> None:
    handler_cls = analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_business_alerts_router", False):
        return

    previous_get = handler_cls.do_GET
    previous_post = getattr(handler_cls, "do_POST", None)

    def business_get(self):
        parsed = urlparse(self.path)
        if parsed.path == hub.HUB_PATH:
            query = parse_qs(parsed.query, keep_blank_values=True)
            section = (query.get("section") or [""])[0].strip().lower()
            source = (query.get("source") or [""])[0].strip().lower()
            token = (query.get("bdm") or [""])[0].strip()
            if section == "alerts" and source == "business_dm" and token:
                try:
                    _verify_business_alert_token(token)
                    hub._send_html(self, 200, _business_alert_page(token))
                except ValueError as exc:
                    hub._send_html(self, 401, f"<html><body style='background:#07101c;color:white;font-family:Arial;padding:24px'><h3>IBETIN Alerts</h3><p>{str(exc)}</p></body></html>")
                return
        previous_get(self)

    def business_post(self):
        parsed = urlparse(self.path)
        if parsed.path == BUSINESS_ALERTS_API:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 8192:
                    raise ValueError("Invalid request")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                user_id = _verify_business_alert_token(str(payload.get("token") or ""))
                _ensure_business_user(user_id)
                action = str(payload.get("action") or "get").lower()
                if action == "set":
                    subscribed = bool(payload.get("subscribed"))
                    core.set_subscription(user_id, subscribed)
                    try:
                        core.track(user_id, "business_alerts_on" if subscribed else "business_alerts_off")
                    except Exception:
                        logger.exception("Could not track IBETIN Business alert preference")
                elif action != "get":
                    raise ValueError("Unsupported action")
                preferences = hub._get_preferences(user_id)
                hub._send_json(self, 200, {"ok": True, **preferences})
            except ValueError as exc:
                hub._send_json(self, 401, {"ok": False, "error": str(exc)})
            except Exception:
                logger.exception("Could not process IBETIN Business alert preference")
                hub._send_json(self, 500, {"ok": False, "error": "Could not save preference"})
            return
        if previous_post:
            previous_post(self)
            return
        self.send_response(404)
        self.end_headers()

    handler_cls.do_GET = business_get
    handler_cls.do_POST = business_post
    handler_cls._ibetin_business_alerts_router = True
    logger.info("IBETIN Business-DM secure alert router installed")


def main() -> None:
    hub.install_on_tracking_handler(analytics)
    install_client_start_param_router()
    install_start_param_router()
    install_business_alerts_router()
    private_apk_upload.install_on_tracking_handler(analytics)
    trial_live_tv.install_on_tracking_handler(analytics)
    fantzo_live_tv.install_on_tracking_handler(analytics)
    analytics.start_tracking_server()
    logger.info(
        "Starting IBETIN Mini-App-first bot with Business explicit-route support; LIVE_TV_MODE=%s",
        runtime.LIVE_TV_MODE,
    )
    runtime.app.run()


if __name__ == "__main__":
    main()
