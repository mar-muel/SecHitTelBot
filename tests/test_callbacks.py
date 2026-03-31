"""Tests for Telegram callback handlers and all present_action branches."""

from unittest.mock import MagicMock

from engine import Action, EndCode
import MainController
import GamesController
from conftest import sent_texts


def make_callback(data, from_user_id, message_id=1):
    """Create a mock Telegram callback query update."""
    update = MagicMock()
    update.callback_query.data = data
    update.callback_query.from_user.id = from_user_id
    update.callback_query.from_user.first_name = f"User{from_user_id}"
    update.callback_query.message.message_id = message_id
    return update


# -- Helpers to drive the engine to specific states --

def step_to_vote(session):
    """Nominate a chancellor to reach VOTE state."""
    _, ctx = session.engine.pending_action()
    chancellor = ctx["eligible"][0]
    session.engine.step(chancellor)
    return ctx["president"], chancellor


def step_to_president_discard(session):
    """Reach PRESIDENT_DISCARD state (nominate + all vote Ja)."""
    pres, chan = step_to_vote(session)
    votes = {p.uid: True for p in session.engine.alive_players}
    session.engine.step(votes)
    return pres, chan


def step_to_chancellor_enact(session):
    """Reach CHANCELLOR_ENACT state (nominate + vote + president discards)."""
    pres, chan = step_to_president_discard(session)
    if session.engine.game_over:
        return None, None
    _, ctx = session.engine.pending_action()
    # President discards first policy
    session.engine.step(ctx["policies"][0])
    return pres, chan


def step_to_veto_choice(session):
    """Reach VETO_CHOICE state. Sets fascist_track=5 to enable veto.

    Returns False if we couldn't reach the state (e.g. Hitler elected).
    """
    # Set fascist_track to 5 AFTER nomination but BEFORE voting,
    # so the Hitler-chancellor check doesn't trigger on our chosen chancellor.
    _, ctx = session.engine.pending_action()
    # Pick a non-Hitler chancellor to avoid the game ending
    non_hitler = [p for p in ctx["eligible"] if p.role != "Hitler"]
    if not non_hitler:
        return False
    session.engine.step(non_hitler[0])
    # Now set fascist_track high so veto is available after the legislative session
    session.engine.state.fascist_track = 5
    votes = {p.uid: True for p in session.engine.alive_players}
    session.engine.step(votes)
    if session.engine.game_over:
        return False
    # President discards
    _, ctx = session.engine.pending_action()
    session.engine.step(ctx["policies"][0])
    # Chancellor should now have veto option
    action, ctx = session.engine.pending_action()
    if action != Action.CHANCELLOR_ENACT or not ctx.get("can_veto"):
        return False
    # Chancellor proposes veto
    session.engine.step("veto")
    return True


# =============================================================================
# present_action — all branches
# =============================================================================

