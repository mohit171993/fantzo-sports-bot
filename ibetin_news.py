import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree import ElementTree as ET

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import fantzo_analytics as analytics

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
NEWS_PATH = "/news"
NEWS_QUERIES = {
    "latest": "sports India when:1d",
    "cricket": "cricket India when:2d",
    "football": "football India when:2d",
    "india": "India sports when:2d",
}
NEWS_LABELS = {
    "latest": "Latest Sports",
    "cricket": "Cricket",
    "football": "Football",
    "india": "India Sports",
}
MAX_ITEMS = 20


def news_url(category: str = "latest") -> str:
    category = category if category in NEWS_QUERIES else "latest"
    base = TRACKING_BASE_URL or "https://ibetin-app-production.up.railway.app"
    return f"{base}{NEWS_PATH}?{urlencode({'category': category})}"


def news_webapp_button(label: str = "📰 OPEN SPORTS NEWS", category: str = "latest") -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=news_url(category)))


def launcher_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [news_webapp_button()],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )


def _feed_url(category: str) -> str:
    query = NEWS_QUERIES.get(category, NEWS_QUERIES["latest"])
    return GOOGLE_NEWS_RSS + "?" + urlencode(
        {
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }
    )


def _clean_title(title: str, source: str) -> str:
    title = " ".join((title or "").split())
    source = " ".join((source or "").split())
    suffix = f" - {source}" if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)].rstrip()
    return title


def _clean_description(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:420]


def _age(pub_date: str) -> str:
    if not pub_date:
        return "recent"
    try:
        dt = parsedate_to_datetime(pub_date)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 3600:
            minutes = max(1, seconds // 60)
            return f"{minutes}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except Exception:
        return "recent"


def _parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    seen = set()
    for node in root.findall("./channel/item"):
        title = node.findtext("title") or ""
        link = node.findtext("link") or ""
        pub_date = node.findtext("pubDate") or ""
        description = _clean_description(node.findtext("description") or "")
        source_node = node.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        clean_title = _clean_title(title, source)
        key = clean_title.casefold()
        if not clean_title or key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "title": clean_title,
                "url": link,
                "source": source or "News",
                "pub_date": pub_date,
                "description": description,
            }
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


