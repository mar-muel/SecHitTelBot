#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Telegram UI layer for Secret Hitler. All game logic lives in engine.py."""

import asyncio
import logging
import re
from typing import assert_never

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import stats
from boardgamebox.game import Game
from constants.cards import PLAYER_SETS
from engine import GameEngine
from game_types import Action, EndCode, ExecutivePower, Role
from narrator import GameNarrator

import datetime
from dataclasses import dataclass, field, fields


logger = logging.getLogger(__name__)


@dataclass
class Feature:
    key: str
    name: str
    description: str
    enabled: bool = False


FEATURES: list[Feature] = [
    Feature(
        key="ai_narration",
        name="AI Narration",
        description="An AI narrator adds dramatic flair to game events, "
                    "referencing the group conversation.",
    ),
    Feature(
        key="narrator_chat",
        name="Narrator Chat",
        description="Players can talk to the narrator by writing @narrator "
                    "in the group chat.",
    ),
]


@dataclass
class GameConfig:
    features: dict[str, Feature] = field(default_factory=lambda: {
        f.key: Feature(key=f.key, name=f.name, description=f.description)
        for f in FEATURES
    })

    def __getattr__(self, name: str) -> bool:
        if name in self.__dict__.get("features", {}):
            return self.features[name].enabled
        raise AttributeError(name)

    def toggle(self, key: str):
        self.features[key].enabled = not self.features[key].enabled

games: dict[int, GameSession] = {}


class GameSession:
    """Wraps a lobby Game (pre-start) and a GameEngine (running) with Telegram state."""

    def __init__(self, cid, initiator):
        self.cid = cid
        self.initiator = initiator
        self.lobby = Game(cid, initiator)
        self.engine: GameEngine | None = None
        self.pending_votes: dict[int, bool] = {}
        self.dateinitvote: datetime.datetime | None = None
        self.config = GameConfig()
        self.narrator: GameNarrator = GameNarrator()

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


async def maybe_narrate(bot, session: GameSession, event: str, narr_ctx: dict):
    """If AI narration is enabled, send a narrated follow-up message."""
    if not session.config.ai_narration:
        return
    narrated = await session.narrator.narrate(event, narr_ctx)
    if narrated:
        await bot.send_message(session.cid, f"📖 {narrated}")


