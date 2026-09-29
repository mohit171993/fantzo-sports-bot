# Fantzo Live TV / Full mode prototype

This is local review work only. It has not been deployed.

## Admin control

In the Fantzo bot's private chat, the configured `ADMIN_USER_ID` can use `/mode livetv`, `/mode full`, or `/mode status`. The status reply also has two inline buttons. `/mode clean` and `/mode liveline` map to Live TV for compatibility. Other users receive no response to these commands or forwarded mode buttons.

`/mode livetv` refuses to switch unless public Live TV is enabled, a public HTTPS `/minitv` URL is configured, the embedded provider URL is HTTPS and does not resemble the private SKY test link, and `DB_PATH` points to a file inside the mounted `/data` volume. The admin sees a clear error and the current mode is unchanged. If a previously saved Live TV mode later loses that configuration, `/mode status` flags the degraded state.

The mode and each switch are stored in the bot SQLite database (`DB_PATH`). The initial state is Full, preserving the current production behaviour. A persistent queue tracks verified users' chat-menu updates and records successes or failures; `/mode status` shows those counts.

## Live TV behaviour

- Existing Telegram self-contact verification stays in place. Public bot descriptions and preverification commands remain neutral in both modes.
- After verification, the Live TV home replaces the current conversion card. Existing Full flow remains unchanged in Full mode.
- An early update handler blocks stale Full callbacks, direct commands and normal Business DM replies. Admin reporting and CRM controls still work in the admin's private chat; broadcasts and channel banner sends are blocked in Live TV. Group and channel updates are silent, avoiding unsolicited bot replies and old Full handler fallthrough.
- The bot-owned `/go` redirect sends old tracking links back to the Live TV bot entry point instead of the Fantzo website. Full mode keeps the existing redirect.
- The current public MiniTV URL is offered only if the existing `LIVE_TV_MODE=public` gate is active. The private SKY admin URL and its test token are never shown.
- Campaign reminders and scheduled channel banners are held in Live TV; their queues/settings remain intact for Full.
- Verified users' per-chat WebApp menus are changed in a bounded background queue and restored on Full. Before each menu update, verification is checked again; a revoked user receives only neutral preverification commands. Menus can take time to reconcile, and errors are visible in status.

## Release gates and limits

1. Verify `DB_PATH` actually points to the mounted `/data` volume in Railway. The code uses `bot.DB_PATH`, whose default is the relative `fantzo_bot.db`; a Railway volume mounted at `/data` does not by itself make that file persistent. The new activation preflight refuses Live TV when `DB_PATH` is outside the mounted volume. Set and privately verify an absolute `DB_PATH` under `/data`, then switch modes, restart the service, and confirm `/mode status` and the audit row survive. Do not change the existing user database path without a data migration or an explicit verification that it already uses `/data`.
2. Inspect the public MiniTV route and embedded provider in a verified test account, including cold load and mobile view. Railway deployment logs confirm the route was installed with `mode=public`, but provider content and the exact public URL are still unverified.
3. Review current ad destinations. If an ad links through the bot-owned `/go`, Live TV mode changes that destination to the bot. The code does **not** pause or manage ads.
4. Previously sent **direct external links** and WebApp URLs cannot be revoked by the bot. New bot replies and bot-owned `/go` are guarded. A fully clean journey also requires reviewing those external destinations.
5. Run a real Telegram smoke test for an unverified user, verified user, admin switch, Business DM, an old callback, MiniTV, and menu synchronisation before deployment.

Review fixes: `fantzo_mode.py` now rechecks verification inside `_sync_one_chat_menu` and stops group/channel updates inside `liveline_guard`. `test_fantzo_mode.py` covers revoked verification during queued menu sync and group command silence.

Local tests: `test_fantzo_mode.py` (15 tests with Telegram API stubs), 7 preverification tests, 5 daily-delivery tests, 3 brand-isolation tests, real `python-telegram-bot==21.6` import/handler construction, Python syntax compilation, and `git diff --check`. These suites run in separate Python processes because the focused mode suite replaces `telegram` and `bot` modules with stubs. No real Telegram or Railway execution has been performed for this prototype.

## Review branch

`feat/fantzo-live-tv-mode` is based on `origin/main` at `c6fb097`. It includes only the mode files and mode-specific changes; the separate first-visit work in the original checkout is excluded. The branch is local and has not been pushed.
