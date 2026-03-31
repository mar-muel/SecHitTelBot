# Secret Hitler Telegram Bot

[![CI](https://github.com/mar-muel/SecHitTelBot/actions/workflows/ci.yml/badge.svg)](https://github.com/mar-muel/SecHitTelBot/actions/workflows/ci.yml)

A Telegram bot for the political card game [Secret Hitler](http://secrethitler.com/).

Forked from [julianschritt/SecretHitlerBot](https://github.com/julianschritt/SecretHitlerBot).

## Start a game

Add the bot to a Telegram group (5-10 players needed).

## Commands

- `/help` - Available commands
- `/start` - About Secret Hitler
- `/symbols` - Board symbols
- `/rules` - Link to official rules
- `/newgame` - Create a new game
- `/join` - Join an existing game
- `/startgame` - Start the game
- `/cancelgame` - Cancel the current game
- `/board` - Print current board state
- `/votes` - Show who voted
- `/calltovote` - Remind players to vote

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
uv run pytest tests/ -q    # run tests
uv run pyright              # type check
```

## Changelog

### v2.0 (2026)
- Forked from [julianschritt/SecretHitlerBot](https://github.com/julianschritt/SecretHitlerBot)
- Refactored game engine
- Upgraded `python-telegram-bot` (v22) and Python version (3.14)
- Added tests covering engine, game logic, and Telegram callbacks

### v1.0 (original)
- Original bot by Julian Schrittwieser with contributions from egenender and leviatas
- Voting and call-to-vote commands added by community contributors

## Copyright and licence

Secret Hitler is designed by Max Temkin, Mike Boxleiter, Tommy Maranges and illustrated by Mackenzie Schubert. Secret Hitler is licensed under [Creative Commons BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) and so is this bot.
