"""Tests for the central cache configuration."""

import importlib
import cache_config


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("RAMBO_CACHE_TTL", raising=False)
    else:
        monkeypatch.setenv("RAMBO_CACHE_TTL", value)
    importlib.reload(cache_config)
    return cache_config


def test_default_is_one_hour(monkeypatch):
    cc = _reload(monkeypatch, None)
    assert cc.cache_ttl() == "1h"
    assert cc.cache_control() == {"type": "ephemeral", "ttl": "1h"}
    assert cc.uses_extended_ttl() is True
    assert cc.beta_headers() == {"anthropic-beta": cc.EXTENDED_TTL_BETA}


def test_five_minute_mode(monkeypatch):
    cc = _reload(monkeypatch, "5m")
    assert cc.cache_ttl() == "5m"
    assert cc.cache_control() == {"type": "ephemeral"}
    assert cc.uses_extended_ttl() is False
    assert cc.beta_headers() == {}


def test_invalid_falls_back_to_one_hour(monkeypatch):
    cc = _reload(monkeypatch, "bogus")
    assert cc.cache_ttl() == "1h"


def test_cleanup(monkeypatch):
    # Restore module to default state for the rest of the suite.
    _reload(monkeypatch, None)
    assert cache_config.cache_ttl() == "1h"
