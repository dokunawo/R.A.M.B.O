# Alt-Strikeout Parlay Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a true-EV alt-strikeout board + parlay assembler that joins RAMBO's existing strikeout model P(8+/9+/10+ K) ladder to real FanDuel and best-of-book `pitcher_strikeouts_alternate` odds.

**Architecture:** Add `pitcher_strikeouts_alternate` to The Odds API prop pull as a new `SO_ALT` market (lands in existing `prop_lines` via the existing normalizer). A new pure-Python brain `brains/ev/alt_k.py` joins `k_model` probabilities to those odds rows per (pitcher, threshold), computes per-leg EV, and assembles parlays (auto-suggest + manual). Two FastAPI endpoints expose it.

**Tech Stack:** Python 3, FastAPI, SQLite (`MlbRepo`), pytest. No new dependencies. Reuse `brains/ev/k_model.py`, `brains/ev/line_shop.american_to_decimal`, `brains/ev/watch.py` patterns.

## Global Constraints

- Data-only — no bet placement (Sentinel boundary). Boards/endpoints return model + odds data only.
- Reuse `k_model` verbatim — no new strikeout modeling.
- New taxonomy market is exactly `SO_ALT` (distinct from `SO`).
- Honest framing: model probabilities vs. real book prices; never fake an EV or odds field — omit/null when absent.
- Board functions follow `watch.py` shape: `_open(repo)` helper, return dict with `title`, `product`, `count`, `rows`, `prompt`.
- Decimal payout conversions use `brains.ev.line_shop.american_to_decimal`.
- Commit messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Use Bash heredoc (never PowerShell) for commit messages.
- Run pytest from `rambo-backend/` (cwd). Tests live in `rambo-backend/tests/`.

---

### Task 1: Register the `SO_ALT` market in The Odds API config

**Files:**
- Modify: `rambo-backend/config/the_odds_api.py:19-27`
- Test: `rambo-backend/tests/test_alt_k_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `prop_markets()` includes `"pitcher_strikeouts_alternate"`; `PROP_MARKET_MAP["pitcher_strikeouts_alternate"] == "SO_ALT"`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_alt_k_config.py
from config import the_odds_api as cfg


def test_alt_strikeout_market_is_pulled_and_mapped():
    assert "pitcher_strikeouts_alternate" in cfg.prop_markets()
    assert cfg.PROP_MARKET_MAP["pitcher_strikeouts_alternate"] == "SO_ALT"


def test_standard_strikeout_still_maps_to_so():
    assert cfg.PROP_MARKET_MAP["pitcher_strikeouts"] == "SO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k_config.py -v`
Expected: FAIL — `pitcher_strikeouts_alternate` not in defaults / KeyError on PROP_MARKET_MAP.

- [ ] **Step 3: Write minimal implementation**

In `config/the_odds_api.py`, add the alternate market to the default set and the map:

```python
_DEFAULT_PROP_MARKETS = ("batter_home_runs,pitcher_strikeouts,"
                         "pitcher_strikeouts_alternate,"
                         "batter_total_bases,batter_hits")

# The Odds API market key -> our EV/Pick6 taxonomy. Only mapped markets are kept.
PROP_MARKET_MAP = {
    "batter_home_runs": "HR",
    "pitcher_strikeouts": "SO",
    "pitcher_strikeouts_alternate": "SO_ALT",
    "batter_total_bases": "TB",
    "batter_hits": "H",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k_config.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/config/the_odds_api.py rambo-backend/tests/test_alt_k_config.py
git commit -m "$(cat <<'EOF'
feat(betting): pull pitcher_strikeouts_alternate as SO_ALT market

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Normalizer lands alt-K lines as multiple `SO_ALT` rows

**Files:**
- Test: `rambo-backend/tests/test_alt_k_normalize.py`
- Modify (only if test fails): `rambo-backend/ingestion/normalize.py:429-472` (`map_props_book`)

**Interfaces:**
- Consumes: `PROP_MARKET_MAP` from Task 1.
- Produces: confirmation that a `pitcher_strikeouts_alternate` event with multiple lines writes one `prop_lines` row per line with `market='SO_ALT'` and real `over_price`/`under_price`.

This task is verification-first: `map_props_book` already groups by `(player, line)` and maps via `PROP_MARKET_MAP`, so it should already work once Task 1 maps the key. The test proves it; only modify the normalizer if the test reveals a gap.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_alt_k_normalize.py
import sqlite3
from db.migrate import apply_migrations
from ingestion.normalize import map_props_book


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_migrations(c)
    return c


def _event():
    return {
        "home_team": "Seattle Mariners", "away_team": "Houston Astros",
        "commence_time": "2026-06-30T02:10:00Z", "_captured_at": "2026-06-29T18:00:00Z",
        "bookmakers": [{
            "title": "FanDuel", "key": "fanduel",
            "markets": [{
                "key": "pitcher_strikeouts_alternate", "last_update": "2026-06-29T18:00:00Z",
                "outcomes": [
                    {"description": "Logan Gilbert", "name": "Over", "point": 7.5, "price": 120},
                    {"description": "Logan Gilbert", "name": "Under", "point": 7.5, "price": -150},
                    {"description": "Logan Gilbert", "name": "Over", "point": 8.5, "price": 175},
                    {"description": "Logan Gilbert", "name": "Under", "point": 8.5, "price": -220},
                ],
            }],
        }],
    }


def test_alt_strikeout_event_lands_one_row_per_line():
    conn = _conn()
    assert map_props_book(conn, _event(), "2026-06-29T18:00:00Z") is True
    rows = conn.execute(
        "SELECT line, over_price, under_price, book, player_name_raw "
        "FROM prop_lines WHERE market='SO_ALT' ORDER BY line").fetchall()
    assert len(rows) == 2
    assert [r["line"] for r in rows] == [7.5, 8.5]
    assert rows[0]["over_price"] == 120 and rows[0]["under_price"] == -150
    assert rows[1]["over_price"] == 175 and rows[1]["under_price"] == -220
    assert rows[0]["book"] == "FanDuel"
    assert rows[0]["player_name_raw"] == "Logan Gilbert"
```

