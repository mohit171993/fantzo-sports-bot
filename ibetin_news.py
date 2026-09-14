import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
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
MAX_ITEMS = 6


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


async def fetch_news(category: str = "latest") -> list[dict]:
    url = _feed_url(category)
    timeout = httpx.Timeout(12.0, connect=7.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IBETINBot/1.0; +https://ibetin.com)"
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)
    items = []
    seen = set()
    for node in root.findall("./channel/item"):
        title = node.findtext("title") or ""
        link = node.findtext("link") or ""
        pub_date = node.findtext("pubDate") or ""
        source_node = node.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        clean_title = _clean_title(title, source)
        key = clean_title.casefold()
        if not clean_title or not link or key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "title": clean_title,
                "url": link,
                "source": source or "News",
                "pub_date": pub_date,
            }
        )
        if len(items) >= MAX_ITEMS:
            break
    return items


def _keyboard(items: list[dict], category: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🔥 Latest", callback_data="news:latest"),
            InlineKeyboardButton("🏏 Cricket", callback_data="news:cricket"),
        ],
        [
            InlineKeyboardButton("⚽ Football", callback_data="news:football"),
            InlineKeyboardButton("🇮🇳 India", callback_data="news:india"),
        ],
    ]
    for index, item in enumerate(items[:5], start=1):
        rows.append(
            [InlineKeyboardButton(f"{index}. Read · {item['source'][:25]}", url=item["url"])]
        )
    rows.extend(
        [
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"news:{category}")],
            [InlineKeyboardButton("⬅️ Back to Home", callback_data="back")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def render_news(items: list[dict], category: str) -> tuple[str, InlineKeyboardMarkup]:
    label = NEWS_LABELS.get(category, NEWS_LABELS["latest"])
    if not items:
        text = (
            f"📰 <b>IBETIN · {escape(label.upper())}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No fresh headlines were returned right now. Tap Refresh or try another category."
        )
        return text, _keyboard([], category)

    lines = [
        f"📰 <b>IBETIN · {escape(label.upper())}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "Fresh headlines from multiple news publishers:",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(f"<b>{index}. {escape(item['title'])}</b>")
        lines.append(f"{escape(item['source'])} · {_age(item['pub_date'])}")
        if index != len(items):
            lines.append("")

    lines.extend(
        [
            "",
            "Tap a numbered source button below to read the original story.",
            "<i>Headlines are provided by external publishers and may change.</i>",
        ]
    )
    return "\n".join(lines), _keyboard(items, category)


async def send_news_message(message, category: str = "latest") -> None:
    try:
        items = await fetch_news(category)
        text, markup = render_news(items, category)
    except Exception as exc:
        logger.exception("IBETIN sports news fetch failed: %s", exc)
        text = (
            "📰 <b>IBETIN SPORTS NEWS</b>\n\n"
            "News is temporarily unavailable. Please try again shortly."
        )
        markup = _keyboard([], category)
    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def edit_news_query(query, category: str = "latest") -> None:
    try:
        items = await fetch_news(category)
        text, markup = render_news(items, category)
    except Exception as exc:
        logger.exception("IBETIN sports news refresh failed: %s", exc)
        text = (
            "📰 <b>IBETIN SPORTS NEWS</b>\n\n"
            "News is temporarily unavailable. Please try again shortly."
        )
        markup = _keyboard([], category)

    if query.message and query.message.text:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    elif query.message:
        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
