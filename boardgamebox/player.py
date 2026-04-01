from game_types import Party, Role


class Player:
    def __init__(self, name: str, uid: int):
        self.name = name
        self.uid = uid
        self.role: Role | None = None
        self.party: Party | None = None
        self.is_dead = False