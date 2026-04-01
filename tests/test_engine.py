import random
from typing import assert_never
from engine import GameEngine
from game_types import Action, EndCode, GameOver, Role
import pytest


def random_step(engine: GameEngine) -> None:
    """Make a random valid choice for the current pending action."""
    pending = engine.pending_action()
    assert pending is not None
    action, ctx = pending

    match action:
        case Action.NOMINATE_CHANCELLOR:
            engine.step(random.choice(ctx["eligible"]))

        case Action.VOTE:
            votes = {p.uid: random.choice([True, False]) for p in ctx["voters"]}
            engine.step(votes)

        case Action.PRESIDENT_DISCARD:
            engine.step(random.choice(ctx["policies"]))

        case Action.CHANCELLOR_ENACT:
            choices = list(ctx["policies"])
            if ctx.get("can_veto") and random.random() < 0.3:
                choices.append("veto")
            engine.step(random.choice(choices))

        case Action.VETO_CHOICE:
            engine.step(random.choice([True, False]))

        case Action.EXECUTIVE_KILL | Action.EXECUTIVE_INSPECT | Action.EXECUTIVE_SPECIAL_ELECTION:
            engine.step(random.choice(ctx["choices"]))

        case _ as unreachable:
            assert_never(unreachable)


class TestEngineBasics:
    def test_initial_state(self):
        e = GameEngine(5, seed=42)
        assert not e.game_over
        assert e.end_code == EndCode.RUNNING
        assert len(e.alive_players) == 5
        assert e.state.liberal_track == 0
        assert e.state.fascist_track == 0

    def test_role_distribution_5p(self):
        e = GameEngine(5, seed=42)
        roles = [e.players[uid].role for uid in e.players]
        assert roles.count(Role.LIBERAL) == 3
        assert roles.count(Role.FASCIST) == 1
        assert roles.count(Role.HITLER) == 1

    def test_role_distribution_10p(self):
        e = GameEngine(10, seed=42)
        roles = [e.players[uid].role for uid in e.players]
        assert roles.count(Role.LIBERAL) == 6
        assert roles.count(Role.FASCIST) == 3
        assert roles.count(Role.HITLER) == 1

    def test_first_pending_is_nomination(self):
        e = GameEngine(5, seed=42)
        action, ctx = e.pending_action()  # type: ignore[misc]
        assert action == Action.NOMINATE_CHANCELLOR
        assert "eligible" in ctx
        assert "president" in ctx

    def test_players_dict_constructor(self):
        players = {100: "Alice", 200: "Bob", 300: "Charlie", 400: "Diana", 500: "Eve"}
        e = GameEngine(players=players, seed=42)
        assert len(e.players) == 5
        assert e.players[100].name == "Alice"
        assert e.players[500].name == "Eve"
        assert not e.game_over
        # All players should have roles assigned
        roles = [e.players[uid].role for uid in e.players]
        assert roles.count(Role.LIBERAL) == 3
        assert roles.count(Role.FASCIST) == 1
        assert roles.count(Role.HITLER) == 1
        # Game should be playable
        action, _ = e.pending_action()  # type: ignore[misc]
        assert action == Action.NOMINATE_CHANCELLOR

    def test_players_dict_game_completes(self):
        players = {10: "A", 20: "B", 30: "C", 40: "D", 50: "E", 60: "F", 70: "G"}
        e = GameEngine(players=players, seed=7)
        steps = 0
        while not e.game_over:
            random_step(e)
            steps += 1
            assert steps < 500
        assert e.end_code != EndCode.RUNNING

    def test_step_after_game_over_raises(self):
        e = GameEngine(5, seed=42)
        # Play until done
        while not e.game_over:
            random_step(e)
        with pytest.raises(GameOver):
            e.step(None)


class TestRandomGames:
    @pytest.mark.parametrize("num_players", [4, 5, 6, 7, 8, 9, 10])
    def test_random_game_completes(self, num_players: int):
        for seed in range(20):
            e = GameEngine(num_players, seed=seed)
            steps = 0
            while not e.game_over:
                random_step(e)
                steps += 1
                assert steps < 500, "Game did not terminate"
            assert e.end_code != EndCode.RUNNING

    def test_all_end_codes_reachable(self):
        """Run enough random games to see every possible ending."""
        seen = set()
        for seed in range(500):
            e = GameEngine(7, seed=seed)
            while not e.game_over:
                random_step(e)
            seen.add(e.end_code)
            if len(seen) == 4:
                break
        expected = {EndCode.LIBERAL_POLICIES, EndCode.FASCIST_POLICIES,
                    EndCode.LIBERAL_KILLED_HITLER, EndCode.FASCIST_HITLER_CHANCELLOR}
        assert seen == expected, f"Missing end codes: {expected - seen}"


class TestGameLog:
    def test_log_not_empty(self):
        e = GameEngine(5, seed=42)
        while not e.game_over:
            random_step(e)
        assert len(e.log) > 0
        assert any("GAME OVER" in l for l in e.log)

    def test_summary(self):
        e = GameEngine(5, seed=42)
        while not e.game_over:
            random_step(e)
        s = e.summary()
        assert "end_code" in s
        assert "roles" in s
        assert s["rounds"] > 0
        assert len(s["roles"]) == 5
