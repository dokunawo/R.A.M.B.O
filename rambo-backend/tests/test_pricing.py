import logging
import pytest
from pricing import compute_cost, _resolve_model, MODEL_PRICING


class TestResolveModel:
    def test_exact_match(self):
        rates = _resolve_model("claude-sonnet-4")
        assert rates is not None
        assert rates["input"] == 3.00

    def test_version_suffix_prefix_match(self):
        rates = _resolve_model("claude-sonnet-4-6")
        assert rates is not None
        assert rates["input"] == 3.00

    def test_longest_prefix_wins(self):
        rates = _resolve_model("claude-sonnet-3.5-20250101")
        assert rates is not None
        assert rates["input"] == 3.00
        assert rates is MODEL_PRICING["claude-sonnet-3.5"]

    def test_unknown_model_returns_none(self):
        assert _resolve_model("gpt-5-turbo") is None


class TestComputeCost:
    def test_basic_input_output(self):
        cost = compute_cost("claude-sonnet-4", input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_with_cache_tokens(self):
        cost = compute_cost(
            "claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_input_tokens=2000,
            cache_read_input_tokens=3000,
        )
        expected = (
            1000 * 3.00
            + 500 * 15.00
            + 2000 * 3.75
            + 3000 * 0.30
        ) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_zero_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            cost = compute_cost("mystery-model-9000", input_tokens=5000, output_tokens=1000)
        assert cost == 0.0
        assert "mystery-model-9000" in caplog.text

    def test_version_suffixed_model(self):
        cost = compute_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self):
        assert compute_cost("claude-sonnet-4") == 0.0

    def test_opus_pricing(self):
        cost = compute_cost("claude-opus-4", input_tokens=1000, output_tokens=1000)
        expected = (1000 * 15.00 + 1000 * 75.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_cache_read_cheaper_than_input(self):
        full_cost = compute_cost("claude-sonnet-4", input_tokens=10000)
        cache_cost = compute_cost("claude-sonnet-4", cache_read_input_tokens=10000)
        assert cache_cost < full_cost