async def handle_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search(r"(-[0-9]*)_config_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    action = regex.group(2)
    try:
        session = games[cid]
        if action in session.config.features:
            session.config.toggle(action)
            await callback.edit_message_text(
                text=_config_text(session),
                reply_markup=_config_markup(session),
            )
        elif action == "done":
            await callback.edit_message_text(_config_summary(session))
    except Exception as e:
        logger.error(f"handle_config error: {e}")


def _config_text(session: GameSession) -> str:
    lines = ["Game configuration:\n"]
    for f in session.config.features.values():
        status = "ON" if f.enabled else "OFF"
        lines.append(f"{f.name} [{status}]")
        lines.append(f"  {f.description}\n")
    lines.append("Toggle settings, then press Done.")
    return "\n".join(lines)


def _config_markup(session: GameSession) -> InlineKeyboardMarkup:
    strcid = str(session.cid)
    btns = []
    for f in session.config.features.values():
        status = "ON" if f.enabled else "OFF"
        btns.append([InlineKeyboardButton(f"{f.name}: {status}", callback_data=f"{strcid}_config_{f.key}")])
    btns.append([InlineKeyboardButton("Done", callback_data=f"{strcid}_config_done")])
    return InlineKeyboardMarkup(btns)


def _config_summary(session: GameSession) -> str:
    lines = ["Game configuration:"]
    for f in session.config.features.values():
        status = "ON" if f.enabled else "OFF"
        lines.append(f"  {f.name}: {status}")
    lines.append("\nPlayers can now /join!")
    return "\n".join(lines)


async def record_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Record group chat messages for AI narration context. Respond if @narrator is mentioned."""
    if update.message is None or update.message.text is None:
        return
    cid = update.message.chat_id
    session = games.get(cid)
    if not session or not (session.config.ai_narration or session.config.narrator_chat):
        return
    name = update.message.from_user.first_name if update.message.from_user else "Unknown"
    text = update.message.text
    session.narrator.record_message(name, text)
    if session.config.narrator_chat and "@narrator" in text.lower():
        response = await session.narrator.respond(name, text)
        if response:
            await context.bot.send_message(cid, f"📖 {response}")


async def present_action(bot, session: GameSession):
    """Map the engine's current pending action to Telegram inline keyboards."""
    assert session.engine is not None
    if session.engine.game_over:
        await end_game(bot, session)
        return

    action, ctx = session.engine.pending_action()  # type: ignore[misc]
    strcid = str(session.cid)

    match action:
        case Action.NOMINATE_CHANCELLOR:
            president = ctx["president"]
            await bot.send_message(session.cid,
                f"The next presidential candidate is {president.name}.\n"
                f"{president.name}, please nominate a Chancellor in our private chat!")
            btns = []
            for p in ctx["eligible"]:
                btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_chan_{p.uid}")])
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid, session.engine.board.print_board())
            await bot.send_message(president.uid, 'Please nominate your chancellor!', reply_markup=markup)

        case Action.VOTE:
            session.pending_votes = {}
            session.dateinitvote = datetime.datetime.now()
            pres = ctx["president"]
            chan = ctx["chancellor"]
            btns = [[InlineKeyboardButton("Ja", callback_data=f"{strcid}_Ja"),
                     InlineKeyboardButton("Nein", callback_data=f"{strcid}_Nein")]]
            markup = InlineKeyboardMarkup(btns)
            for p in ctx["voters"]:
                if p is not pres:
                    await bot.send_message(p.uid, session.engine.board.print_board())
                await bot.send_message(p.uid,
                    f"Do you want to elect President {pres.name} and Chancellor {chan.name}?",
                    reply_markup=markup)

        case Action.PRESIDENT_DISCARD:
            president = ctx["president"]
            btns = []
            for policy in ctx["policies"]:
                btns.append([InlineKeyboardButton(policy, callback_data=f"{strcid}_{policy}")])
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid,
                "You drew the following 3 policies. Which one do you want to discard?",
                reply_markup=markup)

        case Action.CHANCELLOR_ENACT:
            chancellor = ctx["chancellor"]
            pres_name = session.engine.current_president.name
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
                await bot.send_message(session.cid,
                    f"President {pres_name} gave two policies to Chancellor {chancellor.name}.")
                msg = (f"President {pres_name} gave you the following 2 policies. "
                       f"Which one do you want to enact? You can also use your Veto power.")
            else:
                msg = (f"President {pres_name} gave you the following 2 policies. "
                       f"Which one do you want to enact?")
            await bot.send_message(chancellor.uid, msg, reply_markup=markup)

        case Action.VETO_CHOICE:
            president = ctx["president"]
            chan_name = session.engine.current_chancellor.name
            btns = [[InlineKeyboardButton("Veto! (accept suggestion)", callback_data=f"{strcid}_yesveto")],
                    [InlineKeyboardButton("No Veto! (refuse suggestion)", callback_data=f"{strcid}_noveto")]]
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid,
                f"Chancellor {chan_name} suggested a Veto to you. "
                f"Do you want to veto (discard) these cards?",
                reply_markup=markup)

        case Action.EXECUTIVE_KILL:
            president = ctx["president"]
            await bot.send_message(session.cid,
                f"Presidential Power enabled: Execution \U0001F5E1\n"
                f"President {president.name} has to kill one person. You can "
                f"discuss the decision now but the President has the final say.")
            btns = []
            for p in ctx["choices"]:
                btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_kill_{p.uid}")])
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid, session.engine.board.print_board())
            await bot.send_message(president.uid,
                'You have to kill one person. You can discuss your decision with the others. Choose wisely!',
                reply_markup=markup)

        case Action.EXECUTIVE_INSPECT:
            president = ctx["president"]
            await bot.send_message(session.cid,
                f"Presidential Power enabled: Investigate Loyalty \U0001F50E\n"
                f"President {president.name} may see the party membership of one "
                f"player. The President may share (or lie about!) the results of "
                f"their investigation at their discretion.")
            btns = []
            for p in ctx["choices"]:
                btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_insp_{p.uid}")])
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid, session.engine.board.print_board())
            await bot.send_message(president.uid,
                'You may see the party membership of one player. Which do you want to know? Choose wisely!',
                reply_markup=markup)

        case Action.EXECUTIVE_SPECIAL_ELECTION:
            president = ctx["president"]
            await bot.send_message(session.cid,
                f"Presidential Power enabled: Call Special Election \U0001F454\n"
                f"President {president.name} gets to choose the next presidential "
                f"candidate. Afterwards the order resumes back to normal.")
            btns = []
            for p in ctx["choices"]:
                btns.append([InlineKeyboardButton(p.name, callback_data=f"{strcid}_choo_{p.uid}")])
            markup = InlineKeyboardMarkup(btns)
            await bot.send_message(president.uid, session.engine.board.print_board())
            await bot.send_message(president.uid,
                'You get to choose the next presidential candidate. '
                'Afterwards the order resumes back to normal. Choose wisely!',
                reply_markup=markup)

        case _ as unreachable:
            assert_never(unreachable)


