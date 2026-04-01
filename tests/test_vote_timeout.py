"""Tests for the vote timeout feature."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import controller
from controller import finish_voting, _vote_reminder_callback, _vote_timeout_callback
from conftest import _setup_session


def _enable_timeout(session):
    session.config.toggle("vote_timeout")


def _step_to_vote(session):
    assert session.engine is not None
    _, ctx = session.engine.pending_action()
    chancellor = ctx["eligible"][0]
    session.engine.step(chancellor)
    return ctx["president"], chancellor


def _prepare_voting(session):
    """Step to VOTE and set up dateinitvote like present_action would."""
    pres, chan = _step_to_vote(session)
    session.pending_votes = {}
    session.dateinitvote = datetime.datetime.now()
    return pres, chan


@pytest.mark.asyncio
async def test_blanks_not_counted_as_ja(bot):
    """1 Ja + 1 Nein + 3 blank (5p) -> fails (1 not > 1)."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: False,
        players[2].uid: None,
        players[3].uid: None,
        players[4].uid: None,
    }
    failed_before = session.engine.state.failed_votes
    await finish_voting(bot, session)
    # 1 Ja, 1 Nein -> 1 not > 1 -> fails
    assert session.engine.state.failed_votes == failed_before + 1


@pytest.mark.asyncio
async def test_blanks_not_counted_as_nein(bot):
    """3 Ja + 0 Nein + 2 blank (5p) -> passes (3 > 1.5)."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: True,
        players[2].uid: True,
        players[3].uid: None,
        players[4].uid: None,
    }
    failed_before = session.engine.state.failed_votes
    await finish_voting(bot, session)
    assert session.engine.state.failed_votes == failed_before


@pytest.mark.asyncio
async def test_min_threshold_not_met(bot):
    """2 Ja + 0 Nein + 3 blank -> auto-fail (only 2 real votes < 3)."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: True,
        players[2].uid: None,
        players[3].uid: None,
        players[4].uid: None,
    }
    failed_before = session.engine.state.failed_votes
    await finish_voting(bot, session)
    assert session.engine.state.failed_votes == failed_before + 1
    texts = [str(c) for c in bot.send_message.call_args_list]
    assert any("auto-fails" in t for t in texts)


@pytest.mark.asyncio
async def test_min_threshold_met(bot):
    """3 Ja + 0 Nein + 2 blank -> passes (3 real votes >= 3, and 3 > 1.5)."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: True,
        players[2].uid: True,
        players[3].uid: None,
        players[4].uid: None,
    }
    failed_before = session.engine.state.failed_votes
    await finish_voting(bot, session)
    assert session.engine.state.failed_votes == failed_before


@pytest.mark.asyncio
async def test_timeout_fills_blanks(bot):
    """Timeout callback sets None for missing voters then calls finish_voting."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: False,
    }
    captured_votes = {}

    original_finish = finish_voting
    async def capture_finish(b, s):
        captured_votes.update(s.pending_votes)
        await original_finish(b, s)

    context = MagicMock()
    context.bot = bot
    context.job.data = {"cid": session.cid}
    with patch("controller.finish_voting", side_effect=capture_finish):
        await _vote_timeout_callback(context)
    assert captured_votes[players[2].uid] is None
    assert captured_votes[players[3].uid] is None
    assert captured_votes[players[4].uid] is None


@pytest.mark.asyncio
async def test_feature_disabled_no_jobs(bot):
    """No jobs scheduled when vote_timeout is disabled."""
    session = _setup_session(bot, 5)
    mock_jq = MagicMock()
    with patch.object(controller, "_job_queue", mock_jq):
        _step_to_vote(session)
        await controller.present_action(bot, session)
    mock_jq.run_once.assert_not_called()


@pytest.mark.asyncio
async def test_feature_enabled_schedules_jobs(bot):
    """Jobs are scheduled when vote_timeout is enabled."""
    session = _setup_session(bot, 5)
    _enable_timeout(session)
    mock_jq = MagicMock()
    mock_jq.get_jobs_by_name.return_value = []
    with patch.object(controller, "_job_queue", mock_jq):
        _step_to_vote(session)
        await controller.present_action(bot, session)
    assert mock_jq.run_once.call_count == 2
    assert session.vote_timeout_job_name is not None
    assert session.vote_reminder_job_name is not None


@pytest.mark.asyncio
async def test_early_completion_cancels_jobs(bot):
    """All players voting before timeout cancels scheduled jobs."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    mock_job = MagicMock()
    mock_jq = MagicMock()
    mock_jq.get_jobs_by_name.return_value = [mock_job]
    with patch.object(controller, "_job_queue", mock_jq):
        _prepare_voting(session)
        session.vote_timeout_job_name = f"vote_timeout_{session.cid}"
        session.vote_reminder_job_name = f"vote_reminder_{session.cid}"
        players = list(session.engine.alive_players)
        for p in players:
            session.pending_votes[p.uid] = True
        controller._cancel_vote_jobs(session)
        await finish_voting(bot, session)
    mock_job.schedule_removal.assert_called()


@pytest.mark.asyncio
async def test_reminder_sends_to_missing_only(bot):
    """Reminder callback only messages players who haven't voted."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {
        players[0].uid: True,
        players[1].uid: False,
    }
    context = MagicMock()
    context.bot = AsyncMock()
    context.job.data = {"cid": session.cid}
    await _vote_reminder_callback(context)
    # 1 group message + 3 DMs to missing players
    assert context.bot.send_message.call_count == 4
    dm_uids = {c.args[0] for c in context.bot.send_message.call_args_list if c.args[0] != session.cid}
    expected_missing = {players[2].uid, players[3].uid, players[4].uid}
    assert dm_uids == expected_missing


@pytest.mark.asyncio
async def test_all_blank_auto_fails(bot):
    """All players blank -> 0 real votes < MIN_REAL_VOTES -> auto-fail."""
    session = _setup_session(bot, 5)
    assert session.engine is not None
    _enable_timeout(session)
    _prepare_voting(session)
    players = list(session.engine.alive_players)
    session.pending_votes = {p.uid: None for p in players}
    failed_before = session.engine.state.failed_votes
    await finish_voting(bot, session)
    assert session.engine.state.failed_votes == failed_before + 1
