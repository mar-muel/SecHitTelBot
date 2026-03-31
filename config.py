import os

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
STATS = os.environ.get("STATS_PATH", "stats.json")
MIN_PLAYERS = int(os.environ.get("MIN_PLAYERS", "5"))
