from random import shuffle

from boardgamebox.board import Board
from boardgamebox.player import Player


class Game:
    def __init__(self, cid: int, initiator: int):
        self.playerlist: dict[int, Player] = {}
        self.player_sequence: list[Player] = []
        self.cid = cid
        self.initiator = initiator
        self.board: Board | None = None

    def add_player(self, uid, player):
        self.playerlist[uid] = player

    def get_hitler(self):
        for uid in self.playerlist:
            if self.playerlist[uid].role == "Hitler":
                return self.playerlist[uid]

    def get_fascists(self):
        fascists = []
        for uid in self.playerlist:
            if self.playerlist[uid].role == "Fascist":
                fascists.append(self.playerlist[uid])
        return fascists

    def shuffle_player_sequence(self):
        for uid in self.playerlist:
            self.player_sequence.append(self.playerlist[uid])
        shuffle(self.player_sequence)
