"""Telegram-free game engine for Secret Hitler. Can be driven by any strategy."""

import random
from random import randrange
from enum import Enum, auto

from constants.cards import PLAYER_SETS
from boardgamebox.board import Board
from boardgamebox.game import Game
from boardgamebox.player import Player


class GameOver(Exception):
    pass


class EndCode(Enum):
    FASCIST_HITLER_CHANCELLOR = -2
    FASCIST_POLICIES = -1
    RUNNING = 0
    LIBERAL_POLICIES = 1
    LIBERAL_KILLED_HITLER = 2


class Action(Enum):
    NOMINATE_CHANCELLOR = auto()
    VOTE = auto()
    PRESIDENT_DISCARD = auto()
    CHANCELLOR_ENACT = auto()
    VETO_CHOICE = auto()
    EXECUTIVE_KILL = auto()
    EXECUTIVE_INSPECT = auto()
    EXECUTIVE_SPECIAL_ELECTION = auto()


class GameEngine:
    """A complete Secret Hitler game that can be stepped through programmatically.

    Usage:
        engine = GameEngine(num_players=7)
        while not engine.game_over:
            action, context = engine.pending_action()
            choice = my_strategy(action, context, engine)
            engine.step(choice)
    """

    def __init__(self, num_players: int = 5, names: list[str] | None = None,
                 players: dict[int, str] | None = None,
                 seed: int | None = None):
        if seed is not None:
            random.seed(seed)

        self.game = Game(-1, 0)
        if players is not None:
            num_players = len(players)
            for uid, name in players.items():
                self.game.add_player(uid, Player(name, uid))
        else:
            if names is None:
                default_names = ["Alice", "Bob", "Charlie", "Diana", "Eve",
                                 "Frank", "Grace", "Hank", "Ivy", "Jack"]
                names = default_names[:num_players]
            for i in range(num_players):
                self.game.add_player(i, Player(names[i], i))

        self._assign_roles(num_players)
        self._board = Board(num_players, self.game)
        self.game.board = self._board
        self.game.shuffle_player_sequence()
        self._board.state.player_counter = 0

        self.log: list[str] = []
        self.end_code: EndCode = EndCode.RUNNING
        self._pending: tuple[Action, dict] | None = None
        self._advance_to_nomination()

    @property
    def game_over(self) -> bool:
        return self.end_code != EndCode.RUNNING

    @property
    def state(self):
        return self._board.state

    @property
    def board(self) -> Board:
        return self._board

    @property
    def players(self) -> dict[int, Player]:
        return self.game.playerlist

    @property
    def alive_players(self) -> list[Player]:
        return list(self.game.player_sequence)

    @property
    def president(self) -> Player | None:
        return self.state.president

    @property
    def chancellor(self) -> Player | None:
        return self.state.chancellor

    @property
    def current_president(self) -> Player:
        assert self.state.president is not None
        return self.state.president

    @property
    def current_chancellor(self) -> Player:
        assert self.state.chancellor is not None
        return self.state.chancellor

    def pending_action(self) -> tuple[Action, dict] | None:
        """Returns (Action, context_dict) describing what decision is needed next."""
        return self._pending

    def step(self, choice) -> None:
        """Provide the decision for the current pending action."""
        if self.game_over or self._pending is None:
            raise GameOver(f"Game is already over: {self.end_code}")

        action, _ = self._pending
        handlers = {
            Action.NOMINATE_CHANCELLOR: self._do_nominate,
            Action.VOTE: self._do_vote,
            Action.PRESIDENT_DISCARD: self._do_president_discard,
            Action.CHANCELLOR_ENACT: self._do_chancellor_enact,
            Action.VETO_CHOICE: self._do_veto_choice,
            Action.EXECUTIVE_KILL: self._do_kill,
            Action.EXECUTIVE_INSPECT: self._do_inspect,
            Action.EXECUTIVE_SPECIAL_ELECTION: self._do_special_election,
        }
        handlers[action](choice)

    def eligible_chancellors(self) -> list[Player]:
        """Returns list of players eligible to be nominated as chancellor."""
        s = self.state
        assert s.nominated_president is not None
        pres_uid = s.president.uid if s.president else None
        chan_uid = s.chancellor.uid if s.chancellor else None
        result = []
        for p in self.alive_players:
            if p.uid == s.nominated_president.uid:
                continue
            if len(self.game.player_sequence) > 5:
                if p.uid == pres_uid or p.uid == chan_uid:
                    continue
            else:
                if p.uid == chan_uid:
                    continue
            result.append(p)
        return result

    def _assign_roles(self, num_players: int) -> None:
        available = list(PLAYER_SETS[num_players]["roles"])
        for uid in self.game.playerlist:
            idx = randrange(len(available))
            role = available.pop(idx)
            self.game.playerlist[uid].role = role
            self.game.playerlist[uid].party = "fascist" if role in ("Fascist", "Hitler") else "liberal"

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _shuffle_if_needed(self) -> None:
        if len(self.board.policies) < 3:
            self.board.discards += self.board.policies
            self.board.policies = random.sample(self.board.discards, len(self.board.discards))
            self.board.discards = []
            self._log("Policy pile reshuffled.")

    def _increment_player_counter(self) -> None:
        if self.state.player_counter < len(self.game.player_sequence) - 1:
            self.state.player_counter += 1
        else:
            self.state.player_counter = 0

    def _advance_to_nomination(self) -> None:
        if self.state.chosen_president is None:
            self.state.nominated_president = self.game.player_sequence[self.state.player_counter]
        else:
            self.state.nominated_president = self.state.chosen_president
            self.state.chosen_president = None
        eligible = self.eligible_chancellors()
        self._log(f"Round: {self.state.nominated_president.name} is presidential candidate.")
        self._pending = (Action.NOMINATE_CHANCELLOR, {
            "president": self.state.nominated_president,
            "eligible": eligible,
        })

    def _do_nominate(self, chancellor: Player) -> None:
        assert self.state.nominated_president is not None
        self.state.nominated_chancellor = chancellor
        self._log(f"{self.state.nominated_president.name} nominated {chancellor.name} as chancellor.")
        self._pending = (Action.VOTE, {
            "president": self.state.nominated_president,
            "chancellor": self.state.nominated_chancellor,
            "voters": list(self.alive_players),
        })

    def _do_vote(self, votes: dict[int, bool]) -> None:
        assert self.state.nominated_president is not None
        assert self.state.nominated_chancellor is not None
        ja_count = sum(1 for v in votes.values() if v)
        total = len(self.game.player_sequence)
        vote_text = ", ".join(
            f"{self.players[uid].name}: {'Ja' if v else 'Nein'}"
            for uid, v in votes.items()
        )
        self._log(f"Vote: {vote_text}")

        if ja_count > total / 2:
            self.state.chancellor = self.state.nominated_chancellor
            self.state.president = self.state.nominated_president
            self.state.nominated_president = None
            self.state.nominated_chancellor = None
            self._log(f"Vote passed! President: {self.state.president.name}, Chancellor: {self.state.chancellor.name}")
            self._voting_aftermath_success()
        else:
            self.state.nominated_president = None
            self.state.nominated_chancellor = None
            self.state.failed_votes += 1
            self._log(f"Vote failed. ({self.state.failed_votes}/3 failed)")
            if self.state.failed_votes == 3:
                self._do_anarchy()
            else:
                self._next_round()

    def _voting_aftermath_success(self) -> None:
        assert self.state.chancellor is not None
        if self.state.fascist_track >= 3 and self.state.chancellor.role == "Hitler":
            self._end_game(EndCode.FASCIST_HITLER_CHANCELLOR)
            return
        if self.state.fascist_track >= 3 and self.state.chancellor.role != "Hitler":
            if self.state.chancellor not in self.state.not_hitlers:
                self.state.not_hitlers.append(self.state.chancellor)
        self._draw_policies()

    def _draw_policies(self) -> None:
        assert self.state.president is not None
        self.state.veto_refused = False
        self._shuffle_if_needed()
        for _ in range(3):
            self.state.drawn_policies.append(self.board.policies.pop(0))
        self._log(f"President {self.state.president.name} drew: {self.state.drawn_policies}")
        self._pending = (Action.PRESIDENT_DISCARD, {
            "president": self.state.president,
            "policies": list(self.state.drawn_policies),
        })

    def _do_president_discard(self, discard: str) -> None:
        self.state.drawn_policies.remove(discard)
        self.board.discards.append(discard)
        self._log(f"President discarded: {discard}")
        can_veto = self.state.fascist_track == 5 and not self.state.veto_refused
        self._pending = (Action.CHANCELLOR_ENACT, {
            "chancellor": self.state.chancellor,
            "policies": list(self.state.drawn_policies),
            "can_veto": can_veto,
        })

    def _do_chancellor_enact(self, choice: str) -> None:
        if choice == "veto":
            self._log(f"Chancellor {self.current_chancellor.name} proposed veto.")
            self._pending = (Action.VETO_CHOICE, {
                "president": self.state.president,
                "policies": list(self.state.drawn_policies),
            })
            return

        self.state.drawn_policies.remove(choice)
        self.board.discards.append(self.state.drawn_policies.pop(0))
        assert len(self.state.drawn_policies) == 0
        self._enact(choice, anarchy=False)

    def _do_veto_choice(self, accept: bool) -> None:
        if accept:
            self._log("President accepted veto.")
            self.board.discards += self.state.drawn_policies
            self.state.drawn_policies = []
            self.state.failed_votes += 1
            if self.state.failed_votes == 3:
                self._do_anarchy()
            else:
                self._next_round()
        else:
            self._log("President refused veto.")
            self.state.veto_refused = True
            self._pending = (Action.CHANCELLOR_ENACT, {
                "chancellor": self.state.chancellor,
                "policies": list(self.state.drawn_policies),
                "can_veto": False,
            })

    def _enact(self, policy: str, anarchy: bool) -> None:
        if policy == "liberal":
            self.state.liberal_track += 1
        else:
            self.state.fascist_track += 1
        self.state.failed_votes = 0
        self._log(f"Enacted: {policy} (liberal={self.state.liberal_track}, fascist={self.state.fascist_track})")

        if self.state.liberal_track == 5:
            self._end_game(EndCode.LIBERAL_POLICIES)
            return
        if self.state.fascist_track == 6:
            self._end_game(EndCode.FASCIST_POLICIES)
            return

        self._shuffle_if_needed()

        if not anarchy and policy == "fascist":
            action = self.board.fascist_track_actions[self.state.fascist_track - 1]
            if action == "policy":
                top3 = self.board.policies[:3]
                self._log(f"President peeked: {top3}")
                self._next_round()
            elif action == "kill":
                killable = [p for p in self.alive_players if p.uid != self.current_president.uid]
                self._pending = (Action.EXECUTIVE_KILL, {
                    "president": self.state.president,
                    "choices": killable,
                })
            elif action == "inspect":
                inspectable = [p for p in self.alive_players if p.uid != self.current_president.uid]
                self._pending = (Action.EXECUTIVE_INSPECT, {
                    "president": self.state.president,
                    "choices": inspectable,
                })
            elif action == "choose":
                choosable = [p for p in self.alive_players if p.uid != self.current_president.uid]
                self._pending = (Action.EXECUTIVE_SPECIAL_ELECTION, {
                    "president": self.state.president,
                    "choices": choosable,
                })
            else:
                self._next_round()
        else:
            self._next_round()

    def _do_kill(self, target: Player) -> None:
        target.is_dead = True
        if self.game.player_sequence.index(target) <= self.state.player_counter:
            self.state.player_counter -= 1
        self.game.player_sequence.remove(target)
        self._log(f"President {self.current_president.name} killed {target.name} ({target.role}).")
        if target.role == "Hitler":
            self._end_game(EndCode.LIBERAL_KILLED_HITLER)
        else:
            self._next_round()

    def _do_inspect(self, target: Player) -> None:
        self._log(f"President {self.current_president.name} inspected {target.name}: {target.party}.")
        self._next_round()

    def _do_special_election(self, target: Player) -> None:
        self.state.chosen_president = target
        self._log(f"President {self.current_president.name} chose {target.name} as next president.")
        self._next_round()

    def _do_anarchy(self) -> None:
        self.state.president = None
        self.state.chancellor = None
        top_policy = self.board.policies.pop(0)
        self.state.failed_votes = 0
        self._log("ANARCHY! Top policy enacted.")
        self._enact(top_policy, anarchy=True)

    def _next_round(self) -> None:
        if self.game_over:
            return
        if self.state.chosen_president is None:
            self._increment_player_counter()
        self._advance_to_nomination()

    def _end_game(self, code: EndCode) -> None:
        self.end_code = code
        self._log(f"GAME OVER: {code.name}")
        self._pending = None

    def summary(self) -> dict:
        """Returns a dict summarizing the game result."""
        return {
            "end_code": self.end_code,
            "liberal_track": self.state.liberal_track,
            "fascist_track": self.state.fascist_track,
            "rounds": len([l for l in self.log if l.startswith("Round:")]),
            "roles": {self.players[uid].name: self.players[uid].role for uid in self.players},
        }
