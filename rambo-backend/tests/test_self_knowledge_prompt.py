import pytest
from personality import load_self_knowledge, build_system_prompt, load_personality


class TestSelfKnowledge:
    def test_slim_mode_produces_output(self):
        sk = load_self_knowledge("slim")
        assert "Self-Knowledge (slim)" in sk
        assert "Skills:" in sk or "Agents:" in sk

    def test_slim_contains_identity(self):
        sk = load_self_knowledge("slim")
        assert "multi-agent orchestrator" in sk

    def test_slim_contains_core_principles(self):
        sk = load_self_knowledge("slim")
        assert "Mission first" in sk

    def test_slim_contains_agent_names(self):
        sk = load_self_knowledge("slim")
        assert "Architect" in sk
        assert "Sentinel" in sk

    def test_slim_contains_skill_names(self):
        sk = load_self_knowledge("slim")
        assert "weather" in sk

    def test_full_mode(self):
        sk = load_self_knowledge("full")
        assert "## Self-Knowledge" in sk
        assert "AUTO-START" in sk

    def test_off_mode(self):
        sk = load_self_knowledge("off")
        assert sk == ""

    def test_slim_under_500_tokens(self):
        sk = load_self_knowledge("slim")
        # rough token estimate: ~4 chars per token
        est_tokens = len(sk) / 4
        assert est_tokens < 500, f"Slim summary ~{est_tokens:.0f} tokens, target <500"


class TestBuildSystemPromptWithSK:
    def test_self_knowledge_block_present(self):
        personality = load_personality()
        blocks = build_system_prompt(personality)
        texts = [b["text"] for b in blocks]
        assert any("Self-Knowledge" in t for t in texts)

    def test_self_knowledge_is_cached(self):
        personality = load_personality()
        blocks = build_system_prompt(personality)
        sk_blocks = [b for b in blocks if "Self-Knowledge" in b["text"]]
        assert len(sk_blocks) == 1
        import cache_config
        assert sk_blocks[0].get("cache_control") == cache_config.cache_control()

    def test_context_still_appended(self):
        personality = load_personality()
        blocks = build_system_prompt(personality, context="extra context here")
        texts = [b["text"] for b in blocks]
        assert any("extra context here" in t for t in texts)
