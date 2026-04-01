from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from config import STATS
from game_types import Role

if TYPE_CHECKING:
    from controller import GameSession

_data: dict = {}

def _defaults() -> dict:
    return {
        "libwin_policies": 0, "libwin_kill": 0,
        "fascwin_policies": 0, "fascwin_hitler": 0,
        "cancelled": 0, "groups": [],
        "player_stats": {},
    }

def load():
    global _data
    if os.path.exists(STATS):
        with open(STATS, 'r') as f:
            _data = json.load(f)
    else:
        _data = _defaults()
        save()

def save():
    with open(STATS, 'w') as f:
        json.dump(_data, f)

def get() -> dict:
    return _data


def _empty_player_entry(name: str) -> dict:
    return {
        "name": name, "games": 0, "wins": 0,
        "played_liberal": 0, "played_fascist": 0, "played_hitler": 0,
        "wins_liberal": 0, "wins_fascist": 0, "wins_hitler": 0,
        "eliminated": 0, "investigated": 0,
    }


def record_player_stats(session: GameSession):
    assert session.engine is not None
    data = _data.setdefault("player_stats", {})
    channel = data.setdefault(str(session.cid), {})
    liberals_win = session.engine.end_code.value > 0

    for uid, player in session.engine.players.items():
        entry = channel.setdefault(str(uid), _empty_player_entry(player.name))
        entry["name"] = player.name
        entry["games"] += 1

        assert player.role is not None
        role_key = player.role.value.lower()
        entry[f"played_{role_key}"] += 1

        is_liberal = player.role == Role.LIBERAL
        won = (is_liberal and liberals_win) or (not is_liberal and not liberals_win)
        if won:
            entry["wins"] += 1
            entry[f"wins_{role_key}"] += 1

        if player.is_dead:
            entry["eliminated"] += 1

        investigated_count = sum(
            1 for p in session.engine.state.inspected_players if p.uid == uid
        )
        entry["investigated"] += investigated_count


def format_stats(cid: int) -> str:
    s = _data
    lib_pol = s.get('libwin_policies', 0)
    lib_kill = s.get('libwin_kill', 0)
    fasc_pol = s.get('fascwin_policies', 0)
    fasc_hit = s.get('fascwin_hitler', 0)
    total = lib_pol + lib_kill + fasc_pol + fasc_hit

    def pct(n: int) -> str:
        return f"{n / total * 100:.0f}%" if total else "-"

    text = (
        "📊 Statistics\n"
        "─────────────────\n"
        f"Games played: {total}\n\n"
        f"🕊 Liberal wins: {lib_pol + lib_kill} ({pct(lib_pol + lib_kill)})\n"
        f"  Policies enacted: {lib_pol}\n"
        f"  Hitler killed: {lib_kill}\n\n"
        f"💀 Fascist wins: {fasc_pol + fasc_hit} ({pct(fasc_pol + fasc_hit)})\n"
        f"  Policies enacted: {fasc_pol}\n"
        f"  Hitler chancellor: {fasc_hit}"
    )
    channel = _data.get("player_stats", {}).get(str(cid), {})
    if not channel:
        text += "\n\n🏆 Leaderboard\n─────────────────\nNo games played yet."
        return text

    entries = sorted(
        channel.values(),
        key=lambda e: e["wins"] / e["games"] if e["games"] else 0,
        reverse=True,
    )

    name_w = max(len(e["name"]) for e in entries)
    text += "\n\n🏆 Leaderboard\n```\n"
    for i, e in enumerate(entries, 1):
        win_pct = f"{e['wins'] / e['games'] * 100:.0f}%" if e["games"] else " -"
        name = e["name"].ljust(name_w)
        text += f"{i}. {name}  {e['games']:>2}G  {win_pct:>3} win"
        extras = []
        if e["eliminated"]:
            extras.append(f"🗡{e['eliminated']}")
        if e["investigated"]:
            extras.append(f"🔍{e['investigated']}")
        if extras:
            text += f"  {' '.join(extras)}"
        text += "\n"
    text += f"\nRoles played (L/F/H):\n"
    role_parts = []
    for e in entries:
        role_parts.append(f"{e['name']} {e['played_liberal']}/{e['played_fascist']}/{e['played_hitler']}")
    text += "  ".join(role_parts)
    text += "\n```"

    return text
