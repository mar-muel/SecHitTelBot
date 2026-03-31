"""Integration tests for the Telegram layer (MainController + GameSession) on top of the engine."""

import pytest
from constants.cards import PLAYER_SETS
from engine import Action, EndCode
import controller
from conftest import sent_texts


class TestPlayerSets:
    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_roles_count_matches_player_count(self, n):
        assert len(PLAYER_SETS[n].roles) == n

    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_exactly_one_hitler(self, n):
        assert PLAYER_SETS[n].roles.count("Hitler") == 1

    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_only_valid_roles(self, n):
        for role in PLAYER_SETS[n].roles:
            assert role in ("Liberal", "Fascist", "Hitler")

    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_track_length_is_six(self, n):
        assert len(PLAYER_SETS[n].track) == 6

    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_track_ends_with_win(self, n):
        assert PLAYER_SETS[n].track[-1] == "win"

    @pytest.mark.parametrize("n", PLAYER_SETS.keys())
    def test_track_only_valid_actions(self, n):
        for action in PLAYER_SETS[n].track:
            assert action in (None, "policy", "inspect", "choose", "kill", "win")

    @pytest.mark.parametrize("n", [5, 6, 7, 8, 9, 10])
    def test_liberal_majority(self, n):
        roles = PLAYER_SETS[n].roles
        assert roles.count("Liberal") > roles.count("Fascist") + 1


class TestGameSession:
    def test_lobby_phase(self, bot, session5):
        # Session should be started (engine exists)
        assert session5.started
        assert session5.engine is not None
        assert session5.board is not None

    def test_playerlist_delegates_to_engine(self, bot, session5):
        assert len(session5.playerlist) == 5
        for uid in session5.playerlist:
            assert session5.playerlist[uid].role is not None

    def test_player_sequence(self, bot, session5):
        assert len(session5.player_sequence) == 5


class TestRoleAssignment:
    def test_correct_role_counts(self, bot, session_any):
        expected = PLAYER_SETS[len(session_any.playerlist)].roles
        actual = [session_any.playerlist[uid].role for uid in session_any.playerlist]
        for role in ("Liberal", "Fascist", "Hitler"):
            assert actual.count(role) == expected.count(role)

    def test_party_membership_matches_role(self, bot, session_any):
        for uid in session_any.playerlist:
            p = session_any.playerlist[uid]
            if p.role in ("Fascist", "Hitler"):
                assert p.party == "fascist"
            else:
                assert p.party == "liberal"


class TestFascistInformation:
    @pytest.mark.asyncio
    async def test_5p_hitler_knows_fascist(self, bot, session5):
        bot.reset_mock()
        await controller.inform_fascists(bot, session5)
        hitler = session5.engine.game.get_hitler()
        fascists = session5.engine.game.get_fascists()
        msgs = [c for c in bot.send_message.call_args_list if c[0][0] == hitler.uid]
        fellow_msgs = [c for c in msgs if "Your fellow fascist is" in str(c)]
        assert len(fellow_msgs) == 1
        assert fascists[0].name in str(fellow_msgs[0])

    @pytest.mark.asyncio
    async def test_7p_hitler_does_not_know_fascists(self, bot, session7):
        bot.reset_mock()
        await controller.inform_fascists(bot, session7)
        hitler = session7.engine.game.get_hitler()
        msgs = [c for c in bot.send_message.call_args_list if c[0][0] == hitler.uid]
        assert not any("fellow fascist" in str(c) for c in msgs)

    @pytest.mark.asyncio
    async def test_7p_fascists_know_hitler(self, bot, session7):
        bot.reset_mock()
        await controller.inform_fascists(bot, session7)
        hitler = session7.engine.game.get_hitler()
        for f in session7.engine.game.get_fascists():
            msgs = [c for c in bot.send_message.call_args_list if c[0][0] == f.uid]
            hitler_msgs = [c for c in msgs if "Hitler is" in str(c)]
            assert len(hitler_msgs) == 1
            assert hitler.name in str(hitler_msgs[0])


class TestBoard:
    def test_initial_state(self, bot, session5):
        assert session5.engine.state.liberal_track == 0
        assert session5.engine.state.fascist_track == 0
        assert session5.engine.state.failed_votes == 0

    def test_policy_deck_size(self, bot, session5):
        assert len(session5.engine.board.policies) == 17

    def test_board_print(self, bot, session5):
        text = session5.engine.board.print_board()
        for section in ("Liberal acts", "Fascist acts", "Election counter", "Presidential order"):
            assert section in text

    def test_5p_fascist_track(self, bot, session5):
        assert session5.engine.board.fascist_track_actions == [None, None, "policy", "kill", "kill", "win"]

    def test_9p_fascist_track(self, bot, session9):
        assert session9.engine.board.fascist_track_actions == ["inspect", "inspect", "choose", "kill", "kill", "win"]


