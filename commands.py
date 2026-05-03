import logging

import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

import controller
import stats
from config import MIN_PLAYERS
from boardgamebox.player import Player

logger = logging.getLogger(__name__)

# command description used in the "help" command
commands = [
    '/help - Gives you information about the available commands',
    '/start - Gives you a short piece of information about Secret Hitler',
    '/symbols - Shows you all possible symbols of the board',
    '/rules - Gives you a link to the official Secret Hitler rules',
    '/newgame - Creates a new game',
    '/join - Joins an existing game',
    '/startgame - Starts an existing game when all players have joined',
    '/cancelgame - Cancels an existing game. All data of the game will be lost',
    '/board - Prints the current board with fascist and liberals tracks, presidential order and election counter',
    '/votes - Prints who voted',
    '/calltovote - Calls the players to vote',
    '/stats - Shows game statistics'
]

symbols = [
    u"\u25FB\uFE0F" + ' Empty field without special power',
    u"\u2716\uFE0F" + ' Field covered with a card',  # X
    u"\U0001F52E" + ' Presidential Power: Policy Peek',  # crystal
    u"\U0001F50E" + ' Presidential Power: Investigate Loyalty',  # inspection glass
    u"\U0001F5E1" + ' Presidential Power: Execution',  # knife
    u"\U0001F454" + ' Presidential Power: Call Special Election',  # tie
    u"\U0001F54A" + ' Liberals win',  # dove
    u"\u2620" + ' Fascists win'  # skull
]


async def command_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    symbol_text = "The following symbols can appear on the board: \n"
    for i in symbols:
        symbol_text += i + "\n"
    await context.bot.send_message(cid, symbol_text)


async def command_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    if cid in controller.games.keys():
        session = controller.games[cid]
        if session.board:
            await context.bot.send_message(cid, session.board.print_board())
        else:
            await context.bot.send_message(cid, "There is no running game in this chat. Please start the game with /startgame")
    else:
        await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")


async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    await context.bot.send_message(cid,
                     "\"Secret Hitler is a social deduction game for 5-10 people about finding and stopping the Secret Hitler."
                     " The majority of players are liberals. If they can learn to trust each other, they have enough "
                     "votes to control the table and win the game. But some players are fascists. They will say whatever "
                     "it takes to get elected, enact their agenda, and blame others for the fallout. The liberals must "
                     "work together to discover the truth before the fascists install their cold-blooded leader and win "
                     "the game.\"\n- official description of Secret Hitler\n\nAdd me to a group and type /newgame to create a game!")
    await command_help(update, context)


async def command_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    btn = [[InlineKeyboardButton("Rules", url="http://www.secrethitler.com/assets/Secret_Hitler_Rules.pdf")]]
    rulesMarkup = InlineKeyboardMarkup(btn)
    await context.bot.send_message(cid, "Read the official Secret Hitler rules:", reply_markup=rulesMarkup)


# pings the bot
async def command_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    await context.bot.send_message(cid, 'pong - v0.4')


async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    text = stats.format_stats(cid)
    await context.bot.send_message(cid, text, parse_mode=constants.ParseMode.MARKDOWN)


# help page
async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    help_text = "The following commands are available:\n"
    for i in commands:
        help_text += i + "\n"
    await context.bot.send_message(cid, help_text)


async def command_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    assert update.message.from_user is not None
    cid = update.message.chat_id
    session = controller.games.get(cid, None)
    groupType = update.message.chat.type
    if groupType not in ['group', 'supergroup']:
        await context.bot.send_message(cid, "You have to add me to a group first and type /newgame there!")
    elif session:
        await context.bot.send_message(cid, "There is currently a game running. If you want to end it please type /cancelgame!")
    else:
        session = controller.GameSession(cid, update.message.from_user.id)
        controller.games[cid] = session
        s = stats.get()
        if cid not in s.get("groups", []):
            s.setdefault("groups", []).append(cid)
            stats.save()
        await context.bot.send_message(cid, "New game created! Configure experimental features below.")
        await context.bot.send_message(cid,
            text=controller._config_text(session),
            reply_markup=controller._config_markup(session))


async def command_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    assert update.message.from_user is not None
    groupName = update.message.chat.title
    cid = update.message.chat_id
    groupType = update.message.chat.type
    session = controller.games.get(cid, None)
    fname = update.message.from_user.first_name

    if groupType not in ['group', 'supergroup']:
        await context.bot.send_message(cid, "You have to add me to a group first and type /newgame there!")
    elif not session:
        await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    elif session.started:
        await context.bot.send_message(cid, "The game has started. Please wait for the next game!")
    elif update.message.from_user.id in session.playerlist:
        await context.bot.send_message(session.cid, f"You already joined the game, {fname}!")
    elif len(session.playerlist) >= 10:
        await context.bot.send_message(session.cid, "You have reached the maximum amount of players. "
                                      "Please start the game with /startgame!")
    else:
        uid = update.message.from_user.id
        player = Player(fname, uid)
        try:
            await context.bot.send_message(uid, f"You joined a game in {groupName}. "
                                  f"I will soon tell you your secret role.")
            session.add_player(uid, player)
        except Exception:
            bot_name = (await context.bot.get_me()).username
            await context.bot.send_message(session.cid,
                             f"{fname}, I can't send you a private message. "
                             f"Please go to @{bot_name} and click \"Start\".\n"
                             f"You then need to send /join again.")
        else:
            logger.info(f"{fname} ({uid}) joined a game in {session.cid}")
            if len(session.playerlist) >= MIN_PLAYERS:
                await context.bot.send_message(session.cid,
                    f"{fname} has joined the game. Type /startgame if this was the last "
                    f"player and you want to start with {len(session.playerlist)} players!")
            elif len(session.playerlist) == 1:
                await context.bot.send_message(session.cid,
                    f"{fname} has joined the game. There is currently "
                    f"{len(session.playerlist)} player in the game and you need {MIN_PLAYERS}-10 players.")
            else:
                await context.bot.send_message(session.cid,
                    f"{fname} has joined the game. There are currently "
                    f"{len(session.playerlist)} players in the game and you need {MIN_PLAYERS}-10 players.")


