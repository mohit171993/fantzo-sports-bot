import logging
import os
from typing import Optional

import httpx

import bot as core

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-luna"
MAX_HISTORY_MESSAGES = 10
MAX_USER_CHARS = 1800

SYSTEM_INSTRUCTIONS = """You are IBETIN Assistant inside Telegram Business chat.

Goals:
- Help verified IBETIN users with navigation, sports questions, Live Line, match alerts, account help, payments, and support.
- Reply naturally in the user's language. If they use Hinglish, reply in Hinglish. Keep answers concise and conversational.
- You are an AI assistant; do not claim to be a human agent.
- Never ask for or repeat passwords, OTPs, CVV, PINs, full card numbers, private keys, or full banking credentials.
- For account-specific payment disputes, failed deposits/withdrawals, KYC, or private account issues, direct the user to official IBETIN Support.
- Do not invent live scores, match status, odds, payment status, or account status. If live data is not provided in the conversation, tell the user to open IBETIN Live Line / Sports or official support as appropriate.
- Do not promise guaranteed winnings or risk-free outcomes.
- Avoid long menus. The chat already has JOIN IBETIN, WATCH IBETIN LIVE LINE, and JOIN CHANNEL buttons.
- If the user only says hi/hello, greet briefly and ask what they need.
"""


def enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def model_name() -> str:
    return os.getenv("IBETIN_AI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def ensure_tables() -> None:
    with core.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_business_ai_history_user
            ON business_ai_history(user_id, id)
            """
        )


def _save(user_id: int, role: str, content: str) -> None:
    ensure_tables()
    clean = str(content or "").strip()[:4000]
    if not clean:
        return
    with core.db() as conn:
        conn.execute(
            """
            INSERT INTO business_ai_history(user_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(user_id), str(role), clean, core.now_iso()),
        )
        # Keep history compact per user.
        conn.execute(
            """
            DELETE FROM business_ai_history
            WHERE user_id = ?
              AND id NOT IN (
                SELECT id FROM business_ai_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
              )
            """,
            (int(user_id), int(user_id), MAX_HISTORY_MESSAGES),
        )


def _history(user_id: int):
    ensure_tables()
    with core.db() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM business_ai_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(user_id), MAX_HISTORY_MESSAGES),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def _build_input(user_id: int, user_text: str) -> str:
    lines = []
    for row in _history(user_id):
        role = "User" if row["role"] == "user" else "Assistant"
        lines.append(f"{role}: {row['content']}")
    lines.append(f"User: {user_text}")
    lines.append("Assistant:")
    return "\n".join(lines)


def _extract_text(payload) -> str:
    if not isinstance(payload, dict):
        return ""

    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    pieces = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                pieces.append(text.strip())
    return "\n".join(pieces).strip()


async def reply(user_id: int, text: str) -> Optional[str]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None

    user_text = " ".join(str(text or "").split())[:MAX_USER_CHARS]
    if not user_text:
        return None

    payload = {
        "model": model_name(),
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": _build_input(int(user_id), user_text),
        "max_output_tokens": 350,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = httpx.Timeout(20.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            answer = _extract_text(response.json())
    except Exception as exc:
        logger.warning("IBETIN AI reply unavailable: %s", str(exc)[:180])
        return None

    if not answer:
        return None

    answer = answer[:3500].strip()
    _save(int(user_id), "user", user_text)
    _save(int(user_id), "assistant", answer)
    return answer
