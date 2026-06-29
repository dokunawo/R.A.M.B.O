# rambo-backend/brains/ev/watch.py
"""Player Watch (top-11 HR board) + Moneyline Board. Each turns EV-brain data into
a ready-to-paste CMC ChatGPT image prompt. Formatting + real-data enrichment only —
no new modeling. Honest: optional fields are omitted when absent, never faked."""
from __future__ import annotations
import os
from brains.ev.engine import daily_edge
from brains.ev.moneyline_model import evaluate_game
from brains.ev.parks import hr_factor
from brains.ev.features import (TEMP_PARKS, LG_BARREL, LG_HARD_HIT,
                                build_hr_features_core, build_count_features_core)
from brains.ev.hr_model import hr_probability
from brains.ev.count_model import poisson_prob_over
from brains.ev.slip import PRODUCT
from brains.ev.k_model import k_projection

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
PLAYER_WATCH_SIZE = 11
STRIKEOUT_WATCH_SIZE = 11


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _pw_row(repo, date: str, season: int, rank: int, mlb_id: int, name: str,
            team: str, model_p: float, support: str, is_lean: bool) -> dict:
    ctx = repo.player_game_context(mlb_id, date) or {}
    game_pk = ctx.get("game_pk")
    home_abbr = ctx.get("home_abbr") or ""
    pitcher = ""
    if ctx.get("opp_pitcher_id"):
        pitcher = repo.player_name(ctx["opp_pitcher_id"]) or ""
    venue, temp, wind = "", None, ""
    if game_pk:
        g = repo.game(game_pk) or {}
        venue = g.get("venue_name") or ""
        w = repo.game_weather(game_pk) or {}
        temp = w.get("temp")
        wind = w.get("wind") or ""
    park = 1.0 if home_abbr in TEMP_PARKS else hr_factor(home_abbr)
    sc = repo.player_statcast(mlb_id, season) or {}
    return {
        "rank": rank, "name": name, "team": team, "is_lean": is_lean,
        "bats": repo.player_bats(mlb_id) or "",
        "pitcher": pitcher, "hr_pct": round(model_p * 100, 1),
        "venue": venue, "temp": temp, "env_pct": round((park - 1) * 100),
        "wind": wind, "barrel": sc.get("barrel_rate"), "hard_hit": sc.get("hard_hit"),
        "form": support,
    }


def _pw_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']} ({r['team']} · {r['bats']}"
    if r["pitcher"]:
        head += f" · vs {r['pitcher']}"
    head += ")"
    if r.get("is_lean"):
        head += " [CMC LEAN]"
    parts = [head, f"HR {r['hr_pct']}%"]
    venue = r["venue"]
    if r["temp"] is not None and r["temp"] != "":
        venue = f"{venue} {r['temp']}°F" if venue else f"{r['temp']}°F"
    if venue:
        parts.append(venue)
    env = f"env {r['env_pct']:+d}%"
    if r["wind"]:
        env += f" · {r['wind']}"
    parts.append(env)
    sub = []
    if r["barrel"] is not None:
        sub.append(f"barrel {r['barrel']}%{'↑' if r['barrel'] >= LG_BARREL else '↓'}")
    if r["hard_hit"] is not None:
        sub.append(f"hardhit {r['hard_hit']}%{'↑' if r['hard_hit'] >= LG_HARD_HIT else '↓'}")
    if sub:
        parts.append(" / ".join(sub))
    if r["form"]:
        parts.append(r["form"])
    return " — ".join(parts)


def _pw_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in (PRODUCT["hr"], f"as of {as_of}" if as_of else None,
                                   book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_pw_line(r) for r in rows) or "(no home-run board available today)"
    return banner + (
        'Create a premium sports-betting "home run watch" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "PLAYER WATCH". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} hitters. Each row shows the "
        "player (team · bat hand · vs starting pitcher), a big HR%, the ballpark and "
        "temperature, the HR environment (park factor % + wind), the power tags, and "
        "recent form. Even spacing, easy to read.\n\n"
        "KEY: % = our model's home-run probability (top of the list = highest). "
        "[CMC LEAN] marks hitters we have an actual DK Pick6 HR play on (shown first); "
        "the rest are the slate's next-best HR threats by model probability. "
        "↑ = above league average, ↓ = below. No pitch-mix or batter-vs-pitcher shown "
        "— figures are model and Statcast based.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"HITTERS:\n{body}"
    )


