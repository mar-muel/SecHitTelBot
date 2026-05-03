"""Tests for the nomination timeout feature."""

import pytest
from unittest.mock import MagicMock

from game_types import Action
import controller
from conftest import _setup_session, sent_texts


class TestSkipNomination:
    def test_skip_advances_player_no_failed_votes(self, bot):
        session = _setup_session(bot, 5)
        engine = session.engine
        assert engine is not None
        result = engine.pending_action()
        assert result is not None
        action, ctx = result
        assert action == Action.NOMINATE_CHANCELLOR
        first_president = ctx["president"]
        failed_before = engine.state.failed_votes

        engine.skip_nomination()

        result = engine.pending_action()
        assert result is not None
        action, ctx = result
        assert action == Action.NOMINATE_CHANCELLOR
        assert ctx["president"] != first_president
        assert engine.state.failed_votes == failed_before
        assert len(engine.messages) == 1
        assert "did not nominate" in engine.messages[0].text

    def test_skip_wrong_action_raises(self, bot):
        session = _setup_session(bot, 5)
        engine = session.engine
        assert engine is not None
        # Advance to VOTE
        result = engine.pending_action()
        assert result is not None
        _, ctx = result
        engine.step(ctx["eligible"][0])
        result = engine.pending_action()
        assert result is not None
        assert result[0] == Action.VOTE

        with pytest.raises(ValueError):
            engine.skip_nomination()

    def test_special_election_skip_resumes_normal_rotation(self, bot):
        session = _setup_session(bot, 7)
        engine = session.engine
        assert engine is not None
        # Simulate special election: set chosen_president to someone
        target = engine.game.player_sequence[3]
        engine.state.chosen_president = target
        engine._increment_player_counter()
        engine._advance_to_nomination()
        # Now the nominated president is the special election target
        result = engine.pending_action()
        assert result is not None
        _, ctx = result
        assert ctx["president"] == target

        # They time out
        engine.skip_nomination()

        # Should resume normal rotation (not loop back to special election target)
        result = engine.pending_action()
        assert result is not None
        _, ctx = result
        assert ctx["president"] != target


class TestTimeoutCallback:
    @pytest.mark.asyncio
    async def test_timeout_skips_and_sends_message(self, bot):
        session = _setup_session(bot, 5)
        assert session.engine is not None
        result = session.engine.pending_action()
        assert result is not None
        _, ctx = result
        first_president = ctx["president"]

        context = MagicMock()
        context.bot = bot
        context.job.data = {"cid": session.cid}
        bot.reset_mock()

        await controller._nomination_timeout_callback(context)

        # Engine advanced to next president
        result = session.engine.pending_action()
        assert result is not None
        _, ctx = result
        assert ctx["president"] != first_president
        # Skip message was sent to group
        texts = sent_texts(bot)
        assert any("did not nominate" in t for t in texts)

    @pytest.mark.asyncio
    async def test_timeout_noop_if_action_changed(self, bot):
        session = _setup_session(bot, 5)
        assert session.engine is not None
        # Advance past nomination
        result = session.engine.pending_action()
        assert result is not None
        _, ctx = result
        session.engine.step(ctx["eligible"][0])
        result = session.engine.pending_action()
        assert result is not None
        assert result[0] == Action.VOTE

        context = MagicMock()
        context.bot = bot
        context.job.data = {"cid": session.cid}
        bot.reset_mock()

        await controller._nomination_timeout_callback(context)

        # Nothing happened
        bot.send_message.assert_not_called()
