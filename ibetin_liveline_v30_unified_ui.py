import gzip
import hmac
import json
import logging
import os
import shutil
import threading
import time
import zlib
from urllib.parse import parse_qs, urlparse

# Use Railway persistent storage whenever the volume is mounted. This executes
# before the bot/data modules import DB_PATH, so all SQLite users share one file.
_IBETIN_PERSIST_DIR = "/app/ibetin_bot_persistent"
_IBETIN_PERSIST_DB = os.path.join(_IBETIN_PERSIST_DIR, "ibetin_bot.db")
_IBETIN_LEGACY_DB = os.getenv("DB_PATH", "").strip() or "/app/ibetin_bot.db"
if os.path.isdir(_IBETIN_PERSIST_DIR):
    try:
        os.makedirs(_IBETIN_PERSIST_DIR, exist_ok=True)
        if (
            os.path.exists(_IBETIN_LEGACY_DB)
            and not os.path.exists(_IBETIN_PERSIST_DB)
            and os.path.abspath(_IBETIN_LEGACY_DB) != os.path.abspath(_IBETIN_PERSIST_DB)
        ):
            shutil.copy2(_IBETIN_LEGACY_DB, _IBETIN_PERSIST_DB)
        os.environ["DB_PATH"] = _IBETIN_PERSIST_DB
        logging.getLogger(__name__).info("IBETIN persistent DB mount detected path=%s", _IBETIN_PERSIST_DB)
    except Exception as exc:
        logging.getLogger(__name__).warning("IBETIN persistent DB bootstrap failed: %s", str(exc)[:140])

import ibetin_liveline_v25_fast_cache as v25
import ibetin_phone_verify as phone_verify

logger = logging.getLogger(__name__)
v23 = v25.v23
API_PATH = v23.liveline.LIVELINE_API_PATH

ROANUZ_WEBHOOK_PATH = "/roanuz/match/feed/v1/"
IBETIN_LIVE_STREAM_PATH = "/admin/ibetin-live-stream"
IBETIN_LIVE_HEALTH_PATH = "/admin/ibetin-live-health"
IBETIN_PUBLIC_LIVELINE_PATH = "/liveline"
IBETIN_PUBLIC_LIVELINE_API_PATH = "/liveline/api"
IBETIN_PUBLIC_LIVE_STREAM_PATH = "/liveline/stream"
IBETIN_PUBLIC_VERIFY_STATUS_PATH = "/liveline/verify-status"
IBETIN_LIVELINE_COOKIE = "ibetin_ll"
IBETIN_LIVELINE_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def _request_liveline_token(handler, parsed=None) -> str:
    parsed = parsed or urlparse(handler.path)
    try:
        query = parse_qs(parsed.query, keep_blank_values=True)
        supplied = (query.get("access") or [""])[0].strip()
        if supplied:
            return supplied
    except Exception:
        pass

    raw_cookie = str(handler.headers.get("Cookie") or "")
    for part in raw_cookie.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name == IBETIN_LIVELINE_COOKIE:
            return value.strip()
    return ""


def _liveline_identity(handler, parsed=None):
    token = _request_liveline_token(handler, parsed)
    user_id = phone_verify.verify_access_token(token) if token else 0
    return int(user_id or 0), token


def _liveline_verified(handler, parsed=None):
    user_id, token = _liveline_identity(handler, parsed)
    return user_id, token, bool(user_id and phone_verify.is_verified(user_id))


def _send_json(handler, status: int, payload) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _set_liveline_cookie(handler, token: str) -> None:
    handler.send_header(
        "Set-Cookie",
        f"{IBETIN_LIVELINE_COOKIE}={token}; Max-Age={IBETIN_LIVELINE_COOKIE_MAX_AGE}; "
        "Path=/liveline; Secure; HttpOnly; SameSite=Lax",
    )


