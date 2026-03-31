from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerSet:
    roles: list[str]
    track: list[str | None]


PLAYER_SETS: dict[int, PlayerSet] = {
    # only for testing purposes
    2: PlayerSet(
        roles=[
            "Liberal",
            "Hitler"
        ],
        track=[
            None,
            None,
            "policy",
            "kill",
            "kill",
            "win"
        ]
    ),
    # only for testing purposes
    3: PlayerSet(
        roles=[
            "Liberal",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            None,
            "policy",
            "kill",
            "kill",
            "win"
        ]
    ),
    # only for testing purposes
    4: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            None,
            "policy",
            "kill",
            "kill",
            "win"
        ]
    ),
    5: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            None,
            "policy",
            "kill",
            "kill",
            "win"
        ]
    ),
    6: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            None,
            "policy",
            "kill",
            "kill",
            "win"
        ]
    ),
    7: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            "inspect",
            "choose",
            "kill",
            "kill",
            "win"
        ]
    ),
    8: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Fascist",
            "Hitler"
        ],
        track=[
            None,
            "inspect",
            "choose",
            "kill",
            "kill",
            "win"
        ]
    ),
    9: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Fascist",
            "Fascist",
            "Hitler"
        ],
        track=[
            "inspect",
            "inspect",
            "choose",
            "kill",
            "kill",
            "win"
        ]
    ),
    10: PlayerSet(
        roles=[
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Liberal",
            "Fascist",
            "Fascist",
            "Fascist",
            "Hitler"
        ],
        track=[
            "inspect",
            "inspect",
            "choose",
            "kill",
            "kill",
            "win"
        ]
    ),
}

POLICIES = [
        "liberal",
        "liberal",
        "liberal",
        "liberal",
        "liberal",
        "liberal",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist",
        "fascist"
    ]