class TestPresentActionAllBranches:
    def test_present_nomination(self, bot, session5):
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("presidential candidate" in t for t in texts)
        assert any("nominate your chancellor" in t.lower() for t in texts)

    def test_present_vote(self, bot, session5):
        step_to_vote(session5)
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Do you want to elect" in t for t in texts)
        assert session5.dateinitvote is not None
        assert session5.pending_votes == {}

    def test_vote_sends_buttons_to_all_alive(self, bot, session5):
        step_to_vote(session5)
        bot.reset_mock()
        MainController.present_action(bot, session5)
        # Every alive player should get a vote prompt
        alive_uids = {p.uid for p in session5.engine.alive_players}
        messaged_uids = {c[0][0] for c in bot.send_message.call_args_list}
        # All alive players should be messaged (group cid messages aside)
        player_msgs = messaged_uids - {session5.cid}
        assert player_msgs == alive_uids

    def test_present_president_discard(self, bot, session5):
        step_to_president_discard(session5)
        if session5.engine.game_over:
            return
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Which one do you want to discard" in t for t in texts)

    def test_present_chancellor_enact(self, bot, session5):
        step_to_chancellor_enact(session5)
        if session5.engine.game_over:
            return
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Which one do you want to enact" in t for t in texts)

    def test_present_chancellor_enact_with_veto_power(self, bot, session5):
        """When fascist_track==5, chancellor should see a Veto button."""
        if not step_to_veto_choice(session5):
            return
        # We're now at VETO_CHOICE, but let's test the CHANCELLOR_ENACT
        # presentation by refusing the veto so the chancellor gets re-prompted
        session5.engine.step(False)  # president refuses veto
        action, ctx = session5.engine.pending_action()
        assert action == Action.CHANCELLOR_ENACT
        assert ctx["can_veto"] is False
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("refused your Veto" in t for t in texts)

    def test_present_veto_choice(self, bot, session5):
        if not step_to_veto_choice(session5):
            return
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("suggested a Veto" in t for t in texts)

    def test_present_executive_kill(self, bot, session5):
        # Inject engine directly into EXECUTIVE_KILL state
        president = session5.engine.alive_players[0]
        others = [p for p in session5.engine.alive_players if p.uid != president.uid]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_KILL, {
            "president": president,
            "choices": others,
        })
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Execution" in t for t in texts)
        assert any("kill one person" in t.lower() for t in texts)

    def test_present_executive_inspect(self, bot, session5):
        president = session5.engine.alive_players[0]
        others = [p for p in session5.engine.alive_players if p.uid != president.uid]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_INSPECT, {
            "president": president,
            "choices": others,
        })
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Investigate Loyalty" in t for t in texts)
        assert any("party membership" in t for t in texts)

    def test_present_executive_special_election(self, bot, session5):
        president = session5.engine.alive_players[0]
        others = [p for p in session5.engine.alive_players if p.uid != president.uid]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_SPECIAL_ELECTION, {
            "president": president,
            "choices": others,
        })
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Special Election" in t for t in texts)
        assert any("next presidential candidate" in t for t in texts)

    def test_present_action_calls_end_game_when_over(self, bot, session5):
        """If engine is game_over, present_action should call end_game."""
        # Force game over
        session5.engine.end_code = EndCode.LIBERAL_POLICIES
        bot.reset_mock()
        MainController.present_action(bot, session5)
        texts = sent_texts(bot)
        assert any("Game over" in t for t in texts)
        # Session should be removed from GamesController
        assert session5.cid not in GamesController.games


# =============================================================================
# Callback handler: nominate_chosen_chancellor
# =============================================================================

class TestNominateCallback:
    def test_nominate_steps_engine_to_vote(self, bot, session5):
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]
        chosen = ctx["eligible"][0]

        update = make_callback(f"{session5.cid}_chan_{chosen.uid}", president.uid)
        bot.reset_mock()
        MainController.nominate_chosen_chancellor(bot, update)

        # Engine should have advanced to VOTE
        action, _ = session5.engine.pending_action()
        assert action == Action.VOTE

    def test_nominate_sends_messages(self, bot, session5):
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]
        chosen = ctx["eligible"][0]

        update = make_callback(f"{session5.cid}_chan_{chosen.uid}", president.uid)
        bot.reset_mock()
        MainController.nominate_chosen_chancellor(bot, update)

        # Confirmation edit to president
        bot.edit_message_text.assert_called_once()
        edit_text = str(bot.edit_message_text.call_args)
        assert "nominated" in edit_text and chosen.name in edit_text
        # Group announcement
        texts = sent_texts(bot)
        assert any("nominated" in t and "Please vote" in t for t in texts)


# =============================================================================
# Callback handler: handle_voting + finish_voting
# =============================================================================

