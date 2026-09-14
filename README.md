# IBETIN Sports Updates Bot

Telegram sports bot deployment for **IBETIN**.

This branch is dedicated to IBETIN and was created from the Fantzo code snapshot locked on 14 September 2026. It is intentionally isolated from the live Fantzo project and is not merged back into Fantzo.

## Current features

- Welcome screen
- Cricket, football, live, upcoming, results, news, subscribe and settings menus
- Direct IBETIN website buttons
- Telegram Business auto replies
- Smart reminders and analytics
- Restricted admin command using `ADMIN_USER_ID`
- Live TV / MiniTV integration from the locked source snapshot

## Environment variables

- `BOT_TOKEN` — use a separate IBETIN Telegram bot token
- `ADMIN_USER_ID` (defaults to `8992664481`)
- `DB_PATH` (IBETIN deployment uses `ibetin_bot.db`)
- `IBETIN_HOME_URL` (default `https://ibetin.com`)
- `IBETIN_MINI_APP_URL` (default `https://ibetin.com`)
- `IBETIN_SPORTS_BOT_URL` (optional)
- `IBETIN_CHANNEL_URL` (optional)
- `IBETIN_MINI_APP_DEEP_LINK` (optional)
- `IBETIN_LIVE_TV_URL` (optional)

## Railway

Project: `ibetin`

Service: `ibetin-app`

Source branch: `ibetin-locked-2026-09-14`

Start command:

```bash
python bot_tracked.py
```

## IBETIN links

- Home: https://ibetin.com
- Live: https://ibetin.com/en/live
- Slots: https://ibetin.com/en/slots
- Registration: https://ibetin.com/en/registration

## Compatibility note

Some internal Python module names and callback identifiers still contain the legacy `fantzo` prefix. They are intentionally retained to preserve the behavior of the locked 14/09 code snapshot. User-facing branding, links and the IBETIN deployment configuration are separate.
