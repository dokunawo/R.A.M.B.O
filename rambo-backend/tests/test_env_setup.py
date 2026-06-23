"""Tests for .env auto-loading."""

import importlib
import env_setup


def test_no_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(env_setup, "_ENV_PATH", tmp_path / "nope.env")
    assert env_setup.load_env() is False


def test_fallback_parser_loads_keys(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text(
        "# a comment\n"
        "ANTHROPIC_API_KEY=sk-ant-fake-123\n"
        "\n"
        'QUOTED="value with spaces"\n'
        "RAMBO_CACHE_TTL=5m\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(env_setup, "_ENV_PATH", envfile)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    monkeypatch.delenv("RAMBO_CACHE_TTL", raising=False)

    # Force the fallback path (ignore python-dotenv if installed).
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name == "dotenv":
            raise ImportError("forced")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    import os
    assert env_setup.load_env() is True
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-fake-123"
    assert os.environ["QUOTED"] == "value with spaces"
    assert os.environ["RAMBO_CACHE_TTL"] == "5m"


def test_does_not_overwrite_existing(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(env_setup, "_ENV_PATH", envfile)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-real-env")

    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name == "dotenv":
            raise ImportError("forced")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    import os
    env_setup.load_env()
    # Real environment wins over the .env file.
    assert os.environ["ANTHROPIC_API_KEY"] == "from-real-env"