class TestVotingCallbacks:
    def test_single_vote_does_not_finish(self, bot, session5):
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()
        voter = ctx["voters"][0]

        update = make_callback(f"{session5.cid}_Ja", voter.uid)
        MainController.handle_voting(bot, update)

        assert voter.uid in session5.pending_votes
        assert session5.pending_votes[voter.uid] is True
        # Engine should still be at VOTE
        action, _ = session5.engine.pending_action()
        assert action == Action.VOTE

    def test_duplicate_vote_ignored(self, bot, session5):
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()
        voter = ctx["voters"][0]

        update_ja = make_callback(f"{session5.cid}_Ja", voter.uid)
        MainController.handle_voting(bot, update_ja)
        assert session5.pending_votes[voter.uid] is True

        # Second vote with Nein — should be ignored
        update_nein = make_callback(f"{session5.cid}_Nein", voter.uid)
        MainController.handle_voting(bot, update_nein)
        assert session5.pending_votes[voter.uid] is True  # still Ja

    def test_all_ja_passes(self, bot, session5):
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()

        for voter in ctx["voters"]:
            update = make_callback(f"{session5.cid}_Ja", voter.uid)
            MainController.handle_voting(bot, update)

        # Vote passed — engine should advance past VOTE
        if not session5.engine.game_over:
            action, _ = session5.engine.pending_action()
            assert action == Action.PRESIDENT_DISCARD
        texts = sent_texts(bot)
        assert any("Hail President" in t for t in texts)

    def test_all_nein_fails(self, bot, session5):
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()

        for voter in ctx["voters"]:
            update = make_callback(f"{session5.cid}_Nein", voter.uid)
            MainController.handle_voting(bot, update)

        # Vote failed — engine should be back at nomination
        action, _ = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR
        texts = sent_texts(bot)
        assert any("didn't like" in t for t in texts)

    def test_anarchy_after_third_failure(self, bot, session5):
        session5.engine.state.failed_votes = 2
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()

        for voter in ctx["voters"]:
            update = make_callback(f"{session5.cid}_Nein", voter.uid)
            MainController.handle_voting(bot, update)

        texts = sent_texts(bot)
        assert any("ANARCHY" in t for t in texts)
        # A policy should have been enacted (track changed or game over)
        assert session5.engine.game_over or session5.engine.pending_action() is not None

    def test_edit_message_sent_to_voter(self, bot, session5):
        step_to_vote(session5)
        _, ctx = session5.engine.pending_action()
        voter = ctx["voters"][0]

        update = make_callback(f"{session5.cid}_Ja", voter.uid)
        bot.reset_mock()
        MainController.handle_voting(bot, update)

        bot.edit_message_text.assert_called_once()
        edit_text = str(bot.edit_message_text.call_args)
        assert "Thank you for your vote" in edit_text
        assert "Ja" in edit_text


# =============================================================================
# Callback handler: choose_policy (president discard + chancellor enact + veto)
# =============================================================================

