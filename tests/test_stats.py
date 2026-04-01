import stats
from game_types import EndCode, Role
from tests.conftest import _make_session


def _finished_session(end_code):
    session = _make_session(5)
    session.start()
    assert session.engine is not None
    session.engine.end_code = end_code
    return session


class TestRecordPlayerStats:
    def test_liberal_win(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        for uid, p in session.engine.players.items():
            entry = channel[str(uid)]
            assert entry["games"] == 1
            assert entry["wins"] == (1 if p.role == Role.LIBERAL else 0)

    def test_fascist_win(self):
        session = _finished_session(EndCode.FASCIST_POLICIES)
        assert session.engine is not None
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        for uid, p in session.engine.players.items():
            entry = channel[str(uid)]
            is_fasc = p.role in (Role.FASCIST, Role.HITLER)
            assert entry["wins"] == (1 if is_fasc else 0)

    def test_role_played(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        for uid, p in session.engine.players.items():
            entry = channel[str(uid)]
            assert p.role is not None
            assert entry[f"played_{p.role.value.lower()}"] == 1

    def test_eliminated(self):
        session = _finished_session(EndCode.LIBERAL_KILLED_HITLER)
        assert session.engine is not None
        hitler = next(p for p in session.engine.players.values() if p.role == Role.HITLER)
        hitler.is_dead = True
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        assert channel[str(hitler.uid)]["eliminated"] == 1
        for uid in session.engine.players:
            if uid != hitler.uid:
                assert channel[str(uid)]["eliminated"] == 0

    def test_investigated(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        target = list(session.engine.players.values())[0]
        session.engine.state.inspected_players.append(target)
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        assert channel[str(target.uid)]["investigated"] == 1

    def test_investigated_multiple_times(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        target = list(session.engine.players.values())[0]
        session.engine.state.inspected_players.append(target)
        session.engine.state.inspected_players.append(target)
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        assert channel[str(target.uid)]["investigated"] == 2

    def test_cumulative(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        stats.record_player_stats(session)
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        for uid in session.engine.players:
            assert channel[str(uid)]["games"] == 2

    def test_name_updated(self):
        session = _finished_session(EndCode.LIBERAL_POLICIES)
        assert session.engine is not None
        uid = next(iter(session.engine.players))
        session.engine.players[uid].name = "OldName"
        stats.record_player_stats(session)
        session.engine.players[uid].name = "NewName"
        stats.record_player_stats(session)
        channel = stats.get()["player_stats"][str(session.cid)]

        assert channel[str(uid)]["name"] == "NewName"


class TestFormatPlayerStats:
    def test_empty(self):
        assert "No games played yet" in stats.format_stats(-12345)

    def test_sorted_by_win_rate(self):
        stats.get()["player_stats"] = {"-777": {
            "1": {**stats._empty_player_entry("Loser"), "games": 4, "wins": 0},
            "2": {**stats._empty_player_entry("Winner"), "games": 4, "wins": 4},
        }}
        text = stats.format_stats(-777)
        assert text.index("Winner") < text.index("Loser")