- [ ] **Step 2: Run test to verify it fails (or passes already)**

Run: `python -m pytest tests/test_alt_k_normalize.py -v`
Expected: PASS if `map_props_book` already handles it (likely). If FAIL, inspect `map_props_book` and the `apply_migrations` import path — fix the smallest thing (e.g. correct the migrate import) to make it pass without changing the grouping logic.

Note: confirm the migrate helper name. Check with `grep -n "def apply_migrations\|def get_connection" rambo-backend/db/migrate.py` and use whichever exists; if only `get_connection(path)` exists, build the in-memory DB via that instead.

- [ ] **Step 3: (Only if failing) minimal fix**

If `map_props_book` does not already map via `PROP_MARKET_MAP`, ensure it uses `PROP_MARKET_MAP.get(mkt.get("key"))` and skips unmapped keys (it does at line 452). Make no behavioral change beyond what the test requires.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/tests/test_alt_k_normalize.py rambo-backend/ingestion/normalize.py
git commit -m "$(cat <<'EOF'
test(betting): verify alt-K event lands per-line SO_ALT prop rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Per-leg EV + parlay math (pure functions)

**Files:**
- Create: `rambo-backend/brains/ev/alt_k.py`
- Test: `rambo-backend/tests/test_alt_k.py`

**Interfaces:**
- Consumes: `brains.ev.line_shop.american_to_decimal(odds: int) -> float`.
- Produces:
  - `leg_ev(model_p: float, american_price: int) -> float` — `model_p * american_to_decimal(price) - 1`, rounded to 4 dp.
  - `parlay_ev(legs: list[dict]) -> dict` where each leg is `{"p": float, "price": int}`; returns `{"combined_p": float, "payout": float, "ev": float}` with `combined_p = ∏ p`, `payout = ∏ american_to_decimal(price)`, `ev = combined_p * payout - 1`, all rounded to 4 dp. Empty list → `{"combined_p": 0.0, "payout": 0.0, "ev": -1.0}`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_alt_k.py
import math
from brains.ev import alt_k


def test_leg_ev_positive_when_model_beats_price():
    # +120 -> decimal 2.2; model 0.50 -> 0.50*2.2 - 1 = 0.10
    assert alt_k.leg_ev(0.50, 120) == 0.10


def test_leg_ev_negative_when_model_trails_price():
    # +120 -> 2.2; model 0.40 -> 0.40*2.2 - 1 = -0.12
    assert alt_k.leg_ev(0.40, 120) == -0.12


def test_parlay_ev_two_legs():
    # legs: p=0.5@+120 (dec 2.2), p=0.4@+150 (dec 2.5)
    res = alt_k.parlay_ev([{"p": 0.5, "price": 120}, {"p": 0.4, "price": 150}])
    assert res["combined_p"] == 0.2
    assert res["payout"] == 5.5
    assert res["ev"] == 0.1   # 0.2*5.5 - 1