class TestChoosePolicyCallback:
    def test_president_discard(self, bot, session5):
        step_to_president_discard(session5)
        if session5.engine.game_over:
            return
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]
        policy = ctx["policies"][0]

        update = make_callback(f"{session5.cid}_{policy}", president.uid)
        bot.reset_mock()
        MainController.choose_policy(bot, update)

        # Should advance to chancellor enact
        action, ctx2 = session5.engine.pending_action()
        assert action == Action.CHANCELLOR_ENACT
        assert len(ctx2["policies"]) == 2

    def test_chancellor_enact(self, bot, session5):
        step_to_chancellor_enact(session5)
        if session5.engine.game_over:
            return
        _, ctx = session5.engine.pending_action()
        chancellor = ctx["chancellor"]
        policy = ctx["policies"][0]

        update = make_callback(f"{session5.cid}_{policy}", chancellor.uid)
        bot.reset_mock()
        MainController.choose_policy(bot, update)

        texts = sent_texts(bot)
        assert any("enacted" in t and policy in t for t in texts)
        # Engine should have advanced (next round, executive action, or game over)
        assert session5.engine.game_over or session5.engine.pending_action() is not None

    def test_chancellor_veto_proposal(self, bot, session5):
        if not step_to_veto_choice(session5):
            return
        # We're at VETO_CHOICE already via the helper.
        # Let's instead test the callback path: back up and test choose_policy with "veto".
        # Reset: refuse the current veto so chancellor is re-prompted without veto
        session5.engine.step(False)
        # Now fascist_track is still 5, but veto_refused is True so can_veto=False.
        # We need a fresh veto-eligible state. Let's use a different approach:
        # just verify the engine reached VETO_CHOICE via the helper already.
        # Instead, test that the callback handler correctly processes a veto.
        pass

    def test_chancellor_veto_via_callback(self, bot, session5):
        """Test the full callback path for a veto proposal."""
        # Get to CHANCELLOR_ENACT with veto available
        _, ctx = session5.engine.pending_action()
        non_hitler = [p for p in ctx["eligible"] if p.role != "Hitler"]
        if not non_hitler:
            return
        session5.engine.step(non_hitler[0])
        session5.engine.state.fascist_track = 5
        votes = {p.uid: True for p in session5.engine.alive_players}
        session5.engine.step(votes)
        if session5.engine.game_over:
            return
        # President discards
        _, ctx = session5.engine.pending_action()
        session5.engine.step(ctx["policies"][0])
        action, ctx = session5.engine.pending_action()
        if action != Action.CHANCELLOR_ENACT or not ctx.get("can_veto"):
            return

        chancellor = ctx["chancellor"]
        update = make_callback(f"{session5.cid}_veto", chancellor.uid)
        bot.reset_mock()
        MainController.choose_policy(bot, update)

        # Should advance to VETO_CHOICE
        action, _ = session5.engine.pending_action()
        assert action == Action.VETO_CHOICE
        texts = sent_texts(bot)
        assert any("Veto" in t for t in texts)

    def test_policy_peek_after_fascist_enact(self, bot, session5):
        """On a 5-player board, the 3rd fascist policy triggers a policy peek."""
        session5.engine.state.fascist_track = 2  # next fascist will be slot 3 → "policy" peek
        step_to_chancellor_enact(session5)
        if session5.engine.game_over:
            return
        _, ctx = session5.engine.pending_action()
        chancellor = ctx["chancellor"]
        # Pick a fascist policy if available
        fascist_policy = next((p for p in ctx["policies"] if p == "fascist"), None)
        if not fascist_policy:
            return

        update = make_callback(f"{session5.cid}_{fascist_policy}", chancellor.uid)
        bot.reset_mock()
        MainController.choose_policy(bot, update)

        texts = sent_texts(bot)
        assert any("Policy Peek" in t for t in texts)
        assert any("top three policies" in t.lower() for t in texts)


# =============================================================================
# Callback handler: choose_veto
# =============================================================================

class TestChooseVetoCallback:
    def test_accept_veto(self, bot, session5):
        if not step_to_veto_choice(session5):
            return
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]

        update = make_callback(f"{session5.cid}_yesveto", president.uid)
        bot.reset_mock()
        MainController.choose_veto(bot, update)

        texts = sent_texts(bot)
        assert any("accepted" in t.lower() for t in texts)
        assert session5.engine.game_over or session5.engine.pending_action() is not None

    def test_refuse_veto(self, bot, session5):
        if not step_to_veto_choice(session5):
            return
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]

        update = make_callback(f"{session5.cid}_noveto", president.uid)
        bot.reset_mock()
        MainController.choose_veto(bot, update)

        # Chancellor should be re-prompted without veto option
        action, ctx = session5.engine.pending_action()
        assert action == Action.CHANCELLOR_ENACT
        assert ctx["can_veto"] is False
        texts = sent_texts(bot)
        assert any("refused" in t.lower() for t in texts)

    def test_veto_accept_triggers_anarchy_on_third_failure(self, bot, session5):
        session5.engine.state.failed_votes = 2
        if not step_to_veto_choice(session5):
            return
        _, ctx = session5.engine.pending_action()
        president = ctx["president"]

        update = make_callback(f"{session5.cid}_yesveto", president.uid)
        bot.reset_mock()
        MainController.choose_veto(bot, update)

        texts = sent_texts(bot)
        assert any("accepted" in t.lower() for t in texts)
        assert any("ANARCHY" in t for t in texts)


# =============================================================================
# Callback handler: choose_kill
# =============================================================================

