import datetime
import os
from unittest.mock import patch

import pytest

import controller
import persistence
from tests.conftest import _make_session


@pytest.fixture(autouse=True)
def clean_games():
    controller.games.clear()
    yield
    controller.games.clear()


@pytest.fixture
def pickle_path(tmp_path):
    return str(tmp_path / "games.pickle")


def test_round_trip(pickle_path):
    session = _make_session(5)
    session.start()
    persistence.save_games(pickle_path)
    assert os.path.exists(pickle_path)

    controller.games.clear()
    persistence.load_games(pickle_path)

    assert -999 in controller.games
    restored = controller.games[-999]
    assert restored.engine is not None
    assert len(restored.engine.players) == 5


def test_engine_state_preserved(pickle_path):
    session = _make_session(5)
    session.start()
    assert session.engine is not None
    action_before, _ = session.engine.pending_action()  # type: ignore[misc]
    tracks_before = (session.engine.state.liberal_track, session.engine.state.fascist_track)

    persistence.save_games(pickle_path)
    controller.games.clear()
    persistence.load_games(pickle_path)

    restored = controller.games[-999]
    assert restored.engine is not None
    action_after, _ = restored.engine.pending_action()  # type: ignore[misc]
    tracks_after = (restored.engine.state.liberal_track, restored.engine.state.fascist_track)
    assert action_before == action_after
    assert tracks_before == tracks_after


def test_empty_games_no_file(pickle_path):
    persistence.save_games(pickle_path)
    assert not os.path.exists(pickle_path)


def test_stale_file_deleted_after_load(pickle_path):
    _make_session(5)
    persistence.save_games(pickle_path)
    assert os.path.exists(pickle_path)

    controller.games.clear()
    persistence.load_games(pickle_path)
    assert not os.path.exists(pickle_path)


def test_stale_file_deleted_on_empty_save(pickle_path):
    _make_session(5)
    persistence.save_games(pickle_path)
    assert os.path.exists(pickle_path)

    controller.games.clear()
    persistence.save_games(pickle_path)
    assert not os.path.exists(pickle_path)


def test_vote_jobs_rescheduled_on_load(pickle_path, bot):
    session = _make_session(5)
    session.start()
    session.dateinitvote = datetime.datetime.now()
    session.config.toggle("vote_timeout")

    persistence.save_games(pickle_path)
    controller.games.clear()

    with patch.object(controller, "_schedule_vote_jobs") as mock_schedule:
        persistence.load_games(pickle_path)
        mock_schedule.assert_called_once()


def test_no_vote_jobs_without_timeout(pickle_path, bot):
    session = _make_session(5)
    session.start()
    session.dateinitvote = datetime.datetime.now()

    persistence.save_games(pickle_path)
    controller.games.clear()

    with patch.object(controller, "_schedule_vote_jobs") as mock_schedule:
        persistence.load_games(pickle_path)
        mock_schedule.assert_not_called()


def test_corrupt_file_no_crash(pickle_path):
    with open(pickle_path, "wb") as f:
        f.write(b"not a pickle")
    persistence.load_games(pickle_path)
    assert len(controller.games) == 0


def test_missing_file_no_crash(pickle_path):
    persistence.load_games(pickle_path)
    assert len(controller.games) == 0
