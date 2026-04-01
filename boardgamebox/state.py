from boardgamebox.player import Player
from game_types import Policy


class State:
    def __init__(self):
        self.liberal_track = 0
        self.fascist_track = 0
        self.failed_votes = 0
        self.president: Player | None = None
        self.nominated_president: Player | None = None
        self.nominated_chancellor: Player | None = None
        self.chosen_president: Player | None = None
        self.chancellor: Player | None = None
        self.drawn_policies: list[Policy] = []
        self.player_counter = 0
        self.veto_refused = False
        self.not_hitlers: list[Player] = []