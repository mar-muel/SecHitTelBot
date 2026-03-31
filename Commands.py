import json
import logging as log

import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode

import MainController
import GamesController
from Constants.Config import STATS
from Boardgamebox.Player import Player

# Enable logging
log.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                level=log.INFO,
                filename='logs/logging.log')

logger = log.getLogger(__name__)

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
    '/calltovote - Calls the players to vote'
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


def command_symbols(bot, update):
    cid = update.message.chat_id
    symbol_text = "The following symbols can appear on the board: \n"
    for i in symbols:
        symbol_text += i + "\n"
    bot.send_message(cid, symbol_text)


def command_board(bot, update):
    cid = update.message.chat_id
    if cid in GamesController.games.keys():
        session = GamesController.games[cid]
        if session.board:
            bot.send_message(cid, session.board.print_board())
        else:
            bot.send_message(cid, "There is no running game in this chat. Please start the game with /startgame")
    else:
        bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")


def command_start(bot, update):
    cid = update.message.chat_id
    bot.send_message(cid,
                     "\"Secret Hitler is a social deduction game for 5-10 people about finding and stopping the Secret Hitler."
                     " The majority of players are liberals. If they can learn to trust each other, they have enough "
                     "votes to control the table and win the game. But some players are fascists. They will say whatever "
                     "it takes to get elected, enact their agenda, and blame others for the fallout. The liberals must "
                     "work together to discover the truth before the fascists install their cold-blooded leader and win "
                     "the game.\"\n- official description of Secret Hitler\n\nAdd me to a group and type /newgame to create a game!")
    command_help(bot, update)


def command_rules(bot, update):
    cid = update.message.chat_id
    btn = [[InlineKeyboardButton("Rules", url="http://www.secrethitler.com/assets/Secret_Hitler_Rules.pdf")]]
    rulesMarkup = InlineKeyboardMarkup(btn)
    bot.send_message(cid, "Read the official Secret Hitler rules:", reply_markup=rulesMarkup)


# pings the bot
def command_ping(bot, update):
    cid = update.message.chat_id
    bot.send_message(cid, 'pong - v0.4')


def command_stats(bot, update):
    cid = update.message.chat_id
    with open(STATS, 'r') as f:
        stats = json.load(f)
    stattext = ("+++ Statistics +++\n"
                f"Liberal Wins (policies): {stats.get('libwin_policies')}\n"
                f"Liberal Wins (killed Hitler): {stats.get('libwin_kill')}\n"
                f"Fascist Wins (policies): {stats.get('fascwin_policies')}\n"
                f"Fascist Wins (Hitler chancellor): {stats.get('fascwin_hitler')}\n"
                f"Games cancelled: {stats.get('cancelled')}\n\n"
                f"Total amount of groups: {len(stats.get('groups'))}\n"
                f"Games running right now: {len(GamesController.games)}")
    bot.send_message(cid, stattext)


# help page
def command_help(bot, update):
    cid = update.message.chat_id
    help_text = "The following commands are available:\n"
    for i in commands:
        help_text += i + "\n"
    bot.send_message(cid, help_text)


def command_newgame(bot, update):
    cid = update.message.chat_id
    session = GamesController.games.get(cid, None)
    groupType = update.message.chat.type
    if groupType not in ['group', 'supergroup']:
        bot.send_message(cid, "You have to add me to a group first and type /newgame there!")
    elif session:
        bot.send_message(cid, "There is currently a game running. If you want to end it please type /cancelgame!")
    else:
        GamesController.games[cid] = MainController.GameSession(cid, update.message.from_user.id)
        with open(STATS, 'r') as f:
            stats = json.load(f)
        if cid not in stats.get("groups"):
            stats.get("groups").append(cid)
            with open(STATS, 'w') as f:
                json.dump(stats, f)
        bot.send_message(cid, "New game created! Each player has to /join the game.\n"
                              "The initiator of this game (or the admin) can /join too and "
                              "type /startgame when everyone has joined the game!")


