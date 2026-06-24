import importlib
import model_config


def test_fast_model_default(monkeypatch):
    monkeypatch.delenv("RAMBO_FAST_MODEL", raising=False)
    importlib.reload(model_config)
    assert model_config.fast_model() == "claude-haiku-4-5"


def test_fast_model_env_override(monkeypatch):
    monkeypatch.setenv("RAMBO_FAST_MODEL", "claude-haiku-x")
    assert model_config.fast_model() == "claude-haiku-x"


def test_fast_model_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("RAMBO_FAST_MODEL", "   ")
    assert model_config.fast_model() == "claude-haiku-4-5"


def test_default_model_unchanged(monkeypatch):
    monkeypatch.delenv("RAMBO_MODEL", raising=False)
    assert model_config.default_model() == "claude-sonnet-4-6"
