import sys
import os
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import GamesController
import MainController
from Boardgamebox.Board import Board
from Boardgamebox.Game import Game
from Boardgamebox.Player import Player

MainController.sleep = lambda x: None

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


@pytest.fixture
def bot():
    return MagicMock()


def _make_game(num_players):
    GamesController.init()
    game = Game(-999, 1)
    for i in range(num_players):
        uid = 100 + i
        game.add_player(uid, Player(NAMES[i], uid))
    GamesController.games[-999] = game
    return game


def _setup_game(bot, num_players):
    game = _make_game(num_players)
    MainController.inform_players(bot, game, game.cid, num_players)
    MainController.inform_fascists(bot, game, num_players)
    game.board = Board(num_players, game)
    game.shuffle_player_sequence()
    game.board.state.player_counter = 0
    bot.reset_mock()
    return game


@pytest.fixture(params=[5, 7, 9, 10])
def game_any(request, bot):
    return _setup_game(bot, request.param)


@pytest.fixture
def game5(bot):
    return _setup_game(bot, 5)


@pytest.fixture
def game7(bot):
    return _setup_game(bot, 7)


@pytest.fixture
def game9(bot):
    return _setup_game(bot, 9)


@pytest.fixture
def game10(bot):
    return _setup_game(bot, 10)


def sent_texts(bot):
    return [str(c) for c in bot.send_message.call_args_list]