def _send_liveline_redirect_with_cookie(handler, token: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", IBETIN_PUBLIC_LIVELINE_PATH)
    handler.send_header("Cache-Control", "no-store")
    _set_liveline_cookie(handler, token)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _liveline_verification_page(token: str = "") -> str:
    verify_url = phone_verify.verification_bot_url()
    if token:
        status_url = (
            IBETIN_PUBLIC_VERIFY_STATUS_PATH
            + "?access="
            + token
        )
        poll_js = f"""
<script>
(function(){{
  const statusUrl={json.dumps(status_url)};
  async function check(){{
    try{{
      const r=await fetch(statusUrl,{{cache:'no-store'}});
      const j=await r.json();
      if(j && j.verified){{
        window.location.replace('/liveline?access='+encodeURIComponent({json.dumps(token)}));
        return;
      }}
    }}catch(e){{}}
    setTimeout(check,1800);
  }}
  check();
}})();
</script>"""
        sub = "After sharing your number in the bot, this page unlocks automatically."
    else:
        poll_js = ""
        sub = "After verification, use the Open Live Line button sent by the bot."

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store">
<title>Verify Mobile · IBETIN Live Line</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;font-family:Inter,Arial,sans-serif;background:#eef3f8;color:#102c4b}}
.wrap{{max-width:560px;margin:0 auto;padding:28px 18px}}
.card{{margin-top:42px;background:#fff;border-radius:22px;padding:26px 20px;box-shadow:0 10px 32px rgba(5,34,69,.10);text-align:center}}
.mark{{width:60px;height:60px;border-radius:18px;margin:0 auto 16px;display:grid;place-items:center;background:#f6c84b;font-size:30px}}
h1{{margin:0;font-size:24px}}p{{color:#6d8297;line-height:1.55;font-size:14px}}
.btn{{display:block;margin-top:20px;padding:15px 16px;border-radius:14px;background:#0b5cb4;color:#fff;text-decoration:none;font-weight:900}}
.note{{font-size:12px;color:#8a9bad;margin-top:14px}}
</style>
</head>
<body><div class="wrap"><div class="card">
<div class="mark">📱</div>
<h1>Mobile verification required</h1>
<p>IBETIN Live Line is available only after you verify the mobile number linked to your Telegram account.</p>
<a class="btn" href="{verify_url}">▶ START VERIFICATION IN BOT</a>
<div class="note">{sub}</div>
</div></div>{poll_js}</body></html>"""


def _deny_liveline_stream(handler) -> None:
    body = b"mobile verification required"
    handler.send_response(401)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

_live_event_condition = threading.Condition()
_live_event_seq = 0
_live_event_key = ""
_live_sse_clients = 0
_webhook_rejected_count = 0


def _publish_live_event(key: str):
    global _live_event_seq, _live_event_key
    with _live_event_condition:
        _live_event_seq += 1
        _live_event_key = str(key or "")
        _live_event_condition.notify_all()


def _live_health_payload():
    base = v23._webhook_health_snapshot() if hasattr(v23, "_webhook_health_snapshot") else {}
    return {
        "ok": True,
        "webhook": {
            **base,
            "lastKey": _roanuz_webhook_last_key,
            "lastAt": _roanuz_webhook_last_at,
            "rejectedPushes": _webhook_rejected_count,
        },
        "sse": {
            "clients": _live_sse_clients,
            "eventSeq": _live_event_seq,
        },
        "productionRenderer": "V40",
        "previewRenderer": "V40",
    }


def _install_live_stream_routes() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_live_stream_routes_installed", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        global _live_sse_clients
        parsed = urlparse(self.path)

        if parsed.path == IBETIN_LIVE_HEALTH_PATH:
            if not v23.liveline._authorized(self.path):
                self.send_response(403)
                self.end_headers()
                return
            raw = json.dumps(_live_health_payload(), separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path in {IBETIN_LIVE_STREAM_PATH, IBETIN_PUBLIC_LIVE_STREAM_PATH}:
            if parsed.path == IBETIN_LIVE_STREAM_PATH and not v23.liveline._authorized(self.path):
                self.send_response(403)
                self.end_headers()
                return
            if parsed.path == IBETIN_PUBLIC_LIVE_STREAM_PATH:
                _, _, verified = _liveline_verified(self, parsed)
                if not verified:
                    _deny_liveline_stream(self)
                    return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            _live_sse_clients += 1
            try:
                with _live_event_condition:
                    seen = _live_event_seq
                initial = f"event: ready\ndata: {{\"seq\":{seen}}}\n\n".encode("utf-8")
                self.wfile.write(initial)
                self.wfile.flush()

                deadline = time.monotonic() + 55
                while time.monotonic() < deadline:
                    with _live_event_condition:
                        if _live_event_seq == seen:
                            _live_event_condition.wait(timeout=12)
                        seq = _live_event_seq
                        key = _live_event_key
                    if seq != seen:
                        seen = seq
                        payload = json.dumps({"seq": seq, "key": key}, separators=(",", ":"))
                        chunk = f"event: match\ndata: {payload}\n\n".encode("utf-8")
                    else:
                        chunk = b": keepalive\n\n"
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                logger.debug("IBETIN SSE connection ended: %s", str(exc)[:100])
            finally:
                _live_sse_clients = max(0, _live_sse_clients - 1)
            return

        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_live_stream_routes_installed = True
    logger.info("IBETIN live SSE/health routes installed")


_roanuz_webhook_last_key = ""
_roanuz_webhook_last_at = ""


def _decode_roanuz_webhook(raw: bytes):
    if not raw:
        raise ValueError("Empty webhook body")
    candidates = []
    try:
        candidates.append(gzip.decompress(raw))
    except Exception:
        pass
    try:
        candidates.append(zlib.decompress(raw))
    except Exception:
        pass
    candidates.append(raw)
    for data in candidates:
        try:
            payload = json.loads(data.decode("utf-8"))
            if isinstance(payload, (dict, list)):
                return payload
        except Exception:
            continue
    raise ValueError("Invalid webhook payload")


def _install_roanuz_webhook_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_roanuz_webhook_installed", False):
        return

    previous_post = getattr(handler_cls, "do_POST", None)

    def routed_post(self):
        global _roanuz_webhook_last_key, _roanuz_webhook_last_at, _webhook_rejected_count
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != ROANUZ_WEBHOOK_PATH.rstrip("/"):
            if previous_post:
                return previous_post(self)
            self.send_response(404)
            self.end_headers()
            return

        expected = os.getenv("ROANUZ_API_KEY", "").strip()
        supplied = str(self.headers.get("rs-api-key") or "").strip()
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            _webhook_rejected_count += 1
            body = b'{"status":false}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 8 * 1024 * 1024:
                raise ValueError("Invalid webhook body size")
            raw = self.rfile.read(length)
            payload = _decode_roanuz_webhook(raw)
            key = v23._accept_roanuz_webhook(payload)
            if not key:
                raise ValueError("No match found in webhook payload")

            # Invalidate stale API caches so all connected users see the pushed
            # state on their next lightweight refresh.
            try:
                with v25._lock:
                    v25._list_cache.pop("live", None)
                    v25._list_cache.pop("upcoming", None)
                    v25._detail_cache.pop(key, None)
            except Exception:
                pass

            _roanuz_webhook_last_key = key
            _roanuz_webhook_last_at = v23.datetime.now(v23.timezone.utc).isoformat()
            _publish_live_event(key)
            body = b'{"status":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            logger.info("IBETIN Roanuz webhook accepted key=%s", key)
        except Exception as exc:
            _webhook_rejected_count += 1
            logger.warning("IBETIN Roanuz webhook rejected: %s", str(exc)[:180])
            body = b'{"status":false}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    handler_cls.do_POST = routed_post
    handler_cls._ibetin_roanuz_webhook_installed = True
    logger.info("IBETIN Roanuz webhook receiver installed at %s", ROANUZ_WEBHOOK_PATH)




def _page_v30() -> str:
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store">
<meta name="referrer" content="no-referrer">
<title>IBETIN Live Cricket</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#eef3f8;--navy:#071a34;--blue:#0b5cb4;--gold:#f6c84b;--ink:#102c4b;--muted:#7b8ea2;--card:#fff;--live:#ef4763;--green:#0c9a68;--shadow:0 8px 24px rgba(5,34,69,.08)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--ink);-webkit-tap-highlight-color:transparent}body{padding-bottom:calc(145px + env(safe-area-inset-bottom));scroll-padding-bottom:calc(145px + env(safe-area-inset-bottom))}
.shell{max-width:760px;margin:auto}.top{position:sticky;top:0;z-index:30;background:linear-gradient(118deg,#041326,#0a315f 74%,#0b4d8e);color:#fff;padding:14px 16px 12px;box-shadow:0 5px 18px rgba(4,23,47,.18)}
.toprow{display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:11px}.mark{width:46px;height:46px;border-radius:14px;background:var(--gold);color:#17314e;display:grid;place-items:center;font-weight:1000;font-size:23px}.brand b{display:block;font-size:22px;letter-spacing:1px}.brand span{display:block;font-size:11px;color:#c7d8eb;margin-top:2px}.liveDot{font-size:11px;font-weight:900;padding:7px 10px;border-radius:999px;background:rgba(14,160,105,.19);border:1px solid rgba(81,220,162,.3);color:#fff}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:14px}.tab{height:48px;border:0;border-radius:13px;background:rgba(255,255,255,.08);color:#c5d6e9;font-size:14px;font-weight:900}.tab.on{background:#fff;color:#0a315f}
.main{padding:16px 16px calc(145px + env(safe-area-inset-bottom))}.tools{display:flex;gap:10px;margin-bottom:8px}.search{flex:1;height:52px;border:1px solid #e7edf3;border-radius:15px;background:#fff;padding:0 16px;font-size:15px;outline:none;box-shadow:var(--shadow)}.refresh{width:52px;border:1px solid #e7edf3;border-radius:15px;background:#fff;color:#0a4f98;font-size:23px;box-shadow:var(--shadow)}.status{font-size:12px;color:#8293a5;margin:10px 3px 12px}.list{display:grid;gap:12px}.league{font-size:14px;font-weight:900;color:#46627f;margin:8px 3px 1px}
.match{background:#fff;border-radius:18px;overflow:hidden;box-shadow:var(--shadow);border-left:4px solid #dbe5ef;cursor:pointer}.match.live{border-left-color:var(--live)}.mh{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:13px 14px 5px}.fmt{font-size:11px;color:#8697a8;font-weight:800}.badge{font-size:10px;font-weight:1000;padding:6px 8px;border-radius:999px;background:#eef4fb;color:#51718f}.badge.live{background:#fff0f2;color:#d72d45}
.team{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:10px 14px}.miniMark,.teamMark{border-radius:50%;display:grid;place-items:center;background:#edf4fb;color:#0b4f94;font-weight:1000;border:1px solid #dbe7f2;overflow:hidden}.miniMark{width:34px;height:34px;font-size:10px}.teamMark{width:40px;height:40px;font-size:11px}.miniMark img,.teamMark img{width:100%;height:100%;object-fit:cover}.tn{font-size:17px;font-weight:1000}.ta{font-size:10px;color:#96a5b4;margin-top:2px}.sc{text-align:right;font-size:27px;font-weight:1000;color:#083f7f;letter-spacing:-.5px}.si{text-align:right;font-size:11px;color:#8b9bad;margin-top:2px}
.oddsRow{display:grid;grid-template-columns:auto 1fr 1fr;gap:7px;align-items:center;padding:9px 14px;border-top:1px solid #f0f3f6;background:#fbfdff}.oddsTitle{font-size:9px;font-weight:1000;color:#7d91a5;letter-spacing:.35px;white-space:nowrap}.oddBox{min-width:0;background:#edf5fd;border:1px solid #dbe9f6;border-radius:10px;padding:8px 9px;display:flex;align-items:center;justify-content:space-between;gap:6px}.oddLabel{font-size:9px;font-weight:800;color:#5e7891;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.oddValue{font-size:13px;font-weight:1000;color:#0a579e;white-space:nowrap}.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:11px 14px;border-top:1px solid #f0f3f6;font-size:12px;color:#6f8499}
.empty,.err,.loading{background:#fff;border-radius:16px;padding:30px 16px;text-align:center;color:#73879a;font-size:13px;box-shadow:var(--shadow)}.spin{width:24px;height:24px;border:3px solid #dce5ed;border-top-color:#0b5cb4;border-radius:50%;animation:s .7s linear infinite;margin:0 auto 10px}@keyframes s{to{transform:rotate(360deg)}}
.detail{display:none;padding:16px 16px calc(175px + env(safe-area-inset-bottom))}.back{height:44px;border:0;border-radius:13px;background:#fff;color:#24578d;font-size:14px;font-weight:1000;padding:0 14px;box-shadow:0 2px 10px rgba(6,37,70,.04)}.scorehero{margin-top:10px;border-radius:20px;background:#fff;overflow:hidden;border:1px solid #e6edf4;box-shadow:var(--shadow)}.scoretop{padding:12px 14px;border-bottom:1px solid #edf1f5;font-size:11px;color:#6f8397;display:flex;justify-content:space-between;gap:10px}.scoremain{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;padding:20px 14px}.side.right{text-align:right}.teamIdentity{display:flex;align-items:center;gap:8px;margin-bottom:6px}.side.right .teamIdentity{justify-content:flex-end}.sname{font-size:13px;font-weight:1000;color:#294662}.sval{font-size:31px;font-weight:1000;color:#083f7f;margin-top:4px;letter-spacing:-.6px}.vs{width:38px;height:38px;border-radius:50%;background:#fff5cf;color:#765700;display:grid;place-items:center;font-size:10px;font-weight:1000}.report{padding:12px 14px;background:#fbfdff;border-top:1px solid #edf1f5;font-size:11px;color:#637b91}
.quickMarket{margin-top:11px;background:#fff;border-radius:16px;padding:13px;box-shadow:var(--shadow);border:1px solid #e6edf4}.quickHead{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}.quickHead b{font-size:13px}.quickHead span{font-size:9px;color:#6c8297;font-weight:900}.quickOdds{display:grid;grid-template-columns:1fr 1fr;gap:8px}.quickOdd{background:#edf5fd;border:1px solid #dbe9f6;border-radius:12px;padding:10px}.quickOdd small{display:block;color:#6d8297;font-size:9px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.quickOdd strong{display:block;color:#084f94;font-size:20px;margin-top:3px}.sessionTitle{font-size:10px;font-weight:1000;color:#73889c;margin:12px 0 6px}.sessionGrid{display:grid;gap:7px}.sessionCard{background:#f8fafc;border:1px solid #e7edf3;border-radius:11px;padding:9px}.sessionCard b{font-size:10px;color:#284d70}.sessionVals{display:flex;gap:8px;flex-wrap:wrap;margin-top:5px;font-size:10px;color:#637b92}.sessionVals strong{color:#0a579e}.quickLoading{font-size:11px;color:#758a9f;padding:4px 0}
.chaseBox{margin-top:9px;background:linear-gradient(135deg,#edf6ff,#f8fbff);border:1px solid #d8e9f8;border-radius:12px;padding:11px 12px}.chaseBox b{display:block;font-size:14px;color:#164a79}.chaseBox span{font-size:10px;color:#6f8498}.lastSix{display:flex;align-items:center;gap:6px;overflow:auto;margin-top:10px;scrollbar-width:none}.lastSix::-webkit-scrollbar{display:none}.lastSixTitle{font-size:9px;font-weight:1000;color:#8194a7;letter-spacing:.4px;margin-right:2px;white-space:nowrap}.ballChip{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:#eaf1f8;color:#294d70;font-size:10px;font-weight:1000;flex:none}.ballChip.boundary{background:#e6f4ff;color:#0968b7}.ballChip.six{background:#efe9ff;color:#6943b5}.ballChip.wicket{background:#fff0f2;color:#d02f47}.ballChip.extra{background:#fff6db;color:#856200}
.dtabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin:11px 0}.dtab{height:43px;border:1px solid #e4ebf2;border-radius:12px;background:#fff;color:#687f96;font-size:9px;font-weight:1000;padding:0 3px}.dtab.on{background:#0a315f;color:#fff;border-color:#0a315f}.panel{background:#fff;border-radius:16px;padding:13px;box-shadow:var(--shadow);margin-bottom:14px}.ptitle{margin-bottom:10px}.ptitle b{font-size:13px}.notice{background:#f7f9fb;border-radius:12px;padding:11px;font-size:11px;color:#647c92;line-height:1.5;margin-bottom:8px}.metricRow{display:flex;gap:7px;flex-wrap:wrap}.metric{display:inline-flex;gap:4px;align-items:center;background:#edf4fb;border-radius:999px;padding:7px 9px;color:#58728b;font-size:10px}.playerStrip{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.playerCard{background:#f7f9fc;border:1px solid #e8edf3;border-radius:12px;padding:10px;min-width:0}.playerRole{font-size:8px;font-weight:1000;color:#8b9caf;letter-spacing:.6px;margin-bottom:4px}.playerName{font-size:11px;font-weight:900;color:#173a5e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.playerStat{font-size:10px;color:#617b93;margin-top:3px}
.innings{display:grid;gap:8px}.inning{border:1px solid #e7edf3;background:#f9fbfd;border-radius:12px;padding:11px}.inningTop{display:flex;align-items:center;justify-content:space-between;gap:8px}.inningTeam{font-size:12px;font-weight:900}.inningScore{font-size:18px;font-weight:1000;color:#083f7f}.inningMeta{font-size:10px;color:#8091a2;margin-top:4px}.balls{display:grid;gap:7px}.ball{background:#f8fafc;border-radius:10px;padding:9px;font-size:10px;line-height:1.45}.moreGrid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.moreItem{border:1px solid #e5ebf2;background:#f8fafc;border-radius:13px;padding:14px 11px;text-align:left;color:#234766;font-size:11px;font-weight:900}.moreItem span{display:block;font-size:9px;font-weight:600;color:#7d90a3;margin-top:4px}.kv{display:grid;grid-template-columns:1fr auto;gap:8px;padding:9px 0;border-bottom:1px solid #edf1f4;font-size:10px}.kv b{color:#244867}
.bottom{position:fixed;left:14px;right:14px;bottom:calc(10px + env(safe-area-inset-bottom));z-index:40;max-width:732px;margin:auto;display:grid;grid-template-columns:repeat(4,1fr);gap:4px;background:rgba(5,22,45,.98);border-radius:20px;padding:8px;box-shadow:0 12px 30px rgba(4,23,48,.25)}.bottom button{border:0;background:transparent;color:#9fb2c8;height:54px;border-radius:13px;font-size:9px;font-weight:1000}.bottom b{display:block;font-size:18px;margin-bottom:2px}.bottom .on{background:rgba(255,255,255,.1);color:#fff}
@media(min-width:620px){.list{grid-template-columns:1fr 1fr}.league{grid-column:1/-1}}@media(max-width:390px){.brand b{font-size:20px}.mark{width:42px;height:42px}.tab{font-size:12px}.tn{font-size:15px}.sc{font-size:24px}.sval{font-size:27px}.playerStrip{grid-template-columns:1fr}.oddsRow{grid-template-columns:1fr 1fr}.oddsTitle{grid-column:1/-1}.dtab{font-size:8px}.quickOdds{grid-template-columns:1fr 1fr}}
</style><link rel="icon" href="data:">
</head>
<body>
<div class="shell">
<header class="top"><div class="toprow"><div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div></div><div class="tabs"><button class="tab on" data-mode="live">● LIVE</button><button class="tab" data-mode="upcoming">UPCOMING</button><button class="tab" data-mode="results">RESULTS</button></div></header>
<main id="home" class="main"><div class="tools"><input id="search" class="search" placeholder="Search match, team or tournament"><button id="refresh" class="refresh">↻</button></div><div id="status" class="status">Loading live cricket…</div><div id="list" class="list"></div></main>
<section id="detail" class="detail"></section>
</div>
<nav class="bottom"><button class="on" data-nav="home"><b>⌂</b>HOME</button><button data-nav="live"><b style="color:#ff5b6f">●</b>LIVE</button><button data-nav="fixtures"><b>◷</b>FIXTURES</button><button data-nav="search"><b>⌕</b>SEARCH</button></nav>
<script>
'use strict';
const tg=window.Telegram&&window.Telegram.WebApp;
if(tg){try{tg.ready();tg.expand();tg.setHeaderColor('#071a34');tg.setBackgroundColor('#eef3f8')}catch(e){}}
const qs=new URLSearchParams(location.search),TOKEN=qs.get('t')||'',API_PATH='__API_PATH__';
let mode='live',allMatches=[],detailData=null,detailTab='match',refreshTimer=null,loadGeneration=0,lastHomeLoad=0;
const bhavCache=new Map(),bhavBusy=new Set();
const BHAV_TTL=10000;
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[m]));
const display=v=>v===null||v===undefined||v===''?'—':esc(v);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function api(params,retry=true){params.t=TOKEN;const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),7000);try{const r=await fetch(API_PATH+'?'+new URLSearchParams(params),{cache:'no-store',signal:ctrl.signal});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||('HTTP '+r.status));return j}catch(e){if(retry&&e.name!=='AbortError'){await sleep(250);return api(params,false)}throw e}finally{clearTimeout(timer)}}
function loading(el){el.innerHTML='<div class="loading"><div class="spin"></div>Loading…</div>'}
function fmtTime(v){if(!v)return'';try{let x=v;if(typeof v==='string'&&/^\d+(\.\d+)?$/.test(v))x=Number(v)*1000;else if(typeof v==='number'&&v<1000000000000)x=v*1000;const d=new Date(x);if(Number.isNaN(d.getTime()))return'';return d.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return''}}
function prettyState(v){const s=String(v||'').toLowerCase().replace(/[_-]+/g,' ').trim();if(!s)return'';if(['in play','inplay','started','live','playing'].includes(s))return'LIVE';if(['not started','scheduled','upcoming','fixture','created','confirmed'].includes(s))return'UPCOMING';if(['completed','complete','finished','result','ended','closed'].includes(s))return'FINAL';return s.replace(/\b\w/g,c=>c.toUpperCase())}
function matchKey(m){return String(m?.roanuzMatchKey||m?.id||'')}
function league(m){return m?.league?.name||'Cricket'}
function initials(t){const n=String(t?.name||t?.abbr||'TM').trim(),p=n.split(/\s+/).filter(Boolean);return (p.length>1?(p[0][0]+p[1][0]):n.slice(0,2)).toUpperCase()}
function imageUrl(t){return t?.logo||t?.logoUrl||t?.image||t?.imageUrl||t?.flag||t?.flagUrl||''}
function miniMark(t){const u=imageUrl(t),i=esc(initials(t));return u?`<span class="miniMark"><img src="${esc(u)}" alt="" onerror="this.parentElement.textContent='${i}'"></span>`:`<span class="miniMark">${i}</span>`}
function teamMark(t){const u=imageUrl(t),i=esc(initials(t));return u?`<span class="teamMark"><img src="${esc(u)}" alt="" onerror="this.parentElement.textContent='${i}'"></span>`:`<span class="teamMark">${i}</span>`}
function teamRow(t,s,i){return `<div class="team">${miniMark(t)}<div><div class="tn">${esc(t?.name||t?.abbr||'Team')}</div><div class="ta">${esc(t?.abbr||'')}</div></div><div><div class="sc">${display(s)}</div><div class="si">${esc(i||'')}</div></div></div>`}
function entries(j){return Array.isArray(j?.entries)?j.entries:[]}
function values(e){return Array.isArray(e?.values)?e.values.filter(v=>v&&v.odd!==undefined&&v.odd!==null):[]}
function findMatchMarket(j){const es=entries(j);return es.find(e=>/match|winner|moneyline/i.test(String(e?.market||''))&&values(e).length>=2)||es.find(e=>values(e).length>=2)||null}
function sessionMarkets(j,main){return entries(j).filter(e=>e!==main&&values(e).length>=2&&/over|session|runs|line|total|fancy|innings/i.test(String(e?.market||''))).slice(0,3)}
function homeOddsHtml(m){if(mode!=='live')return'';const c=bhavCache.get(matchKey(m));if(!c?.data)return'';const market=findMatchMarket(c.data);if(!market)return'';const vs=values(market).slice(0,2);return `<div class="oddsRow"><span class="oddsTitle">MATCH ODDS</span>${vs.map(x=>`<div class="oddBox"><span class="oddLabel">${esc(x.label||'Selection')}</span><span class="oddValue">${esc(x.odd)}</span></div>`).join('')}</div>`}
function card(m){const live=mode==='live',label=live?'● LIVE':mode==='upcoming'?(fmtTime(m.startTime)||'UPCOMING'):(prettyState(m.state)||'FINAL');return `<article class="match ${live?'live':''}" data-key="${esc(matchKey(m))}"><div class="mh"><div class="fmt">${esc(m.format||'CRICKET')} · ${esc(league(m))}</div><span class="badge ${live?'live':''}">${esc(label)}</span></div>${teamRow(m.home,m.homeScore,m.homeInfo)}${teamRow(m.away,m.awayScore,m.awayInfo)}${homeOddsHtml(m)}<div class="foot"><span>${esc(m.report||prettyState(m.state)||fmtTime(m.startTime)||'Tap for details')}</span><b>›</b></div></article>`}
function render(){const q=(document.getElementById('search').value||'').trim().toLowerCase(),rows=allMatches.filter(m=>!q||[m.home?.name,m.away?.name,league(m),m.format].join(' ').toLowerCase().includes(q)),list=document.getElementById('list');if(!rows.length){list.innerHTML='<div class="empty">'+(mode==='live'&&!q?'No live matches right now.':mode==='upcoming'&&!q?'No upcoming matches right now.':mode==='results'&&!q?'No recent results found.':'No matching cricket matches found.')+'</div>';return}let last='';list.innerHTML=rows.map(m=>{const l=league(m),h=l!==last?`<div class="league">${esc(l)}</div>`:'';last=l;return h+card(m)}).join('');list.querySelectorAll('.match').forEach(el=>el.onclick=()=>openMatch(el.dataset.key));if(mode==='live')setTimeout(()=>rows.slice(0,6).forEach(m=>getBhav(matchKey(m))),120)}
function mergeScore(base,fresh){if(!base||!fresh)return base;return {...base,home:fresh.home||base.home,away:fresh.away||base.away,homeScore:fresh.homeScore||base.homeScore,homeInfo:fresh.homeInfo||base.homeInfo,awayScore:fresh.awayScore||base.awayScore,awayInfo:fresh.awayInfo||base.awayInfo,report:fresh.report||base.report,state:fresh.state||base.state}}
async function hydrateScore(m){const key=matchKey(m);if(!key)return;try{const j=await api({action:'score',key});const i=allMatches.findIndex(x=>matchKey(x)===key);if(i>=0){allMatches[i]=mergeScore(allMatches[i],j.match||{});render()}}catch(e){}}
async function getBhav(key,force=false){if(!key)return null;const c=bhavCache.get(key);if(!force&&c&&Date.now()-c.ts<BHAV_TTL)return c.data;if(bhavBusy.has(key))return c?.data||null;bhavBusy.add(key);try{const j=await api({action:'bhav',matchId:key},false);bhavCache.set(key,{ts:Date.now(),data:j});if(mode==='live'&&document.getElementById('home').style.display!=='none')render();return j}catch(e){bhavCache.set(key,{ts:Date.now(),data:null});return null}finally{bhavBusy.delete(key)}}
async function load(nextMode=mode,force=false){mode=nextMode;document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.mode===mode));const gen=++loadGeneration,list=document.getElementById('list');if(force||!allMatches.length)loading(list);document.getElementById('status').textContent='Updating '+mode+' matches…';try{const j=await api({action:'matches',mode});if(gen!==loadGeneration)return;allMatches=j.matches||[];render();lastHomeLoad=Date.now();const stamp=j.generatedAt?new Date(j.generatedAt):new Date();document.getElementById('status').textContent=`${allMatches.length} ${mode==='live'?'live ':''}matches · Updated ${stamp.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`;if(mode==='live'){allMatches.slice(0,6).forEach(hydrateScore);setTimeout(()=>allMatches.slice(0,6).forEach(hydrateScore),1600)}}catch(e){if(gen!==loadGeneration)return;if(allMatches.length){document.getElementById('status').textContent='Showing last update · Refresh to retry'}else list.innerHTML='<div class="err">Live cricket is temporarily unavailable.<br><br><button class="back" onclick="load(mode,true)">RETRY</button></div>'}if(refreshTimer)clearInterval(refreshTimer);if(mode==='live')refreshTimer=setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)}
function showTelegramBack(on){if(!tg?.BackButton)return;try{if(on){tg.BackButton.show();tg.BackButton.onClick(backHome)}else{tg.BackButton.offClick(backHome);tg.BackButton.hide()}}catch(e){}}
async function openMatch(key){if(!key)return;document.getElementById('home').style.display='none';const d=document.getElementById('detail');d.style.display='block';loading(d);showTelegramBack(true);try{const j=await api({action:'match',id:key});detailData=j.detail||{};detailTab='match';drawDetail();getBhav(key).then(x=>{if(document.getElementById('quickMarket'))renderQuickMarket(x);if(detailTab==='bhav')drawPanel()})}catch(e){d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button><div class="err">Unable to load match details.<br><br><button class="back" onclick="openMatch('${esc(key)}')">RETRY</button></div>`}}
function backHome(){document.getElementById('detail').style.display='none';document.getElementById('home').style.display='block';detailData=null;showTelegramBack(false);window.scrollTo({top:0,behavior:'smooth'});if(Date.now()-lastHomeLoad>15000)load(mode)}
function targetRuns(t){if(!t||typeof t!=='object')return null;for(const k of ['runs','target','score','target_runs','targetRuns']){const v=Number(t[k]);if(Number.isFinite(v)&&v>0)return v}return null}
function targetBalls(t){if(!t||typeof t!=='object')return null;for(const k of ['balls','balls_remaining','ballsRemaining']){const v=Number(t[k]);if(Number.isFinite(v)&&v>=0)return v}return null}
function scoreRuns(s){const m=String(s||'').match(/^\s*(\d+)/);return m?Number(m[1]):null}
function scoreOvers(info){const m=String(info||'').match(/(\d+)(?:\.(\d+))?/);if(!m)return null;return Number(m[1])*6+Number(m[2]||0)}
function chaseInfo(target,m){const tr=targetRuns(target);if(!tr)return'';const h=scoreRuns(m.homeScore),a=scoreRuns(m.awayScore),hb=scoreOvers(m.homeInfo),ab=scoreOvers(m.awayInfo);let battingRuns=null,ballsUsed=null,team='Chasing side';if(ab!==null&&(hb===null||ab>=hb)){battingRuns=a;ballsUsed=ab;team=m.away?.name||team}else if(hb!==null){battingRuns=h;ballsUsed=hb;team=m.home?.name||team}const need=battingRuns===null?null:Math.max(0,tr-battingRuns);let balls=targetBalls(target);if(balls===null&&ballsUsed!==null)balls=Math.max(0,120-ballsUsed);if(need===null)return `<div class="chaseBox"><b>Target ${tr}</b></div>`;const rrr=balls>0?((need*6)/balls).toFixed(2):null;return `<div class="chaseBox"><b>${esc(team)} need ${need}${balls!==null?' from '+balls+' balls':''}</b><span>Target ${tr}${rrr?' · RRR '+rrr:''}</span></div>`}
function ballOutcome(e){const s=String(e?.commentary||e?.comment||e?.description||e?.text||'').toLowerCase();if(/six|6 runs|6 run/.test(s))return['6','six'];if(/four|4 runs|4 run/.test(s))return['4','boundary'];if(/wicket|out\b|bowled|caught|lbw|run out/.test(s))return['W','wicket'];if(/no.?ball/.test(s))return['NB','extra'];if(/wide/.test(s))return['WD','extra'];const m=s.match(/\b([0-3]) runs?\b/);if(m)return[m[1],''];if(/dot ball|no run/.test(s))return['•',''];return['•','']}
function lastSixHtml(rows){const a=(Array.isArray(rows)?rows:[]).slice(-6);if(!a.length)return'';return `<div class="lastSix"><span class="lastSixTitle">LAST 6</span>${a.map(e=>{const o=ballOutcome(e);return `<span class="ballChip ${o[1]}">${o[0]}</span>`}).join('')}</div>`}
function rateValue(v){if(v===null||v===undefined||v==='')return'';if(typeof v==='number'||typeof v==='string')return String(v);if(typeof v==='object'){for(const k of ['current','value','rate','run_rate','runRate'])if(v[k]!==undefined&&v[k]!==null)return String(v[k])}return''}
function normKey(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
function deepFind(root,aliases,depth=0,seen){if(root===null||root===undefined||depth>5||typeof root!=='object')return null;seen=seen||new Set();if(seen.has(root))return null;seen.add(root);const wanted=new Set(aliases.map(normKey));for(const [k,v] of Object.entries(root))if(wanted.has(normKey(k))&&v!==null&&v!==undefined)return v;for(const v of Object.values(root)){if(v&&typeof v==='object'){const found=deepFind(v,aliases,depth+1,seen);if(found!==null&&found!==undefined)return found}}return null}
function playerInfo(v){if(v===null||v===undefined)return null;if(typeof v==='string')return{name:v,stat:''};if(typeof v!=='object')return null;const p=(v.player&&typeof v.player==='object')?v.player:v,name=p.name||p.full_name||p.fullName||p.short_name||p.shortName||p.player_name||p.playerName||v.name||'';if(!name)return null;const runs=v.runs??v.score??p.runs??p.score,balls=v.balls??v.balls_faced??v.ballsFaced??p.balls??p.balls_faced,wickets=v.wickets??p.wickets,overs=v.overs??p.overs;let stat='';if(runs!==undefined&&runs!==null)stat=String(runs)+(balls!==undefined&&balls!==null?' ('+balls+')':'');else if(wickets!==undefined&&wickets!==null)stat=String(wickets)+' wkts'+(overs!==undefined&&overs!==null?' · '+overs+' ov':'');return{name:String(name),stat}}
function currentPlayersHtml(detail){const root=detail?.inplayData||{},striker=playerInfo(deepFind(root,['striker','current_striker','currentBatsman','current_batsman','batsman','batter','on_strike'])),bowler=playerInfo(deepFind(root,['bowler','current_bowler','currentBowler','bowling','currentBowling']));if(!striker&&!bowler)return'';return `<div class="playerStrip">${striker?`<div class="playerCard"><div class="playerRole">AT CREASE</div><div class="playerName">${esc(striker.name)}</div>${striker.stat?`<div class="playerStat">${esc(striker.stat)}</div>`:''}</div>`:''}${bowler?`<div class="playerCard"><div class="playerRole">BOWLER</div><div class="playerName">${esc(bowler.name)}</div>${bowler.stat?`<div class="playerStat">${esc(bowler.stat)}</div>`:''}</div>`:''}</div>`}
function quickMarketHtml(j){if(!j)return'';const main=findMatchMarket(j);if(!main)return'';const mv=values(main).slice(0,2),sessions=sessionMarkets(j,main);return `<div class="quickHead"><b>LIVE BHAV</b><span>LIVE MARKET</span></div><div class="quickOdds">${mv.map(v=>`<div class="quickOdd"><small>${esc(v.label||'Selection')}</small><strong>${esc(v.odd)}</strong></div>`).join('')}</div>${sessions.length?`<div class="sessionTitle">SESSION MARKETS</div><div class="sessionGrid">${sessions.map(e=>`<div class="sessionCard"><b>${esc(e.market||'Session')}</b><div class="sessionVals">${values(e).slice(0,3).map(v=>`<span>${esc(v.label||'Line')} <strong>${esc(v.odd)}</strong></span>`).join('')}</div></div>`).join('')}</div>`:''}`}
function renderQuickMarket(j){const el=document.getElementById('quickMarket');if(!el)return;const h=quickMarketHtml(j);if(h){el.style.display='block';el.innerHTML=h}else{el.style.display='none';el.innerHTML=''}}
function tabsHtml(){const moreOn=['more','graphs','stats','info'].includes(detailTab);return [['match','MATCH'],['bhav','BHAV'],['scorecard','SCORECARD'],['balls','BALLS'],['more','MORE']].map(([k,l])=>`<button class="dtab ${(detailTab===k||(k==='more'&&moreOn))?'on':''}" data-tab="${k}">${l}</button>`).join('')}
function drawDetail(){const d=document.getElementById('detail'),m=detailData?.match||{},cached=bhavCache.get(matchKey(m))?.data||null;d.innerHTML=`<button class="back" onclick="backHome()">← BACK</button><div class="scorehero"><div class="scoretop"><span>${esc(league(m))} · ${esc(m.format||'')}</span><span>${esc(prettyState(m.state)||'')}</span></div><div class="scoremain"><div class="side"><div class="teamIdentity">${teamMark(m.home)}</div><div class="sname">${esc(m.home?.name||'Home')}</div><div class="sval">${display(m.homeScore)}</div><div class="ta">${esc(m.homeInfo||'')}</div></div><div class="vs">VS</div><div class="side right"><div class="teamIdentity">${teamMark(m.away)}</div><div class="sname">${esc(m.away?.name||'Away')}</div><div class="sval">${display(m.awayScore)}</div><div class="ta">${esc(m.awayInfo||'')}</div></div></div><div class="report">${esc(m.report||prettyState(m.state)||'')}${detailData?.roanuz?.target?chaseInfo(detailData.roanuz.target,m):''}${lastSixHtml(detailData?.timeline||[])}</div></div><div id="quickMarket" class="quickMarket" style="${cached?'':'display:block'}">${cached?quickMarketHtml(cached):'<div class="quickLoading">Loading live BHAV…</div>'}</div><div class="dtabs">${tabsHtml()}</div><div id="panel" class="panel"></div>`;d.querySelectorAll('.dtab').forEach(b=>b.onclick=()=>{detailTab=b.dataset.tab;drawDetail()});drawPanel()}
function inningsRows(detail){if(Array.isArray(detail?.statistics)&&detail.statistics.length)return detail.statistics;if(Array.isArray(detail?.innings))return detail.innings;return[]}
function inningScore(row){if(!row||typeof row!=='object')return'';if(row.score_str)return String(row.score_str).split(' in ')[0];const s=row.score&&typeof row.score==='object'?row.score:{},runs=s.runs??row.runs??row.score,w=s.wickets??row.wickets;if(runs===undefined||runs===null||typeof runs==='object')return'';return String(runs)+(w!==undefined&&w!==null?'/'+w:'')}
function inningOvers(row){if(!row||typeof row!=='object')return'';let v=row.overs??row.over??(row.score&&typeof row.score==='object'?row.score.overs:null);if(Array.isArray(v))return v.length>1?`${v[0]}.${v[1]} ov`:'';return v!==undefined&&v!==null&&v!==''?String(v)+(String(v).toLowerCase().includes('ov')?'':' ov'):''}
function inningName(row,i){if(!row||typeof row!=='object')return `Innings ${i+1}`;const t=row.team||row.batting_team||row.battingTeam||row.team_name||row.name;if(typeof t==='string'&&t)return t;if(t&&typeof t==='object')return t.name||t.short_name||t.shortName||`Innings ${i+1}`;return `Innings ${i+1}`}
function scorecardHtml(detail){const rows=inningsRows(detail);if(!rows.length)return'<div class="notice">Scorecard will appear as soon as innings data is available.</div>';return `<div class="innings">${rows.map((r,i)=>`<div class="inning"><div class="inningTop"><div class="inningTeam">${esc(inningName(r,i))}</div><div class="inningScore">${esc(inningScore(r)||'—')}</div></div><div class="inningMeta">${esc(inningOvers(r))}</div></div>`).join('')}</div>`}
function ballsHtml(detail){const a=Array.isArray(detail?.timeline)?detail.timeline:[];if(!a.length)return'<div class="notice">Ball-by-ball will appear with the next live update.</div>';return `<div class="balls">${a.slice().reverse().slice(0,60).map((e,i)=>`<div class="ball"><b>${esc(e.over||e.ball||('#'+(i+1)))}</b><br>${esc(e.commentary||e.comment||e.description||e.text||'Delivery update')}</div>`).join('')}</div>`}
function ptitle(t){return `<div class="ptitle"><b>${esc(t)}</b></div>`}
function fullBhavHtml(j){const es=entries(j);if(!es.length)return'<div class="notice">Live BHAV is not available for this match right now.</div>';return es.map(e=>`<div class="notice"><b>${esc(e.market||'Market')}</b><br>${values(e).map(v=>`${esc(v.label||'Selection')} <b>${esc(v.odd)}</b>`).join(' · ')}</div>`).join('')}
function drawPanel(){const p=document.getElementById('panel'),detail=detailData||{},m=detail.match||{};if(detailTab==='match'){const rr=rateValue(detail.roanuz?.runRate);p.innerHTML=ptitle('MATCH SNAPSHOT')+`<div class="notice">${rr?`<div class="metricRow"><span class="metric">CRR <b>${esc(rr)}</b></span></div>`:''}${currentPlayersHtml(detail)}${lastSixHtml(detail.timeline||[])}</div>`}else if(detailTab==='scorecard'){p.innerHTML=ptitle('SCORECARD')+scorecardHtml(detail)}else if(detailTab==='balls'){p.innerHTML=ptitle('BALL-BY-BALL')+ballsHtml(detail)}else if(detailTab==='more'){p.innerHTML=ptitle('MORE')+'<div class="moreGrid"><button class="moreItem" data-more="graphs">GRAPHS<span>Match trends</span></button><button class="moreItem" data-more="stats">STATS<span>Match numbers</span></button><button class="moreItem" data-more="info">INFO<span>Venue and match details</span></button></div>';p.querySelectorAll('[data-more]').forEach(b=>b.onclick=()=>{detailTab=b.dataset.more;drawDetail()})}else if(detailTab==='bhav'){const key=matchKey(m),cached=bhavCache.get(key)?.data||null;p.innerHTML=ptitle('LIVE BHAV')+(cached?fullBhavHtml(cached):'<div class="loading"><div class="spin"></div>Loading…</div>');getBhav(key).then(j=>{if(detailTab==='bhav'&&document.getElementById('panel'))document.getElementById('panel').innerHTML=ptitle('LIVE BHAV')+fullBhavHtml(j)})}else if(detailTab==='graphs'){p.innerHTML=ptitle('MATCH TRENDS')+'<div class="notice">Trend data is loading…</div>';api({action:'graphs',key:matchKey(m)}).then(j=>{const g=j.graphs||{},items=Object.entries(g).slice(0,8);p.innerHTML=ptitle('MATCH TRENDS')+(items.length?items.map(([k,v])=>`<div class="kv"><span>${esc(k.replace(/_/g,' '))}</span><b>${esc(typeof v==='number'||typeof v==='string'?v:'Available')}</b></div>`).join(''):'<div class="notice">No trend data is available yet.</div>')}).catch(()=>p.innerHTML=ptitle('MATCH TRENDS')+'<div class="notice">Trend data is temporarily unavailable.</div>')}else if(detailTab==='stats'){p.innerHTML=ptitle('MATCH STATS')+scorecardHtml(detail)}else{const venue=detail.venue||{},items=[['Venue',venue.name],['City',venue.city],['Format',m.format],['Status',prettyState(m.state)]].filter(x=>x[1]);p.innerHTML=ptitle('MATCH INFO')+(items.length?items.map(x=>`<div class="kv"><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join(''):'<div class="notice">Match information will appear here when available.</div>')}}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{allMatches=[];load(b.dataset.mode,true)});
document.getElementById('refresh').onclick=()=>load(mode,true);
document.getElementById('search').oninput=render;
document.querySelector('.bottom').onclick=e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.bottom button').forEach(x=>x.classList.toggle('on',x===b));const nav=b.dataset.nav;if(nav==='home'||nav==='live'){backHome();if(mode!=='live'||Date.now()-lastHomeLoad>10000){allMatches=[];load('live',true)}}else if(nav==='fixtures'){backHome();allMatches=[];load('upcoming',true)}else{backHome();setTimeout(()=>document.getElementById('search').focus(),100)}};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&mode==='live'&&document.getElementById('home').style.display!=='none'&&Date.now()-lastHomeLoad>15000)load('live')});
window.addEventListener('unhandledrejection',e=>console.error('IBETIN UI promise error',e.reason));
window.addEventListener('error',e=>console.error('IBETIN UI error',e.message));
load('live',true);
</script>
</body>
</html>'''
    return html.replace('__API_PATH__', API_PATH)


v23._page = _page_v30
v23.liveline._page = _page_v30


def _self_test() -> None:
    page = _page_v30()
    checks = {
        'single_ui_owner': 'ibetin_liveline_v26' not in page and 'ibetin_liveline_v27' not in page,
        'home_tabs': 'UPCOMING' in page and 'RESULTS' in page,
        'detail_tabs': "['match','MATCH']" in page and "['bhav','BHAV']" in page and "['more','MORE']" in page,
        'inline_bhav': 'id="quickMarket"' in page and 'LIVE BHAV' in page and 'SESSION MARKETS' in page,
        'shared_bhav_cache': 'bhavCache' in page and 'BHAV_TTL=10000' in page and 'getBhav' in page,
        'main_odds': 'MATCH ODDS' in page and 'homeOddsHtml' in page,
        'no_provider_internals': 'ROANUZ V5 · PRIMARY DATA' not in page and 'HIGHLIGHTLY FALLBACK' not in page,
        'no_raw_json_ui': 'JSON.stringify' not in page,
        'scope_safe': 'detailData?.roanuz?.target' in page,
        'fast_score_hydrate': "action:'score'" in page,
        'safe_bottom_spacing': 'calc(175px + env(safe-area-inset-bottom))' in page,
        'telegram_back': 'tg.BackButton' in page,
        'friendly_errors': 'Unable to load match details.' in page,
    }
    live_matches = 0
    detail_ok = False
    source = ''
    try:
        rows, source = v25._fast_matches_cached('live')
        live_matches = len(rows or [])
        if rows:
            key = str(rows[0].get('roanuzMatchKey') or rows[0].get('id') or '')
            if key:
                detail, _ = v25._match_detail_cached(key)
                detail_ok = isinstance(detail, dict) and isinstance(detail.get('match'), dict)
    except Exception as exc:
        logger.warning('IBETIN V30 runtime self-test provider probe skipped: %s', str(exc)[:160])
    ok = all(checks.values()) and (detail_ok or live_matches == 0)
    (logger.info if ok else logger.error)(
        'IBETIN V30 unified self-test %s checks=%s live_matches=%s source=%s detail_ok=%s',
        'PASS' if ok else 'FAILED', checks, live_matches, source, detail_ok,
    )
    if not ok:
        raise RuntimeError(f'V30 unified UI self-test failed: {checks}')


_self_test()
logger.info('IBETIN V30 installed: inline BHAV + session markets + full BHAV tab over frozen V25 fast feed/cache')


# ---------------------------------------------------------------------------
# IBETIN V35 isolated premium preview
# Production /admin/liveline-ibetinv23 continues to use _page_v30 unchanged.
# ---------------------------------------------------------------------------
IBETIN_V35_PREVIEW_PATH = "/admin/ibetin-v35-preview"

IBETIN_V35_PREVIEW_CSS = r"""
/* V35 PREVIEW ONLY */
:root{--pbg:#020814;--ppanel:#06182b;--pline:#153f63;--pblue:#1497ff;--pgreen:#23d98b;--ppurple:#794cff;--ptext:#f4f9ff;--pmuted:#8fa8bf}
html,body{background:radial-gradient(circle at 50% -10%,#0b315e 0,#041425 35%,#020814 76%)!important;color:var(--ptext)!important}
body{padding-bottom:calc(105px + env(safe-area-inset-bottom))!important}
.top{background:linear-gradient(125deg,#031125,#092c55 72%,#12396b)!important;border-bottom:1px solid rgba(42,155,255,.24)!important;box-shadow:0 12px 32px rgba(0,0,0,.30)!important}
.mark{background:linear-gradient(145deg,#ffd553,#ffae17)!important;color:#152235!important;border-radius:12px!important}
.brand b{color:#fff!important}.brand span{color:#b7cae0!important}
.liveDot{background:rgba(20,157,91,.22)!important;border-color:#2bdd8d!important;box-shadow:0 0 20px rgba(35,217,139,.14)!important}
.tab{background:#0a2747!important;color:#a9bed2!important}.tab.on{background:linear-gradient(135deg,#178fff,#0a66d5)!important;color:#fff!important;box-shadow:0 8px 24px rgba(20,126,255,.22)!important}
.main{background:transparent!important}.search,.refresh{background:#06182b!important;color:#edf7ff!important;border-color:#154262!important;box-shadow:none!important}.search::placeholder{color:#6f8aa4!important}
.status,.league{color:#8da8c0!important}
.match{background:linear-gradient(180deg,#071b30,#051522)!important;border:1px solid #164463!important;border-left:4px solid #2b9cff!important;box-shadow:0 15px 34px rgba(0,0,0,.25)!important}.match.live{border-left-color:#ff536f!important}
.fmt,.ta,.si,.foot{color:#8da7bf!important}.tn{color:#fff!important}.sc{color:#f8fbff!important}.badge{background:#102b47!important;color:#a8c5df!important}.badge.live{background:rgba(255,83,111,.14)!important;color:#ff758a!important}
.oddsRow{background:#051522!important;border-top-color:#143b5a!important}.oddBox{background:linear-gradient(135deg,#0b6fd7,#0a3b78)!important;border-color:#1d99ff!important}.oddBox:nth-of-type(3){background:linear-gradient(135deg,#119c61,#075d3d)!important;border-color:#25d98b!important}.oddLabel{color:#cfe4f5!important}.oddValue{color:#fff!important}
.detail{background:transparent!important;padding-top:12px!important}.back{background:#08213a!important;color:#d9ecff!important;border:1px solid #174565!important;box-shadow:none!important}
.scorehero{background:radial-gradient(circle at 50% 10%,rgba(25,139,255,.20),transparent 30%),linear-gradient(180deg,#082342,#06182b)!important;border-color:#174c70!important;box-shadow:0 18px 38px rgba(0,0,0,.28)!important}
.scoretop{border-bottom-color:#16415f!important;color:#9cb5cc!important}.sname{color:#d9ecff!important}.sval{color:#fff!important}.vs{background:#0b2848!important;color:#d9ecff!important;border:1px solid #246da8!important}.report{background:#061729!important;border-top-color:#16415f!important;color:#c5d8e8!important}
.quickMarket,.panel{background:linear-gradient(180deg,#071b30,#061522)!important;border-color:#174767!important;box-shadow:0 14px 32px rgba(0,0,0,.24)!important}.quickHead b,.ptitle b{color:#fff!important}.quickHead span,.sessionTitle{color:#38b9ff!important}
.quickOdd{background:linear-gradient(135deg,#0a78e8,#08448d)!important;border-color:#20a4ff!important}.quickOdd:nth-child(2){background:linear-gradient(135deg,#10a466,#075c3d)!important;border-color:#2cde8c!important}.quickOdd small{color:#d7edff!important}.quickOdd strong{color:#fff!important;font-size:24px!important}
.sessionGrid{display:flex!important;gap:8px!important;overflow-x:auto!important;scrollbar-width:none!important}.sessionGrid::-webkit-scrollbar{display:none!important}.sessionCard{flex:0 0 min(74vw,240px)!important;background:linear-gradient(135deg,#0a448f,#082750)!important;border-color:#367ee0!important}.sessionCard:nth-child(even){background:linear-gradient(135deg,#5b2aad,#2f1c66)!important;border-color:#9b67ff!important}.sessionCard b,.sessionVals strong{color:#fff!important}.sessionVals{color:#c8dcef!important}
.dtab{background:#0a2139!important;color:#9eb7cd!important;border-color:#173f5f!important}.dtab.on{background:linear-gradient(135deg,#1594ff,#1268e7)!important;color:#fff!important;border-color:#2ca9ff!important}
.notice,.inning,.ball,.moreItem,.playerCard{background:#081a2c!important;border-color:#173e5d!important;color:#bad0e2!important}.playerName,.inningTeam,.inningScore,.moreItem,.kv b{color:#fff!important}.metric{background:#0b2a49!important;color:#a9c3d9!important}.ballChip{background:#244764!important;color:#fff!important}.ballChip.boundary{background:#1398ef!important}.ballChip.six{background:#7650e3!important}.ballChip.wicket{background:#e94d68!important}
.bottom{background:rgba(2,11,23,.98)!important;border:1px solid #153854!important;box-shadow:0 18px 40px rgba(0,0,0,.42)!important}.bottom .on{background:linear-gradient(180deg,rgba(27,137,255,.24),rgba(11,76,139,.16))!important}
/* V35 NAV CLEARANCE FIX */
.main{padding-bottom:calc(185px + env(safe-area-inset-bottom))!important}
.detail{padding-bottom:calc(185px + env(safe-area-inset-bottom))!important}
.bottom{left:16px!important;right:16px!important;bottom:calc(8px + env(safe-area-inset-bottom))!important;padding:6px!important;border-radius:18px!important}
.bottom button{height:48px!important;font-size:8px!important}
.bottom b{font-size:17px!important;margin-bottom:1px!important}
body:before{content:"PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#7b43f6;color:#fff;font-size:8px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}
.previewHomeOdds{padding:12px 13px 13px;border-top:1px solid #153d5d;background:#051522}
.previewOddsTitle{font-size:9px;font-weight:1000;color:#8fb1cc;letter-spacing:.7px;margin-bottom:8px}
.previewHomeGrid,.previewBhavGrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.previewPrice{border-radius:14px;padding:12px 13px;border:1px solid #25a5ff;background:linear-gradient(135deg,#0b79e7,#083f86);min-width:0}
.previewPrice.green{border-color:#31df90;background:linear-gradient(135deg,#11a868,#075b3c)}
.previewPrice small{display:block;color:#d8edff;font-size:9px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.previewPrice strong{display:block;color:#fff;font-size:28px;line-height:1;margin-top:6px;font-weight:1000;font-variant-numeric:tabular-nums}
.previewBhav{margin-top:2px}
.previewBhavHead{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
.previewBhavHead b{font-size:17px;color:#fff}.previewBhavHead span{font-size:9px;color:#31baff;font-weight:1000}
.previewHist{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #17496d;border-radius:12px;overflow:hidden;margin-top:9px}
.previewHist div{padding:8px 4px;text-align:center;background:#08223c;border-right:1px solid #17496d}.previewHist div:last-child{border-right:0}
.previewHist span{display:block;color:#7f9db7;font-size:7px;font-weight:900}.previewHist b{display:block;color:#fff;font-size:13px;margin-top:3px;font-variant-numeric:tabular-nums}.previewHist .cur b{color:#2db8ff}
.previewSessionTitle{font-size:10px;font-weight:1000;color:#35b9ff;margin:13px 0 7px}
.previewSessionStrip{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}.previewSessionStrip::-webkit-scrollbar{display:none}
.previewSessionCard{flex:0 0 min(76vw,250px);padding:11px;border-radius:13px;background:linear-gradient(135deg,#0b468f,#092855);border:1px solid #397fd7}
.previewSessionCard:nth-child(even){background:linear-gradient(135deg,#5a2bad,#2d1a64);border-color:#9c68ff}
.previewSessionCard>b{font-size:11px;color:#fff}.previewSessionVals{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.previewSessionVals span{padding:5px 7px;border-radius:8px;background:rgba(255,255,255,.08);font-size:8px;color:#c6d9ea}.previewSessionVals b{color:#fff;font-size:12px;margin-left:3px}
.previewMarketList{display:grid;gap:8px}.previewMarketRow{background:#081a2c;border:1px solid #17405f;border-radius:12px;padding:11px}
.previewMarketRow>b{display:block;color:#fff;font-size:11px;margin-bottom:7px}.previewMarketVals{display:flex;gap:8px;flex-wrap:wrap;color:#a8c1d6;font-size:10px}.previewMarketVals strong{color:#fff}

"""


IBETIN_V35_MARKET_JS = r"""
<script>
(function(){
  function previewPriceFmt(v){
    if(v===null||v===undefined||v==='')return '—';
    const n=Number(v);
    return Number.isFinite(n)?esc(n.toFixed(2)):esc(v);
  }
  function previewLineFmt(v){
    if(v===null||v===undefined||v==='')return '—';
    const n=Number(v);
    if(!Number.isFinite(n))return esc(v);
    if(Number.isInteger(n))return esc(String(n));
    return esc(String(Math.round((n+Number.EPSILON)*100)/100));
  }
  homeOddsHtml=function(m){
    if(mode!=='live')return'';
    const c=bhavCache.get(matchKey(m));if(!c?.data)return'';
    const market=findMatchMarket(c.data);if(!market)return'';
    const vs=values(market).slice(0,2);
    return `<div class="previewHomeOdds"><div class="previewOddsTitle">MATCH ODDS</div><div class="previewHomeGrid">${vs.map((x,i)=>`<div class="previewPrice ${i===1?'green':''}"><small>${esc(x.label||'Selection')}</small><strong>${previewPriceFmt(x.odd)}</strong></div>`).join('')}</div></div>`;
  };
  quickMarketHtml=function(j){
    if(!j)return'';
    const main=findMatchMarket(j);if(!main)return'';
    const mv=values(main).slice(0,2),sessions=sessionMarkets(j,main);
    const current=mv[0]?.odd;
    return `<div class="previewBhav"><div class="previewBhavHead"><b>↗ LIVE BHAV</b><span>LIVE MARKET</span></div><div class="previewBhavGrid">${mv.map((v,i)=>`<div class="previewPrice ${i===1?'green':''}"><small>${esc(v.label||'Selection')}</small><strong>${previewPriceFmt(v.odd)}</strong></div>`).join('')}</div><div class="previewHist"><div><span>OPEN</span><b>—</b></div><div><span>MIN</span><b>—</b></div><div><span>MAX</span><b>—</b></div><div class="cur"><span>CURRENT</span><b>${previewPriceFmt(current)}</b></div></div>${sessions.length?`<div class="previewSessionTitle">SESSION MARKET</div><div class="previewSessionStrip">${sessions.map(e=>`<div class="previewSessionCard"><b>${esc(e.market||'Session')}</b><div class="previewSessionVals">${values(e).slice(0,4).map(v=>`<span>${esc(v.label||'Line')} <b>${previewLineFmt(v.odd)}</b></span>`).join('')}</div></div>`).join('')}</div>`:''}</div>`;
  };
  fullBhavHtml=function(j){
    const es=entries(j);if(!es.length)return'<div class="notice">Live BHAV is not available for this match right now.</div>';
    return `<div class="previewMarketList">${es.map(e=>{const session=/over|session|runs|line|total|fancy|innings/i.test(String(e?.market||''));return `<div class="previewMarketRow"><b>${esc(e.market||'Market')}</b><div class="previewMarketVals">${values(e).map(v=>`<span>${esc(v.label||'Selection')} <strong>${session?previewLineFmt(v.odd):previewPriceFmt(v.odd)}</strong></span>`).join('')}</div></div>`}).join('')}</div>`;
  };

  let previewWarmCycle=0;
  function previewWarmBhav(){
    if(mode!=='live'||!Array.isArray(allMatches)||!allMatches.length)return;
    const cycle=++previewWarmCycle;
    allMatches.slice(0,8).forEach((m,i)=>{
      const key=matchKey(m);if(!key)return;
      const cached=bhavCache.get(key);
      if(cached?.data && Date.now()-cached.ts < BHAV_TTL)return;
      setTimeout(()=>{
        if(cycle!==previewWarmCycle||mode!=='live')return;
        getBhav(key,false).then(()=>{
          if(cycle===previewWarmCycle && document.getElementById('home')?.style.display!=='none'){
            try{previewBaseRender()}catch(e){}
          }
        }).catch(()=>{});
      },i*90);
    });
  }

  const previewBaseRender=render;
  render=function(){
    previewBaseRender();
    if(mode==='live')previewWarmBhav();
  };

  const previewBaseOpenMatch=openMatch;
  openMatch=async function(key){
    if(!key)return;
    const bhavPromise=getBhav(key,false);
    const detailPromise=previewBaseOpenMatch(key);
    try{
      const market=await bhavPromise;
      if(market && document.getElementById('quickMarket'))renderQuickMarket(market);
      if(market && detailTab==='bhav' && document.getElementById('panel'))drawPanel();
    }catch(e){}
    return await detailPromise;
  };

  try{
    if(allMatches?.length){previewBaseRender();previewWarmBhav()}
    if(detailData)drawDetail();
  }catch(e){console.error('IBETIN preview renderer',e)}
  window.__IBETIN_V35_MARKET_RENDERER__=true;
  window.__IBETIN_V35_BHAV_PREFETCH__=true;
})();
</script>
"""


def _page_v35_preview() -> str:
    html = _page_v30()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Premium UI Preview</title>", 1)
    html = html.replace("</style>", IBETIN_V35_PREVIEW_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V35_MARKET_JS + "\n</body>", 1)
    return html


IBETIN_V35_PREVIEW_BADGE_CSS = 'body:before{content:"PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#7b43f6;color:#fff;font-size:8px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}'


def _page_v35_production() -> str:
    html = _page_v30()
    live_css = IBETIN_V35_PREVIEW_CSS.replace(IBETIN_V35_PREVIEW_BADGE_CSS, "")
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Live Cricket</title>", 1)
    html = html.replace("</style>", live_css + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V35_MARKET_JS + "\n</body>", 1)
    return html


IBETIN_V36_BRAND_PREVIEW_PATH = "/admin/ibetin-v36-brand-preview"

IBETIN_V36_BRAND_CSS = r"""
/* V36 IBETIN.COM BRAND PREVIEW ONLY */
.brand b{font-size:20px!important;letter-spacing:.35px!important}
.brand b .dotcom{color:#2fb7ff;font-weight:1000}
.brand span{font-size:9px!important;letter-spacing:1.2px!important;font-weight:900!important;color:#9fc0db!important}
.mark{position:relative!important;background:linear-gradient(145deg,#ffe071,#ffb319)!important;box-shadow:0 8px 22px rgba(255,180,25,.20)!important}
.mark:after{content:".COM";position:absolute;right:-8px;bottom:-5px;background:#0b6ee0;color:#fff;font-size:6px;line-height:1;font-weight:1000;padding:4px 5px;border-radius:6px;border:2px solid #06182b}
.liveDot{font-size:9px!important;letter-spacing:.5px!important}
.top{padding-top:16px!important}
.ibBrandSig{margin:4px 16px 16px;padding:12px 14px;border:1px solid #143d5b;border-radius:14px;background:linear-gradient(135deg,rgba(9,37,66,.78),rgba(5,22,39,.82));display:flex;align-items:center;justify-content:space-between;gap:10px}
.ibBrandSig b{font-size:12px;color:#fff;letter-spacing:.5px}.ibBrandSig span{font-size:8px;color:#7fa4c3;letter-spacing:.8px;font-weight:900}
.loading:after{content:"IBETIN.COM";display:block;margin-top:7px;color:#3fb5ff;font-size:8px;font-weight:1000;letter-spacing:1.5px}
.match{position:relative}.match:after{content:"IBETIN.COM";position:absolute;right:10px;bottom:7px;font-size:6px;font-weight:1000;letter-spacing:1px;color:rgba(111,164,206,.35);pointer-events:none}
.scorehero:before{content:"IBETIN.COM LIVE";display:block;padding:7px 14px;background:linear-gradient(90deg,rgba(16,135,255,.12),rgba(22,210,137,.08));border-bottom:1px solid #153e5e;color:#69c8ff;font-size:7px;font-weight:1000;letter-spacing:1.2px}
body:before{content:"BRAND PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#0a76df;color:#fff;font-size:7px;font-weight:1000;letter-spacing:1px;padding:5px 8px;border-radius:999px;pointer-events:none}
"""


def _page_v36_brand_preview() -> str:
    html = _page_v35_production()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN.COM · Live Sports</title>", 1)
    html = html.replace(
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div>',
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN<span class="dotcom">.COM</span></b><span>LIVE SPORTS</span></div></div><div class="liveDot">● LIVE NOW</div>',
        1,
    )
    html = html.replace(
        'placeholder="Search match, team or tournament"',
        'placeholder="Search IBETIN Sports"',
        1,
    )
    html = html.replace(
        '<div id="status" class="status">Loading live cricket…</div>',
        '<div id="status" class="status">IBETIN.COM is loading live cricket…</div>',
        1,
    )
    html = html.replace(
        '<nav class="bottom">',
        '<div class="ibBrandSig"><b>IBETIN.COM</b><span>LIVE SPORTS · FAST SCORES</span></div><nav class="bottom">',
        1,
    )
    html = html.replace(
        "tg.setHeaderColor('#071a34');tg.setBackgroundColor('#eef3f8')",
        "tg.setHeaderColor('#020814');tg.setBackgroundColor('#020814')",
        1,
    )
    html = html.replace(
        "Unable to load match details.",
        "IBETIN.COM could not load this match right now.",
    )
    html = html.replace(
        "</style>",
        IBETIN_V36_BRAND_CSS + "\n</style>",
        1,
    )
    return html


IBETIN_V37_PROMO_PREVIEW_PATH = "/admin/ibetin-v37-promo-preview"

IBETIN_V37_PROMO_CSS = r"""
/* V37 LIVE LINE x IBETIN.COM PROMO PREVIEW */
.brand b{font-size:20px!important;letter-spacing:.6px!important}
.brand span{font-size:9px!important;letter-spacing:1.2px!important;font-weight:900!important;color:#9bb8d1!important}
.liveLineSub{display:block;margin-top:2px;font-size:8px;color:#74baff;font-weight:900;letter-spacing:.7px}
.ibPromoCard{margin:11px 0 0;border:1px solid #1a5e8b;border-radius:16px;background:linear-gradient(135deg,#08284a,#071a31 62%,#09263d);padding:13px;box-shadow:0 12px 28px rgba(0,0,0,.18)}
.ibPromoTop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.ibPromoBrand{font-size:12px;font-weight:1000;color:#fff;letter-spacing:.5px}.ibPromoBrand span{color:#38b8ff}
.ibPromoPill{font-size:7px;font-weight:1000;color:#9ed2f5;border:1px solid #215c83;background:#0b2a47;border-radius:999px;padding:5px 7px;letter-spacing:.7px}
.ibPromoTitle{font-size:14px;font-weight:1000;color:#fff;margin-bottom:4px}.ibPromoCopy{font-size:9px;line-height:1.45;color:#91abc2}
.ibPromoBtn{width:100%;margin-top:10px;height:44px;border:0;border-radius:12px;background:linear-gradient(135deg,#1496ff,#0d68d4);color:#fff;font-size:11px;font-weight:1000;letter-spacing:.4px}
.ibPromoLegal{margin-top:7px;font-size:7px;line-height:1.4;color:#6f8ca5;text-align:center}
.ibHomePromo{display:block;width:100%;border:0;border-top:1px solid #17405f;background:#061a2d;color:#58bdff;text-align:left;padding:9px 13px;font-size:9px;font-weight:1000;letter-spacing:.2px}
.ibHomePromo small{float:right;color:#6689a6;font-size:7px;font-weight:900}
.ibQuickPromo{display:flex;align-items:center;justify-content:space-between;gap:9px;margin-top:9px;padding:9px 10px;border:1px solid #1b5a82;border-radius:11px;background:linear-gradient(135deg,#09284a,#071a30)}
.ibQuickPromo div{min-width:0}.ibQuickPromo b{display:block;color:#fff;font-size:10px}.ibQuickPromo span{display:block;color:#7fa1bd;font-size:7px;margin-top:2px}
.ibQuickPromo button{flex:0 0 auto;border:0;border-radius:9px;background:#0f82e9;color:#fff;padding:8px 10px;font-size:8px;font-weight:1000}
.ibPowered{margin:2px 16px 14px;text-align:center;color:#6f8da7;font-size:7px;font-weight:900;letter-spacing:1px}
.detail{padding-bottom:calc(240px + env(safe-area-inset-bottom))!important}
body:before{content:"V37 PROMO PREVIEW";position:fixed;right:10px;top:8px;z-index:9999;background:#0d73d7;color:#fff;font-size:7px;font-weight:1000;letter-spacing:.9px;padding:5px 8px;border-radius:999px;pointer-events:none}
"""

IBETIN_V37_PROMO_JS = r"""
<script>
(function(){
  const IBETIN_LIVE_CRICKET_URL='https://ibetin.com/live/cricket?utm_source=telegram&utm_medium=miniapp&utm_campaign=ibetin_liveline';
  function openIbetinLive(){
    try{
      if(window.Telegram&&Telegram.WebApp&&typeof Telegram.WebApp.openLink==='function'){
        Telegram.WebApp.openLink(IBETIN_LIVE_CRICKET_URL);
        return;
      }
    }catch(e){}
    window.open(IBETIN_LIVE_CRICKET_URL,'_blank','noopener,noreferrer');
  }
  window.openIbetinLive=openIbetinLive;

  const v37BaseHomeOddsHtml=homeOddsHtml;
  homeOddsHtml=function(m){
    const base=v37BaseHomeOddsHtml(m);
    if(mode!=='live'||!base)return base;
    return base+'<button class="ibHomePromo" onclick="event.stopPropagation();openIbetinLive()">More live markets on ibetin.com → <small>18+</small></button>';
  };

  function quickPromoHtml(){
    return '<div class="ibQuickPromo" id="ibetinQuickPromo">'
      +'<div><b>More live markets on ibetin.com</b><span>18+ · Please gamble responsibly</span></div>'
      +'<button onclick="openIbetinLive()">VIEW →</button>'
      +'</div>';
  }

  const v37BaseQuickMarketHtml=quickMarketHtml;
  quickMarketHtml=function(j){
    const base=v37BaseQuickMarketHtml(j);
    if(!base)return base;
    const marker='</div><div class="previewHist">';
    if(base.includes(marker)){
      return base.replace(marker,'</div>'+quickPromoHtml()+'<div class="previewHist">');
    }
    return base+quickPromoHtml();
  };

  function promoHtml(){
    return '<div class="ibPromoCard" id="ibetinPromoCard">'
      +'<div class="ibPromoTop"><div class="ibPromoBrand">IBETIN<span>.COM</span></div><div class="ibPromoPill">18+ · BET RESPONSIBLY</div></div>'
      +'<div class="ibPromoTitle">More live cricket markets</div>'
      +'<div class="ibPromoCopy">Continue to ibetin.com to view the live cricket betting section and available markets.</div>'
      +'<button class="ibPromoBtn" onclick="openIbetinLive()">VIEW LIVE CRICKET MARKETS →</button>'
      +'<div class="ibPromoLegal">18+ only. Availability depends on your location and local laws. Please gamble responsibly.</div>'
      +'</div>';
  }

  const v37BaseDrawDetail=drawDetail;
  drawDetail=function(){
    v37BaseDrawDetail();
    try{
      const q=document.getElementById('quickMarket');
      if(q){
        if(!document.getElementById('ibetinPromoCard')){
          q.insertAdjacentHTML('afterend',promoHtml());
        }
      }
    }catch(e){console.error('IBETIN V37 promo card',e)}
  };

  try{
    if(allMatches?.length)render();
    if(detailData)drawDetail();
  }catch(e){}
  window.__IBETIN_V37_PROMO__=true;
})();
</script>
"""


def _page_v37_promo_preview() -> str:
    html = _page_v35_production()
    html = html.replace("<title>IBETIN Live Cricket</title>", "<title>IBETIN Live Line · Powered by ibetin.com</title>", 1)
    html = html.replace(
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE CRICKET</span></div></div><div class="liveDot">● LIVE</div>',
        '<div class="brand"><div class="mark">I</div><div><b>IBETIN</b><span>LIVE LINE</span><small class="liveLineSub">POWERED BY IBETIN.COM</small></div></div><div class="liveDot">● LIVE</div>',
        1,
    )
    html = html.replace(
        '<nav class="bottom">',
        '<div class="ibPowered">IBETIN LIVE LINE · POWERED BY IBETIN.COM</div><nav class="bottom">',
        1,
    )
    html = html.replace("</style>", IBETIN_V37_PROMO_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V37_PROMO_JS + "\n</body>", 1)
    return html


IBETIN_V38_MATCH_PULSE_PATH = "/admin/ibetin-v38-match-pulse"

IBETIN_V38_MATCH_PULSE_CSS = r"""
/* V38 MATCH PULSE PREVIEW */
body:before{content:"V38 MATCH PULSE"!important;background:#176fe5!important}
.v38Pulse{margin:10px 0 12px;border:1px solid #1a547d;border-radius:17px;background:linear-gradient(145deg,#071b31,#092845 68%,#082238);padding:13px;box-shadow:0 14px 34px rgba(0,0,0,.22)}
.v38PulseHead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px}
.v38PulseHead b{font-size:15px;color:#fff;letter-spacing:.2px}.v38PulseHead span{font-size:7px;font-weight:1000;color:#63c3ff;letter-spacing:1px}
.v38PulseMetrics{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:10px}
.v38PulseMetric{padding:9px 8px;border-radius:11px;border:1px solid #174566;background:#061625;min-width:0}
.v38PulseMetric span{display:block;font-size:7px;color:#7695ae;font-weight:900;letter-spacing:.7px}
.v38PulseMetric b{display:block;margin-top:3px;font-size:15px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.v38Recent{padding:10px;border-radius:12px;background:#061725;border:1px solid #163e5c}
.v38RecentTop{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}
.v38RecentTop b{font-size:9px;color:#fff}.v38RecentTop span{font-size:7px;color:#7898b2}
.v38Balls{display:flex;gap:5px;overflow-x:auto;scrollbar-width:none}.v38Balls::-webkit-scrollbar{display:none}
.v38Ball{flex:0 0 27px;height:27px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#0b2943;border:1px solid #245578;color:#fff;font-size:9px;font-weight:1000}
.v38Ball.boundary{background:#0b6c49;border-color:#22bd7b}.v38Ball.six{background:#6140b1;border-color:#9d77ff}.v38Ball.wicket{background:#8e2436;border-color:#e55068}.v38Ball.extra{background:#7b5a13;border-color:#d7ac39}
.v38PulseSummary{margin-top:9px;color:#a9c0d4;font-size:9px;line-height:1.45}.v38PulseSummary b{color:#fff}
.v38Latest{margin-top:7px;padding-top:8px;border-top:1px solid #143952;color:#87a8c1;font-size:8px;line-height:1.45}
.v38Pulse .playerStrip{margin-top:10px!important}
.v38HideNav{display:none!important}
.detail{padding-bottom:calc(90px + env(safe-area-inset-bottom))!important}
"""

IBETIN_V38_MATCH_PULSE_JS = r"""
<script>
(function(){
  function pulseMetric(label,value){
    if(value===null||value===undefined||value==='')return '';
    return '<div class="v38PulseMetric"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>';
  }
  function pulseBallClass(o){
    if(!o||!o[1])return '';
    return o[1];
  }
  function latestText(e){
    if(!e||typeof e!=='object')return '';
    return String(e.commentary||e.comment||e.description||e.text||'').trim();
  }
  function matchPulseHtml(detail){
    detail=detail||{};
    const m=detail.match||{};
    const rows=Array.isArray(detail.timeline)?detail.timeline:[];
    const recent=rows.slice(-12);
    const crr=rateValue(detail.roanuz?.runRate)||rateValue(deepFind(detail,['current_run_rate','currentRunRate','crr']));
    const rrr=rateValue(deepFind(detail,['required_run_rate','requiredRunRate','required_rate','requiredRate','rrr']));
    const target=targetRuns(detail.roanuz?.target)||targetRuns(deepFind(detail,['target']));
    const metrics=[
      pulseMetric('CRR',crr),
      pulseMetric('RRR',rrr),
      pulseMetric('TARGET',target)
    ].filter(Boolean).join('');

    let fours=0,sixes=0,wickets=0;
    const balls=recent.map(e=>{
      const o=ballOutcome(e);
      if(o[0]==='4')fours++;
      if(o[0]==='6')sixes++;
      if(o[0]==='W')wickets++;
      return '<span class="v38Ball '+pulseBallClass(o)+'">'+esc(o[0])+'</span>';
    }).join('');

    const boundaryCount=fours+sixes;
    const facts=[];
    if(boundaryCount)facts.push(boundaryCount+' '+(boundaryCount===1?'boundary':'boundaries'));
    if(wickets)facts.push(wickets+' '+(wickets===1?'wicket':'wickets'));
    if(recent.length && !facts.length)facts.push('no boundary or wicket in the recent '+recent.length+' deliveries');
    const latest=latestText(recent[recent.length-1]);
    const latestSafe=latest.length>120?latest.slice(0,117)+'…':latest;

    return '<div class="v38Pulse">'
      +'<div class="v38PulseHead"><b>⚡ MATCH PULSE</b><span>5-SECOND VIEW</span></div>'
      +(metrics?'<div class="v38PulseMetrics">'+metrics+'</div>':'')
      +(recent.length?'<div class="v38Recent"><div class="v38RecentTop"><b>LAST '+recent.length+' DELIVERIES</b><span>RECENT PHASE</span></div><div class="v38Balls">'+balls+'</div>'
        +(facts.length?'<div class="v38PulseSummary"><b>Recent:</b> '+esc(facts.join(' · '))+'</div>':'')
        +(latestSafe?'<div class="v38Latest"><b>Latest:</b> '+esc(latestSafe)+'</div>':'')
        +'</div>':'<div class="v38PulseSummary">Live context will update as delivery data arrives.</div>')
      +currentPlayersHtml(detail)
      +'</div>';
  }

  function v38SetDetailMode(on){
    const bottom=document.querySelector('.bottom');
    const powered=document.querySelector('.ibPowered');
    if(bottom)bottom.classList.toggle('v38HideNav',!!on);
    if(powered)powered.classList.toggle('v38HideNav',!!on);
  }

  const v38BaseDrawDetail=drawDetail;
  drawDetail=function(){
    v38BaseDrawDetail();
    try{
      v38SetDetailMode(true);
      const hero=document.querySelector('#detail .scorehero');
      if(hero && !document.getElementById('v38Pulse')){
        const wrap=document.createElement('div');
        wrap.id='v38Pulse';
        wrap.innerHTML=matchPulseHtml(detailData||{});
        hero.insertAdjacentElement('afterend',wrap);
      }
    }catch(e){console.error('IBETIN V38 Match Pulse',e)}
  };

  const v38BaseOpenMatch=openMatch;
  openMatch=async function(key){
    v38SetDetailMode(true);
    return await v38BaseOpenMatch(key);
  };

  const v38BaseBackHome=backHome;
  backHome=function(){
    const out=v38BaseBackHome();
    v38SetDetailMode(false);
    return out;
  };

  try{
    if(detailData)drawDetail();
    else v38SetDetailMode(false);
  }catch(e){}
  window.__IBETIN_V38_MATCH_PULSE__=true;
})();
</script>
"""


def _page_v38_match_pulse() -> str:
    html = _page_v37_promo_preview()
    html = html.replace("<title>IBETIN Live Line · Powered by ibetin.com</title>", "<title>IBETIN Live Line · Match Pulse V38</title>", 1)
    html = html.replace("</style>", IBETIN_V38_MATCH_PULSE_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V38_MATCH_PULSE_JS + "\n</body>", 1)
    return html


IBETIN_V39_FAVOURITES_PATH = "/admin/ibetin-v39-favourites"

IBETIN_V39_FAVOURITES_CSS = r"""
/* V39 MY MATCHES / FAVOURITES PREVIEW */
body:before{content:"V39 MY MATCHES"!important;background:#8a5cf6!important}
.v39FavBar{display:flex;align-items:center;gap:8px;margin:9px 0 10px;overflow-x:auto;scrollbar-width:none}
.v39FavBar::-webkit-scrollbar{display:none}
.v39FavFilter{flex:0 0 auto;border:1px solid #1a4667;background:#071827;color:#8da8be;border-radius:999px;padding:8px 11px;font-size:8px;font-weight:1000;letter-spacing:.45px}
.v39FavFilter.on{border-color:#5d9cff;background:#0b3157;color:#fff}
.v39FavCount{display:inline-flex;align-items:center;justify-content:center;min-width:16px;height:16px;margin-left:4px;border-radius:999px;background:#163f62;color:#cce9ff;font-size:7px}
.match{position:relative!important}
.v39FavBtn{border:0;background:transparent;color:#698aa6;font-size:17px;line-height:1;padding:2px 5px;margin-left:auto;margin-right:4px;cursor:pointer}
.v39FavBtn.on{color:#ffd85e;text-shadow:0 0 14px rgba(255,216,94,.24)}
.v39DetailFav{width:100%;height:42px;margin:0 0 10px;border:1px solid #1a4c70;border-radius:12px;background:#071a2d;color:#9dc2de;font-size:9px;font-weight:1000;letter-spacing:.45px}
.v39DetailFav.on{border-color:#c2a33e;background:linear-gradient(135deg,#382f11,#211c0d);color:#ffe582}
.v39Empty{padding:28px 18px;text-align:center;border:1px dashed #1a4565;border-radius:16px;background:#061522;color:#7897af;font-size:10px;line-height:1.6}
.v39Empty b{display:block;color:#fff;font-size:14px;margin-bottom:5px}
"""

IBETIN_V39_FAVOURITES_JS = r"""
<script>
(function(){
  const V39_STORE='ibetin_live_line_favourites_v1';
  let v39FavOnly=false;

  function readFavs(){
    try{
      const raw=JSON.parse(localStorage.getItem(V39_STORE)||'[]');
      return new Set(Array.isArray(raw)?raw.map(String):[]);
    }catch(e){return new Set()}
  }
  let v39Favs=readFavs();

  function saveFavs(){
    try{localStorage.setItem(V39_STORE,JSON.stringify(Array.from(v39Favs)))}catch(e){}
  }
  function isFavourite(key){return !!key&&v39Favs.has(String(key))}
  function currentFavCount(){
    return (Array.isArray(allMatches)?allMatches:[]).filter(m=>isFavourite(matchKey(m))).length;
  }
  function ensureFavBar(){
    const home=document.getElementById('home');
    const tools=home?.querySelector('.tools');
    if(!tools||document.getElementById('v39FavBar'))return;
    tools.insertAdjacentHTML('afterend',
      '<div class="v39FavBar" id="v39FavBar">'
      +'<button class="v39FavFilter on" data-fav-view="all">ALL MATCHES</button>'
      +'<button class="v39FavFilter" data-fav-view="mine">★ MY MATCHES <span class="v39FavCount" id="v39FavCount">0</span></button>'
      +'</div>'
    );
    document.getElementById('v39FavBar').onclick=function(e){
      const b=e.target.closest('[data-fav-view]');if(!b)return;
      v39FavOnly=b.dataset.favView==='mine';
      document.querySelectorAll('.v39FavFilter').forEach(x=>x.classList.toggle('on',x===b));
      render();
    };
  }
  function updateFavCount(){
    const el=document.getElementById('v39FavCount');
    if(el)el.textContent=String(currentFavCount());
  }

  window.toggleFavourite=function(key){
    key=String(key||'');if(!key)return;
    if(v39Favs.has(key))v39Favs.delete(key);else v39Favs.add(key);
    saveFavs();
    try{
      if(document.getElementById('home')?.style.display!=='none')render();
      else if(detailData)drawDetail();
    }catch(e){}
  };

  const v39BaseCard=card;
  card=function(m){
    const key=matchKey(m),saved=isFavourite(key);
    let html=v39BaseCard(m);
    const marker='<span class="badge ';
    const fav='<button class="v39FavBtn '+(saved?'on':'')+'" data-fav-key="'+esc(key)+'" '
      +'aria-label="'+(saved?'Remove from My Matches':'Add to My Matches')+'" '
      +'onclick="event.stopPropagation();toggleFavourite(this.dataset.favKey)">★</button>';
    if(html.includes(marker))html=html.replace(marker,fav+marker);
    return html;
  };

  const v39BaseRender=render;
  render=function(){
    ensureFavBar();
    const original=allMatches;
    const indexed=(Array.isArray(original)?original:[]).map((m,i)=>({m,i,f:isFavourite(matchKey(m))}));
    let ordered=indexed.sort((a,b)=>(Number(b.f)-Number(a.f))||(a.i-b.i)).map(x=>x.m);
    if(v39FavOnly)ordered=ordered.filter(m=>isFavourite(matchKey(m)));
    allMatches=ordered;
    try{
      v39BaseRender();
      if(v39FavOnly && !ordered.length){
        const list=document.getElementById('list');
        if(list)list.innerHTML='<div class="v39Empty"><b>★ My Matches is empty</b>Tap the star on any match to keep it here.</div>';
      }
      updateFavCount();
    }finally{
      allMatches=original;
    }
  };

  const v39BaseDrawDetail=drawDetail;
  drawDetail=function(){
    v39BaseDrawDetail();
    try{
      const m=detailData?.match||{},key=matchKey(m);if(!key)return;
      const back=document.querySelector('#detail .back');
      if(back && !document.getElementById('v39DetailFav')){
        const saved=isFavourite(key);
        back.insertAdjacentHTML('afterend',
          '<button id="v39DetailFav" class="v39DetailFav '+(saved?'on':'')+'" data-fav-key="'+esc(key)+'" '
          +'onclick="event.stopPropagation();toggleFavourite(this.dataset.favKey)">'
          +(saved?'★ SAVED TO MY MATCHES':'☆ SAVE TO MY MATCHES')+'</button>'
        );
      }
    }catch(e){console.error('IBETIN V39 detail favourite',e)}
  };

  try{ensureFavBar();render()}catch(e){console.error('IBETIN V39 favourites',e)}
  window.__IBETIN_V39_FAVOURITES__=true;
})();
</script>
"""


def _page_v39_favourites() -> str:
    html = _page_v38_match_pulse()
    html = html.replace("<title>IBETIN Live Line · Match Pulse V38</title>", "<title>IBETIN Live Line · My Matches V39</title>", 1)
    html = html.replace("</style>", IBETIN_V39_FAVOURITES_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V39_FAVOURITES_JS + "\n</body>", 1)
    return html


IBETIN_V40_VISUAL_POLISH_PATH = "/admin/ibetin-v40-visual-polish"

IBETIN_V40_VISUAL_POLISH_CSS = r"""
/* V40 VISUAL REFINEMENT PREVIEW */
/* V40 single-live-control refinement */
body:before{content:"V40 POLISH"!important;background:#0f82e9!important;font-size:6px!important;padding:4px 7px!important;opacity:.92}
.liveDot{display:none!important}

/* Cleaner brand hierarchy */
.top{padding:12px 15px 10px!important;box-shadow:0 8px 24px rgba(0,0,0,.22)!important}
.brand b{font-size:19px!important;letter-spacing:.45px!important}
.brand span{font-size:8px!important;letter-spacing:1px!important}
.liveLineSub{font-size:6.5px!important;letter-spacing:.55px!important;margin-top:1px!important;color:#668cae!important}
.liveDot{font-size:8px!important;padding:6px 8px!important}
.ibPowered{display:none!important}

/* Tighter navigation and search */
.tabs{gap:6px!important;margin-top:10px!important}
.tab{height:35px!important;border-radius:10px!important;font-size:8px!important;box-shadow:none!important}
.main{padding-top:10px!important}
.tools{gap:7px!important;margin-bottom:6px!important}
.search,.refresh{height:42px!important;border-radius:12px!important}
.status{font-size:8px!important;margin:6px 1px 8px!important}
.v39FavBar{margin:5px 0 9px!important;gap:6px!important}
.v39FavFilter{padding:7px 10px!important;font-size:7.5px!important;background:#061522!important}
.v39FavFilter.on{background:#0a2a49!important;border-color:#3978ac!important;box-shadow:none!important}

/* Match cards: flatter, more premium */
.list{gap:9px!important}
.league{margin:12px 2px 5px!important;font-size:8px!important;letter-spacing:.65px!important}
.match{border:1px solid rgba(32,82,119,.72)!important;border-left:3px solid #278ee8!important;border-radius:15px!important;box-shadow:0 8px 22px rgba(0,0,0,.16)!important;overflow:hidden!important;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease!important}
.match.live{border-left-color:#ee5870!important}
.match:active{transform:scale(.992)!important}
.mh{padding:10px 11px 7px!important}
.fmt{font-size:8px!important}
.badge{font-size:7px!important;padding:5px 7px!important;border-radius:999px!important}
.team{padding:7px 11px!important}
.tn{font-size:11px!important}.sc{font-size:18px!important}.ta,.si{font-size:8px!important}
.previewHomeOdds{padding:9px 11px 10px!important;background:rgba(3,15,27,.38)!important}
.previewOddsTitle{font-size:7px!important;margin-bottom:6px!important;color:#7396b2!important}
.previewHomeGrid{gap:7px!important}
.previewPrice{padding:9px 10px!important;border-radius:11px!important}
.previewPrice small{font-size:8px!important}.previewPrice strong{font-size:23px!important;margin-top:4px!important}
.foot{padding:8px 11px 9px!important;font-size:8px!important}
.ibHomePromo{padding:8px 11px!important;font-size:8px!important;background:#061522!important;color:#4ca9e8!important}

/* Favourite star should feel native, not bolted on */
.v39FavBtn{display:inline-flex!important;align-items:center!important;justify-content:center!important;width:27px!important;height:27px!important;border-radius:50%!important;background:rgba(255,255,255,.025)!important;border:1px solid transparent!important;font-size:14px!important;margin-left:auto!important;margin-right:3px!important;transition:transform .14s ease,background .14s ease,border-color .14s ease!important}
.v39FavBtn:active{transform:scale(.84)!important}
.v39FavBtn.on{background:rgba(255,214,74,.08)!important;border-color:rgba(255,214,74,.2)!important;color:#ffd75c!important;text-shadow:none!important}

/* Match detail: score first, everything else quieter */
.detail{padding-top:9px!important}
.back{height:36px!important;padding:0 11px!important;border-radius:10px!important;font-size:8px!important}
.v39DetailFav{height:36px!important;margin:0 0 8px!important;border-radius:10px!important;background:#061725!important;font-size:8px!important}
.scorehero{border-radius:17px!important;box-shadow:0 10px 28px rgba(0,0,0,.2)!important}
.scoretop{padding:9px 12px!important;font-size:7px!important}
.scoremain{padding:15px 10px 13px!important}
.sname{font-size:9px!important}.sval{font-size:30px!important;line-height:1!important;margin-top:4px!important}.vs{transform:scale(.88)!important}
.report{padding:9px 11px!important;font-size:8px!important}

/* Match Pulse becomes one compact information layer */
.v38Pulse{margin:8px 0 9px!important;padding:10px!important;border-radius:14px!important;border-color:#153e5c!important;background:linear-gradient(180deg,#061827,#071d31)!important;box-shadow:none!important}
.v38PulseHead{margin-bottom:7px!important}
.v38PulseHead b{font-size:12px!important}.v38PulseHead span{font-size:6px!important;color:#528fb9!important}
.v38PulseMetrics{gap:5px!important;margin-bottom:7px!important}
.v38PulseMetric{padding:7px!important;border-radius:9px!important;background:#071522!important;border-color:#12354f!important}
.v38PulseMetric span{font-size:6px!important}.v38PulseMetric b{font-size:13px!important}
.v38Recent{padding:8px!important;border:0!important;border-top:1px solid #123750!important;border-radius:0!important;background:transparent!important}
.v38RecentTop{margin-bottom:6px!important}.v38RecentTop b{font-size:8px!important}.v38RecentTop span{font-size:6px!important}
.v38Ball{flex-basis:24px!important;width:24px!important;height:24px!important;font-size:8px!important}
.v38PulseSummary{font-size:8px!important;margin-top:7px!important}
.v38Latest{font-size:7.5px!important;margin-top:6px!important;padding-top:6px!important}
.v38Pulse .playerStrip{margin-top:7px!important}
.v38Pulse .playerCard{padding:8px!important}

/* BHAV remains strong but visually connected to match */
.quickMarket{margin-top:8px!important;padding:11px!important;border-radius:14px!important;box-shadow:none!important}
.previewBhavHead{margin-bottom:7px!important}
.previewBhavHead b{font-size:14px!important}.previewBhavHead span{font-size:7px!important}
.previewBhavGrid{gap:7px!important}
.quickMarket .previewPrice{padding:10px!important}
.quickMarket .previewPrice strong{font-size:24px!important}
.previewHist{margin-top:7px!important;border-radius:9px!important}
.previewHist div{padding:6px 3px!important}
.previewHist span{font-size:6px!important}.previewHist b{font-size:11px!important}

/* Promotion is contextual, never louder than the cricket */
.ibQuickPromo{margin-top:7px!important;padding:8px 9px!important;border-radius:9px!important;background:#071b2c!important;border-color:#17405b!important}
.ibQuickPromo b{font-size:8.5px!important}.ibQuickPromo span{font-size:6.5px!important}
.ibQuickPromo button{padding:7px 9px!important;font-size:7px!important;background:#0c6fc8!important}
.ibPromoCard{display:none!important}

/* Tabs/panels */
.dtabs{gap:5px!important;margin:9px 0!important}
.dtab{height:34px!important;border-radius:9px!important;font-size:7px!important}
.panel{border-radius:14px!important;box-shadow:none!important}
.ptitle{padding:10px 11px!important}.ptitle b{font-size:9px!important}
.notice,.inning,.ball,.moreItem,.playerCard{border-color:#143a55!important;box-shadow:none!important}

/* Motion: subtle only */
@keyframes v40In{from{opacity:.35;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.match,.scorehero,.v38Pulse,.quickMarket{animation:v40In .18s ease both}
button{transition:transform .12s ease,opacity .12s ease!important}
button:active{opacity:.86}

/* Bottom nav stays clean on home, hidden by V38 on detail */
.bottom{left:18px!important;right:18px!important;border-radius:16px!important;padding:5px!important;box-shadow:0 12px 30px rgba(0,0,0,.34)!important}
.bottom button{height:44px!important;font-size:7px!important}
.bottom b{font-size:15px!important}

/* Empty-live state with useful upcoming matches */
.v40LiveEmpty{padding:22px 14px 14px;text-align:center;border:1px dashed #19405e;border-radius:15px;background:#061522}
.v40LiveEmpty b{display:block;color:#fff;font-size:14px}.v40LiveEmpty span{display:block;color:#7897af;font-size:8px;margin-top:5px}
.v40Coming{margin-top:12px}
.v40ComingHead{display:flex;align-items:center;justify-content:space-between;margin:0 2px 7px}
.v40ComingHead b{font-size:9px;color:#cbe4f8;letter-spacing:.8px}.v40ComingHead button{border:0;background:transparent;color:#58b9ff;font-size:7px;font-weight:1000}
.v40ComingCard{width:100%;border:1px solid #173f5e;border-radius:13px;background:#061827;color:#fff;padding:10px 11px;margin-bottom:7px;text-align:left}
.v40ComingTop{display:flex;align-items:center;justify-content:space-between;gap:8px}
.v40ComingLeague{font-size:7px;color:#6f91ac;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v40ComingTime{font-size:7px;color:#f0c25b;font-weight:900;white-space:nowrap}
.v40ComingTeams{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:8px}
.v40ComingTeam{font-size:10px;font-weight:900;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v40ComingVs{font-size:7px;color:#627f98;font-weight:1000}
.v40ComingNote{margin-top:7px;padding-top:7px;border-top:1px solid #12364f;color:#84a3bb;font-size:7px;line-height:1.35}
.v40Stage{margin:8px 0 9px;padding:9px 10px;border:1px solid #1c557b;border-radius:11px;background:#082039;display:flex;align-items:center;gap:9px}
.v40StageIcon{flex:0 0 28px;height:28px;border-radius:9px;background:#0d6fc8;display:grid;place-items:center;font-size:14px}
.v40StageText{min-width:0}.v40StageText b{display:block;color:#fff;font-size:9px}.v40StageText span{display:block;color:#8fb1ca;font-size:7px;margin-top:2px;line-height:1.35}
.v40Stage.weather{border-color:#665a24;background:#25200d}.v40Stage.weather .v40StageIcon{background:#8b741d}

/* V40 MOBILE READABILITY PASS */
.brand b{font-size:21px!important}
.brand span{font-size:10px!important}
.liveLineSub{font-size:8.5px!important}
.tab{height:40px!important;font-size:11px!important}
.status{font-size:10px!important}
.v39FavFilter{font-size:10px!important;padding:8px 11px!important}
.league{font-size:10px!important}
.fmt{font-size:10px!important}
.badge{font-size:9px!important}
.tn{font-size:15px!important}
.ta,.si{font-size:10px!important}
.sc{font-size:23px!important}
.previewOddsTitle{font-size:9px!important}
.previewPrice small{font-size:10px!important}
.foot{font-size:10px!important}
.ibHomePromo{font-size:10px!important}
.back,.v39DetailFav{font-size:10px!important;height:40px!important}
.scoretop{font-size:9px!important}
.sname{font-size:11px!important}
.report{font-size:10px!important;line-height:1.45!important}
.v38PulseHead b{font-size:14px!important}
.v38PulseHead span{font-size:8px!important}
.v38PulseMetric span{font-size:8px!important}
.v38PulseMetric b{font-size:15px!important}
.v38RecentTop b{font-size:10px!important}
.v38RecentTop span{font-size:8px!important}
.v38Ball{font-size:9px!important}
.v38PulseSummary{font-size:10px!important;line-height:1.45!important}
.v38Latest{font-size:9px!important;line-height:1.45!important}
.previewBhavHead b{font-size:15px!important}
.previewBhavHead span{font-size:9px!important}
.previewHist span{font-size:8px!important}
.previewHist b{font-size:12px!important}
.ibQuickPromo b{font-size:10px!important}
.ibQuickPromo span{font-size:8px!important}
.ibQuickPromo button{font-size:9px!important}
.dtab{height:39px!important;font-size:9px!important}
.ptitle b{font-size:11px!important}
.bottom button{height:48px!important;font-size:9px!important}
.bottom b{font-size:17px!important}
.v40LiveEmpty b{font-size:15px!important}
.v40LiveEmpty span{font-size:10px!important;line-height:1.45!important}
.v40ComingHead b{font-size:10px!important}
.v40ComingHead button{font-size:9px!important}
.v40ComingLeague,.v40ComingTime{font-size:9px!important}
.v40ComingTeam{font-size:12px!important}
.v40ComingVs{font-size:9px!important}
.v40ComingNote{font-size:9px!important;line-height:1.45!important}
.v40StageText b{font-size:11px!important}
.v40StageText span{font-size:9px!important;line-height:1.45!important}
"""


IBETIN_V40_COMING_UP_JS = r"""
<script>
(function(){
  let v40UpcomingCache=null,v40UpcomingAt=0,v40UpcomingBusy=false;

  function v40Time(m){
    const v=m?.startTime||m?.startDate;
    if(!v)return 'UPCOMING';
    try{
      let x=v;
      if(typeof v==='string'&&/^\d+(\.\d+)?$/.test(v))x=Number(v)*1000;
      else if(typeof v==='number'&&v<1000000000000)x=v*1000;
      const d=new Date(x);
      if(Number.isNaN(d.getTime()))return 'UPCOMING';
      return d.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
    }catch(e){return 'UPCOMING'}
  }
  function v40ComingCard(m){
    const key=matchKey(m),note=m.report||prettyState(m.state)||'Scheduled';
    return '<button class="v40ComingCard" data-coming-key="'+esc(key)+'">'
      +'<div class="v40ComingTop"><span class="v40ComingLeague">'+esc((m.format||'CRICKET')+' · '+league(m))+'</span><span class="v40ComingTime">'+esc(v40Time(m))+'</span></div>'
      +'<div class="v40ComingTeams"><span class="v40ComingTeam">'+esc(m.home?.name||'Team A')+'</span><span class="v40ComingVs">VS</span><span class="v40ComingTeam" style="text-align:right">'+esc(m.away?.name||'Team B')+'</span></div>'
      +(note?'<div class="v40ComingNote">'+esc(note)+'</div>':'')
      +'</button>';
  }
  async function v40FetchUpcoming(){
    if(v40UpcomingBusy)return v40UpcomingCache||[];
    if(v40UpcomingCache&&Date.now()-v40UpcomingAt<30000)return v40UpcomingCache;
    v40UpcomingBusy=true;
    try{
      const j=await api({action:'matches',mode:'upcoming'});
      v40UpcomingCache=Array.isArray(j.matches)?j.matches.slice(0,4):[];
      v40UpcomingAt=Date.now();
      return v40UpcomingCache;
    }catch(e){return v40UpcomingCache||[]}
    finally{v40UpcomingBusy=false}
  }
  async function v40EmptyLive(){
    if(mode!=='live'||!Array.isArray(allMatches)||allMatches.length)return;
    const search=(document.getElementById('search')?.value||'').trim();
    if(search)return;
    const list=document.getElementById('list');if(!list)return;
    const rows=await v40FetchUpcoming();
    if(mode!=='live'||allMatches.length)return;
    list.innerHTML='<div class="v40LiveEmpty"><b>No live matches right now</b><span>We will move a match here as soon as the toss is completed.</span></div>'
      +(rows.length?'<div class="v40Coming"><div class="v40ComingHead"><b>COMING UP</b><button id="v40ViewUpcoming">VIEW ALL →</button></div>'+rows.map(v40ComingCard).join('')+'</div>':'');
    list.querySelectorAll('[data-coming-key]').forEach(el=>el.onclick=()=>openMatch(el.dataset.comingKey));
    const all=document.getElementById('v40ViewUpcoming');
    if(all)all.onclick=()=>{const t=document.querySelector('.tab[data-mode="upcoming"]');if(t)t.click()};
  }

  const v40BaseRender=render;
  render=function(){
    v40BaseRender();
    if(mode==='live'&&allMatches.length===0)setTimeout(v40EmptyLive,0);
  };

  const v40BaseLoad=load;
  load=async function(nextMode=mode,force=false){
    const out=await v40BaseLoad(nextMode,force);
    if(mode==='live'&&allMatches.length===0)await v40EmptyLive();
    return out;
  };

  setTimeout(v40EmptyLive,350);
  setTimeout(v40EmptyLive,1400);
  window.__IBETIN_V40_COMING_UP__=true;
})();
</script>
"""

IBETIN_V40_LIVE_STATE_JS = r"""
<script>
(function(){
  function v40TeamNameFromToss(toss,detail){
    if(!toss||typeof toss!=='object')return '';
    let w=toss.winner||toss.team||toss.won_by||toss.wonBy||toss.winner_key||toss.winnerKey||'';
    if(w&&typeof w==='object')return String(w.name||w.short_name||w.shortName||'');
    w=String(w||'');
    const m=detail?.match||{};
    for(const team of [m.home,m.away]){
      if(!team)continue;
      const ids=[team.id,team.key,team.abbr,team.code].filter(Boolean).map(String);
      if(ids.includes(w))return String(team.name||team.abbr||w);
    }
    return w;
  }
  function v40TossStage(detail){
    const toss=detail?.roanuz?.toss;
    const m=detail?.match||{};
    const hasScore=!!(m.homeScore||m.awayScore);
    if(!toss||hasScore)return '';
    let decision='',winner='';
    if(typeof toss==='object'){
      winner=v40TeamNameFromToss(toss,detail);
      decision=String(toss.decision||toss.choice||toss.elected||toss.opted||'').toLowerCase();
    }
    const line=winner&&decision?winner+' won the toss · chose to '+decision:
      winner?winner+' won the toss':decision?'Toss completed · chose to '+decision:'Toss completed';
    return '<div class="v40Stage" id="v40Stage"><div class="v40StageIcon">🪙</div><div class="v40StageText"><b>'+esc(line)+'</b><span>Awaiting first ball · This match remains in LIVE.</span></div></div>';
  }
  function v40InterruptionStage(detail){
    const m=detail?.match||{};
    const text=String(m.report||m.state||'').toLowerCase();
    if(!/(rain|wet outfield|bad light|weather|interrupted|suspended|delayed)/.test(text))return '';
    return '<div class="v40Stage weather" id="v40Stage"><div class="v40StageIcon">🌧</div><div class="v40StageText"><b>Play temporarily interrupted</b><span>'+esc(m.report||prettyState(m.state)||'Weather delay')+' · Match remains in LIVE.</span></div></div>';
  }
  function v40StageHtml(detail){
    return v40InterruptionStage(detail)||v40TossStage(detail);
  }

  const v40StateBaseDrawDetail=drawDetail;
  drawDetail=function(){
    v40StateBaseDrawDetail();
    try{
      const hero=document.querySelector('#detail .scorehero');
      if(hero&&!document.getElementById('v40Stage')){
        const html=v40StageHtml(detailData||{});
        if(html)hero.insertAdjacentHTML('afterend',html);
      }
    }catch(e){console.error('IBETIN V40 stage',e)}
  };

  const IBETIN_LIVE_STREAM='/admin/ibetin-live-stream?t='+encodeURIComponent(TOKEN);
  let v40EventSource=null,v40PushTimer=null;
  function v40ConnectPush(){
    if(v40EventSource||!TOKEN||typeof EventSource==='undefined')return;
    try{
      v40EventSource=new EventSource(IBETIN_LIVE_STREAM);
      v40EventSource.addEventListener('match',()=>{
        clearTimeout(v40PushTimer);
        v40PushTimer=setTimeout(v40StateRefresh,120);
      });
      v40EventSource.onerror=()=>{
        try{v40EventSource.close()}catch(e){}
        v40EventSource=null;
        setTimeout(v40ConnectPush,3000);
      };
    }catch(e){
      v40EventSource=null;
      setTimeout(v40ConnectPush,5000);
    }
  }

  let v40RefreshBusy=false;
  async function v40StateRefresh(){
    if(document.hidden||v40RefreshBusy)return;
    v40RefreshBusy=true;
    try{
      const detail=document.getElementById('detail');
      if(detail&&detail.style.display==='block'&&detailData?.match){
        const key=matchKey(detailData.match);
        if(key){
          const y=window.scrollY;
          const j=await api({action:'match',id:key},false);
          if(j?.detail){
            detailData=j.detail;
            drawDetail();
            requestAnimationFrame(()=>window.scrollTo(0,y));
          }
          getBhav(key,true).then(x=>{
            if(x&&document.getElementById('quickMarket'))renderQuickMarket(x);
            if(detailTab==='bhav')drawPanel();
          });
        }
      }else if(mode==='live'&&Date.now()-lastHomeLoad>10000){
        await load('live');
      }
    }catch(e){}
    finally{v40RefreshBusy=false}
  }
  setInterval(v40StateRefresh,30000);
  v40ConnectPush();
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){setTimeout(v40StateRefresh,250);v40ConnectPush()}});
  window.__IBETIN_V40_LIVE_STATE__=true;
})();
</script>
"""


def _page_v40_visual_polish() -> str:
    html = _page_v39_favourites()
    html = html.replace("<title>IBETIN Live Line · My Matches V39</title>", "<title>IBETIN Live Line · Visual Polish V40</title>", 1)
    html = html.replace(
        '<button data-nav="live"><b style="color:#ff5b6f">●</b>LIVE</button>',
        '<button data-nav="mymatches"><b>★</b>MY MATCHES</button>',
        1,
    )
    html = html.replace(
        "if(nav==='home'||nav==='live'){backHome();if(mode!=='live'||Date.now()-lastHomeLoad>10000){allMatches=[];load('live',true)}}else if(nav==='fixtures'){backHome();allMatches=[];load('upcoming',true)}else{backHome();setTimeout(()=>document.getElementById('search').focus(),100)}",
        "if(nav==='home'){backHome();if(mode!=='live'||Date.now()-lastHomeLoad>10000){allMatches=[];load('live',true)}}else if(nav==='mymatches'){backHome();const mine=document.querySelector('[data-fav-view=\"mine\"]');if(mine)mine.click()}else if(nav==='fixtures'){backHome();allMatches=[];load('upcoming',true)}else{backHome();setTimeout(()=>document.getElementById('search').focus(),100)}",
        1,
    )
    html = html.replace("</style>", IBETIN_V40_VISUAL_POLISH_CSS + "\n</style>", 1)
    html = html.replace("</body>", IBETIN_V40_COMING_UP_JS + "\n</body>", 1)
    html = html.replace("</body>", IBETIN_V40_LIVE_STATE_JS + "\n</body>", 1)
    return html


def _page_v40_public() -> str:
    html = _page_v40_visual_polish()
    html = html.replace(
        "<title>IBETIN Live Line · Visual Polish V40</title>",
        "<title>IBETIN Live Line</title>",
        1,
    )
    html = html.replace(API_PATH, IBETIN_PUBLIC_LIVELINE_API_PATH)
    html = html.replace(
        "const IBETIN_LIVE_STREAM='/admin/ibetin-live-stream?t='+encodeURIComponent(TOKEN);",
        "const IBETIN_LIVE_STREAM='/liveline/stream';",
        1,
    )
    html = html.replace(
        "if(v40EventSource||!TOKEN||typeof EventSource==='undefined')return;",
        "if(v40EventSource||typeof EventSource==='undefined')return;",
        1,
    )
    return html


def _install_public_liveline_routes() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_public_liveline_installed", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)

        if parsed.path == IBETIN_PUBLIC_VERIFY_STATUS_PATH:
            user_id, _, verified = _liveline_verified(self, parsed)
            _send_json(self, 200, {"verified": bool(user_id and verified)})
            return

        if parsed.path == IBETIN_PUBLIC_LIVELINE_PATH:
            user_id, token, verified = _liveline_verified(self, parsed)
            if not verified:
                v23.liveline._send_html(self, 401, _liveline_verification_page(token))
                return

            # A signed access token may arrive in the DM/bot button. Convert it
            # to an HttpOnly cookie, then remove it from the visible URL.
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if (query.get("access") or [""])[0].strip():
                    _send_liveline_redirect_with_cookie(self, token)
                    return
            except Exception:
                pass

            v23.liveline._send_html(self, 200, _page_v40_public())
            return

        if parsed.path == IBETIN_PUBLIC_LIVELINE_API_PATH:
            _, _, verified = _liveline_verified(self, parsed)
            if not verified:
                _send_json(self, 401, {"ok": False, "error": "mobile_verification_required"})
                return
            v23.liveline._api(self)
            return

        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_public_liveline_installed = True
    logger.info(
        "IBETIN verified Live Line installed page=%s api=%s stream=%s verify=%s",
        IBETIN_PUBLIC_LIVELINE_PATH,
        IBETIN_PUBLIC_LIVELINE_API_PATH,
        IBETIN_PUBLIC_LIVE_STREAM_PATH,
        IBETIN_PUBLIC_VERIFY_STATUS_PATH,
    )


def _preview_v40_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V40_VISUAL_POLISH_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v40-sse-health'})}"


def _install_v40_visual_polish_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v40_visual_polish_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V40_VISUAL_POLISH_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v40_visual_polish())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v40_visual_polish_installed = True
    logger.info("IBETIN V40 visual polish preview route installed at %s", IBETIN_V40_VISUAL_POLISH_PATH)


def _preview_v39_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V39_FAVOURITES_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v39-favourites'})}"


def _install_v39_favourites_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v39_favourites_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V39_FAVOURITES_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v39_favourites())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v39_favourites_installed = True
    logger.info("IBETIN V39 favourites preview route installed at %s", IBETIN_V39_FAVOURITES_PATH)


def _preview_v38_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V38_MATCH_PULSE_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v38-pulse'})}"


def _install_v38_match_pulse_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v38_match_pulse_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V38_MATCH_PULSE_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v38_match_pulse())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v38_match_pulse_installed = True
    logger.info("IBETIN V38 Match Pulse preview route installed at %s", IBETIN_V38_MATCH_PULSE_PATH)


def _preview_v37_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V37_PROMO_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v37-inapp-browser'})}"


def _install_v37_promo_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v37_promo_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V37_PROMO_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN Live Line preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v37_promo_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v37_promo_preview_installed = True
    logger.info("IBETIN V37 promo preview route installed at %s", IBETIN_V37_PROMO_PREVIEW_PATH)


def _preview_v36_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V36_BRAND_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v36-brand'})}"


def _install_v36_brand_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v36_brand_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V36_BRAND_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN.COM preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v36_brand_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v36_brand_preview_installed = True
    logger.info("IBETIN V36 brand preview route installed at %s", IBETIN_V36_BRAND_PREVIEW_PATH)


def _preview_v35_url() -> str:
    root = v23.os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{IBETIN_V35_PREVIEW_PATH}?{v23.urlencode({'t': v23.liveline._token(), 'v': '20260918-v35-approved'})}"


def _install_v35_preview_route() -> None:
    handler_cls = v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_v35_preview_installed", False):
        return
    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = v23.urlparse(self.path)
        if parsed.path == IBETIN_V35_PREVIEW_PATH:
            if not v23.liveline._authorized(self.path):
                v23.liveline._send_html(self, 403, "<h3>IBETIN preview link is invalid.</h3>")
                return
            v23.liveline._send_html(self, 200, _page_v35_preview())
            return
        previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_v35_preview_installed = True
    logger.info("IBETIN V35 isolated preview route installed at %s", IBETIN_V35_PREVIEW_PATH)


async def _previewui_command(update, context):
    user, message, chat = update.effective_user, update.effective_message, update.effective_chat
    if not user or not message or not chat:
        return
    if getattr(chat, "type", "") != "private":
        await message.reply_text("Open this preview from a private chat with the bot.")
        return
    await message.reply_text(
        "✨ <b>IBETIN LIVE LINE · V40 VISUAL POLISH</b>\n\n"
        "Same V39 features, with a cleaner premium hierarchy, tighter Match Pulse, native favourites and calmer promotion. "
        "V40 is now the production LIVE renderer. This command opens the same V40 build for direct verification.",
        parse_mode="HTML",
        reply_markup=v23.liveline.InlineKeyboardMarkup(
            [[v23.liveline.InlineKeyboardButton(
                "✨ OPEN V40 POLISHED UI",
                web_app=v23.liveline.WebAppInfo(url=_preview_v40_url()),
            )]]
        ),
        disable_web_page_preview=True,
    )


def _install_v35_preview_command() -> None:
    runtime = v23.liveline.base._runtime
    if getattr(runtime, "_ibetin_v35_preview_configured", False):
        return
    previous_config = runtime.configure_telegram_ui

    async def configure_with_preview(application):
        await previous_config(application)
        application.add_handler(v23.liveline.CommandHandler("previewui", _previewui_command))
        logger.info("IBETIN /previewui premium preview command registered")

    runtime.configure_telegram_ui = configure_with_preview
    runtime.app.configure_telegram_ui = configure_with_preview
    runtime._ibetin_v35_preview_configured = True


_install_v35_preview_route()
_install_live_stream_routes()
_install_roanuz_webhook_route()
_install_v36_brand_preview_route()
_install_v37_promo_preview_route()
_install_v38_match_pulse_route()
_install_v39_favourites_route()
_install_v40_visual_polish_route()
_install_public_liveline_routes()
_install_v35_preview_command()

# Promote the approved V40 UI to the production Live route.
v23._page = _page_v40_visual_polish
v23.liveline._page = _page_v40_visual_polish
logger.info("IBETIN V40 promoted to production Live route; V35 and V30 remain rollback baselines")

app = v25.app

if __name__ == '__main__':
    app.base.ibetin_start.main()