def fetch_news_sync(category: str = "latest") -> list[dict]:
    category = category if category in NEWS_QUERIES else "latest"
    timeout = httpx.Timeout(12.0, connect=7.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IBETINBot/1.0; +https://ibetin.com)"
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(_feed_url(category))
        response.raise_for_status()
    return _parse_feed(response.text)


async def fetch_news(category: str = "latest") -> list[dict]:
    category = category if category in NEWS_QUERIES else "latest"
    timeout = httpx.Timeout(12.0, connect=7.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IBETINBot/1.0; +https://ibetin.com)"
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(_feed_url(category))
        response.raise_for_status()
    return _parse_feed(response.text)


def _news_page(category: str, items: list[dict]) -> str:
    category = category if category in NEWS_QUERIES else "latest"
    label = NEWS_LABELS.get(category, NEWS_LABELS["latest"])

    tabs = []
    for key, title in NEWS_LABELS.items():
        active = " active" if key == category else ""
        tabs.append(
            f'<a class="tab{active}" href="{NEWS_PATH}?{urlencode({"category": key})}">{escape(title)}</a>'
        )

    cards = []
    for index, item in enumerate(items, start=1):
        desc = item.get("description") or "Fresh update from the listed publisher."
        cards.append(
            f"""
            <article class="card">
              <div class="meta"><span>{escape(item['source'])}</span><span>{escape(_age(item['pub_date']))}</span></div>
              <h2>{index}. {escape(item['title'])}</h2>
              <p>{escape(desc)}</p>
            </article>
            """
        )

    if not cards:
        cards.append(
            '<div class="empty"><b>No fresh headlines right now.</b><br>Use Refresh or try another category.</div>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate">
<title>IBETIN Sports News</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;background:#07111f;color:#f4f7fb;font-family:Arial,Helvetica,sans-serif}}
body{{min-height:100%;padding-bottom:28px}}
.top{{position:sticky;top:0;z-index:5;background:#0a1626;border-bottom:1px solid #1d3148;padding:14px 14px 10px}}
.brand{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
.brand h1{{font-size:18px;margin:0;font-weight:900;letter-spacing:.3px}}
.badge{{font-size:11px;border:1px solid #2b425d;border-radius:999px;padding:6px 9px;color:#9fb2c8;font-weight:800}}
.sub{{margin-top:6px;color:#91a6bd;font-size:12px}}
.tabs{{display:flex;gap:8px;overflow-x:auto;padding:12px 14px 2px;scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{white-space:nowrap;text-decoration:none;color:#b8c7d8;border:1px solid #263c55;background:#0b192a;border-radius:999px;padding:9px 12px;font-size:12px;font-weight:800}}
.tab.active{{background:#f4f7fb;color:#07111f;border-color:#f4f7fb}}
.wrap{{padding:12px 14px}}
.card{{background:#0d1b2e;border:1px solid #1d334c;border-radius:16px;padding:14px;margin-bottom:12px}}
.meta{{display:flex;justify-content:space-between;gap:10px;color:#85a0bb;font-size:11px;font-weight:700}}
.card h2{{font-size:16px;line-height:1.35;margin:9px 0 8px;color:#fff}}
.card p{{font-size:13px;line-height:1.5;margin:0;color:#afc0d1}}
.empty{{padding:28px 18px;text-align:center;border:1px dashed #2a4059;border-radius:16px;color:#9db0c4}}
.bottom{{padding:0 14px}}
.refresh{{display:block;text-align:center;text-decoration:none;background:#f4f7fb;color:#07111f;border-radius:14px;padding:13px 16px;font-weight:900}}
.note{{font-size:11px;color:#7189a2;line-height:1.45;text-align:center;margin-top:12px}}
</style>
</head>
<body>
  <div class="top">
    <div class="brand"><h1>📰 IBETIN SPORTS NEWS</h1><span class="badge">LIVE FEED</span></div>
    <div class="sub">{escape(label)} · India-focused sports headlines</div>
  </div>
  <nav class="tabs">{''.join(tabs)}</nav>
  <main class="wrap">{''.join(cards)}</main>
  <div class="bottom">
    <a class="refresh" href="{NEWS_PATH}?{urlencode({'category': category, 'refresh': '1'})}">↻ REFRESH NEWS</a>
    <div class="note">Headlines and short feed summaries come from external publishers via Google News RSS.</div>
  </div>
<script>
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {{
  tg.ready();
  tg.expand();
  try {{ tg.setHeaderColor('#0a1626'); tg.setBackgroundColor('#07111f'); }} catch (e) {{}}
}}
</script>
</body>
</html>"""


def _send_html(handler, status: int, html_text: str) -> None:
    data = html_text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.end_headers()
    handler.wfile.write(data)


def install_on_tracking_handler(analytics_module) -> None:
    handler_cls = analytics_module.TrackingHandler
    if getattr(handler_cls, "_ibetin_news_installed", False):
        return
    previous_get = handler_cls.do_GET

    def patched_get(self):
        parsed = urlparse(self.path)
        if parsed.path == NEWS_PATH:
            category = parse_qs(parsed.query).get("category", ["latest"])[0]
            category = category if category in NEWS_QUERIES else "latest"
            try:
                items = fetch_news_sync(category)
                _send_html(self, 200, _news_page(category, items))
            except Exception as exc:
                logger.exception("Could not render IBETIN News Mini App: %s", exc)
                _send_html(self, 503, _news_page(category, []))
            return
        previous_get(self)

    handler_cls.do_GET = patched_get
    handler_cls._ibetin_news_installed = True
    logger.info("IBETIN Sports News Mini App route installed at %s", NEWS_PATH)


async def send_news_message(message, category: str = "latest") -> None:
    await message.reply_text(
        "📰 <b>IBETIN SPORTS NEWS</b>\n\nOpen the News Mini App to browse Latest, Cricket, Football and India Sports headlines.",
        parse_mode="HTML",
        reply_markup=launcher_keyboard(),
        disable_web_page_preview=True,
    )


async def edit_news_query(query, category: str = "latest") -> None:
    await query.edit_message_text(
        "📰 <b>IBETIN SPORTS NEWS</b>\n\nAll sports news now opens inside the IBETIN Mini App.",
        parse_mode="HTML",
        reply_markup=launcher_keyboard(),
        disable_web_page_preview=True,
    )


install_on_tracking_handler(analytics)
