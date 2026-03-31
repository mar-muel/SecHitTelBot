class Player:
    def __init__(self, name: str, uid: int):
        self.name = name
        self.uid = uid
        self.role: str | None = None
        self.party: str | None = None
        self.is_dead = False