import model_config
from orchestrator.routing import SmartRouter


def test_router_uses_fast_model_when_passed():
    router = SmartRouter(llm_client=None, model=model_config.fast_model())
    assert router._model == "claude-haiku-4-5"


def test_router_defaults_to_deep_when_unspecified():
    router = SmartRouter(llm_client=None)
    assert router._model == model_config.default_model()
