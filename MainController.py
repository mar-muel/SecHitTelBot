#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Telegram UI layer for Secret Hitler. All game logic lives in engine.py."""

import json
import logging as log
import re
from time import sleep

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Updater, CommandHandler, CallbackQueryHandler)

import Commands
from Constants.Config import TOKEN, STATS
from Boardgamebox.Game import Game
from Boardgamebox.Player import Player
from engine import GameEngine, Action, EndCode
import GamesController

import datetime

log.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                level=log.INFO,
                filename='logs/logging.log')

logger = log.getLogger(__name__)


class GameSession:
    """Wraps a lobby Game (pre-start) and a GameEngine (running) with Telegram state."""

    def __init__(self, cid, initiator):
        self.cid = cid
        self.initiator = initiator
        self.lobby = Game(cid, initiator)
        self.engine = None
        self.pending_votes = {}
        self.dateinitvote = None

    @property
    def started(self):
        return self.engine is not None

    @property
    def board(self):
        return self.engine.board if self.engine else None

    @property
    def playerlist(self):
        if self.engine:
            return self.engine.players
        return self.lobby.playerlist

    @property
    def player_sequence(self):
        if self.engine:
            return self.engine.alive_players
        return self.lobby.player_sequence

    def add_player(self, uid, player):
        self.lobby.add_player(uid, player)

    def start(self):
        players = {uid: p.name for uid, p in self.lobby.playerlist.items()}
        self.engine = GameEngine(players=players)

    def print_roles(self):
        if not self.engine:
            return ""
        rtext = ""
        for uid in self.engine.players:
            p = self.engine.players[uid]
            rtext += f"{p.name}'s "
            if p.is_dead:
                rtext += "(dead) "
            rtext += f"secret role was {p.role}\n"
        return rtext


