import os

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
STATS = os.environ.get("STATS_PATH", "stats.json")
GAME_STATE_PATH = os.environ.get("GAME_STATE_PATH", "games.pickle")
MIN_PLAYERS = int(os.environ.get("MIN_PLAYERS", "5"))
if MIN_PLAYERS < 2 or MIN_PLAYERS > 10:
    raise ValueError(f"MIN_PLAYERS must be between 2 and 10, got {MIN_PLAYERS}")