##
# Callback handlers
##

async def nominate_chosen_chancellor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_chan_([0-9]*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    chosen_uid = int(regex.group(2))
    try:
        session = games[cid]
        assert session.engine is not None
        chosen = session.engine.players[chosen_uid]
        assert session.engine.state.nominated_president is not None
        pres_name = session.engine.state.nominated_president.name
        await callback.edit_message_text(f"You nominated {chosen.name} as Chancellor!")
        await context.bot.send_message(session.cid,
            f"President {pres_name} nominated {chosen.name} as Chancellor. Please vote now!")
        session.engine.step(chosen)
        await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"nominate_chosen_chancellor error: {e}")


async def handle_voting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = games[cid]
        assert session.engine is not None
        uid = callback.from_user.id
        _, ctx = session.engine.pending_action()  # type: ignore[misc]
        pres_name = ctx["president"].name
        chan_name = ctx["chancellor"].name

        await callback.edit_message_text(
            f"Thank you for your vote: {answer} to President {pres_name} and Chancellor {chan_name}")

        if uid not in session.pending_votes:
            session.pending_votes[uid] = (answer == "Ja")

        if len(session.pending_votes) == len(session.engine.alive_players):
            await finish_voting(context.bot, session)
    except Exception as e:
        logger.error(f"handle_voting error: {e}")


async def finish_voting(bot, session: GameSession):
    """Called when all votes are collected."""
    assert session.engine is not None
    votes = session.pending_votes
    session.dateinitvote = None

    voting_text = ""
    for p in session.engine.alive_players:
        answer = "Ja" if votes[p.uid] else "Nein"
        voting_text += f"{p.name} voted {answer}!\n"

    ja_count = sum(1 for v in votes.values() if v)
    passed = ja_count > len(session.engine.alive_players) / 2

    assert session.engine.state.nominated_president is not None
    assert session.engine.state.nominated_chancellor is not None
    pres_name = session.engine.state.nominated_president.name
    chan_name = session.engine.state.nominated_chancellor.name
    failed_before = session.engine.state.failed_votes
    lib_before = session.engine.state.liberal_track
    fasc_before = session.engine.state.fascist_track

    if passed:
        voting_text += f"Hail President {pres_name}! Hail Chancellor {chan_name}!"
    else:
        voting_text += "The people didn't like the two candidates!"
    await bot.send_message(session.cid, voting_text)
    await maybe_narrate(bot, session, "vote_passed" if passed else "vote_failed", {
        "president": pres_name, "chancellor": chan_name,
        "failed_votes": failed_before + (0 if passed else 1),
    })

    session.engine.step(votes)
    session.pending_votes = {}

    # Anarchy messaging must come before game_over check, because anarchy
    # can enact the winning policy and end the game in the same step.
    if not passed and failed_before == 2:
        anarchy_policy = ("liberal" if session.engine.state.liberal_track > lib_before else "fascist")
        await bot.send_message(session.cid, "ANARCHY!!")
        if session.engine.state.liberal_track > lib_before:
            await bot.send_message(session.cid, "The topmost policy was enacted: liberal")
        elif session.engine.state.fascist_track > fasc_before:
            await bot.send_message(session.cid, "The topmost policy was enacted: fascist")
        await maybe_narrate(bot, session, "anarchy", {"policy": anarchy_policy})

    if session.engine.game_over:
        await end_game(bot, session)
        return

    if not passed:
        await bot.send_message(session.cid, session.engine.board.print_board())

    await asyncio.sleep(3)
    await present_action(bot, session)


