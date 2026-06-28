"""Tests for prop→game linking + team confirmation, and the Pick6 MLB-only filter."""
from db.migrate import get_connection, apply_migrations
from ingestion.link import link_prop_games
from ingestion.normalize import map_props, _is_mlb_prop


_NOW = "2026-06-26T00:00:00Z"
_DATE = "2026-06-26"


def _seed_schedule_and_players(conn):
    # One game: NYY (147) home vs BOS (111) away.
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_probable_pitcher_id, "
        "away_probable_pitcher_id, scraped_at) "
        "VALUES (999,?,147,111,'NYY','BOS',111,222,?)", (_DATE, _NOW))
    # Judge plays for NYY (in the game); Nomatch plays for a team not on the slate.
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (592450,'Aaron Judge',147,?)", (_NOW,))
    conn.execute("INSERT INTO players (mlb_id, full_name, current_team_id, updated_at) "
                 "VALUES (777,'Off Today',135,?)", (_NOW,))


def _insert_prop(conn, mlb_id, name):
    conn.execute(
        "INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
        "player_name_raw, captured_at) VALUES (NULL,?,'dk_pick6','HR',0.5,2.5,?,?)",
        (mlb_id, name, "2026-06-26T18:00Z"))


# ── prop → game linking + team confirmation ───────────────────────────────────
def test_links_resolved_prop_to_its_game(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed_schedule_and_players(conn)
    _insert_prop(conn, 592450, "Aaron Judge")

    out = link_prop_games(conn, _DATE)
    assert out == {"linked": 1, "unconfirmed": 0}
    game_pk = conn.execute(
        "SELECT game_pk FROM prop_lines WHERE mlb_id=592450").fetchone()[0]
    assert game_pk == 999


def test_team_not_playing_stays_unconfirmed(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed_schedule_and_players(conn)
    _insert_prop(conn, 777, "Off Today")        # team 135 has no game today

    out = link_prop_games(conn, _DATE)
    assert out == {"linked": 0, "unconfirmed": 1}
    game_pk = conn.execute(
        "SELECT game_pk FROM prop_lines WHERE mlb_id=777").fetchone()[0]
    assert game_pk is None                       # left unlinked, not mis-attributed


def test_skips_already_linked_and_unresolved(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    _seed_schedule_and_players(conn)
    # already linked (game_pk set) — must be left alone
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (999,592450,'dk_pick6','SB',0.5,3.0,"
                 "'Aaron Judge','2026-06-26T18:00Z')")
    # unresolved (mlb_id NULL) — not eligible for linking
    conn.execute("INSERT INTO prop_lines (game_pk, mlb_id, book, market, line, multiplier, "
                 "player_name_raw, captured_at) VALUES (NULL,NULL,'dk_pick6','HR',0.5,2.0,"
                 "'Mystery Man','2026-06-26T18:00Z')")
    out = link_prop_games(conn, _DATE)
    assert out == {"linked": 0, "unconfirmed": 0}


# ── Pick6 MLB-only filter ─────────────────────────────────────────────────────
def test_is_mlb_prop_accepts_variants():
    assert _is_mlb_prop({"league": "MLB"})
    assert _is_mlb_prop({"league": "mlb"})
    assert _is_mlb_prop({"league": "Major League Baseball"})
    assert _is_mlb_prop({"sport": "Baseball"})


def test_is_mlb_prop_rejects_other_sports_and_missing():
    assert not _is_mlb_prop({"league": "NBA"})
    assert not _is_mlb_prop({"league": ""})
    assert not _is_mlb_prop({})


def test_map_props_skips_non_mlb_without_inserting(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    handled = map_props(conn, {"league": "NBA", "stat_abbr": "PTS",
                               "line": 24.5, "player_name": "A Guard"}, _NOW)
    assert handled is True                         # handled (skipped), won't reprocess
    assert conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0] == 0


def test_map_props_inserts_mlb(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    ok = map_props(conn, {"league": "MLB", "stat_abbr": "HR", "line": 0.5,
                          "player_name": "Aaron Judge", "over_multiplier": 2.5}, _NOW)
    assert ok is True
    row = conn.execute("SELECT market, player_name_raw, game_pk, mlb_id "
                       "FROM prop_lines").fetchone()
    assert row[0] == "HR" and row[1] == "Aaron Judge"
    assert row[2] is None and row[3] is None       # linked/resolved downstream
