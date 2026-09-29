# DURASPORTS Telegram bot

This production branch is dedicated to DURASPORTS. It uses the established
Live Line feed with Roanuz first and Highlightly as a fallback. The `ibetin_*`
Python module and environment names are legacy implementation names; configure
the DURA deployment separately from IBETIN and Fantzo.

Production branch: `durasports-production-2026-09-22`. Start command:
`python bot_tracked.py`.

The active bot username is resolved from Telegram at startup for verification
links. If Telegram cannot supply it, those links are omitted without stopping
the bot or falling back to another brand. Inspect the live BotFather display
name, username, avatar, about text, and manual menu before deployment; source
review alone cannot confirm them. This change preserves the existing channel
posting schedule, destination, and enabled state. Verify the live channel
configuration before any future routing change.

## Verified lead entry

Before mobile verification, the bot chat and public profile show neutral
verification copy. After verification, the first card leads with Live Line,
offers the on-demand **Today on DURA** match briefing, and keeps the Mini App
one tap away. The briefing shows at most three actual feed rows, with an empty
state when the feed cannot provide a current result. It adds no reminders.

A campaign `/start` payload can route to a specific match only when it is
listed in `DURA_ENTRY_MAP`. Example configuration (use a real provider key
confirmed from the DURA Live Line feed):

```text
DURA_ENTRY_MAP={"dura_live":"liveline","dura_matchday":{"kind":"match","match_key":"PROVIDER_MATCH_KEY"}}
```

The bot never treats the payload as a URL. The match key is restricted to
letters, digits, underscores, hyphens, periods and colons. The pending route
survives a bot restart during contact verification and expires after 24 hours.
The Live Line opens the requested match only when its current feed lists that
key; an expired or missing match leaves the standard match board available.
Unknown campaign payloads show the regular DURA card.

Keep the existing DURA `DB_PATH` on persistent storage so this handoff survives
a process restart. The existing `IBETIN_LIVE_LINE_URL` must point to the
approved DURA Live Line endpoint. A Mini App button open is an open, not a
completed registration or confirmed stream playback.

Run focused tests with:

```bash
python -m unittest test_dura_entry test_dura_preverification test_dura_automation_controls test_dura_creative_gate
```
