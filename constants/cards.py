from dataclasses import dataclass

from game_types import ExecutivePower as EP, Policy as P, Role as R


@dataclass(frozen=True)
class PlayerSet:
    roles: list[R]
    track: list[EP]


PLAYER_SETS: dict[int, PlayerSet] = {
    # only for testing purposes
    2: PlayerSet(
        roles=[R.LIBERAL, R.HITLER],
        track=[EP.NONE, EP.NONE, EP.POLICY, EP.KILL, EP.KILL, EP.WIN],
    ),
    # only for testing purposes
    3: PlayerSet(
        roles=[R.LIBERAL, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.NONE, EP.POLICY, EP.KILL, EP.KILL, EP.WIN],
    ),
    # only for testing purposes
    4: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.NONE, EP.POLICY, EP.KILL, EP.KILL, EP.WIN],
    ),
    5: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.NONE, EP.POLICY, EP.KILL, EP.KILL, EP.WIN],
    ),
    6: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.NONE, EP.POLICY, EP.KILL, EP.KILL, EP.WIN],
    ),
    7: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.INSPECT, EP.CHOOSE, EP.KILL, EP.KILL, EP.WIN],
    ),
    8: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.FASCIST, R.HITLER],
        track=[EP.NONE, EP.INSPECT, EP.CHOOSE, EP.KILL, EP.KILL, EP.WIN],
    ),
    9: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.FASCIST, R.FASCIST, R.HITLER],
        track=[EP.INSPECT, EP.INSPECT, EP.CHOOSE, EP.KILL, EP.KILL, EP.WIN],
    ),
    10: PlayerSet(
        roles=[R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.LIBERAL, R.FASCIST, R.FASCIST, R.FASCIST, R.HITLER],
        track=[EP.INSPECT, EP.INSPECT, EP.CHOOSE, EP.KILL, EP.KILL, EP.WIN],
    ),
}

POLICIES = [P.LIBERAL] * 6 + [P.FASCIST] * 11