def player_watch(date: str, repo=None, *, count: int = PLAYER_WATCH_SIZE,
                 as_of: str | None = None, book: str | None = None) -> dict:
    """Top-`count` HR threats for the slate. Hitters we have a DK Pick6 HR play on
    (our "leans") are pinned first, ranked by HR%; the rest of the board is filled
    with the highest-probability hitters from the day's confirmed lineups."""
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        # 1) Our leans = players with a DK Pick6 HR prop, best HR% first.
        lean_by_id: dict[int, object] = {}
        for p in sorted(daily_edge(date, "hr", repo=repo, threshold=-1.0),
                        key=lambda p: p.model_p, reverse=True):
            lean_by_id.setdefault(p.mlb_id, p)

        # 2) Pool = every other hitter in a confirmed lineup, scored by HR model.
        pool = []
        for b in repo.lineup_batters(date):
            mid = b["mlb_id"]
            if mid is None or mid in lean_by_id:
                continue
            feat = build_hr_features_core(repo, date, mid, b.get("name") or "")
            if feat is None:
                continue
            pool.append((mid, feat, hr_probability(feat.hr_rate, feat.park_factor)))
        pool.sort(key=lambda t: t[2], reverse=True)

        # 3) Leans pinned first, then the pool, capped at `count`.
        rows: list[dict] = []
        for p in sorted(lean_by_id.values(), key=lambda p: p.model_p, reverse=True):
            if len(rows) >= count:
                break
            rows.append(_pw_row(repo, date, season, len(rows) + 1,
                                p.mlb_id, p.name, p.team, p.model_p, p.support, True))
        for mid, feat, mp in pool:
            if len(rows) >= count:
                break
            rows.append(_pw_row(repo, date, season, len(rows) + 1,
                                mid, (feat.name or "").upper(), feat.team_abbr,
                                mp, feat.support, False))

        return {"title": "PLAYER WATCH", "product": PRODUCT["hr"],
                "count": len(rows), "rows": rows,
                "prompt": _pw_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()


# ── Strikeout Watch (alt-K board: full P(1+..10+) ladder per probable starter) ──
def _sw_row(rank: int, proj: dict) -> dict:
    row = {
        "rank": rank, "name": (proj["name"] or "").upper(),
        "team": proj["team_abbr"], "opponent": proj["opponent_abbr"],
        "k_rate": round(proj["k_rate"], 3),
        "batters_faced": round(proj["batters_faced"], 1),
        "k_mean": round(proj["k_mean"], 1),
    }
    for j, p in proj["ladder"].items():
        row[f"p{j}"] = round(p * 100)
    return row


def _sw_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']}"
    if r["team"] or r["opponent"]:
        head += f" ({r['team']} vs {r['opponent']})"
    ladder = " · ".join(f"{j}+ {r[f'p{j}']}%" for j in range(1, 11) if f"p{j}" in r)
    return " — ".join([head, ladder,
                       f"rate {r['k_rate']} · {int(round(r['batters_faced']))} BF · proj {r['k_mean']} K"])


def _sw_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in ("Strikeout model (alt-K)",
                                   f"as of {as_of}" if as_of else None, book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_sw_line(r) for r in rows) or "(no probable starters available yet)"
    return banner + (
        'Create a premium sports-betting "strikeout watch" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "STRIKEOUT WATCH". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} starting pitchers. Each row "
        "shows the pitcher (team vs opponent), the full ladder of 1+ through 10+ "
        "strikeout probabilities, the expected K rate, batters faced, and projected K "
        "total. Even spacing.\n\n"
        "KEY: N+ % = our model's probability of at least N strikeouts (Binomial on the "
        "pitcher's K rate x batters faced, opponent-adjusted) — pick your alt-strikeout "
        "line from the arms at the top. These are probabilities, NOT guarantees.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"PITCHERS:\n{body}"
    )


def _opp_team_id(repo, game_pk: int, pitcher_team_abbr: str) -> int | None:
    """The opposing team's id for a probable starter (the side the pitcher is NOT on)."""
    g = repo.game(game_pk) or {}
    if g.get("home_team_abbr") == pitcher_team_abbr:
        return g.get("away_team_id")
    if g.get("away_team_abbr") == pitcher_team_abbr:
        return g.get("home_team_id")
    return None


def strikeout_watch(date: str, repo=None, *, count: int = STRIKEOUT_WATCH_SIZE,
                    as_of: str | None = None, book: str | None = None) -> dict:
    """Top-`count` probable starters by P(9+ K) — the alt-K board, now with the full
    P(1+..10+) ladder from the opponent-adjusted rate x batters-faced model."""
    import json as _json
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        min_starts = int(os.environ.get("RAMBO_K_MIN_STARTS", "5"))
        scored, seen = [], set()
        for s in repo.probable_starters(date):
            mid = s["mlb_id"]
            if mid in seen:
                continue
            seen.add(mid)
            rows_season = repo.player_season(mid, season, "pitching")
            try:
                gs = float((_json.loads(rows_season[0]["stats"]).get("season") or {}).get("gamesStarted") or 0)
            except Exception:
                gs = 0
            if gs < min_starts:
                continue
            starter = {
                "mlb_id": mid, "name": s.get("name") or "",
                "team_abbr": s.get("team_abbr", ""), "opponent_abbr": s.get("opponent_abbr", ""),
                "opponent_team_id": _opp_team_id(repo, s.get("game_pk"), s.get("team_abbr", "")),
            }
            proj = k_projection(repo, date, starter)
            if proj is None or proj["k_mean"] <= 0:
                continue
            scored.append(proj)
        scored.sort(key=lambda p: p["ladder"].get(9, 0.0), reverse=True)
        rows = [_sw_row(i + 1, p) for i, p in enumerate(scored[:count])]
        return {"title": "STRIKEOUT WATCH", "product": "Strikeout model (alt-K)",
                "count": len(rows), "rows": rows,
                "prompt": _sw_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()


# ── Hits & Total Bases Watch (P(1+ hit) / P(2+ TB) per hitter) ──────────────
HITS_TB_WATCH_SIZE = 11


def _ht_row(rank: int, feat, hit_mean: float, tb_mean: float) -> dict:
    return {
        "rank": rank, "name": (feat.name or "").upper(), "team": feat.team_abbr,
        "opponent": feat.opponent_abbr,
        "p_hit": round(poisson_prob_over(hit_mean, 1) * 100),    # P(1+ hit)
        "p_tb2": round(poisson_prob_over(tb_mean, 2) * 100),     # P(2+ total bases)
        "hit_mean": round(hit_mean, 2), "tb_mean": round(tb_mean, 2),
        "form": feat.support,
    }


def _ht_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']}"
    if r["team"] or r["opponent"]:
        head += f" ({r['team']} vs {r['opponent']})"
    return " — ".join([head, f"1+ hit {r['p_hit']}% · 2+ TB {r['p_tb2']}%",
                       f"proj {r['hit_mean']} H / {r['tb_mean']} TB", r["form"]])


def _ht_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in ("Hits/TB model",
                                   f"as of {as_of}" if as_of else None, book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_ht_line(r) for r in rows) or "(no lineups available yet)"
    return banner + (
        'Create a premium sports-betting "hits & total bases" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "HITS & TOTAL BASES". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} hitters. Each row shows the "
        "hitter (team vs opponent), the probability of 1+ hit and of 2+ total bases, "
        "the projected hits and total bases, and recent form. Even spacing.\n\n"
        "KEY: 1+ hit % and 2+ TB % = our model's probabilities (Poisson on the "
        "hitter's per-game rate, vs-hand split where known, blended with last-15). "
        "Use 1+ hit as your floor legs and 2+ total bases as the power legs. These "
        "are probabilities, NOT guarantees. Figures are model-based.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"HITTERS:\n{body}"
    )


def hits_tb_watch(date: str, repo=None, *, count: int = HITS_TB_WATCH_SIZE,
                  as_of: str | None = None, book: str | None = None) -> dict:
    """Top-`count` hitters by P(2+ total bases), each also showing P(1+ hit) — the
    board for hits / total-bases parlays. Poisson on per-game hit and total-base
    rates (vs-hand split + last-15) over the day's confirmed lineups."""
    repo, conn = _open(repo)
    try:
        scored, seen = [], set()
        for b in repo.lineup_batters(date):
            mid = b["mlb_id"]
            if mid is None or mid in seen:
                continue
            seen.add(mid)
            feat_h = build_count_features_core(
                repo, date, mid, b.get("name") or "", stat_keys=["hits"],
                label="H", group="hitting", games_key="gamesPlayed", use_splits=True)
            if feat_h is None or feat_h.per_game_mean <= 0:
                continue
            feat_tb = build_count_features_core(
                repo, date, mid, b.get("name") or "", stat_keys=["totalBases"],
                label="TB", group="hitting", games_key="gamesPlayed", use_splits=True)
            tb_mean = feat_tb.per_game_mean if feat_tb else 0.0
            feat_h.team_abbr = feat_h.team_abbr or b.get("team_abbr", "")
            scored.append((feat_h, feat_h.per_game_mean, tb_mean))
        scored.sort(key=lambda t: poisson_prob_over(t[2], 2), reverse=True)
        rows = [_ht_row(i + 1, f, h, tb) for i, (f, h, tb) in enumerate(scored[:count])]
        return {"title": "HITS & TOTAL BASES", "product": "Hits/TB model",
                "count": len(rows), "rows": rows,
                "prompt": _ht_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()


def _mb_row(rank: int, ev: dict) -> dict:
    diff_pct = round(ev["diff"] * 100, 1)
    if diff_pct == 0.0:
        lean_side, lean_pct = None, 0.0
    elif diff_pct > 0:
        lean_side, lean_pct = ev["home_abbr"], diff_pct
    else:
        lean_side, lean_pct = ev["away_abbr"], -diff_pct
    return {
        "rank": rank, "away": ev["away_abbr"], "away_price": ev["away_price"],
        "home": ev["home_abbr"], "home_price": ev["home_price"],
        "model_home_pct": round(ev["model_home"] * 100),
        "model_away_pct": round(ev["model_away"] * 100),
        "lean_side": lean_side, "lean_pct": lean_pct,
    }


def _mb_line(r: dict) -> str:
    head = (f"{r['rank']}. {r['away']} ({r['away_price']:+d}) @ "
            f"{r['home']} ({r['home_price']:+d}) — model: "
            f"{r['home']} {r['model_home_pct']}% / {r['away']} {r['model_away_pct']}%")
    if r["lean_side"]:
        head += f" — CMC lean: {r['lean_side']} +{r['lean_pct']}%"
    else:
        head += " — no lean"
    return head


def _mb_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in (PRODUCT["ml"], f"as of {as_of}" if as_of else None,
                                   book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    body = "\n".join(_mb_line(r) for r in rows) or "(no games on the board today)"
    return banner + (
        'Create a premium sports-betting "moneyline board" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "MONEYLINE BOARD". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} games in start-time order. Each "
        "row shows the matchup (away @ home with book odds), our model win % for each "
        "side, and our suggested lean (or 'no lean'). Even spacing, easy to read.\n\n"
        "KEY: odds are the book's American moneyline. Our leans are small, bounded "
        "disagreements with the de-vigged book — they are reads, NOT guarantees. "
        "Build your own card from any side.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any team, number, %, or odds.\n\n"
        f"GAMES:\n{body}"
    )


def moneyline_board(date: str, repo=None, *, as_of: str | None = None,
                    book: str | None = None) -> dict:
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        rows = []
        for g in repo.moneyline_slate(date):
            ev = evaluate_game(repo, season, g)
            if ev is None:
                continue
            rows.append(_mb_row(len(rows) + 1, ev))
        return {"title": "MONEYLINE BOARD", "product": PRODUCT["ml"],
                "count": len(rows), "rows": rows,
                "prompt": _mb_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
