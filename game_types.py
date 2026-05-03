from dataclasses import dataclass
from enum import Enum, StrEnum, auto


class Policy(StrEnum):
    """A policy card: liberal or fascist."""
    LIBERAL = auto()
    FASCIST = auto()


class Role(StrEnum):
    """Secret role assigned to each player."""
    LIBERAL = "Liberal"
    FASCIST = "Fascist"
    HITLER = "Hitler"


class Party(StrEnum):
    """Party membership shown during loyalty investigations."""
    LIBERAL = auto()
    FASCIST = auto()


class ExecutivePower(StrEnum):
    """Power triggered when a fascist policy is enacted on a board slot."""
    NONE = auto()
    POLICY = auto()
    INSPECT = auto()
    KILL = auto()
    CHOOSE = auto()
    WIN = auto()


class EndCode(Enum):
    """How a game ended (or that it's still running)."""
    FASCIST_HITLER_CHANCELLOR = -2
    FASCIST_POLICIES = -1
    RUNNING = 0
    LIBERAL_POLICIES = 1
    LIBERAL_KILLED_HITLER = 2


class Action(Enum):
    """What decision the game is currently waiting on."""
    NOMINATE_CHANCELLOR = auto()
    VOTE = auto()
    PRESIDENT_DISCARD = auto()
    CHANCELLOR_ENACT = auto()
    VETO_CHOICE = auto()
    EXECUTIVE_KILL = auto()
    EXECUTIVE_INSPECT = auto()
    EXECUTIVE_SPECIAL_ELECTION = auto()


@dataclass
class EngineMessage:
    """A message queued by the engine for the UI layer to deliver."""
    text: str
    uid: int | None = None


class GameOver(Exception):
    """Raised when stepping an already-finished game."""
    pass
