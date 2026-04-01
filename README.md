# Secret Hitler Telegram Bot

[![CI](https://github.com/mar-muel/SecHitTelBot/actions/workflows/ci.yml/badge.svg)](https://github.com/mar-muel/SecHitTelBot/actions/workflows/ci.yml)

A Telegram bot for the political card game [Secret Hitler](http://secrethitler.com/).

## Start a game

Run your own bot (see below) and add it to a Telegram group (5-10 players needed).

## Run bot

Install [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
# 1. Get a bot token from @BotFather on Telegram
# 2. Run:
TELEGRAM_BOT_TOKEN=<your_token> uv run python main.py
```

Set `MIN_PLAYERS=2` for testing with fewer people.

```sh
uv run pytest tests/ -q    # run tests
uv run pyright             # type check
```

## Changelog

### v2.0 (Apr 2026)
- Upgraded `python-telegram-bot` (v22) and Python version (3.14)
- Refactored game engine
- Added tests for core game logic
- Added simulation runner, basic strategies

### v1.0 (original)
- Original bot by Julian Schrittwieser with contributions from egenender and leviatas, see [julianschritt/SecretHitlerBot](https://github.com/julianschritt/SecretHitlerBot)
- Voting and call-to-vote commands added by community contributors

## Copyright and licence

Secret Hitler is designed by Max Temkin, Mike Boxleiter, Tommy Maranges and illustrated by Mackenzie Schubert. Secret Hitler is licensed under [Creative Commons BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) and so is this bot.
