"""
R.A.M.B.O. MLB Betting Agent — Ingestion CLI (Step 5)
ingestion/cli.py

Command-line entry for on-demand / scheduled pulls. Same data-only boundary as
the API: no bet capability lives here.

Examples:
  python -m ingestion.cli migrate
  python -m ingestion.cli pull --source roster
  python -m ingestion.cli pull --source schedule --date 2026-06-26
  python -m ingestion.cli pull --source odds --date 2026-06-26
  python -m ingestion.cli pull --source props
  python -m ingestion.cli pull --source stats --player-id 592450 --season 2026
  python -m ingestion.cli normalize --limit 500
  python -m ingestion.cli renormalize --actor zen-studio/draftkings-pick6-player-props
"""

from __future__ import annotations

import argparse
import json
import os

# Load .env so APIFY_TOKEN (paid sources) is available when run standalone.
try:
    from env_setup import load_env
    load_env()
except Exception:
    pass

from db.migrate import apply_migrations, get_connection
from ingestion.normalize import normalize_pending, renormalize_actor
from ingestion.sources import SOURCES, pull_source

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
MIGRATIONS_DIR = os.environ.get("RAMBO_MIGRATIONS_DIR", "db/migrations")


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_migrate(args, conn) -> None:
    _out({"applied": apply_migrations(conn, MIGRATIONS_DIR)})


def cmd_pull(args, conn) -> None:
    params = {"date": args.date, "season": args.season, "player_id": args.player_id,
              "overrides": json.loads(args.input) if args.input else {}}
    _out(pull_source(conn, args.source, params))
    if args.normalize:
        _out(normalize_pending(conn))


def cmd_normalize(args, conn) -> None:
    _out(normalize_pending(conn, limit=args.limit))


def cmd_renormalize(args, conn) -> None:
    _out({"watermarks_cleared": renormalize_actor(conn, args.actor)})


def main() -> None:
    p = argparse.ArgumentParser(prog="rambo-ingest")
    sub = p.add_subparsers(required=True)

    sub.add_parser("migrate").set_defaults(func=cmd_migrate)

    pp = sub.add_parser("pull")
    pp.add_argument("--source", required=True, choices=SOURCES)
    pp.add_argument("--date", help="YYYY-MM-DD (schedule / odds)")
    pp.add_argument("--season", type=int, help="season year (roster / stats)")
    pp.add_argument("--player-id", type=int, dest="player_id", help="required for 'stats'")
    pp.add_argument("--input", help="JSON input overrides (paid actors)")
    pp.add_argument("--no-normalize", dest="normalize", action="store_false")
    pp.set_defaults(func=cmd_pull, normalize=True)

    pn = sub.add_parser("normalize")
    pn.add_argument("--limit", type=int, default=None)
    pn.set_defaults(func=cmd_normalize)

    pr = sub.add_parser("renormalize")
    pr.add_argument("--actor", required=True,
                    help="source id whose raw rows to re-process "
                         "(e.g. mlb/statsapi:schedule or an Apify actor id)")
    pr.set_defaults(func=cmd_renormalize)

    args = p.parse_args()
    conn = get_connection(DB_PATH)
    apply_migrations(conn, MIGRATIONS_DIR)  # always current before any command
    try:
        args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
