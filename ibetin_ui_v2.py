import json
import logging
from html import escape
from urllib.parse import urlencode, urlparse, parse_qs

logger = logging.getLogger(__name__)


def _hub_page(hub, section: str) -> str:
    section = (section or "home").strip().lower()
    if section not in hub.ALLOWED_SECTIONS:
        section = "home"

    home = hub.hub_url("home")
    alerts = hub.hub_url("alerts")
    settings = hub.hub_url("settings")
    support = hub.hub_url("support")
    news = hub.news_url()

    cards = [
        ("🏆", "Sports", "Matches & markets", hub.hub_url("sports")),
        ("🔴", "Live", "Live action", hub.hub_url("live")),
        ("📰", "Sports News", "Latest updates", news),
        ("🎰", "Live Casino", "Casino section", hub.hub_url("casino")),
        ("🎮", "Games", "Browse games", hub.hub_url("games")),
        ("📊", "Results", "Latest results", hub.hub_url("results")),
        ("💳", "Payments", "Payment information", hub.hub_url("payments")),
        ("🛟", "Support", "Official help", support),
        ("🔔", "My Alerts", "Notification controls", alerts),
        ("⚙️", "Settings", "Language & preferences", settings),
    ]

    card_html = "".join(
        f'<a class="tile" href="{escape(url, quote=True)}"><span class="ico">{icon}</span>'
        f'<span><b>{escape(title)}</b><small>{escape(subtitle)}</small></span></a>'
        for icon, title, subtitle, url in cards
    )

    body = ""
    extra_script = ""

    if section == "home":
        body = f"""
<section class="hero">
  <div class="eyebrow">IBETIN MINI APP</div>
  <h1>Everything in one place.</h1>
  <p>Sports, live action, news, alerts and support — directly inside Telegram.</p>
</section>
<div class="grid">{card_html}</div>
<section class="info"><b>Quick access</b><p>Tap any section. There is no separate command-center or black intermediate screen.</p></section>
"""
    elif section == "alerts":
        body = """
<section class="hero">
  <div class="eyebrow">PERSONAL NOTIFICATIONS</div>
  <h1>My Match Alerts</h1>
  <p>Turn Telegram sports notifications on or off for your IBETIN account.</p>
</section>
<section class="info">
  <div class="row"><div><b>Sports notifications</b><small id="alertStatus">Checking your preference…</small></div>
  <label class="switch"><input id="alertsToggle" type="checkbox" disabled><span></span></label></div>
</section>
"""
        extra_script = """
const toggle=document.getElementById('alertsToggle');
const status=document.getElementById('alertStatus');
async function loadAlerts(){
  if(!initData){status.textContent='Open this Mini App from @Ibtnofficialbot to manage alerts.';return;}
  try{const d=await prefs({action:'get'});toggle.checked=!!d.subscribed;toggle.disabled=false;status.textContent=d.subscribed?'Alerts are ON':'Alerts are OFF';}
  catch(e){status.textContent=e.message;}
}
toggle.addEventListener('change',async()=>{toggle.disabled=true;try{const d=await prefs({action:'set',subscribed:toggle.checked});toggle.checked=!!d.subscribed;status.textContent=d.subscribed?'Alerts are ON':'Alerts are OFF';showToast(d.subscribed?'Alerts enabled':'Alerts disabled');}catch(e){toggle.checked=!toggle.checked;status.textContent=e.message;showToast('Could not save');}finally{toggle.disabled=false;}});
loadAlerts();
"""
    elif section == "settings":
        body = """
<section class="hero">
  <div class="eyebrow">YOUR PREFERENCES</div>
  <h1>Settings</h1>
  <p>Keep your IBETIN language preference synced with Telegram.</p>
</section>
<section class="info">
  <b>Language</b>
  <select id="language" disabled><option value="en">English</option><option value="hi">हिन्दी</option></select>
  <small id="languageStatus">Checking your preference…</small>
</section>
"""
        extra_script = """
const language=document.getElementById('language');
const languageStatus=document.getElementById('languageStatus');
async function loadSettings(){
  if(!initData){languageStatus.textContent='Open this Mini App from @Ibtnofficialbot to manage settings.';return;}
  try{const d=await prefs({action:'get'});language.value=d.language||'en';language.disabled=false;languageStatus.textContent='Synced with your bot profile';}
  catch(e){languageStatus.textContent=e.message;}
}
language.addEventListener('change',async()=>{language.disabled=true;try{const d=await prefs({action:'set',language:language.value});language.value=d.language||'en';languageStatus.textContent='Saved';showToast('Language saved');}catch(e){languageStatus.textContent=e.message;showToast('Could not save');}finally{language.disabled=false;}});
loadSettings();
"""
    else:
        target = hub.SECTION_TARGETS.get(section, hub.IBETIN_HOME_URL)
        label = hub.SECTION_LABELS.get(section, section.title())
        body = f"""
<section class="hero">
  <div class="eyebrow">IBETIN MINI APP</div>
  <h1>{escape(label)}</h1>
  <p>Opening {escape(label)} inside Telegram…</p>
</section>
<section class="info center"><div class="spinner"></div><b>Loading {escape(label)}</b></section>
"""
        extra_script = f"window.location.replace({json.dumps(target)});"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate"><title>IBETIN</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:#f7f9f9;color:#0e1417;font-family:'Space Grotesk','Sora',Arial,sans-serif}}
