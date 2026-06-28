"""CLI: walk-forward moneyline backtest. Usage: python scripts/walkforward.py START END
Prints the metrics JSON (early + closing line, side by side)."""
from __future__ import annotations

import json
import os
import sys

# allow running from repo root or rambo-backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrate import get_connection
from repositories.mlb_repo import MlbRepo
from brains.ev.walkforward import run


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python scripts/walkforward.py START_DATE END_DATE", file=sys.stderr)
        return 2
    start, end = sys.argv[1], sys.argv[2]
    db = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
    conn = get_connection(db)
    try:
        print(json.dumps(run(MlbRepo(conn), start, end), indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
