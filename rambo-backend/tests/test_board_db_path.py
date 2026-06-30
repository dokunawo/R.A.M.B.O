"""Regression: EV board `_open(None)` must resolve RAMBO_DB_PATH at CALL time,
not from a module-level constant captured at import. Otherwise a board imported
before the env is set queries a stale DB (the bug fixed for the prizepicks boards
and now watch.py / alt_k.py)."""
import os

from brains.ev import watch, alt_k, prizepicks_board, prizepicks_tiers


def _assert_opens_env_path(module, tmp_path, monkeypatch, name):
    db = str(tmp_path / f"{name}.db")
    monkeypatch.setenv("RAMBO_DB_PATH", db)
    repo, conn = module._open(None)          # repo=None -> opens RAMBO_DB_PATH
    try:
        assert os.path.exists(db)            # opened the env path set AFTER import
    finally:
        conn.close()


def test_watch_open_uses_env_db_path(tmp_path, monkeypatch):
    _assert_opens_env_path(watch, tmp_path, monkeypatch, "watch")


def test_alt_k_open_uses_env_db_path(tmp_path, monkeypatch):
    _assert_opens_env_path(alt_k, tmp_path, monkeypatch, "altk")


def test_prizepicks_board_open_uses_env_db_path(tmp_path, monkeypatch):
    _assert_opens_env_path(prizepicks_board, tmp_path, monkeypatch, "ppb")


def test_prizepicks_tiers_open_uses_env_db_path(tmp_path, monkeypatch):
    _assert_opens_env_path(prizepicks_tiers, tmp_path, monkeypatch, "ppt")
