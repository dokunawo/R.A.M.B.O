# rambo-backend/brains/ev/watch.py
"""Player Watch (top-11 HR board) + Moneyline Board. Each turns EV-brain data into
a ready-to-paste CMC ChatGPT image prompt. Formatting + real-data enrichment only —
no new modeling. Honest: optional fields are omitted when absent, never faked."""
from __future__ import annotations
import os
from brains.ev.engine import daily_edge
from brains.ev.moneyline_model import evaluate_game
from brains.ev.parks import hr_factor
from brains.ev.features import TEMP_PARKS, LG_BARREL, LG_HARD_HIT
from brains.ev.slip import PRODUCT

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
PLAYER_WATCH_SIZE = 11


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _pw_row(repo, date: str, season: int, rank: int, pick) -> dict:
    ctx = repo.player_game_context(pick.mlb_id, date) or {}
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
    sc = repo.player_statcast(pick.mlb_id, season) or {}
    return {
        "rank": rank, "name": pick.name, "team": pick.team,
        "bats": repo.player_bats(pick.mlb_id) or "",
        "pitcher": pitcher, "hr_pct": round(pick.model_p * 100, 1),
        "venue": venue, "temp": temp, "env_pct": round((park - 1) * 100),
        "wind": wind, "barrel": sc.get("barrel_rate"), "hard_hit": sc.get("hard_hit"),
        "form": pick.support,
    }


def _pw_line(r: dict) -> str:
    head = f"{r['rank']}. {r['name']} ({r['team']} · {r['bats']}"
    if r["pitcher"]:
        head += f" · vs {r['pitcher']}"
    head += ")"
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
        "KEY: % = our model's home-run probability. ↑ = above league average, "
        "↓ = below. No pitch-mix or batter-vs-pitcher shown — figures are model and "
        "Statcast based.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or stat.\n\n"
        f"HITTERS:\n{body}"
    )


def player_watch(date: str, repo=None, *, count: int = PLAYER_WATCH_SIZE,
                 as_of: str | None = None, book: str | None = None) -> dict:
    repo, conn = _open(repo)
    try:
        season = int(date[:4])
        picks = daily_edge(date, "hr", repo=repo, threshold=-1.0)
        picks = sorted(picks, key=lambda p: p.model_p, reverse=True)
        seen: set[int] = set()
        top = []
        for p in picks:
            if p.mlb_id in seen:
                continue
            seen.add(p.mlb_id)
            top.append(p)
            if len(top) >= count:
                break
        rows = [_pw_row(repo, date, season, i + 1, p) for i, p in enumerate(top)]
        return {"title": "PLAYER WATCH", "product": PRODUCT["hr"],
                "count": len(rows), "rows": rows,
                "prompt": _pw_prompt(rows, as_of, book)}
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
