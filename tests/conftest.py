import sys
import os
import json
from unittest.mock import AsyncMock, mock_open, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import GamesController
from MainController import GameSession
from Boardgamebox.Player import Player

FAKE_STATS = json.dumps({
    "libwin_policies": 0, "libwin_kill": 0,
    "fascwin_policies": 0, "fascwin_hitler": 0,
    "cancelled": 0, "groups": []
})

NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank", "Ivy", "Jack"]


@pytest.fixture(autouse=True)
def mock_stats():
    with patch("builtins.open", mock_open(read_data=FAKE_STATS)):
        yield


@pytest.fixture(autouse=True)
def mock_sleep():
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


@pytest.fixture
def bot():
    return AsyncMock()


def _make_session(num_players, seed=None):
    """Create a GameSession in lobby phase with players added."""
    GamesController.games.clear()
    cid = -999
    session = GameSession(cid, 100)
    for i in range(num_players):
        uid = 100 + i
        session.add_player(uid, Player(NAMES[i], uid))
    GamesController.games[cid] = session
    return session


def _setup_session(bot, num_players):
    """Create a fully started GameSession with engine running."""
    session = _make_session(num_players)
    session.start()
    bot.reset_mock()
    return session


@pytest.fixture(params=[5, 7, 9, 10])
def session_any(request, bot):
    return _setup_session(bot, request.param)


@pytest.fixture
def session5(bot):
    return _setup_session(bot, 5)


@pytest.fixture
def session7(bot):
    return _setup_session(bot, 7)


@pytest.fixture
def session9(bot):
    return _setup_session(bot, 9)


@pytest.fixture
def session10(bot):
    return _setup_session(bot, 10)


def sent_texts(bot):
    """Extract all send_message call args as strings for assertion."""
    return [str(c) for c in bot.send_message.call_args_list]