async def choose_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = games[cid]
        assert session.engine is not None
        uid = callback.from_user.id
        action, ctx = session.engine.pending_action()  # type: ignore[misc]

        if action == Action.PRESIDENT_DISCARD:
            await callback.edit_message_text(f"The policy {answer} will be discarded!")
            session.engine.step(answer)
            await present_action(context.bot, session)

        elif action == Action.CHANCELLOR_ENACT:
            if answer == "veto":
                pres_name = session.engine.current_president.name
                chan_name = session.engine.current_chancellor.name
                await callback.edit_message_text(
                    f"You suggested a Veto to President {pres_name}")
                await context.bot.send_message(session.cid,
                    f"Chancellor {chan_name} suggested a Veto to President {pres_name}.")
                session.engine.step("veto")
                await present_action(context.bot, session)
            else:
                pres_name = session.engine.current_president.name
                chan_name = session.engine.current_chancellor.name
                pres_uid = session.engine.current_president.uid
                fasc_before = session.engine.state.fascist_track

                await callback.edit_message_text(f"The policy {answer} will be enacted!")
                session.engine.step(answer)

                await context.bot.send_message(session.cid,
                    f"President {pres_name} and Chancellor {chan_name} enacted a {answer} policy!")
                await maybe_narrate(context.bot, session, "policy_enacted", {
                    "president": pres_name, "chancellor": chan_name, "policy": answer,
                    "liberal_track": session.engine.state.liberal_track,
                    "fascist_track": session.engine.state.fascist_track,
                })
                await asyncio.sleep(3)
                await context.bot.send_message(session.cid, session.engine.board.print_board())

                if session.engine.game_over:
                    await end_game(context.bot, session)
                    return

                fasc_after = session.engine.state.fascist_track
                if fasc_after > fasc_before:
                    track_action = session.engine.board.fascist_track_actions[fasc_after - 1]
                    if track_action == ExecutivePower.POLICY:
                        top3 = session.engine.board.policies[:3]
                        await context.bot.send_message(session.cid,
                            f"Presidential Power enabled: Policy Peek \U0001F52E\n"
                            f"President {pres_name} now knows the next three policies on "
                            f"the pile. The President may share (or lie about!) the results "
                            f"of their investigation at their discretion.")
                        top_text = "\n".join(top3)
                        await context.bot.send_message(pres_uid,
                            f"The top three policies are (top most first):\n{top_text}\n"
                            f"You may lie about this.")

                await asyncio.sleep(3)
                await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"choose_policy error: {e}")


async def choose_veto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    answer = regex.group(2)
    try:
        session = games[cid]
        assert session.engine is not None
        uid = callback.from_user.id
        pres_name = session.engine.current_president.name
        chan_name = session.engine.current_chancellor.name

        if answer == "yesveto":
            await callback.edit_message_text("You accepted the Veto!")
            failed_before = session.engine.state.failed_votes
            lib_before = session.engine.state.liberal_track
            fasc_before = session.engine.state.fascist_track

            session.engine.step(True)

            await context.bot.send_message(session.cid,
                f"President {pres_name} accepted Chancellor {chan_name}'s Veto. "
                f"No policy was enacted but this counts as a failed election.")
            await maybe_narrate(context.bot, session, "veto_accepted", {
                "president": pres_name, "chancellor": chan_name,
            })

            if failed_before == 2:
                await context.bot.send_message(session.cid, "ANARCHY!!")
                if session.engine.state.liberal_track > lib_before:
                    await context.bot.send_message(session.cid, "The topmost policy was enacted: liberal")
                elif session.engine.state.fascist_track > fasc_before:
                    await context.bot.send_message(session.cid, "The topmost policy was enacted: fascist")

            if session.engine.game_over:
                await end_game(context.bot, session)
                return

            await context.bot.send_message(session.cid, session.engine.board.print_board())
            await present_action(context.bot, session)

        elif answer == "noveto":
            await callback.edit_message_text("You refused the Veto!")
            session.engine.step(False)
            await context.bot.send_message(session.cid,
                f"President {pres_name} refused Chancellor {chan_name}'s Veto. "
                f"The Chancellor now has to choose a policy!")
            await maybe_narrate(context.bot, session, "veto_refused", {
                "president": pres_name, "chancellor": chan_name,
            })
            await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"choose_veto error: {e}")


async def choose_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_kill_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = games[cid]
        assert session.engine is not None
        target = session.engine.players[target_uid]
        pres_name = session.engine.current_president.name

        await callback.edit_message_text(f"You killed {target.name}!")
        session.engine.step(target)

        if session.engine.game_over:
            await context.bot.send_message(session.cid,
                f"President {pres_name} killed {target.name}.")
            await maybe_narrate(context.bot, session, "execution", {
                "president": pres_name, "target": target.name, "was_hitler": True,
            })
            await end_game(context.bot, session)
        else:
            await context.bot.send_message(session.cid,
                f"President {pres_name} killed {target.name} who was not Hitler. "
                f"{target.name}, you are dead now and are not allowed to talk anymore!")
            await maybe_narrate(context.bot, session, "execution", {
                "president": pres_name, "target": target.name, "was_hitler": False,
            })
            await context.bot.send_message(session.cid, session.engine.board.print_board())
            await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"choose_kill error: {e}")


