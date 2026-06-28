"""Prop → game linking + team confirmation.

After the ID resolver fills `prop_lines.mlb_id`, attach each prop to the actual
scheduled game its player is in (`prop_lines.game_pk`). The link doubles as a
TEAM CONFIRMATION: if the resolved player's team has no game on the slate date,
the prop is left unlinked (game_pk NULL) rather than trusted — a guard against a
fuzzy name match resolving to a player who isn't even playing that day.

Reuses MlbRepo.player_game_context, which already finds the game where the
player's current team is home or away on a given date.
"""
from __future__ import annotations

import sqlite3

from repositories.mlb_repo import MlbRepo


def link_prop_games(conn: sqlite3.Connection, date_iso: str) -> dict:
    """Fill game_pk for resolved-but-unlinked props on `date_iso`.

    Returns {"linked": n, "unconfirmed": m}, where `unconfirmed` counts resolved
    props whose player's team has no game that day (left NULL, not trusted)."""
    repo = MlbRepo(conn)
    rows = conn.execute(
        "SELECT id, mlb_id FROM prop_lines "
        "WHERE game_pk IS NULL AND mlb_id IS NOT NULL"
    ).fetchall()

    linked = unconfirmed = 0
    for r in rows:
        prop_id, mlb_id = r[0], r[1]
        ctx = repo.player_game_context(mlb_id, date_iso)
        if ctx and ctx.get("game_pk") is not None:
            conn.execute(
                "UPDATE prop_lines SET game_pk=? WHERE id=?", (ctx["game_pk"], prop_id))
            linked += 1
        else:
            unconfirmed += 1
    conn.commit()
    return {"linked": linked, "unconfirmed": unconfirmed}