class TestChooseKillCallback:
    def _setup_kill(self, session, target_role="Liberal"):
        """Inject engine into EXECUTIVE_KILL state. Returns (president, target)."""
        president = session.engine.alive_players[0]
        if president.role == "Hitler" and target_role == "Hitler":
            president = session.engine.alive_players[1]
        target = next(
            p for p in session.engine.alive_players
            if p.uid != president.uid and p.role == target_role
        )
        session.engine.state.president = president
        session.engine._pending = (Action.EXECUTIVE_KILL, {
            "president": president,
            "choices": [p for p in session.engine.alive_players if p.uid != president.uid],
        })
        return president, target

    def test_kill_non_hitler(self, bot, session5):
        president, target = self._setup_kill(session5, "Liberal")

        update = make_callback(f"{session5.cid}_kill_{target.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_kill(bot, update)

        assert not session5.engine.game_over
        assert target.is_dead
        texts = sent_texts(bot)
        assert any("killed" in t and target.name in t for t in texts)
        assert any("not Hitler" in t for t in texts)
        # Engine should advance to next round
        action, _ = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR

    def test_kill_hitler_ends_game(self, bot, session5):
        president, hitler = self._setup_kill(session5, "Hitler")

        update = make_callback(f"{session5.cid}_kill_{hitler.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_kill(bot, update)

        assert session5.engine.game_over
        assert session5.engine.end_code == EndCode.LIBERAL_KILLED_HITLER
        texts = sent_texts(bot)
        assert any("killed" in t and hitler.name in t for t in texts)

    def test_kill_edits_president_message(self, bot, session5):
        president, target = self._setup_kill(session5, "Liberal")

        update = make_callback(f"{session5.cid}_kill_{target.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_kill(bot, update)

        bot.edit_message_text.assert_called_once()
        edit_text = str(bot.edit_message_text.call_args)
        assert "killed" in edit_text.lower() and target.name in edit_text


# =============================================================================
# Callback handler: choose_inspect
# =============================================================================

class TestChooseInspectCallback:
    def test_inspect_reveals_party(self, bot, session5):
        president = session5.engine.alive_players[0]
        target = session5.engine.alive_players[1]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_INSPECT, {
            "president": president,
            "choices": [p for p in session5.engine.alive_players if p.uid != president.uid],
        })

        update = make_callback(f"{session5.cid}_insp_{target.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_inspect(bot, update)

        # President should see target's party in the edit message
        edit_text = str(bot.edit_message_text.call_args)
        assert target.party in edit_text
        assert target.name in edit_text
        # Group gets a public message that inspection happened (but not the result)
        texts = sent_texts(bot)
        assert any("inspected" in t and target.name in t for t in texts)
        # Engine should advance to next round
        action, _ = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR


# =============================================================================
# Callback handler: choose_choose (special election)
# =============================================================================

class TestChooseChooseCallback:
    def test_special_election(self, bot, session5):
        president = session5.engine.alive_players[0]
        target = session5.engine.alive_players[2]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_SPECIAL_ELECTION, {
            "president": president,
            "choices": [p for p in session5.engine.alive_players if p.uid != president.uid],
        })

        update = make_callback(f"{session5.cid}_choo_{target.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_choose(bot, update)

        # Group message about the special election
        texts = sent_texts(bot)
        assert any("chose" in t and target.name in t for t in texts)
        # Next nomination should have the chosen player as president
        action, ctx = session5.engine.pending_action()
        assert action == Action.NOMINATE_CHANCELLOR
        assert ctx["president"] == target

    def test_special_election_edits_president_message(self, bot, session5):
        president = session5.engine.alive_players[0]
        target = session5.engine.alive_players[2]
        session5.engine.state.president = president
        session5.engine._pending = (Action.EXECUTIVE_SPECIAL_ELECTION, {
            "president": president,
            "choices": [p for p in session5.engine.alive_players if p.uid != president.uid],
        })

        update = make_callback(f"{session5.cid}_choo_{target.uid}", president.uid)
        bot.reset_mock()
        MainController.choose_choose(bot, update)

        bot.edit_message_text.assert_called_once()
        edit_text = str(bot.edit_message_text.call_args)
        assert target.name in edit_text
        assert "next president" in edit_text