body{{padding-bottom:82px}}.wrap{{max-width:760px;margin:0 auto;padding:16px 14px 28px}}.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}.brand{{font-size:20px;font-weight:950;letter-spacing:.7px}}.pill{{border:1px solid #e0e8e9;background:#fff;border-radius:999px;padding:6px 9px;color:#688287;font-size:10px;font-weight:900}}
.hero{{background:#fff;border:1px solid #e0e8e9;border-radius:22px;padding:20px 18px}}.eyebrow{{font-size:11px;font-weight:900;letter-spacing:1.1px;color:#678288;margin-bottom:8px}}h1{{font-size:27px;line-height:1.08;margin:0 0 8px}}.hero p,.info p{{margin:0;color:#678288;font-size:13px;line-height:1.5}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}}.tile{{display:flex;align-items:center;gap:11px;min-height:78px;background:#fff;border:1px solid #e0e8e9;border-radius:18px;padding:13px;text-decoration:none;color:#0e1417}}.tile:active{{transform:scale(.985)}}.ico{{font-size:25px;flex:0 0 32px;text-align:center}}.tile span:last-child{{display:flex;min-width:0;flex-direction:column;gap:4px}}.tile b{{font-size:13px}}.tile small{{color:#768e93;font-size:10.5px;line-height:1.3}}
.info{{margin-top:14px;background:#fff;border:1px solid #e0e8e9;border-radius:18px;padding:16px}}.info>small{{display:block;color:#768e93;margin-top:8px}}.row{{display:flex;align-items:center;justify-content:space-between;gap:14px}}.row small{{display:block;color:#768e93;margin-top:5px}}
.switch{{position:relative;width:58px;height:32px;flex:0 0 58px}}.switch input{{opacity:0;width:0;height:0}}.switch span{{position:absolute;inset:0;border-radius:999px;background:#cfdbdd;transition:.18s}}.switch span:before{{content:'';position:absolute;width:24px;height:24px;left:4px;top:4px;background:#fff;border-radius:50%;transition:.18s;box-shadow:0 1px 3px rgba(0,0,0,.18)}}.switch input:checked+span{{background:#11dfff}}.switch input:checked+span:before{{transform:translateX(26px)}}
select{{width:100%;margin-top:12px;padding:13px;border-radius:12px;background:#fff;color:#0e1417;border:1px solid #cfdbdd;font-size:15px}}.center{{text-align:center}}.spinner{{width:28px;height:28px;margin:4px auto 12px;border:3px solid #e5eced;border-top-color:#11dfff;border-radius:50%;animation:spin .7s linear infinite}}@keyframes spin{{to{{transform:rotate(360deg)}}}}
.nav{{position:fixed;left:0;right:0;bottom:0;background:rgba(255,255,255,.97);border-top:1px solid #e0e8e9;padding:9px 12px max(9px,env(safe-area-inset-bottom));display:flex;justify-content:center;gap:6px;z-index:20}}.nav a{{flex:1;max-width:160px;text-align:center;text-decoration:none;color:#678288;font-size:10px;font-weight:900;padding:7px 4px;border-radius:11px}}.nav a strong{{display:block;color:#0e1417;font-size:17px;margin-bottom:2px}}
.toast{{position:fixed;left:50%;bottom:92px;transform:translate(-50%,16px);opacity:0;pointer-events:none;background:#0e1417;color:#fff;border-radius:999px;padding:9px 13px;font-size:11px;font-weight:900;transition:.2s;z-index:30}}.toast.show{{opacity:1;transform:translate(-50%,0)}}
@media(max-width:390px){{.grid{{gap:8px}}.tile{{padding:11px;min-height:74px}}.tile b{{font-size:12px}}}}
/* iBetin premium neon theme: deep black, cyan neon, blue lightning edges (colours only) */
:root{{--hB:#030607;--hP:#0a1216;--hP2:#070d10;--hInk:#eef9fb;--hInk2:#b4cbd0;--hMu:#7f9aa1;--hC:#19e3ff;--hC2:#8af3ff;--hBl:#2f7dff;--hRule:rgba(25,227,255,.14);--hEdge:rgba(25,227,255,.3)}}
html,body{{background:radial-gradient(90% 40% at 50% -6%,rgba(25,227,255,.14),transparent 70%),url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='48' viewBox='0 0 28 48'%3E%3Cpath d='M14 0l14 8v16L14 32 0 24V8zM14 32l14 8v16M14 32L0 40' fill='none' stroke='%2319e3ff' stroke-opacity='.045'/%3E%3C/svg%3E"),linear-gradient(180deg,#061014,var(--hB) 40%) fixed!important;color:var(--hInk)!important}}
.wrap>.top{{margin:-16px -14px 16px!important;padding:16px 16px 14px!important;position:relative;background:radial-gradient(120% 140% at 0 0,rgba(25,227,255,.13),transparent 55%),linear-gradient(180deg,rgba(6,13,16,.97),rgba(3,7,8,.95));box-shadow:0 14px 30px rgba(0,0,0,.5)}}
.wrap>.top:after{{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,var(--hC) 30%,var(--hC2) 50%,var(--hBl) 75%,transparent);box-shadow:0 0 12px rgba(25,227,255,.7)}}
.wrap>.top .brand{{color:var(--hInk)!important;letter-spacing:2px!important;text-shadow:0 0 16px rgba(25,227,255,.55)}}
.wrap>.top .pill{{background:rgba(25,227,255,.06)!important;border:1px solid var(--hEdge)!important;color:var(--hC2)!important;letter-spacing:1.2px}}
.hero{{position:relative;overflow:hidden;color:var(--hInk);border:0!important;background:radial-gradient(110% 90% at 100% 0,rgba(25,227,255,.2),transparent 55%),radial-gradient(90% 80% at 0 100%,rgba(47,125,255,.14),transparent 60%),linear-gradient(160deg,#0c1a1f,#060c0f 60%,#030607)!important;box-shadow:inset 0 0 0 1px rgba(25,227,255,.4),0 0 26px -8px rgba(25,227,255,.35),0 18px 34px -14px rgba(0,0,0,.8)!important}}
.hero:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,var(--hBl),var(--hC) 45%,var(--hC2));box-shadow:0 0 10px var(--hC)}}
.hero .eyebrow,.eyebrow{{color:var(--hC2)!important;letter-spacing:2.2px!important}}.hero h1{{color:#fff!important}}.hero p{{color:var(--hInk2)!important}}
.info,.tile,.card,.empty{{background:linear-gradient(180deg,var(--hP),var(--hP2))!important;border:0!important;box-shadow:inset 0 0 0 1px var(--hRule),inset 0 1px 0 rgba(255,255,255,.04),0 16px 30px -14px rgba(0,0,0,.8)!important;color:var(--hInk)!important}}
.tile b,.info b,.row b,.row strong{{color:var(--hInk)!important}}
.info small,.row small,.tile small,.card p,.meta{{color:var(--hMu)!important}}.card h2{{color:var(--hInk)!important}}
.row+.row{{border-top:1px solid var(--hRule)}}
.switch span,.slider{{background:#14242a!important;box-shadow:inset 0 0 0 1px var(--hEdge)}}
.switch input:checked+span,.switch input:checked+.slider{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;box-shadow:0 0 12px rgba(25,227,255,.5)}}
select{{background:#071013!important;border:1px solid var(--hEdge)!important;color:var(--hInk)!important}}
.spinner{{border-color:var(--hRule)!important;border-top-color:var(--hC)!important}}
.nav{{background:linear-gradient(180deg,rgba(9,17,20,.97),rgba(3,7,8,.98))!important;border-top:1px solid var(--hEdge)!important;box-shadow:0 -8px 24px -10px rgba(25,227,255,.25)}}
.nav a{{color:var(--hMu)!important}}.nav a strong{{color:var(--hInk)!important}}
.toast,.refresh{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;color:#021014!important;box-shadow:0 0 16px rgba(25,227,255,.45)}}
.top:not(.wrap>.top){{background:radial-gradient(120% 140% at 0 0,rgba(25,227,255,.13),transparent 55%),linear-gradient(180deg,rgba(6,13,16,.97),rgba(3,7,8,.95))!important;border-bottom:1px solid rgba(25,227,255,.5)!important;box-shadow:0 0 14px rgba(25,227,255,.25)!important;color:var(--hInk)}}
.top .brand h1{{color:#fff!important;text-shadow:0 0 14px rgba(25,227,255,.5);letter-spacing:.6px}}.top .badge{{border-color:var(--hEdge)!important;color:var(--hC2)!important}}.top .sub{{color:var(--hMu)!important}}
.tab{{background:rgba(25,227,255,.04)!important;border-color:var(--hRule)!important;color:var(--hInk2)!important}}.tab.active{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;border-color:transparent!important;color:#021014!important;box-shadow:0 0 12px rgba(25,227,255,.4)}}
.note{{color:var(--hMu)!important}}
</style></head><body>
<div class="wrap"><div class="top"><div class="brand">IBETIN</div><div class="pill">TELEGRAM MINI APP</div></div>{body}</div>
<nav class="nav"><a href="{escape(home, quote=True)}"><strong>⌂</strong>Home</a><a href="{escape(news, quote=True)}"><strong>📰</strong>News</a><a href="{escape(alerts, quote=True)}"><strong>🔔</strong>Alerts</a><a href="{escape(support, quote=True)}"><strong>🛟</strong>Support</a></nav>
<div id="toast" class="toast"></div>
<script>
const tg=window.Telegram&&window.Telegram.WebApp;if(tg){{tg.ready();tg.expand();try{{tg.setHeaderColor('#061014');tg.setBackgroundColor('#030607');}}catch(e){{}}}}
const initData=tg?(tg.initData||''):'';
function showToast(m){{const el=document.getElementById('toast');el.textContent=m;el.classList.add('show');clearTimeout(window.__ibt);window.__ibt=setTimeout(()=>el.classList.remove('show'),1800);}}
async function prefs(payload){{const r=await fetch({json.dumps(hub.PREFS_PATH)},{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(Object.assign({{initData:initData}},payload))}});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not save preference');return d;}}
{extra_script}
</script></body></html>"""


def _news_page(news, category: str, items: list[dict]) -> str:
    category = category if category in news.NEWS_QUERIES else "latest"
    label = news.NEWS_LABELS.get(category, news.NEWS_LABELS["latest"])
    tabs = "".join(
        f'<a class="tab{" active" if key == category else ""}" href="{news.NEWS_PATH}?{urlencode({"category": key})}">{escape(title)}</a>'
        for key, title in news.NEWS_LABELS.items()
    )
    cards = []
    for item in items:
        desc = item.get("description") or "Fresh update from the listed publisher."
        cards.append(
            f'<article class="card"><div class="meta"><span>{escape(item["source"])}</span><span>{escape(news._age(item["pub_date"]))}</span></div>'
            f'<h2>{escape(item["title"])}</h2><p>{escape(desc)}</p></article>'
        )
    if not cards:
        cards.append('<div class="empty"><b>No fresh headlines right now.</b><br>Refresh or try another category.</div>')
    refresh = f'{news.NEWS_PATH}?{urlencode({"category": category, "refresh": "1"})}'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>IBETIN Sports News</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>*{{box-sizing:border-box}}html,body{{margin:0;background:#f7f9f9;color:#0e1417;font-family:'Space Grotesk','Sora',Arial,sans-serif}}body{{min-height:100%;padding-bottom:28px}}.top{{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #e0e8e9;padding:14px 14px 10px}}.brand{{display:flex;align-items:center;justify-content:space-between;gap:10px}}.brand h1{{font-size:18px;margin:0;font-weight:900}}.badge{{font-size:11px;border:1px solid #e0e8e9;border-radius:999px;padding:6px 9px;color:#678288;font-weight:800}}.sub{{margin-top:6px;color:#678288;font-size:12px}}.tabs{{display:flex;gap:8px;overflow-x:auto;padding:12px 14px 2px;scrollbar-width:none}}.tabs::-webkit-scrollbar{{display:none}}.tab{{white-space:nowrap;text-decoration:none;color:#4a6166;border:1px solid #e0e8e9;background:#fff;border-radius:999px;padding:9px 12px;font-size:12px;font-weight:800}}.tab.active{{background:#0e1417;color:#fff;border-color:#0e1417}}.wrap{{padding:12px 14px}}.card{{background:#fff;border:1px solid #e0e8e9;border-radius:16px;padding:14px;margin-bottom:12px}}.meta{{display:flex;justify-content:space-between;gap:10px;color:#678288;font-size:11px;font-weight:700}}.card h2{{font-size:16px;line-height:1.35;margin:9px 0 8px;color:#0e1417}}.card p{{font-size:13px;line-height:1.5;margin:0;color:#678288}}.empty{{padding:28px 18px;text-align:center;border:1px dashed #cfdbdd;border-radius:16px;color:#678288;background:#fff}}.bottom{{padding:0 14px}}.refresh{{display:block;text-align:center;text-decoration:none;background:#0e1417;color:#fff;border-radius:14px;padding:13px 16px;font-weight:900}}.note{{font-size:11px;color:#7d9195;line-height:1.45;text-align:center;margin-top:12px}}
/* iBetin premium neon theme: deep black, cyan neon, blue lightning edges (colours only) */
:root{{--hB:#030607;--hP:#0a1216;--hP2:#070d10;--hInk:#eef9fb;--hInk2:#b4cbd0;--hMu:#7f9aa1;--hC:#19e3ff;--hC2:#8af3ff;--hBl:#2f7dff;--hRule:rgba(25,227,255,.14);--hEdge:rgba(25,227,255,.3)}}
html,body{{background:radial-gradient(90% 40% at 50% -6%,rgba(25,227,255,.14),transparent 70%),url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='48' viewBox='0 0 28 48'%3E%3Cpath d='M14 0l14 8v16L14 32 0 24V8zM14 32l14 8v16M14 32L0 40' fill='none' stroke='%2319e3ff' stroke-opacity='.045'/%3E%3C/svg%3E"),linear-gradient(180deg,#061014,var(--hB) 40%) fixed!important;color:var(--hInk)!important}}
.wrap>.top{{margin:-16px -14px 16px!important;padding:16px 16px 14px!important;position:relative;background:radial-gradient(120% 140% at 0 0,rgba(25,227,255,.13),transparent 55%),linear-gradient(180deg,rgba(6,13,16,.97),rgba(3,7,8,.95));box-shadow:0 14px 30px rgba(0,0,0,.5)}}
.wrap>.top:after{{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,var(--hC) 30%,var(--hC2) 50%,var(--hBl) 75%,transparent);box-shadow:0 0 12px rgba(25,227,255,.7)}}
.wrap>.top .brand{{color:var(--hInk)!important;letter-spacing:2px!important;text-shadow:0 0 16px rgba(25,227,255,.55)}}
.wrap>.top .pill{{background:rgba(25,227,255,.06)!important;border:1px solid var(--hEdge)!important;color:var(--hC2)!important;letter-spacing:1.2px}}
.hero{{position:relative;overflow:hidden;color:var(--hInk);border:0!important;background:radial-gradient(110% 90% at 100% 0,rgba(25,227,255,.2),transparent 55%),radial-gradient(90% 80% at 0 100%,rgba(47,125,255,.14),transparent 60%),linear-gradient(160deg,#0c1a1f,#060c0f 60%,#030607)!important;box-shadow:inset 0 0 0 1px rgba(25,227,255,.4),0 0 26px -8px rgba(25,227,255,.35),0 18px 34px -14px rgba(0,0,0,.8)!important}}
.hero:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:linear-gradient(90deg,var(--hBl),var(--hC) 45%,var(--hC2));box-shadow:0 0 10px var(--hC)}}
.hero .eyebrow,.eyebrow{{color:var(--hC2)!important;letter-spacing:2.2px!important}}.hero h1{{color:#fff!important}}.hero p{{color:var(--hInk2)!important}}
.info,.tile,.card,.empty{{background:linear-gradient(180deg,var(--hP),var(--hP2))!important;border:0!important;box-shadow:inset 0 0 0 1px var(--hRule),inset 0 1px 0 rgba(255,255,255,.04),0 16px 30px -14px rgba(0,0,0,.8)!important;color:var(--hInk)!important}}
.tile b,.info b,.row b,.row strong{{color:var(--hInk)!important}}
.info small,.row small,.tile small,.card p,.meta{{color:var(--hMu)!important}}.card h2{{color:var(--hInk)!important}}
.row+.row{{border-top:1px solid var(--hRule)}}
.switch span,.slider{{background:#14242a!important;box-shadow:inset 0 0 0 1px var(--hEdge)}}
.switch input:checked+span,.switch input:checked+.slider{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;box-shadow:0 0 12px rgba(25,227,255,.5)}}
select{{background:#071013!important;border:1px solid var(--hEdge)!important;color:var(--hInk)!important}}
.spinner{{border-color:var(--hRule)!important;border-top-color:var(--hC)!important}}
.nav{{background:linear-gradient(180deg,rgba(9,17,20,.97),rgba(3,7,8,.98))!important;border-top:1px solid var(--hEdge)!important;box-shadow:0 -8px 24px -10px rgba(25,227,255,.25)}}
.nav a{{color:var(--hMu)!important}}.nav a strong{{color:var(--hInk)!important}}
.toast,.refresh{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;color:#021014!important;box-shadow:0 0 16px rgba(25,227,255,.45)}}
.top:not(.wrap>.top){{background:radial-gradient(120% 140% at 0 0,rgba(25,227,255,.13),transparent 55%),linear-gradient(180deg,rgba(6,13,16,.97),rgba(3,7,8,.95))!important;border-bottom:1px solid rgba(25,227,255,.5)!important;box-shadow:0 0 14px rgba(25,227,255,.25)!important;color:var(--hInk)}}
.top .brand h1{{color:#fff!important;text-shadow:0 0 14px rgba(25,227,255,.5);letter-spacing:.6px}}.top .badge{{border-color:var(--hEdge)!important;color:var(--hC2)!important}}.top .sub{{color:var(--hMu)!important}}
.tab{{background:rgba(25,227,255,.04)!important;border-color:var(--hRule)!important;color:var(--hInk2)!important}}.tab.active{{background:linear-gradient(180deg,var(--hC2),var(--hC))!important;border-color:transparent!important;color:#021014!important;box-shadow:0 0 12px rgba(25,227,255,.4)}}
.note{{color:var(--hMu)!important}}</style></head><body>
<div class="top"><div class="brand"><h1>📰 IBETIN SPORTS NEWS</h1><span class="badge">LIVE FEED</span></div><div class="sub">{escape(label)} · India-focused sports headlines</div></div><nav class="tabs">{tabs}</nav><main class="wrap">{''.join(cards)}</main><div class="bottom"><a class="refresh" href="{escape(refresh, quote=True)}">↻ REFRESH NEWS</a><div class="note">Headlines and short summaries come from external publishers via Google News RSS.</div></div>
<script>const tg=window.Telegram&&window.Telegram.WebApp;if(tg){{tg.ready();tg.expand();try{{tg.setHeaderColor('#061014');tg.setBackgroundColor('#030607');}}catch(e){{}}}}</script></body></html>"""


def _install_router(start_module):
    hub = start_module.hub
    entry = start_module.ibetin_entry

    def install_native_router() -> None:
        handler_cls = entry.analytics.TrackingHandler
        if getattr(handler_cls, "_ibetin_native_mini_app_router_v2", False):
            return
        previous_get = handler_cls.do_GET

        def routed_get(self):
            parsed = urlparse(self.path)
            if parsed.path == hub.HUB_PATH:
                query = parse_qs(parsed.query, keep_blank_values=True)
                section = (query.get("section") or [""])[0].strip().lower()
                start_param = entry._telegram_start_param(parsed)
                requested = (start_param or section or "home").strip().lower()
                logger.info("IBETIN unified Mini App route=%s", requested)

                if requested == "news":
                    start_module._send_redirect(self, hub.news_url())
                    return
                if requested in {"home", "alerts", "settings"}:
                    hub._send_html(self, 200, hub._page(requested))
                    return
                if requested in hub.SECTION_TARGETS:
                    start_module._send_redirect(self, hub.SECTION_TARGETS[requested])
                    return

                hub._send_html(self, 200, hub._page("home"))
                return

            previous_get(self)

        handler_cls.do_GET = routed_get
        handler_cls._ibetin_native_mini_app_router_v2 = True
        logger.info("IBETIN unified Mini App light router installed")

    start_module._install_native_mini_app_server_router = install_native_router
    entry.install_start_param_router = install_native_router


def install(start_module) -> None:
    if getattr(start_module, "_ibetin_ui_v2_installed", False):
        return
    hub = start_module.hub
    news = start_module.news
    hub._page = lambda section: _hub_page(hub, section)
    news._news_page = lambda category, items: _news_page(news, category, items)
    _install_router(start_module)
    start_module._ibetin_ui_v2_installed = True
    logger.info("IBETIN unified light Mini App UI installed")