async def choose_inspect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_insp_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = games[cid]
        assert session.engine is not None
        target = session.engine.players[target_uid]
        pres_name = session.engine.current_president.name

        await callback.edit_message_text(
            f"The party membership of {target.name} is {target.party}")
        await context.bot.send_message(session.cid,
            f"President {pres_name} inspected {target.name}.")
        session.engine.step(target)
        await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"choose_inspect error: {e}")


async def choose_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback = update.callback_query
    assert callback is not None
    assert callback.data is not None
    regex = re.search("(-[0-9]*)_choo_(.*)", callback.data)
    assert regex is not None
    cid = int(regex.group(1))
    target_uid = int(regex.group(2))
    try:
        session = games[cid]
        assert session.engine is not None
        target = session.engine.players[target_uid]
        pres_name = session.engine.current_president.name

        await callback.edit_message_text(f"You chose {target.name} as the next president!")
        await context.bot.send_message(session.cid,
            f"President {pres_name} chose {target.name} as the next president.")
        session.engine.step(target)
        await present_action(context.bot, session)
    except Exception as e:
        logger.error(f"choose_choose error: {e}")


##
# Game lifecycle
##

async def inform_players(bot, session):
    n = len(session.engine.players)
    await bot.send_message(session.cid,
        f"Let's start the game with {n} players!\n{print_player_info(n)}\n"
        f"Go to your private chat and look at your secret role!")
    names = [p.name for p in session.engine.players.values()]
    await maybe_narrate(bot, session, "game_start", {
        "num_players": n, "players": ", ".join(names),
    })
    for uid, p in session.engine.players.items():
        await bot.send_message(uid, f"Your secret role is: {p.role}\nYour party membership is: {p.party}")


async def inform_fascists(bot, session):
    n = len(session.engine.players)
    for uid, p in session.engine.players.items():
        if p.role == Role.FASCIST:
            fascists = session.engine.game.get_fascists()
            if n > 6:
                others = [f.name for f in fascists if f.uid != uid]
                await bot.send_message(uid, f"Your fellow fascists are: {', '.join(others)}")
            hitler = session.engine.game.get_hitler()
            await bot.send_message(uid, f"Hitler is: {hitler.name}")
        elif p.role == Role.HITLER:
            if n <= 6:
                fascists = session.engine.game.get_fascists()
                if fascists:
                    await bot.send_message(uid, f"Your fellow fascist is: {fascists[0].name}")


def print_player_info(player_number):
    roles = PLAYER_SETS[player_number].roles
    libs = roles.count(Role.LIBERAL)
    fascs = roles.count(Role.FASCIST)
    fasc_word = "Fascist" if fascs == 1 else "Fascists"
    hitler_info = ("Hitler knows who the Fascist is."
                   if player_number <= 6
                   else "Hitler doesn't know who the Fascists are.")
    return f"There are {libs} Liberals, {fascs} {fasc_word} and Hitler. {hitler_info}"


async def end_game(bot, session, cancelled=False):
    s = stats.get()

    if cancelled:
        if session.started:
            await bot.send_message(session.cid, f"Game cancelled!\n\n{session.print_roles()}")
            s['cancelled'] += 1
        else:
            await bot.send_message(session.cid, "Game cancelled!")
    else:
        code = session.engine.end_code
        roles_text = session.print_roles()
        results = {
            EndCode.FASCIST_HITLER_CHANCELLOR: ("The fascists win by electing Hitler as Chancellor!", 'fascwin_hitler'),
            EndCode.FASCIST_POLICIES: ("The fascists win by enacting 6 fascist policies!", 'fascwin_policies'),
            EndCode.LIBERAL_POLICIES: ("The liberals win by enacting 5 liberal policies!", 'libwin_policies'),
            EndCode.LIBERAL_KILLED_HITLER: ("The liberals win by killing Hitler!", 'libwin_kill'),
        }
        result_text, stat_key = results[code]
        await bot.send_message(session.cid, f"Game over! {result_text}\n\n{roles_text}")
        s[stat_key] += 1
        await maybe_narrate(bot, session, "game_over", {
            "result": result_text,
            "liberal_track": session.engine.state.liberal_track,
            "fascist_track": session.engine.state.fascist_track,
        })

    stats.save()

    if session.cid in games:
        del games[session.cid]


async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f'Update caused error "{context.error}"', exc_info=context.error)


