# Fantzo Conversation / Project Archive — 2026-09-22

This is a durable operational archive of the Fantzo work completed and decisions made in the ChatGPT conversation up to this lock point. It is a project-state summary, not a verbatim chat transcript.

## Locked state

- Repository: `mohit171993/fantzo-sports-bot`
- Exact locked code commit: `d320f7a1cb793281d06f7be1a1cf3766176ab4b7`
- Lock branch: `locked-fantzo-2026-09-22-admin-crm-strategy`
- Current successful Railway deployment at lock time:
  - Deployment ID: `37264263-cc38-46f2-9dd7-a79fe465177e`
  - Status: SUCCESS
  - Commit: `d320f7a1cb793281d06f7be1a1cf3766176ab4b7`
- Production start command remains: `python bot_restore_test.py`
- Persistent DB remains mounted under `/data`
- Do not repoint this lock branch. Future approved versions must get a NEW timestamped lock.

## Final business strategy agreed

The acquisition and conversion strategy is:

1. Run Telegram Ads to Fantzo bot.
2. User enters the bot.
3. User completes Telegram self-contact verification.
4. Fantzo captures the Telegram-linked mobile number.
5. The lead is stored/deduplicated.
6. Admin/team gets the lead and contacts the user.
7. Sales team updates lead status and attempts conversion.
8. Campaign and conversion reporting is used to judge ad quality.
9. Unverified users receive reminder follow-up.
10. Verified users continue into Fantzo sports experience.

Primary commercial objective: turn Telegram Ads traffic into verified mobile leads, then contact and convert those leads.

## Verification rules

Verification is global across Fantzo and Live TV.

A user is verified only when Telegram provides a Contact whose `contact.user_id` matches the requesting Telegram user.

Rules:
- Any country number is accepted.
- Typed numbers do not verify.
- Same verification is shared across normal bot, Business DM handoff and Live TV.
- No second verification should be required after successful verification.
- Verification copy includes notice that Fantzo may contact the user about the enquiry and that the user may ask to stop.
- Users can opt out with STOP / UNSUBSCRIBE / DO NOT CONTACT / /stop.

Current verified-state storage:
- `live_tv_mobile_users`
- verified iff `capture_method='telegram_contact'`

## Test account rule

Permanent testing instruction from the user:

After every Fantzo change:
1. deploy the change;
2. health-check it;
3. reset Telegram username `mohit_97saxena` to unverified;
4. confirm `verified_after=0`;
5. remove the temporary reset hook so future restarts do not repeatedly reset the user.

Known resolved test user:
- username: `mohit_97saxena`
- Telegram user ID: `1456774567`

Reset must preserve:
- mobile number
- source
- created_at
- lead history
- campaign attribution
- CRM/reporting history

Only verification state is changed for testing.

At this archive point the user is unverified for testing.

## Paid-ad attribution

Fantzo now supports campaign attribution from Telegram start parameters.

Recommended ad links:
- `https://t.me/fantzoofficialbot?start=ad_cricket_01`
- `https://t.me/fantzoofficialbot?start=ad_football_01`
- etc.

Use a unique `ad_...` code for every Telegram Ad or campaign.

Admin helper:
- `/adlink NAME`

Attribution is persisted before the verification gate so paid users are not lost from campaign reporting.

Lead funnel tracks:
- bot starts
- paid-ad starts
- verification prompts
- verified users
- deduplicated mobile leads
- reminder-assisted verifications
- interested leads
- converted leads
- campaign-level starts → verified → interested → converted

## CRM / leads

Fantzo has a lead/CRM backend based on deduplicated verified mobile numbers.

Lead statuses:
- NEW
- CONTACTED
- NO_ANSWER
- INTERESTED
- CONVERTED
- NOT_INTERESTED
- DO_NOT_CONTACT

Lead data includes:
- verified mobile
- primary Telegram user ID
- Telegram username/name
- source campaign
- status
- assigned agent
- notes
- contact permission timestamp
- created/updated timestamps
- last contact timestamp
- converted timestamp

Admin commands:
- `/lead <user_id | @username | mobile>`
- `/leadstatus <lead> <status>`
- `/leadassign <lead> <agent name>`
- `/leadnote <lead> <note>`
- `/adlink <campaign name>`

New verified leads generate an instant admin notification.

A CRM lead can be opened in Telegram and statuses can be changed by buttons.

A direct WhatsApp button was added for contactable leads.

DO_NOT_CONTACT users must not be contacted.

## Reminder strategy

Unverified normal bot users:
- approximately 1 hour
- approximately 24 hours
- approximately 72 hours

Unverified Business DM users:
- approximately 6 hours
- approximately 24 hours
- approximately 72 hours

Verified users keep the normal sports re-engagement reminder cycle.

Quiet hours remain:
- 22:00–08:00 Dubai time

Unverified reminder copy is verification-specific.

Business reminder opens the normal bot verification handoff.

Normal-bot reminder uses native Telegram contact sharing.

## Verification UI / conversion screen

Verification button:
- `✅ VERIFY & CONTINUE`
- native Telegram contact request
- persistent until verification completes

Reason for persistence:
Telegram could hide a one-time ReplyKeyboard button, leaving only the Telegram menu button visible.

Post-verification behavior:
- confirmation
- campaign-relevant primary action
- Open Fantzo CTA
- Full Sports Menu
- existing Fantzo banner can be reused as the hero graphic when configured

## Current admin state at this lock point

The latest deployed Fantzo /admin is a CRM-first team dashboard.