def present_action(bot, session):
    """Map the engine's current pending action to Telegram inline keyboards."""
    if session.engine.game_over:
        end_game(bot, session)
        return

    action, ctx = session.engine.pending_action()
    strcid = str(session.cid)

    if action == Action.NOMINATE_CHANCELLOR:
        president = ctx["president"]
        bot.send_message(session.cid,
            f"The next presidential candidate is {president.name}.\n"
            f"{president.name}, please nominate a Chancellor in our private chat!")
        btns = []
        for p in ctx["eligible"]:
            btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_chan_{p.uid}")])
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid, session.engine.board.print_board())
        bot.send_message(president.uid, 'Please nominate your chancellor!', reply_markup=markup)

    elif action == Action.VOTE:
        session.pending_votes = {}
        session.dateinitvote = datetime.datetime.now()
        pres = ctx["president"]
        chan = ctx["chancellor"]
        btns = [[InlineKeyboardButton("Ja", callback_data=f"{strcid}_Ja"),
                 InlineKeyboardButton("Nein", callback_data=f"{strcid}_Nein")]]
        markup = InlineKeyboardMarkup(btns)
        for p in ctx["voters"]:
            if p is not pres:
                bot.send_message(p.uid, session.engine.board.print_board())
            bot.send_message(p.uid,
                f"Do you want to elect President {pres.name} and Chancellor {chan.name}?",
                reply_markup=markup)

    elif action == Action.PRESIDENT_DISCARD:
        president = ctx["president"]
        btns = []
        for policy in ctx["policies"]:
            btns.append([InlineKeyboardButton(policy, callback_data=f"{strcid}_{policy}")])
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid,
            "You drew the following 3 policies. Which one do you want to discard?",
            reply_markup=markup)

    elif action == Action.CHANCELLOR_ENACT:
        chancellor = ctx["chancellor"]
        pres_name = session.engine.president.name
        btns = []
        for policy in ctx["policies"]:
            btns.append([InlineKeyboardButton(policy, callback_data=f"{strcid}_{policy}")])
        if ctx.get("can_veto"):
            btns.append([InlineKeyboardButton("Veto", callback_data=f"{strcid}_veto")])
        markup = InlineKeyboardMarkup(btns)
        if session.engine.state.veto_refused:
            msg = (f"President {pres_name} refused your Veto. "
                   f"Now you have to choose. Which one do you want to enact?")
        elif ctx.get("can_veto"):
            bot.send_message(session.cid,
                f"President {pres_name} gave two policies to Chancellor {chancellor.name}.")
            msg = (f"President {pres_name} gave you the following 2 policies. "
                   f"Which one do you want to enact? You can also use your Veto power.")
        else:
            msg = (f"President {pres_name} gave you the following 2 policies. "
                   f"Which one do you want to enact?")
        bot.send_message(chancellor.uid, msg, reply_markup=markup)

    elif action == Action.VETO_CHOICE:
        president = ctx["president"]
        chan_name = session.engine.chancellor.name
        btns = [[InlineKeyboardButton("Veto! (accept suggestion)", callback_data=f"{strcid}_yesveto")],
                [InlineKeyboardButton("No Veto! (refuse suggestion)", callback_data=f"{strcid}_noveto")]]
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid,
            f"Chancellor {chan_name} suggested a Veto to you. "
            f"Do you want to veto (discard) these cards?",
            reply_markup=markup)

    elif action == Action.EXECUTIVE_KILL:
        president = ctx["president"]
        bot.send_message(session.cid,
            f"Presidential Power enabled: Execution \U0001F5E1\n"
            f"President {president.name} has to kill one person. You can "
            f"discuss the decision now but the President has the final say.")
        btns = []
        for p in ctx["choices"]:
            btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_kill_{p.uid}")])
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid, session.engine.board.print_board())
        bot.send_message(president.uid,
            'You have to kill one person. You can discuss your decision with the others. Choose wisely!',
            reply_markup=markup)

    elif action == Action.EXECUTIVE_INSPECT:
        president = ctx["president"]
        bot.send_message(session.cid,
            f"Presidential Power enabled: Investigate Loyalty \U0001F50E\n"
            f"President {president.name} may see the party membership of one "
            f"player. The President may share (or lie about!) the results of "
            f"their investigation at their discretion.")
        btns = []
        for p in ctx["choices"]:
            btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_insp_{p.uid}")])
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid, session.engine.board.print_board())
        bot.send_message(president.uid,
            'You may see the party membership of one player. Which do you want to know? Choose wisely!',
            reply_markup=markup)

    elif action == Action.EXECUTIVE_SPECIAL_ELECTION:
        president = ctx["president"]
        bot.send_message(session.cid,
            f"Presidential Power enabled: Call Special Election \U0001F454\n"
            f"President {president.name} gets to choose the next presidential "
            f"candidate. Afterwards the order resumes back to normal.")
        btns = []
        for p in ctx["choices"]:
            btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_choo_{p.uid}")])
        markup = InlineKeyboardMarkup(btns)
        bot.send_message(president.uid, session.engine.board.print_board())
        bot.send_message(president.uid,
            'You get to choose the next presidential candidate. '
            'Afterwards the order resumes back to normal. Choose wisely!',
            reply_markup=markup)


##
# Callback handlers
##

