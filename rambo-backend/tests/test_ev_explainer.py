from brains.ev.types import Pick
from brains.ev.explainer import explain, _fallback

def _pick(name, edge):
    return Pick(market="hr", mlb_id=1, name=name, initials="X", team="NYY",
                opponent="BOS", hand="L", pick="1+ HOME RUN — OVER", line=0.5,
                multiplier=2.5, breakeven=0.4, model_p=0.46, edge=edge,
                support="50 HR", tags=["EDGE"], glow="gold", headshot_url="u")

def test_explain_fills_from_completion():
    picks = [_pick("A", 0.16), _pick("B", 0.10)]
    out = explain(picks, "hr", complete=lambda prompt: "first reason\nsecond reason")
    assert out[0].rationale == "first reason"
    assert out[1].rationale == "second reason"

def test_explain_fallback_on_error():
    picks = [_pick("A", 0.16)]
    def boom(prompt): raise RuntimeError("no api key")
    out = explain(picks, "hr", complete=boom)
    assert out[0].rationale == _fallback(picks[0])
    assert "%" in out[0].rationale

def test_explain_empty_is_noop():
    assert explain([], "hr", complete=lambda p: "") == []
