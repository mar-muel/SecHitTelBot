"""Secret Hitler Telegram Bot.

Setup:
    1. Create a bot via @BotFather on Telegram
    2. Set the token: export TELEGRAM_BOT_TOKEN=<your_token>
    3. Run: uv run python main.py

Optional env vars:
    MIN_PLAYERS      - Minimum players to start a game (default: 5)
    STATS_PATH       - Path to stats JSON file (default: stats.json)
    ANTHROPIC_API_KEY - API key for AI narration feature (optional)
"""

import logging

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

import commands
import controller
import persistence
import stats
from config import GAME_STATE_PATH, TOKEN

logging.basicConfig(format='%(asctime)s [%(levelname)-5.5s] [%(name)-12.12s]: %(message)s',
                level=logging.INFO,
                handlers=[
                    logging.FileHandler('logs/logging.log'),
                    logging.StreamHandler(),
                ])

logger = logging.getLogger(__name__)


async def _save_state(app):
    persistence.save_games(GAME_STATE_PATH)


def main():
    controller.games.clear()
    stats.load()
    logger.info("Starting bot...")

    app = Application.builder().token(TOKEN).post_shutdown(_save_state).build()
    controller._job_queue = app.job_queue
    persistence.load_games(GAME_STATE_PATH)

    app.add_handler(CommandHandler("start", commands.command_start))
    app.add_handler(CommandHandler("help", commands.command_help))
    app.add_handler(CommandHandler("board", commands.command_board))
    app.add_handler(CommandHandler("rules", commands.command_rules))
    app.add_handler(CommandHandler("ping", commands.command_ping))
    app.add_handler(CommandHandler("symbols", commands.command_symbols))
    app.add_handler(CommandHandler("stats", commands.command_stats))
    app.add_handler(CommandHandler("newgame", commands.command_newgame))
    app.add_handler(CommandHandler("startgame", commands.command_startgame))
    app.add_handler(CommandHandler("cancelgame", commands.command_cancelgame))
    app.add_handler(CommandHandler("join", commands.command_join))
    app.add_handler(CommandHandler("votes", commands.command_votes))
    app.add_handler(CommandHandler("calltovote", commands.command_calltovote))

    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_config_(.*)", callback=controller.handle_config))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_chan_(.*)", callback=controller.nominate_chosen_chancellor))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_insp_(.*)", callback=controller.choose_inspect))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_choo_(.*)", callback=controller.choose_choose))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_kill_(.*)", callback=controller.choose_kill))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(yesveto|noveto)", callback=controller.choose_veto))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(liberal|fascist|veto)", callback=controller.choose_policy))
    app.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(Ja|Nein)", callback=controller.handle_voting))

    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, controller.record_message))

    app.add_error_handler(controller.error_handler)

    app.run_polling()


if __name__ == '__main__':
    main()