async def command_startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info('command_startgame called')
    assert update.message is not None
    assert update.message.from_user is not None
    cid = update.message.chat_id
    session = controller.games.get(cid, None)
    if not session:
        await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    elif session.started:
        await context.bot.send_message(cid, "The game is already running!")
    elif update.message.from_user.id != session.initiator and \
            (await context.bot.get_chat_member(cid, update.message.from_user.id)).status not in ("administrator", "creator"):
        await context.bot.send_message(session.cid, "Only the initiator of the game or a group admin "
                                      "can start the game with /startgame")
    elif len(session.playerlist) < MIN_PLAYERS:
        await context.bot.send_message(session.cid, f"There are not enough players (min. {MIN_PLAYERS}, max. 10). "
                                      "Join the game with /join")
    else:
        # Create engine from lobby players, assign roles, set up board
        session.start()
        assert session.engine is not None
        if session.config.ai_narration:
            await context.bot.send_message(session.cid, "AI Narration is enabled for this game.")
        await controller.inform_players(context.bot, session)
        await controller.inform_fascists(context.bot, session)
        await context.bot.send_message(session.cid, session.engine.board.print_board())
        await controller.present_action(context.bot, session)


async def command_cancelgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info('command_cancelgame called')
    assert update.message is not None
    assert update.message.from_user is not None
    cid = update.message.chat_id
    if cid in controller.games.keys():
        session = controller.games[cid]
        status = (await context.bot.get_chat_member(cid, update.message.from_user.id)).status
        if update.message.from_user.id == session.initiator or \
                status in ("administrator", "creator"):
            await controller.end_game(context.bot, session, cancelled=True)
        else:
            await context.bot.send_message(cid, "Only the initiator of the game or a group admin "
                                  "can cancel the game with /cancelgame")
    else:
        await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")


async def command_votes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    try:
        if cid in controller.games.keys():
            session = controller.games[cid]
            if not session.dateinitvote:
                # If dateinitvote is null, then the voting didn't start
                if session.dateinitnomination:
                    _, ctx = session.engine.pending_action()  # type: ignore[misc]
                    president = ctx["president"]
                    text = f"Waiting on {president.name} to nominate a Chancellor."
                    elapsed = (datetime.datetime.now() - session.dateinitnomination).total_seconds()
                    remaining = controller.NOMINATION_TIMEOUT_SECONDS - elapsed
                    hours, minutes = int(remaining // 3600), int((remaining % 3600) // 60)
                    text += f"\nTime remaining: {hours}h {minutes}m"
                    await context.bot.send_message(cid, text)
                else:
                    await context.bot.send_message(cid, "The voting didn't start yet.")
            else:
                start = session.dateinitvote
                stop = datetime.datetime.now()
                elapsed = stop - start
                if elapsed > datetime.timedelta(minutes=1):
                    assert session.engine is not None
                    _, ctx = session.engine.pending_action()  # type: ignore[misc]
                    history_text = (f"Vote history for President {ctx['president'].name} "
                                    f"and Chancellor {ctx['chancellor'].name}:\n\n")
                    for player in session.player_sequence:
                        if player.uid in session.pending_votes:
                            history_text += f"{session.playerlist[player.uid].name} registered a vote.\n"
                        else:
                            history_text += f"{session.playerlist[player.uid].name} didn't register a vote.\n"
                    if session.config.vote_timeout:
                        elapsed = (datetime.datetime.now() - session.dateinitvote).total_seconds()
                        remaining = controller.VOTE_TIMEOUT_SECONDS - elapsed
                        hours, minutes = int(remaining // 3600), int((remaining % 3600) // 60)
                        history_text += f"\nTime remaining: {hours}h {minutes}m"
                    await context.bot.send_message(cid, history_text)
                else:
                    await context.bot.send_message(cid, "One minute must pass before you can see the votes.")
        else:
            await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    except Exception as e:
        await context.bot.send_message(cid, str(e))


async def command_calltovote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    cid = update.message.chat_id
    try:
        if cid in controller.games.keys():
            session = controller.games[cid]
            if not session.dateinitvote:
                await context.bot.send_message(cid, "The voting didn't start yet.")
            else:
                start = session.dateinitvote
                stop = datetime.datetime.now()
                elapsed = stop - start
                if elapsed > datetime.timedelta(minutes=1):
                    # Only remind players that haven't voted yet
                    history_text = ""
                    for player in session.player_sequence:
                        if player.uid not in session.pending_votes:
                            history_text += (f"It's time to vote "
                                             f"[{session.playerlist[player.uid].name}]"
                                             f"(tg://user?id={player.uid}).\n")
                    await context.bot.send_message(cid, text=history_text, parse_mode=constants.ParseMode.MARKDOWN)
                else:
                    await context.bot.send_message(cid, "One minute must pass before you can call to vote.")
        else:
            await context.bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    except Exception as e:
        await context.bot.send_message(cid, str(e))
