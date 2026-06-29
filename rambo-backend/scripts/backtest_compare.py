"""CLI: run BOTH the closed-form baseline and the learned model over a window and
print their metrics side by side, with a one-line verdict on whether the learned
model beat the baseline. Usage: python scripts/backtest_compare.py START END"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.walkforward import run
from brains.ev.ml.predictor import AnchoredPredictor, LogRegPredictor


def _verdict(base: dict, learned: dict) -> str:
    b, l = base["early"], learned["early"]
    parts = []
    for k in ("roi", "brier", "log_loss"):
        bv, lv = b.get(k), l.get(k)
        if bv is None or lv is None:
            parts.append(f"{k}: n/a")
            continue
        better = lv > bv if k == "roi" else lv < bv   # higher ROI good; lower error good
        parts.append(f"{k}: {lv} vs {bv} {'BEAT' if better else 'worse'}")
    return " | ".join(parts)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/backtest_compare.py START_DATE END_DATE",
              file=sys.stderr)
        return 2
    start, end = sys.argv[1], sys.argv[2]
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        repo = MlbRepo(conn)
        base = run(repo, start, end, predictor=AnchoredPredictor())
        learned = run(repo, start, end, predictor=LogRegPredictor())
    finally:
        conn.close()
    print(json.dumps({"baseline": base, "logreg": learned}, indent=2))
    print("\nVERDICT (early line):", _verdict(base, learned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
