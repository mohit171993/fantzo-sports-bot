# Fantzo Live TV Banner Queue

Admin-only Telegram commands:

- `/banners` — queue/status instructions
- `/bannerpostnow` — post next queued banner immediately
- `/bannerpause` — pause automatic posting
- `/bannerresume` — resume automatic posting
- `/bannerclear` — clear unposted queue

Send photo banners directly to the admin bot account to enqueue them. Telegram file IDs are stored in the existing Fantzo database.

Default automatic slot: 17:30 Dubai / 19:00 IST, maximum one queued banner per calendar day.

Environment overrides:

- `FANTZO_CHANNEL_ID` (default `@fantzoupdates`)
- `FANTZO_BANNER_HOUR_DUBAI` (default `17`)
- `FANTZO_BANNER_MINUTE_DUBAI` (default `30`)

Production launcher after verification: `python bot_banner_test.py`.
