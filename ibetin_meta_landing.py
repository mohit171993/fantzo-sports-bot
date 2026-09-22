"""Public IBETIN Live Line acquisition landing page.

This page intentionally contains no betting/casino/sportsbook links. It is
used as a clean entry point for the IBETIN Live Line product.
"""
from urllib.parse import urlparse

PATH = "/meta-ch"


def page_html() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#071a34">
<meta name="description" content="IBETIN Live Line - cricket match updates, fixtures, results and match details.">
<title>IBETIN Live Line</title>
<style>
:root{--navy:#071a34;--blue:#0b5cb4;--gold:#f6c84b;--ink:#102c4b;--muted:#6f8498;--bg:#eef3f8;--card:#fff}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;font-family:Inter,Arial,sans-serif;background:var(--bg);color:var(--ink)}
body{background:
radial-gradient(circle at 90% 0%,rgba(11,92,180,.16),transparent 34%),
linear-gradient(180deg,#f8fbff 0%,#eef3f8 58%,#e8eff6 100%)}
.shell{width:min(100%,620px);margin:0 auto;padding:20px 16px 30px}
.hero{background:linear-gradient(135deg,#041326,#0a315f 70%,#0b4d8e);border-radius:26px;padding:24px 20px;color:#fff;box-shadow:0 18px 44px rgba(5,34,69,.18);overflow:hidden;position:relative}
.hero:after{content:"";position:absolute;width:180px;height:180px;border-radius:50%;background:rgba(246,200,75,.12);right:-70px;top:-70px}
.brand{display:flex;align-items:center;gap:11px;position:relative;z-index:1}
.mark{width:50px;height:50px;border-radius:15px;background:var(--gold);display:grid;place-items:center;color:#17314e;font-weight:1000;font-size:25px}
.brand b{font-size:23px;letter-spacing:1px}.brand small{display:block;color:#c7d8eb;font-size:11px;margin-top:2px;letter-spacing:.7px}
.pill{display:inline-flex;margin-top:24px;padding:7px 10px;border-radius:999px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.12);font-size:11px;font-weight:800;color:#dfeaf6;position:relative;z-index:1}
h1{font-size:36px;line-height:1.02;margin:15px 0 10px;letter-spacing:-1px;position:relative;z-index:1}
h1 span{color:var(--gold)}
.sub{margin:0;color:#d7e3f0;font-size:14px;line-height:1.55;max-width:480px;position:relative;z-index:1}
.cta{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:22px;padding:16px;border-radius:16px;background:var(--gold);color:#17314e;text-decoration:none;font-weight:1000;box-shadow:0 10px 22px rgba(246,200,75,.22);position:relative;z-index:1}
.cta small{display:block;font-size:10px;font-weight:700;opacity:.72;margin-top:2px}.arrow{font-size:23px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.card{background:var(--card);border:1px solid #e1e9f1;border-radius:17px;padding:15px;box-shadow:0 7px 20px rgba(5,34,69,.06)}
.icon{width:38px;height:38px;border-radius:12px;background:#edf5fd;display:grid;place-items:center;font-size:19px;margin-bottom:10px}
.card b{display:block;font-size:13px}.card small{display:block;color:var(--muted);font-size:10px;line-height:1.45;margin-top:3px}
.section{margin-top:17px;background:#fff;border:1px solid #e1e9f1;border-radius:20px;padding:17px}
.section h2{font-size:17px;margin:0 0 12px}
.step{display:flex;gap:11px;align-items:flex-start;padding:9px 0}
.num{width:28px;height:28px;flex:0 0 28px;border-radius:9px;background:#eaf3fc;color:#0b5cb4;display:grid;place-items:center;font-size:11px;font-weight:1000}
.step b{font-size:12px}.step p{margin:2px 0 0;color:var(--muted);font-size:10px;line-height:1.45}
.bottom{margin-top:16px;text-align:center;color:#7d90a3;font-size:10px;line-height:1.5}
.bottom strong{color:#3e5d78}
@media(max-width:390px){h1{font-size:31px}.grid{grid-template-columns:1fr 1fr}.hero{padding:21px 17px}.shell{padding:14px 12px 24px}}
</style>
</head>
<body>
<main class="shell">
<section class="hero">
  <div class="brand"><div class="mark">I</div><div><b>IBETIN</b><small>LIVE LINE</small></div></div>
  <div class="pill">CRICKET MATCH CENTRE</div>
  <h1>Follow cricket.<br><span>Stay updated.</span></h1>
  <p class="sub">One clean place for live match updates, upcoming fixtures, recent results and detailed match information.</p>
  <a id="openLiveLine" class="cta" href="/liveline">
    <span>OPEN IBETIN LIVE LINE<small>Continue to the cricket match centre</small></span><span class="arrow">→</span>
  </a>
</section>

<section class="grid">
  <div class="card"><div class="icon">⚡</div><b>Live Matches</b><small>Follow matches currently in progress.</small></div>
  <div class="card"><div class="icon">🗓️</div><b>Fixtures</b><small>See upcoming cricket schedules.</small></div>
  <div class="card"><div class="icon">✅</div><b>Results</b><small>Check recently completed matches.</small></div>
  <div class="card"><div class="icon">📊</div><b>Match Details</b><small>Open a match for more information.</small></div>
</section>

<section class="section">
  <h2>How it works</h2>
  <div class="step"><div class="num">1</div><div><b>Open Live Line</b><p>Tap the button above to continue.</p></div></div>
  <div class="step"><div class="num">2</div><div><b>Verify your mobile</b><p>New users complete the existing IBETIN verification flow.</p></div></div>
  <div class="step"><div class="num">3</div><div><b>Access the match centre</b><p>Use Live, Upcoming and Results from one place.</p></div></div>
</section>

<div class="bottom"><strong>IBETIN Live Line</strong><br>Cricket information product. Availability and data may vary by match.</div>
</main>
<script>
(function(){
  try{
    const q=new URLSearchParams(location.search);
    if(q.size){sessionStorage.setItem('ibetin_meta_landing_qs',q.toString())}
  }catch(e){}
})();
</script>
</body>
</html>"""


def install(runtime) -> None:
    handler_cls = runtime.v23.liveline.base.ibetin_start.ibetin_entry.analytics.TrackingHandler
    if getattr(handler_cls, "_ibetin_meta_landing_installed", False):
        return

    previous_get = handler_cls.do_GET

    def routed_get(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == PATH:
            raw = page_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return previous_get(self)

    handler_cls.do_GET = routed_get
    handler_cls._ibetin_meta_landing_installed = True
