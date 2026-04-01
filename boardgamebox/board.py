import random
from typing import assert_never

from constants.cards import PLAYER_SETS, POLICIES
from boardgamebox.state import State
from game_types import ExecutivePower

class Board:
    def __init__(self, playercount, game):
        self.state = State()
        self.num_players = playercount
        self.fascist_track_actions = PLAYER_SETS[self.num_players].track
        self.policies = random.sample(POLICIES, len(POLICIES))
        self.game = game
        self.discards = []

    def print_board(self):
        board = "--- Liberal acts ---\n"
        for i in range(5):
            if i < self.state.liberal_track:
                board += u"\u2716\uFE0F" + " " #X
            elif i >= self.state.liberal_track and i == 4:
                board += u"\U0001F54A" + " " #dove
            else:
                board += u"\u25FB\uFE0F" + " " #empty
        board += "\n--- Fascist acts ---\n"
        for i in range(6):
            if i < self.state.fascist_track:
                board += u"\u2716\uFE0F" + " " #X
            else:
                match self.fascist_track_actions[i]:
                    case ExecutivePower.NONE:
                        board += u"\u25FB\uFE0F" + " "  # empty
                    case ExecutivePower.POLICY:
                        board += u"\U0001F52E" + " " # crystal
                    case ExecutivePower.INSPECT:
                        board += u"\U0001F50E" + " " # inspection glass
                    case ExecutivePower.KILL:
                        board += u"\U0001F5E1" + " " # knife
                    case ExecutivePower.WIN:
                        board += u"\u2620" + " " # skull
                    case ExecutivePower.CHOOSE:
                        board += u"\U0001F454" + " " # tie
                    case _ as unreachable:
                        assert_never(unreachable)

        board += "\n--- Election counter ---\n"
        for i in range(3):
            if i < self.state.failed_votes:
                board += u"\u2716\uFE0F" + " " #X
            else:
                board += u"\u25FB\uFE0F" + " " #empty

        board += "\n--- Presidential order  ---\n"
        for player in self.game.player_sequence:
            board += player.name + " " + u"\u27A1\uFE0F" + " "
        board = board[:-3]
        board += u"\U0001F501"
        board += "\n\nThere are " + str(len(self.policies)) + " policies left on the pile."
        if self.state.fascist_track >= 3:
            board += "\n\n" + u"\u203C\uFE0F" + " Beware: If Hitler gets elected as Chancellor the fascists win the game! " + u"\u203C\uFE0F"
        if len(self.state.not_hitlers) > 0:
            board += "\n\nWe know that the following players are not Hitler because they got elected as Chancellor after 3 fascist policies:\n"
            for nh in self.state.not_hitlers:
                board += nh.name + ", "
            board = board[:-2]
        return board
