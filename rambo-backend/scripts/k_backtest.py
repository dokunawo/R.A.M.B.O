"""CLI: leak-free strikeout-model calibration backtest.
Usage: python scripts/k_backtest.py START END"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.k_backtest import run


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/k_backtest.py START_DATE END_DATE", file=sys.stderr)
        return 2
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        print(json.dumps(run(MlbRepo(conn), sys.argv[1], sys.argv[2]), indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
