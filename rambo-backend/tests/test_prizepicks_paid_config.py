import importlib
from config import prizepicks as cfg


def test_no_actor_env_disables_fallback(monkeypatch):
    monkeypatch.delenv("PRIZEPICKS_APIFY_ACTOR", raising=False)
    assert cfg.paid_actor_config() is None


def test_actor_env_builds_config(monkeypatch):
    monkeypatch.setenv("PRIZEPICKS_APIFY_ACTOR", "someuser/pp-scraper")
    monkeypatch.setenv("PRIZEPICKS_APIFY_MAX_COST_USD", "1.50")
    monkeypatch.setenv("PRIZEPICKS_APIFY_MAX_ITEMS", "500")
    ac = cfg.paid_actor_config()
    assert ac is not None
    assert ac.actor_id == "someuser/pp-scraper"
    assert ac.max_cost_usd == 1.50
    assert ac.max_items == 500


def test_actor_input_defaults_and_parses(monkeypatch):
    monkeypatch.delenv("PRIZEPICKS_APIFY_INPUT", raising=False)
    assert cfg.paid_actor_input() == {"league": "MLB"}
    monkeypatch.setenv("PRIZEPICKS_APIFY_INPUT", '{"league": "MLB", "x": 1}')
    assert cfg.paid_actor_input() == {"league": "MLB", "x": 1}
    monkeypatch.setenv("PRIZEPICKS_APIFY_INPUT", "not json")
    assert cfg.paid_actor_input() == {"league": "MLB"}   # bad JSON -> default