def nominate_chosen_chancellor(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_chan_([0-9]*)", callback.data)
    cid = int(regex.group(1))
    chosen_uid = int(regex.group(2))
    try:
        session = GamesController.games[cid]
        chosen = session.engine.players[chosen_uid]
        pres_name = session.engine.state.nominated_president.name
        bot.edit_message_text(f"You nominated {chosen.name} as Chancellor!",
                              callback.from_user.id, callback.message.message_id)
        bot.send_message(session.cid,
            f"President {pres_name} nominated {chosen.name} as Chancellor. Please vote now!")
        session.engine.step(chosen)
        present_action(bot, session)
    except Exception as e:
        log.error(f"nominate_chosen_chancellor error: {e}")


def handle_voting(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = GamesController.games[cid]
        uid = callback.from_user.id
        _, ctx = session.engine.pending_action()
        pres_name = ctx["president"].name
        chan_name = ctx["chancellor"].name

        bot.edit_message_text(
            f"Thank you for your vote: {answer} to a President {pres_name} and a Chancellor {chan_name}",
            uid, callback.message.message_id)

        if uid not in session.pending_votes:
            session.pending_votes[uid] = (answer == "Ja")

        if len(session.pending_votes) == len(session.engine.alive_players):
            finish_voting(bot, session)
    except Exception as e:
        log.error(f"handle_voting error: {e}")


def finish_voting(bot, session):
    """Called when all votes are collected."""
    votes = session.pending_votes
    session.dateinitvote = None

    voting_text = ""
    for p in session.engine.alive_players:
        answer = "Ja" if votes[p.uid] else "Nein"
        voting_text += f"{p.name} voted {answer}!\n"

    ja_count = sum(1 for v in votes.values() if v)
    passed = ja_count > len(session.engine.alive_players) / 2

    pres_name = session.engine.state.nominated_president.name
    chan_name = session.engine.state.nominated_chancellor.name
    failed_before = session.engine.state.failed_votes
    lib_before = session.engine.state.liberal_track
    fasc_before = session.engine.state.fascist_track

    if passed:
        voting_text += f"Hail President {pres_name}! Hail Chancellor {chan_name}!"
    else:
        voting_text += "The people didn't like the two candidates!"
    bot.send_message(session.cid, voting_text)

    session.engine.step(votes)
    session.pending_votes = {}

    # Anarchy messaging must come before game_over check, because anarchy
    # can enact the winning policy and end the game in the same step.
    if not passed and failed_before == 2:
        bot.send_message(session.cid, "ANARCHY!!")
        if session.engine.state.liberal_track > lib_before:
            bot.send_message(session.cid, "The top most policy was enacted: liberal")
        elif session.engine.state.fascist_track > fasc_before:
            bot.send_message(session.cid, "The top most policy was enacted: fascist")

    if session.engine.game_over:
        end_game(bot, session)
        return

    if not passed:
        bot.send_message(session.cid, session.engine.board.print_board())

    sleep(3)
    present_action(bot, session)


def choose_policy(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = GamesController.games[cid]
        uid = callback.from_user.id
        action, ctx = session.engine.pending_action()

        if action == Action.PRESIDENT_DISCARD:
            bot.edit_message_text(f"The policy {answer} will be discarded!",
                                  uid, callback.message.message_id)
            session.engine.step(answer)
            present_action(bot, session)

        elif action == Action.CHANCELLOR_ENACT:
            if answer == "veto":
                pres_name = session.engine.president.name
                chan_name = session.engine.chancellor.name
                bot.edit_message_text(
                    f"You suggested a Veto to President {pres_name}",
                    uid, callback.message.message_id)
                bot.send_message(session.cid,
                    f"Chancellor {chan_name} suggested a Veto to President {pres_name}.")
                session.engine.step("veto")
                present_action(bot, session)
            else:
                pres_name = session.engine.president.name
                chan_name = session.engine.chancellor.name
                pres_uid = session.engine.president.uid
                fasc_before = session.engine.state.fascist_track

                bot.edit_message_text(f"The policy {answer} will be enacted!",
                                      uid, callback.message.message_id)
                session.engine.step(answer)

                bot.send_message(session.cid,
                    f"President {pres_name} and Chancellor {chan_name} enacted a {answer} policy!")
                sleep(3)
                bot.send_message(session.cid, session.engine.board.print_board())

                if session.engine.game_over:
                    end_game(bot, session)
                    return

                fasc_after = session.engine.state.fascist_track
                if fasc_after > fasc_before:
                    track_action = session.engine.board.fascist_track_actions[fasc_after - 1]
                    if track_action == "policy":
                        top3 = session.engine.board.policies[:3]
                        bot.send_message(session.cid,
                            f"Presidential Power enabled: Policy Peek \U0001F52E\n"
                            f"President {pres_name} now knows the next three policies on "
                            f"the pile. The President may share (or lie about!) the results "
                            f"of their investigation at their discretion.")
                        top_text = "\n".join(top3)
                        bot.send_message(pres_uid,
                            f"The top three policies are (top most first):\n{top_text}\n"
                            f"You may lie about this.")

                sleep(3)
                present_action(bot, session)
    except Exception as e:
        log.error(f"choose_policy error: {e}")


def choose_veto(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = GamesController.games[cid]
        uid = callback.from_user.id
        pres_name = session.engine.president.name
        chan_name = session.engine.chancellor.name

        if answer == "yesveto":
            bot.edit_message_text("You accepted the Veto!", uid, callback.message.message_id)
            failed_before = session.engine.state.failed_votes
            lib_before = session.engine.state.liberal_track
            fasc_before = session.engine.state.fascist_track

            session.engine.step(True)

            bot.send_message(session.cid,
                f"President {pres_name} accepted Chancellor {chan_name}'s Veto. "
                f"No policy was enacted but this counts as a failed election.")

            if failed_before == 2:
                bot.send_message(session.cid, "ANARCHY!!")
                if session.engine.state.liberal_track > lib_before:
                    bot.send_message(session.cid, "The top most policy was enacted: liberal")
                elif session.engine.state.fascist_track > fasc_before:
                    bot.send_message(session.cid, "The top most policy was enacted: fascist")

            if session.engine.game_over:
                end_game(bot, session)
                return

            bot.send_message(session.cid, session.engine.board.print_board())
            present_action(bot, session)

        elif answer == "noveto":
            bot.edit_message_text("You refused the Veto!", uid, callback.message.message_id)
            session.engine.step(False)
            bot.send_message(session.cid,
                f"President {pres_name} refused Chancellor {chan_name}'s Veto. "
                f"The Chancellor now has to choose a policy!")
            present_action(bot, session)
    except Exception as e:
        log.error(f"choose_veto error: {e}")


def choose_kill(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_kill_(.*)", callback.data)
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = GamesController.games[cid]
        target = session.engine.players[target_uid]
        pres_name = session.engine.president.name

        bot.edit_message_text(f"You killed {target.name}!",
                              callback.from_user.id, callback.message.message_id)
        session.engine.step(target)

        if session.engine.game_over:
            bot.send_message(session.cid,
                f"President {pres_name} killed {target.name}.")
            end_game(bot, session)
        else:
            bot.send_message(session.cid,
                f"President {pres_name} killed {target.name} who was not Hitler. "
                f"{target.name}, you are dead now and are not allowed to talk anymore!")
            bot.send_message(session.cid, session.engine.board.print_board())
            present_action(bot, session)
    except Exception as e:
        log.error(f"choose_kill error: {e}")


def choose_inspect(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_insp_(.*)", callback.data)
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = GamesController.games[cid]
        target = session.engine.players[target_uid]
        pres_name = session.engine.president.name

        bot.edit_message_text(
            f"The party membership of {target.name} is {target.party}",
            callback.from_user.id, callback.message.message_id)
        bot.send_message(session.cid,
            f"President {pres_name} inspected {target.name}.")
        session.engine.step(target)
        present_action(bot, session)
    except Exception as e:
        log.error(f"choose_inspect error: {e}")


def choose_choose(bot, update):
    callback = update.callback_query
    regex = re.search("(-[0-9]*)_choo_(.*)", callback.data)
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = GamesController.games[cid]
        target = session.engine.players[target_uid]
        pres_name = session.engine.president.name

        bot.edit_message_text(f"You chose {target.name} as the next president!",
                              callback.from_user.id, callback.message.message_id)
        bot.send_message(session.cid,
            f"President {pres_name} chose {target.name} as the next president.")
        session.engine.step(target)
        present_action(bot, session)
    except Exception as e:
        log.error(f"choose_choose error: {e}")


##
# Game lifecycle
##

def inform_players(bot, session):
    n = len(session.engine.players)
    bot.send_message(session.cid,
        f"Let's start the game with {n} players!\n{print_player_info(n)}\n"
        f"Go to your private chat and look at your secret role!")
    for uid, p in session.engine.players.items():
        bot.send_message(uid, f"Your secret role is: {p.role}\nYour party membership is: {p.party}")


def inform_fascists(bot, session):
    n = len(session.engine.players)
    for uid, p in session.engine.players.items():
        if p.role == "Fascist":
            fascists = session.engine.game.get_fascists()
            if n > 6:
                others = [f.name for f in fascists if f.uid != uid]
                bot.send_message(uid, f"Your fellow fascists are: {', '.join(others)}")
            hitler = session.engine.game.get_hitler()
            bot.send_message(uid, f"Hitler is: {hitler.name}")
        elif p.role == "Hitler":
            if n <= 6:
                fascists = session.engine.game.get_fascists()
                bot.send_message(uid, f"Your fellow fascist is: {fascists[0].name}")


def print_player_info(player_number):
    if player_number == 5:
        return "There are 3 Liberals, 1 Fascist and Hitler. Hitler knows who the Fascist is."
    elif player_number == 6:
        return "There are 4 Liberals, 1 Fascist and Hitler. Hitler knows who the Fascist is."
    elif player_number == 7:
        return "There are 4 Liberals, 2 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 8:
        return "There are 5 Liberals, 2 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 9:
        return "There are 5 Liberals, 3 Fascist and Hitler. Hitler doesn't know who the Fascists are."
    elif player_number == 10:
        return "There are 6 Liberals, 3 Fascist and Hitler. Hitler doesn't know who the Fascists are."


def end_game(bot, session, cancelled=False):
    with open(STATS, 'r') as f:
        stats = json.load(f)

    if cancelled:
        if session.started:
            bot.send_message(session.cid, f"Game cancelled!\n\n{session.print_roles()}")
            stats['cancelled'] = stats['cancelled'] + 1
        else:
            bot.send_message(session.cid, "Game cancelled!")
    else:
        code = session.engine.end_code
        roles_text = session.print_roles()
        if code == EndCode.FASCIST_HITLER_CHANCELLOR:
            bot.send_message(session.cid,
                f"Game over! The fascists win by electing Hitler as Chancellor!\n\n{roles_text}")
            stats['fascwin_hitler'] += 1
        elif code == EndCode.FASCIST_POLICIES:
            bot.send_message(session.cid,
                f"Game over! The fascists win by enacting 6 fascist policies!\n\n{roles_text}")
            stats['fascwin_policies'] += 1
        elif code == EndCode.LIBERAL_POLICIES:
            bot.send_message(session.cid,
                f"Game over! The liberals win by enacting 5 liberal policies!\n\n{roles_text}")
            stats['libwin_policies'] += 1
        elif code == EndCode.LIBERAL_KILLED_HITLER:
            bot.send_message(session.cid,
                f"Game over! The liberals win by killing Hitler!\n\n{roles_text}")
            stats['libwin_kill'] += 1

    with open(STATS, 'w') as f:
        json.dump(stats, f)

    if session.cid in GamesController.games:
        del GamesController.games[session.cid]


def error(bot, update, error):
    logger.warning(f'Update "{update}" caused error "{error}"')


def main():
    GamesController.init()

    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", Commands.command_start))
    dp.add_handler(CommandHandler("help", Commands.command_help))
    dp.add_handler(CommandHandler("board", Commands.command_board))
    dp.add_handler(CommandHandler("rules", Commands.command_rules))
    dp.add_handler(CommandHandler("ping", Commands.command_ping))
    dp.add_handler(CommandHandler("symbols", Commands.command_symbols))
    dp.add_handler(CommandHandler("stats", Commands.command_stats))
    dp.add_handler(CommandHandler("newgame", Commands.command_newgame))
    dp.add_handler(CommandHandler("startgame", Commands.command_startgame))
    dp.add_handler(CommandHandler("cancelgame", Commands.command_cancelgame))
    dp.add_handler(CommandHandler("join", Commands.command_join))
    dp.add_handler(CommandHandler("votes", Commands.command_votes))
    dp.add_handler(CommandHandler("calltovote", Commands.command_calltovote))

    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_chan_(.*)", callback=nominate_chosen_chancellor))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_insp_(.*)", callback=choose_inspect))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_choo_(.*)", callback=choose_choose))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_kill_(.*)", callback=choose_kill))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(yesveto|noveto)", callback=choose_veto))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(liberal|fascist|veto)", callback=choose_policy))
    dp.add_handler(CallbackQueryHandler(pattern="(-[0-9]*)_(Ja|Nein)", callback=handle_voting))

    dp.add_error_handler(error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