def command_join(bot, update):
    groupName = update.message.chat.title
    cid = update.message.chat_id
    groupType = update.message.chat.type
    session = GamesController.games.get(cid, None)
    fname = update.message.from_user.first_name

    if groupType not in ['group', 'supergroup']:
        bot.send_message(cid, "You have to add me to a group first and type /newgame there!")
    elif not session:
        bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    elif session.started:
        bot.send_message(cid, "The game has started. Please wait for the next game!")
    elif update.message.from_user.id in session.playerlist:
        bot.send_message(session.cid, f"You already joined the game, {fname}!")
    elif len(session.playerlist) >= 10:
        bot.send_message(session.cid, "You have reached the maximum amount of players. "
                                      "Please start the game with /startgame!")
    else:
        uid = update.message.from_user.id
        player = Player(fname, uid)
        try:
            bot.send_message(uid, f"You joined a game in {groupName}. "
                                  f"I will soon tell you your secret role.")
            session.add_player(uid, player)
        except Exception:
            bot.send_message(session.cid,
                             f"{fname}, I can't send you a private message. "
                             f"Please go to @thesecrethitlerbot and click \"Start\".\n"
                             f"You then need to send /join again.")
        else:
            log.info(f"{fname} ({uid}) joined a game in {session.cid}")
            if len(session.playerlist) > 4:
                bot.send_message(session.cid,
                    f"{fname} has joined the game. Type /startgame if this was the last "
                    f"player and you want to start with {len(session.playerlist)} players!")
            elif len(session.playerlist) == 1:
                bot.send_message(session.cid,
                    f"{fname} has joined the game. There is currently "
                    f"{len(session.playerlist)} player in the game and you need 5-10 players.")
            else:
                bot.send_message(session.cid,
                    f"{fname} has joined the game. There are currently "
                    f"{len(session.playerlist)} players in the game and you need 5-10 players.")


def command_startgame(bot, update):
    log.info('command_startgame called')
    cid = update.message.chat_id
    session = GamesController.games.get(cid, None)
    if not session:
        bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    elif session.started:
        bot.send_message(cid, "The game is already running!")
    elif update.message.from_user.id != session.initiator and \
            bot.getChatMember(cid, update.message.from_user.id).status not in ("administrator", "creator"):
        bot.send_message(session.cid, "Only the initiator of the game or a group admin "
                                      "can start the game with /startgame")
    elif len(session.playerlist) < 5:
        bot.send_message(session.cid, "There are not enough players (min. 5, max. 10). "
                                      "Join the game with /join")
    else:
        # Create engine from lobby players, assign roles, set up board
        session.start()
        MainController.inform_players(bot, session)
        MainController.inform_fascists(bot, session)
        bot.send_message(session.cid, session.engine.board.print_board())
        MainController.present_action(bot, session)


def command_cancelgame(bot, update):
    log.info('command_cancelgame called')
    cid = update.message.chat_id
    if cid in GamesController.games.keys():
        session = GamesController.games[cid]
        status = bot.getChatMember(cid, update.message.from_user.id).status
        if update.message.from_user.id == session.initiator or \
                status in ("administrator", "creator"):
            MainController.end_game(bot, session, cancelled=True)
        else:
            bot.send_message(cid, "Only the initiator of the game or a group admin "
                                  "can cancel the game with /cancelgame")
    else:
        bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")


def command_votes(bot, update):
    try:
        cid = update.message.chat_id
        if cid in GamesController.games.keys():
            session = GamesController.games[cid]
            if not session.dateinitvote:
                # If dateinitvote is null, then the voting didn't start
                bot.send_message(cid, "The voting didn't start yet.")
            else:
                start = session.dateinitvote
                stop = datetime.datetime.now()
                elapsed = stop - start
                if elapsed > datetime.timedelta(minutes=1):
                    _, ctx = session.engine.pending_action()
                    history_text = (f"Vote history for President {ctx['president'].name} "
                                    f"and Chancellor {ctx['chancellor'].name}:\n\n")
                    for player in session.player_sequence:
                        if player.uid in session.pending_votes:
                            history_text += f"{session.playerlist[player.uid].name} registered a vote.\n"
                        else:
                            history_text += f"{session.playerlist[player.uid].name} didn't register a vote.\n"
                    bot.send_message(cid, history_text)
                else:
                    bot.send_message(cid, "Five minutes must pass to see the votes")
        else:
            bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    except Exception as e:
        bot.send_message(cid, str(e))


def command_calltovote(bot, update):
    try:
        cid = update.message.chat_id
        if cid in GamesController.games.keys():
            session = GamesController.games[cid]
            if not session.dateinitvote:
                bot.send_message(cid, "The voting didn't start yet.")
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
                    bot.send_message(cid, text=history_text, parse_mode=ParseMode.MARKDOWN)
                else:
                    bot.send_message(cid, "Five minutes must pass to see call to vote")
        else:
            bot.send_message(cid, "There is no game in this chat. Create a new game with /newgame")
    except Exception as e:
        bot.send_message(cid, str(e))