def test_parlay_ev_empty():
    res = alt_k.parlay_ev([])
    assert res == {"combined_p": 0.0, "payout": 0.0, "ev": -1.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k.py -v`
Expected: FAIL — `module brains.ev.alt_k has no attribute 'leg_ev'`.

- [ ] **Step 3: Write minimal implementation**

```python
# rambo-backend/brains/ev/alt_k.py
"""Alt-strikeout board + parlay EV. Joins the k_model P(line+) ladder to real
book (FanDuel + best-of-book) pitcher_strikeouts_alternate odds. Pure-Python
math here; the board/repo glue is added in later tasks. Data-only."""
from __future__ import annotations

from brains.ev.line_shop import american_to_decimal


def leg_ev(model_p: float, american_price: int) -> float:
    """EV per 1u for a single over leg: model_p * decimal_payout - 1."""
    return round(model_p * american_to_decimal(american_price) - 1.0, 4)


def parlay_ev(legs: list[dict]) -> dict:
    """Independent-leg parlay. legs: [{"p": float, "price": int}, ...].
    combined_p = prod(p); payout = prod(decimal odds); ev = combined_p*payout - 1."""
    if not legs:
        return {"combined_p": 0.0, "payout": 0.0, "ev": -1.0}
    combined_p, payout = 1.0, 1.0
    for leg in legs:
        combined_p *= leg["p"]
        payout *= american_to_decimal(leg["price"])
    return {"combined_p": round(combined_p, 4), "payout": round(payout, 4),
            "ev": round(combined_p * payout - 1.0, 4)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/alt_k.py rambo-backend/tests/test_alt_k.py
git commit -m "$(cat <<'EOF'
feat(betting): alt-K per-leg + parlay EV math

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Join the k_model ladder to alt-K odds rows (`alt_k_legs`)

**Files:**
- Modify: `rambo-backend/brains/ev/alt_k.py`
- Test: `rambo-backend/tests/test_alt_k.py` (append)

**Interfaces:**
- Consumes:
  - `k_model.binom_prob_over(n: int, p: float, j: int) -> float` and a projection dict with `batters_faced` + `k_rate` (from `k_model.k_projection`).
  - `leg_ev` from Task 3.
- Produces:
  - `price_legs(proj: dict, odds_rows: list[dict], *, thresholds=(8, 9, 10)) -> list[dict]` — for each threshold present in `odds_rows`, build a leg dict:
    `{"threshold": int, "model_p": float, "fanduel": {"price": int, "ev": float} | None, "best": {"book": str, "price": int, "ev": float} | None}`.
    `model_p = binom_prob_over(round(proj["batters_faced"]), proj["k_rate"], threshold)` rounded 4 dp.
    `odds_rows` are `prop_lines`-shaped dicts: `{"line": float, "over_price": int|None, "book": str}`. An alt line `L` covers threshold `j = ceil(L)` (line 7.5 -> 8+). FanDuel match: `book.lower() == "fanduel"`. Best = highest `american_to_decimal(over_price)` among rows for that threshold with a non-null `over_price`. If no row for a threshold, `fanduel`/`best` are `None` but the leg is still emitted (model_p only).

- [ ] **Step 1: Write the failing test (append to tests/test_alt_k.py)**

```python
def _proj(bf=24, rate=0.30):
    return {"batters_faced": bf, "k_rate": rate}


def test_price_legs_matches_thresholds_and_picks_best_book():
    proj = _proj()
    # line 7.5 -> threshold 8; two books, DraftKings has the better over price
    odds_rows = [
        {"line": 7.5, "over_price": 120, "book": "FanDuel"},
        {"line": 7.5, "over_price": 150, "book": "DraftKings"},
        {"line": 8.5, "over_price": 200, "book": "FanDuel"},   # threshold 9
    ]
    legs = alt_k.price_legs(proj, odds_rows, thresholds=(8, 9, 10))
    by_t = {l["threshold"]: l for l in legs}

    # threshold 8 present, FanDuel + best (DK +150) priced
    assert by_t[8]["fanduel"]["price"] == 120
    assert by_t[8]["best"]["book"] == "DraftKings"
    assert by_t[8]["best"]["price"] == 150
    # model_p == binom_prob_over(24, 0.30, 8)
    from brains.ev.k_model import binom_prob_over
    assert by_t[8]["model_p"] == round(binom_prob_over(24, 0.30, 8), 4)

    # threshold 9 present from FanDuel only -> best is FanDuel
    assert by_t[9]["fanduel"]["price"] == 200
    assert by_t[9]["best"]["price"] == 200

    # threshold 10 has no odds row -> leg still emitted, odds None
    assert by_t[10]["fanduel"] is None
    assert by_t[10]["best"] is None
    assert by_t[10]["model_p"] == round(binom_prob_over(24, 0.30, 10), 4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k.py::test_price_legs_matches_thresholds_and_picks_best_book -v`
Expected: FAIL — no attribute `price_legs`.

- [ ] **Step 3: Write minimal implementation (append to alt_k.py)**

```python
import math

from brains.ev.k_model import binom_prob_over


def _threshold_for_line(line: float) -> int:
    """Alt over line L is cleared by ceil(L) Ks (7.5 -> 8+)."""
    return math.ceil(line + 1e-9)


def price_legs(proj: dict, odds_rows: list[dict], *,
               thresholds=(8, 9, 10)) -> list[dict]:
    n = round(proj["batters_faced"])
    rate = proj["k_rate"]
    # group priced rows by threshold
    by_t: dict[int, list[dict]] = {}
    for r in odds_rows:
        if r.get("over_price") is None or r.get("line") is None:
            continue
        by_t.setdefault(_threshold_for_line(r["line"]), []).append(r)
    legs = []
    for t in thresholds:
        model_p = round(binom_prob_over(n, rate, t), 4)
        rows = by_t.get(t, [])
        fanduel = None
        for r in rows:
            if (r.get("book") or "").lower() == "fanduel":
                fanduel = {"price": r["over_price"],
                           "ev": leg_ev(model_p, r["over_price"])}
                break
        best = None
        if rows:
            br = max(rows, key=lambda r: american_to_decimal(r["over_price"]))
            best = {"book": br.get("book") or "", "price": br["over_price"],
                    "ev": leg_ev(model_p, br["over_price"])}
        legs.append({"threshold": t, "model_p": model_p,
                     "fanduel": fanduel, "best": best})
    return legs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k.py -v`
Expected: PASS (all, including Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/alt_k.py rambo-backend/tests/test_alt_k.py
git commit -m "$(cat <<'EOF'
feat(betting): join k_model ladder to alt-K odds (FanDuel + best book)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Slate board assembler (`alt_k_board`)

**Files:**
- Modify: `rambo-backend/brains/ev/alt_k.py`
- Test: `rambo-backend/tests/test_alt_k_board.py`

**Interfaces:**
- Consumes:
  - `price_legs` (Task 4).
  - `MlbRepo` methods: `probable_starters(date) -> list[dict]` (each `{mlb_id, name, team_abbr, opponent_abbr, game_pk}`), `latest_props(market="SO_ALT", official_date=date) -> list[dict]` (`prop_lines` dicts incl. `mlb_id`, `line`, `over_price`, `book`).
  - `k_model.k_projection(repo, date, starter)` and `watch._opp_team_id(repo, game_pk, team_abbr)`.
- Produces:
  - `alt_k_board(date: str, repo=None, *, count: int = 11, as_of=None, book=None) -> dict` returning `{"title": "ALT-K BOARD", "product": "Strikeout model (alt-K)", "count": int, "rows": list, "prompt": str}`.
  - Each row: `{"rank", "name" (UPPER), "team", "opponent", "k_rate", "batters_faced", "k_mean", "thresholds": [<price_legs output>]}`. Ranked by `model_p` at threshold 9 (descending). `prompt` is a CMC image prompt.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_alt_k_board.py
from brains.ev import alt_k


class FakeRepo:
    """Minimal repo: one starter with alt-K odds, one with none."""
    def __init__(self):
        self._starters = [
            {"mlb_id": 1, "name": "Ace One", "team_abbr": "SEA",
             "opponent_abbr": "HOU", "game_pk": 100},
            {"mlb_id": 2, "name": "Arm Two", "team_abbr": "LAD",
             "opponent_abbr": "SDP", "game_pk": 200},
        ]
        self._props = [
            {"mlb_id": 1, "line": 7.5, "over_price": 150, "book": "FanDuel"},
            {"mlb_id": 1, "line": 8.5, "over_price": 220, "book": "DraftKings"},
        ]

    def probable_starters(self, date):
        return list(self._starters)

    def latest_props(self, market=None, official_date=None):
        assert market == "SO_ALT"
        return list(self._props)

    def game(self, game_pk):
        return {"home_team_abbr": "SEA", "away_team_abbr": "HOU",
                "home_team_id": 11, "away_team_id": 22}


def _fake_projection(monkeypatch):
    def fake_proj(repo, date, starter, **kw):
        return {"mlb_id": starter["mlb_id"], "name": starter["name"],
                "team_abbr": starter["team_abbr"], "opponent_abbr": starter["opponent_abbr"],
                "k_rate": 0.30, "batters_faced": 24.0, "k_mean": 7.2,
                "ladder": {9: 0.25 if starter["mlb_id"] == 1 else 0.10}}
    monkeypatch.setattr(alt_k.k_model, "k_projection", fake_proj)


def test_alt_k_board_ranks_and_prices(monkeypatch):
    _fake_projection(monkeypatch)
    board = alt_k.alt_k_board("2026-06-29", repo=FakeRepo())
    assert board["title"] == "ALT-K BOARD"
    assert board["count"] == 2
    # pitcher 1 ranked first (higher P(9+))
    assert board["rows"][0]["name"] == "ACE ONE"
    assert board["rows"][0]["rank"] == 1
    # pitcher 1 has priced thresholds; threshold 8 from FanDuel
    t8 = next(t for t in board["rows"][0]["thresholds"] if t["threshold"] == 8)
    assert t8["fanduel"]["price"] == 150
    # pitcher 2 has no odds -> thresholds present but odds None
    t9_p2 = next(t for t in board["rows"][1]["thresholds"] if t["threshold"] == 9)
    assert t9_p2["best"] is None
    assert isinstance(board["prompt"], str) and "ALT-K" in board["prompt"].upper()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k_board.py -v`
Expected: FAIL — no attribute `alt_k_board`.

- [ ] **Step 3: Write minimal implementation (append to alt_k.py)**

```python
import os

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
ALT_K_BOARD_SIZE = 11


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _alt_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in ("Alt-strikeout model (FanDuel + best book)",
                                   f"as of {as_of}" if as_of else None, book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    lines = []
    for r in rows:
        head = f"{r['rank']}. {r['name']}"
        if r["team"] or r["opponent"]:
            head += f" ({r['team']} vs {r['opponent']})"
        parts = [head]
        for t in r["thresholds"]:
            seg = f"{t['threshold']}+ {round(t['model_p']*100)}%"
            if t["best"]:
                seg += f" (best {t['best']['price']:+d} ev {t['best']['ev']:+.2f})"
            parts.append(seg)
        parts.append(f"proj {r['k_mean']} K")
        lines.append(" — ".join(parts))
    body = "\n".join(lines) or "(no probable starters available yet)"
    return banner + (
        'Create a premium sports-betting "alt-strikeout board" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "ALT-K BOARD". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} starting pitchers. Each row shows "
        "the pitcher (team vs opponent), the 8+/9+/10+ strikeout probabilities with the "
        "best book price and EV, and the projected K total. Even spacing.\n\n"
        "KEY: N+ % = our model probability of at least N strikeouts; price = best "
        "available alt-strikeout over; EV is per 1 unit. Most alt-K overs are −EV — the "
        "value is the rare +EV threshold, not chasing every arm. NOT guarantees.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or odds.\n\n"
        f"PITCHERS:\n{body}"
    )


def alt_k_board(date: str, repo=None, *, count: int = ALT_K_BOARD_SIZE,
                as_of: str | None = None, book: str | None = None) -> dict:
    from brains.ev import k_model
    from brains.ev.watch import _opp_team_id
    repo, conn = _open(repo)
    try:
        # alt-K odds rows grouped by pitcher mlb_id
        odds_by_pid: dict[int, list[dict]] = {}
        for p in repo.latest_props(market="SO_ALT", official_date=date):
            if p.get("mlb_id") is None:
                continue
            odds_by_pid.setdefault(p["mlb_id"], []).append(p)

        scored, seen = [], set()
        for s in repo.probable_starters(date):
            mid = s["mlb_id"]
            if mid in seen:
                continue
            seen.add(mid)
            starter = {
                "mlb_id": mid, "name": s.get("name") or "",
                "team_abbr": s.get("team_abbr", ""), "opponent_abbr": s.get("opponent_abbr", ""),
                "opponent_team_id": _opp_team_id(repo, s.get("game_pk"), s.get("team_abbr", "")),
            }
            proj = k_model.k_projection(repo, date, starter)
            if proj is None or proj["k_mean"] <= 0:
                continue
            legs = price_legs(proj, odds_by_pid.get(mid, []))
            scored.append((proj, legs))
        scored.sort(key=lambda pl: pl[0]["ladder"].get(9, 0.0), reverse=True)

        rows = []
        for i, (proj, legs) in enumerate(scored[:count]):
            rows.append({
                "rank": i + 1, "name": (proj["name"] or "").upper(),
                "team": proj["team_abbr"], "opponent": proj["opponent_abbr"],
                "k_rate": round(proj["k_rate"], 3),
                "batters_faced": round(proj["batters_faced"], 1),
                "k_mean": round(proj["k_mean"], 1), "thresholds": legs,
            })
        return {"title": "ALT-K BOARD", "product": "Strikeout model (alt-K)",
                "count": len(rows), "rows": rows,
                "prompt": _alt_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
```

Note: `k_projection` must return a `ladder` with key 9 for ranking. The real `k_model.k_projection` already returns a full ladder (max_j=10). The fake in the test supplies `ladder={9: ...}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k_board.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/alt_k.py rambo-backend/tests/test_alt_k_board.py
git commit -m "$(cat <<'EOF'
feat(betting): alt-K slate board (ranked starters + priced thresholds)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Parlay suggestion + manual assembly over a board

**Files:**
- Modify: `rambo-backend/brains/ev/alt_k.py`
- Test: `rambo-backend/tests/test_alt_k.py` (append)

**Interfaces:**
- Consumes: `parlay_ev` (Task 3); board rows from `alt_k_board` (Task 5).
- Produces:
  - `board_to_best_legs(board: dict, *, book: str = "best") -> dict[int, dict]` — map pitcher rank -> best-value leg for that pitcher: pick the threshold with the highest `ev` under the chosen book (`"best"` uses `best`, `"fanduel"` uses `fanduel`); skip pitchers with no priced leg. Each value: `{"name", "threshold", "p", "price", "book", "ev"}`.
  - `suggest_parlays(board: dict, *, sizes=(2, 3, 4), book: str = "best") -> list[dict]` — from best legs ranked by `ev` desc, build a parlay per size from the top-`size` legs; each: `{"size", "legs": [name@threshold...], "combined_p", "payout", "ev"}`, sorted by `ev` desc.
  - `manual_parlay(board: dict, picks: list[dict], *, book: str = "best") -> dict` — `picks` = `[{"name": str, "threshold": int}]`; resolve each to its board leg/price, return `parlay_ev`-shaped dict plus `"legs"` (resolved) and `"missing"` (picks with no priced leg). EV computed only if `missing` is empty.

- [ ] **Step 1: Write the failing test (append to tests/test_alt_k.py)**

```python
def _board():
    return {"rows": [
        {"rank": 1, "name": "ACE ONE", "thresholds": [
            {"threshold": 8, "model_p": 0.55,
             "fanduel": {"price": 120, "ev": 0.21},
             "best": {"book": "DK", "price": 150, "ev": 0.375}},
            {"threshold": 9, "model_p": 0.30,
             "fanduel": {"price": 200, "ev": -0.10},
             "best": {"book": "DK", "price": 210, "ev": -0.07}},
        ]},
        {"rank": 2, "name": "ARM TWO", "thresholds": [
            {"threshold": 8, "model_p": 0.45,
             "fanduel": {"price": 130, "ev": 0.035},
             "best": {"book": "FD", "price": 130, "ev": 0.035}},
        ]},
    ]}


def test_board_to_best_legs_picks_highest_ev_threshold():
    best = alt_k.board_to_best_legs(_board(), book="best")
    assert best[1]["threshold"] == 8       # ev 0.375 beats 9+ (-0.07)
    assert best[1]["price"] == 150
    assert best[2]["threshold"] == 8


def test_suggest_parlays_builds_sizes_and_sorts():
    out = alt_k.suggest_parlays(_board(), sizes=(2,), book="best")
    assert len(out) == 1
    assert out[0]["size"] == 2
    # combined_p = 0.55*0.45 = 0.2475; payout = 2.5*2.3 = 5.75
    assert out[0]["combined_p"] == 0.2475
    assert out[0]["payout"] == 5.75


def test_manual_parlay_resolves_and_flags_missing():
    res = alt_k.manual_parlay(
        _board(),
        [{"name": "ACE ONE", "threshold": 8}, {"name": "GHOST", "threshold": 9}],
        book="best")
    assert res["missing"] == [{"name": "GHOST", "threshold": 9}]
    assert res["ev"] is None     # not all legs priced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k.py -v`
Expected: FAIL — no attribute `board_to_best_legs`.

- [ ] **Step 3: Write minimal implementation (append to alt_k.py)**

```python
def _leg_price(threshold_row: dict, book: str) -> dict | None:
    return threshold_row.get("fanduel" if book == "fanduel" else "best")


def board_to_best_legs(board: dict, *, book: str = "best") -> dict[int, dict]:
    out: dict[int, dict] = {}
    for row in board.get("rows", []):
        priced = []
        for t in row.get("thresholds", []):
            pr = _leg_price(t, book)
            if pr is not None:
                priced.append((t, pr))
        if not priced:
            continue
        t, pr = max(priced, key=lambda tp: tp[1]["ev"])
        out[row["rank"]] = {
            "name": row["name"], "threshold": t["threshold"], "p": t["model_p"],
            "price": pr["price"], "book": pr.get("book", "FanDuel"), "ev": pr["ev"]}
    return out


def suggest_parlays(board: dict, *, sizes=(2, 3, 4), book: str = "best") -> list[dict]:
    legs = sorted(board_to_best_legs(board, book=book).values(),
                  key=lambda l: l["ev"], reverse=True)
    out = []
    for size in sizes:
        if size > len(legs):
            continue
        chosen = legs[:size]
        res = parlay_ev([{"p": l["p"], "price": l["price"]} for l in chosen])
        out.append({"size": size,
                    "legs": [f"{l['name']} {l['threshold']}+" for l in chosen],
                    "combined_p": res["combined_p"], "payout": res["payout"],
                    "ev": res["ev"]})
    out.sort(key=lambda e: e["ev"], reverse=True)
    return out


def manual_parlay(board: dict, picks: list[dict], *, book: str = "best") -> dict:
    by_name: dict[str, dict] = {r["name"].upper(): r for r in board.get("rows", [])}
    resolved, missing = [], []
    for pick in picks:
        row = by_name.get((pick.get("name") or "").upper())
        leg = None
        if row is not None:
            for t in row.get("thresholds", []):
                if t["threshold"] == pick.get("threshold"):
                    pr = _leg_price(t, book)
                    if pr is not None:
                        leg = {"name": row["name"], "threshold": t["threshold"],
                               "p": t["model_p"], "price": pr["price"],
                               "book": pr.get("book", "FanDuel"), "ev": pr["ev"]}
                    break
        if leg is None:
            missing.append({"name": pick.get("name"), "threshold": pick.get("threshold")})
        else:
            resolved.append(leg)
    if missing:
        return {"legs": resolved, "missing": missing,
                "combined_p": None, "payout": None, "ev": None}
    res = parlay_ev([{"p": l["p"], "price": l["price"]} for l in resolved])
    return {"legs": resolved, "missing": [], **res}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k.py -v`
Expected: PASS (all alt_k tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/brains/ev/alt_k.py rambo-backend/tests/test_alt_k.py
git commit -m "$(cat <<'EOF'
feat(betting): alt-K parlay auto-suggest + manual assembly

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: API endpoints

**Files:**
- Modify: `rambo-backend/api/betting.py` (add two routes near the existing prizepicks routes ~line 294-314; reuse `_data_as_of`/`_provenance` if present)
- Test: `rambo-backend/tests/test_alt_k_api.py`

**Interfaces:**
- Consumes: `alt_k.alt_k_board`, `alt_k.suggest_parlays`, `alt_k.manual_parlay` (Tasks 5-6).
- Produces:
  - `GET /betting/alt-k-board?date=` -> `alt_k_board(date)` dict.
  - `POST /betting/alt-k/parlay?date=&book=&sizes=` with optional JSON body `{"legs": [{"name","threshold"}]}` -> when `legs` present, `manual_parlay`; else `suggest_parlays`. Response includes `date` and `book`.

- [ ] **Step 1: Write the failing test**

```python
# rambo-backend/tests/test_alt_k_api.py
from fastapi.testclient import TestClient
from main import app
from brains.ev import alt_k

client = TestClient(app)


def _fake_board(date, **kw):
    return {"title": "ALT-K BOARD", "product": "Strikeout model (alt-K)",
            "count": 1, "rows": [
                {"rank": 1, "name": "ACE ONE", "team": "SEA", "opponent": "HOU",
                 "k_rate": 0.3, "batters_faced": 24.0, "k_mean": 7.2,
                 "thresholds": [{"threshold": 8, "model_p": 0.55,
                                 "fanduel": {"price": 120, "ev": 0.21},
                                 "best": {"book": "DK", "price": 150, "ev": 0.375}}]}],
            "prompt": "ALT-K BOARD ..."}


def test_alt_k_board_endpoint(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    r = client.get("/betting/alt-k-board?date=2026-06-29")
    assert r.status_code == 200
    assert r.json()["title"] == "ALT-K BOARD"


def test_alt_k_parlay_auto(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    monkeypatch.setattr(alt_k, "suggest_parlays",
                        lambda board, **kw: [{"size": 1, "legs": ["ACE ONE 8+"],
                                              "combined_p": 0.55, "payout": 2.5, "ev": 0.375}])
    r = client.post("/betting/alt-k/parlay?date=2026-06-29&book=best")
    assert r.status_code == 200
    body = r.json()
    assert body["book"] == "best"
    assert body["suggestions"][0]["ev"] == 0.375


def test_alt_k_parlay_manual(monkeypatch):
    monkeypatch.setattr(alt_k, "alt_k_board", _fake_board)
    monkeypatch.setattr(alt_k, "manual_parlay",
                        lambda board, picks, **kw: {"legs": [], "missing": [],
                                                    "combined_p": 0.55, "payout": 2.5, "ev": 0.375})
    r = client.post("/betting/alt-k/parlay?date=2026-06-29",
                    json={"legs": [{"name": "ACE ONE", "threshold": 8}]})
    assert r.status_code == 200
    assert r.json()["parlay"]["ev"] == 0.375
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alt_k_api.py -v`
Expected: FAIL — 404 on the new routes.

- [ ] **Step 3: Write minimal implementation**

Add to `api/betting.py` (top-level import block already imports from `brains.ev.watch`; add `from brains.ev import alt_k` lazily inside the handlers to match the file's existing lazy-import style, OR at top — match what the file does for prizepicks). Use the existing `Body`/`Optional` imports; if `Body` isn't imported, add `from fastapi import Body`.

```python
@router.get("/alt-k-board")
def get_alt_k_board(date: Optional[str] = None) -> dict:
    """Probable starters ranked by P(9+ K) with FanDuel + best-book alt-strikeout
    odds and per-threshold EV (+ CMC prompt). Data-only."""
    from brains.ev import alt_k
    d = date or datetime.date.today().isoformat()
    try:
        return alt_k.alt_k_board(d)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"alt_k_board failed: {e}") from e


@router.post("/alt-k/parlay")
def post_alt_k_parlay(date: Optional[str] = None, book: str = "best",
                      sizes: Optional[str] = None,
                      body: Optional[dict] = Body(default=None)) -> dict:
    """Auto-suggest alt-K parlays, or evaluate a manual leg list when body.legs
    is provided. book in {best, fanduel}."""
    from brains.ev import alt_k
    d = date or datetime.date.today().isoformat()
    board = alt_k.alt_k_board(d, book=book)
    legs = (body or {}).get("legs")
    if legs:
        return {"date": d, "book": book,
                "parlay": alt_k.manual_parlay(board, legs, book=book)}
    size_tuple = (tuple(int(s) for s in sizes.split(",")) if sizes else (2, 3, 4))
    return {"date": d, "book": book,
            "suggestions": alt_k.suggest_parlays(board, sizes=size_tuple, book=book)}
```

Match the file's actual import style for `datetime`, `Optional`, `HTTPException`, `Body` (check the top of `api/betting.py`; add `Body` to the `from fastapi import ...` line if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alt_k_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/api/betting.py rambo-backend/tests/test_alt_k_api.py
git commit -m "$(cat <<'EOF'
feat(betting): /alt-k-board + /alt-k/parlay endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Full-suite regression + finish

**Files:** none (verification only).

- [ ] **Step 1: Run the whole betting/EV suite**

Run: `python -m pytest tests/ -q`
Expected: all prior tests still pass (the spec's "557 pass" baseline plus the new alt-K tests). If any pre-existing test fails, investigate before proceeding — do not edit unrelated tests to make them pass.

- [ ] **Step 2: Sanity-check the board against live data (best effort)**

Run: `python -c "from brains.ev.alt_k import alt_k_board; import json, datetime; print(json.dumps(alt_k_board(datetime.date.today().isoformat()), indent=2)[:800])"`
Expected: a dict with `title=ALT-K BOARD` and `rows` (empty `rows` is acceptable if no slate/odds are loaded today — the point is no exception). If `SO_ALT` odds haven't been pulled, thresholds will have null odds; that is expected until `/betting/pull-book-props` runs with the new market.

- [ ] **Step 3: Confirm clean tree + push branch**

```bash
git status -s
git push -u origin feat/alt-k-parlay
```

- [ ] **Step 4: Open the PR** (per operator's branch-and-PR preference)

```bash
gh pr create --title "Alt-strikeout parlay builder (true EV)" --body "$(cat <<'EOF'
Adds a true-EV alt-strikeout board + parlay builder on top of the existing K model.

- New SO_ALT market via The Odds API pitcher_strikeouts_alternate (FanDuel + best-of-book)
- brains/ev/alt_k.py: joins k_model P(8+/9+/10+) ladder to real odds -> per-leg + parlay EV
- /betting/alt-k-board and /betting/alt-k/parlay (auto-suggest + manual legs)
- Full TDD coverage; honest -EV-avoidance framing kept

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for the implementer

- The new strikeout market only produces data after `/betting/pull-book-props` is run with `pitcher_strikeouts_alternate` in the market set (Task 1 adds it to the default). Until then `SO_ALT` rows won't exist and thresholds carry null odds — that is the designed graceful path, not a bug.
- `k_model.k_projection` and `watch._opp_team_id` are imported lazily inside `alt_k_board` to avoid import cycles and to keep the pure-math functions (Tasks 3-4) importable without a DB.
- Quota: each slate prop pull now costs 1 extra credit per event on The Odds API. This is gated behind the manual prop-pull endpoint, never auto-run.
