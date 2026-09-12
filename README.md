# Fantzo Sports Updates Bot

Telegram bot for **@fantzoofficialbot**.

This repository is dedicated to Fantzo only and is intentionally separate from all Betroxy repositories, services, variables and deployments.

## Current features

- Welcome screen
- Cricket, football, live, upcoming, results, news, subscribe and settings menus
- Direct Fantzo website buttons
- Restricted admin command using `ADMIN_USER_ID`

## Environment variables

- `BOT_TOKEN`
- `ADMIN_USER_ID` (defaults to `8992664481`)
- `HIGHLIGHTLY_API_KEY` (Highlightly Sports API key, sent as `x-rapidapi-key`)

## Run locally

```bash
pip install -r requirements.txt
python bot.py
```

## Fantzo links

- Home: https://fantzo.com
- Live: https://fantzo.com/en/live
- Slots: https://fantzo.com/en/slots
- Registration: https://fantzo.com/en/registration