Current structure includes:
- CRM
- New Leads
- Interested
- No Answer
- Campaigns
- Funnel
- Verified Leads
- Follow-up
- Reports
- Tools
- Team Guide

Technical/raw reports were moved under advanced sections so they do not clutter daily sales workflow.

Main admin dashboard includes attention metrics such as:
- hot leads
- new
- interested
- no answer
- contacted
- DNC
- paid-ad starts
- verified leads
- new mobile leads
- converted
- total leads
- ad users not yet verified

Reports were simplified for sales/marketing use.

## Important next decision: make Fantzo admin like iBetin

The user explicitly decided that Fantzo admin should be made more like iBetin.

The exact iBetin implementation was found in the SAME repository using branch:

- `ibetin-locked-2026-09-21`

Important iBetin source files:
- `ibetin_reports.py`
- `bot_tracked.py`
- `ibetin_hub.py`
- `ibetin_phone_verify.py`
- `ibetin_liveline_v19_trust_intel.py`

The iBetin report center is simpler and uses a compact navigation model:
- Overview
- Bot Users
- Verified Users + Mobile
- DM Users
- Reminders
- Activity
- Web Opens
- Campaigns
- Download All Reports

Agreed direction for the NEXT Fantzo admin iteration:

Keep iBetin's simple navigation philosophy, while preserving Fantzo's stronger CRM.

Proposed Fantzo structure:
- 📊 OVERVIEW
- 💼 CRM / LEADS
- 📱 VERIFIED USERS + MOBILE
- 📣 CAMPAIGNS
- 💬 DM USERS
- ⏰ FOLLOW-UP
- 📈 ACTIVITY
- 📦 DOWNLOAD REPORTS

CRM then contains:
- NEW
- CONTACTED
- NO ANSWER
- INTERESTED
- CONVERTED
- NOT INTERESTED
- DO NOT CONTACT
- WhatsApp action
- agent
- notes
- lead detail

This iBetin-style simplification has NOT yet been implemented at this archive point. The current live code is still the CRM-first Fantzo dashboard at commit `d320f7a1...`.

## iBetin reference details already inspected

iBetin report implementation:
- file: `ibetin_reports.py`
- branch: `ibetin-locked-2026-09-21`

Notable iBetin design strengths:
- simple report center
- compact set of first-level buttons
- verified-mobile reporting
- DM reporting
- reminders/activity/web/campaign reporting
- complete report export
- multi-admin/report authorization model

Fantzo should reuse the architecture and team familiarity, but should not lose the dedicated CRM functionality added for Fantzo.

## Business DM path

Business DM verification handoff remains supported.

Unverified Business DM:
- user sees verification prompt/link
- opens normal Fantzo bot
- verifies through Telegram self-contact
- same verification is reused afterward

Business DM reply sending uses the correct Telegram Business connection context.

## Reports / exports

Current Fantzo reports include:
- overview
- lead funnel
- verified numbers
- Business DM
- reminders/follow-up
- daily activity
- advanced users/engagement/Live TV/web/favourites/banner reports
- CSV exports
- complete ZIP reporting pack

Full mobile numbers remain admin-only.

## Startup / reliability improvements

Background job startup was cleaned so reminder/growth/banner tasks wait until the Telegram Application is running.

At successful deployments after this cleanup:
- no PTB startup task warning
- no startup traceback
- bot starts normally

Existing operational safety retained:
- /apistatus
- /backupstatus
- /backupnow
- automatic SQLite backup
- backup retention
- existing Live TV reliability layer

## Live TV rule

Do not unnecessarily modify the working Live TV engine.

Live TV analytics canonical action remains:
- `clicks.action='live_tv_status'`

Verification changes should not create a second verification for Live TV.

## Visual strategy

Do not overload the verification screen with graphics.

Preferred:
- clean verification screen with strong CTA
- hero/banner immediately after verification
- graphics for major sports moments/campaigns
- button-driven bot UX

## Telegram Ads considerations discussed

Ad copy and destination should match the actual bot experience.

If verification is required immediately, ad copy/profile should not imply a frictionless sports screen without mentioning verification.

Bot native description was updated to align the destination with sports content and one-time Telegram mobile verification.

No guarantee should be made about Telegram Ads approval.

## Current production infrastructure

Railway project:
- `fantzo-sports-bot`
- Project ID: `984cfd39-b5df-4e6c-983c-7c7f7f781fd0`
- Production environment ID: `dc2daf40-9fe1-443c-845a-616a3859cdcb`
- Service: `fantzo-sports-bot-app`
- Service ID: `902b2d38-4b76-41d4-8e8e-33bf5727befd`
- Volume mount: `/data`
- DB: `/data/fantzo_bot.db`
- Start command: `python bot_restore_test.py`

Do not accept environment-wide staged changes blindly. Always inspect staged Railway config first because stale staged source patches have existed.

## Development / deployment discipline

User preference:
- direct execution
- narrow changes
- test before merge/lock
- preserve working code
- do not claim live-tested if only startup-tested
- reset `mohit_97saxena` after every change
- only merge/lock after behavior is confirmed or user explicitly requests it

When locking:
1. verify exact live commit;
2. create a NEW lock branch;
3. never repoint an older lock;
4. keep old rollback locks intact.

## This archive point

User request:
- "Lock till here archive our conversation so u can review when needed"

Completed actions represented by this archive:
- current live code locked at exact commit `d320f7a1cb793281d06f7be1a1cf3766176ab4b7`
- conversation/project decisions archived in GitHub
- iBetin admin source identified and reviewed
- next logical task is to redesign Fantzo admin to follow iBetin's simpler structure while retaining Fantzo CRM