class TestPresentAction:
    def test_first_action_is_nomination(self, bot, session5):
        action, ctx = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR
        assert "eligible" in ctx
        assert "president" in ctx

    @pytest.mark.asyncio
    async def test_present_nomination_sends_keyboard(self, bot, session5):
        bot.reset_mock()
        await controller.present_action(bot, session5)
        # Should send messages: one to group (announcement) + two to president (board + keyboard)
        texts = sent_texts(bot)
        assert any("presidential candidate" in t for t in texts)
        assert any("nominate your chancellor" in t.lower() for t in texts)

    def test_nomination_then_vote(self, bot, session5):
        action, ctx = session5.engine.pending_action()
        # Nominate the first eligible player
        chancellor = ctx["eligible"][0]
        session5.engine.step(chancellor)
        # Engine should now be waiting for votes
        action2, ctx2 = session5.engine.pending_action()
        assert action2 == Action.VOTE
        assert "voters" in ctx2


class TestEngineViaSession:
    def test_vote_pass_leads_to_policy_draw(self, bot, session5):
        # Nominate
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        # Vote all Ja
        voters = session5.engine.alive_players
        votes = {p.uid: True for p in voters}
        session5.engine.step(votes)
        # Should be in legislative session (unless Hitler elected)
        if not session5.engine.game_over:
            action, _ = session5.engine.pending_action()
            assert action == Action.PRESIDENT_DISCARD

    def test_vote_fail_leads_to_next_nomination(self, bot, session5):
        # Nominate
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        # Vote all Nein
        voters = session5.engine.alive_players
        votes = {p.uid: False for p in voters}
        session5.engine.step(votes)
        # Should be back to nomination
        action, _ = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR

    def test_three_failed_votes_triggers_anarchy(self, bot, session5):
        session5.engine.state.failed_votes = 2
        # Nominate
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        # Vote all Nein — this is the 3rd failure
        voters = session5.engine.alive_players
        votes = {p.uid: False for p in voters}
        lib_before = session5.engine.state.liberal_track
        fasc_before = session5.engine.state.fascist_track
        session5.engine.step(votes)
        # A policy should have been enacted (anarchy)
        lib_after = session5.engine.state.liberal_track
        fasc_after = session5.engine.state.fascist_track
        assert (lib_after > lib_before) or (fasc_after > fasc_before) or session5.engine.game_over

    def test_full_legislative_session(self, bot, session5):
        """Walk through nomination → vote → president discard → chancellor enact."""
        # Nominate
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        # Vote Ja
        votes = {p.uid: True for p in session5.engine.alive_players}
        session5.engine.step(votes)
        if session5.engine.game_over:
            return
        # President discards one policy
        action, ctx = session5.engine.pending_action()
        assert action == Action.PRESIDENT_DISCARD
        assert len(ctx["policies"]) == 3
        session5.engine.step(ctx["policies"][0])
        # Chancellor enacts one of the remaining two
        action, ctx = session5.engine.pending_action()
        assert action == Action.CHANCELLOR_ENACT
        assert len(ctx["policies"]) == 2
        session5.engine.step(ctx["policies"][0])
        # Game should continue (next nomination or executive action or game over)
        assert session5.engine.game_over or session5.engine.pending_action() is not None


class TestEndGame:
    def test_end_game_liberal_policies(self, bot, session5):
        session5.engine.state.liberal_track = 4
        # Nominate + vote
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        votes = {p.uid: True for p in session5.engine.alive_players}
        session5.engine.step(votes)
        if session5.engine.game_over:
            return
        # Discard a fascist policy, enact liberal
        _, ctx = session5.engine.pending_action()
        # Find a liberal policy if possible
        policies = ctx["policies"]
        fascist_idx = next((i for i, p in enumerate(policies) if p == "fascist"), 0)
        session5.engine.step(policies[fascist_idx])
        _, ctx = session5.engine.pending_action()
        policies = ctx["policies"]
        liberal_idx = next((i for i, p in enumerate(policies) if p == "liberal"), 0)
        session5.engine.step(policies[liberal_idx])
        if session5.engine.state.liberal_track == 5:
            assert session5.engine.game_over
            assert session5.engine.end_code == EndCode.LIBERAL_POLICIES

    @pytest.mark.asyncio
    async def test_end_game_sends_message(self, bot, session5):
        # Force a game-over state
        session5.engine.state.liberal_track = 4
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["eligible"][0])
        votes = {p.uid: True for p in session5.engine.alive_players}
        session5.engine.step(votes)
        if session5.engine.game_over:
            # Hitler was elected
            bot.reset_mock()
            await controller.end_game(bot, session5)
            texts = sent_texts(bot)
            assert any("Game over" in t for t in texts)

    @pytest.mark.asyncio
    async def test_cancel_game(self, bot, session5):
        bot.reset_mock()
        await controller.end_game(bot, session5, cancelled=True)
        texts = sent_texts(bot)
        assert any("Game cancelled" in t for t in texts)
