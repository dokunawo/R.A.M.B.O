import pytest
from self_knowledge.generators.capabilities import generate as gen_cap
from self_knowledge.generators.subagents import generate as gen_sub
from self_knowledge.generators.integrations import generate as gen_int
from self_knowledge.generators.voice import generate as gen_voice
from self_knowledge.generators.recent_activity import generate as gen_activity


class TestCapabilities:
    def test_fixture_registry(self):
        fixture = [
            {"name": "weather", "agent": "seeker", "match": lambda g: "weather" in g},
            {"name": "calendar", "agent": "pilot", "match": lambda g: "calendar" in g},
        ]
        out = gen_cap(skills=fixture)
        assert "weather" in out
        assert "seeker" in out
        assert "calendar" in out
        assert "pilot" in out
        assert "| Skill |" in out

    def test_empty_registry(self):
        assert "_No skills registered._" in gen_cap(skills=[])

    def test_from_live_registry(self):
        out = gen_cap()
        assert "weather" in out
        assert "| Skill |" in out


class TestSubagents:
    def test_fixture_agents(self):
        agents = {"architect": None, "engineer": None, "seeker": None}
        out = gen_sub(agents=agents)
        assert "Architect" in out
        assert "Engineer" in out
        assert "Seeker" in out
        assert "| Agent |" in out

    def test_empty_agents(self):
        assert "_No sub-agents registered._" in gen_sub(agents={})

    def test_from_live_registry(self):
        out = gen_sub()
        assert "Architect" in out
        assert "Sentinel" in out


class TestIntegrations:
    def test_lists_services(self):
        out = gen_int()
        assert "Anthropic Claude" in out
        assert "Open-Meteo" in out
        assert "| Service |" in out


class TestVoice:
    def test_detects_components(self):
        out = gen_voice()
        assert "LLM streaming" in out or "_Voice loop not detected._" in out


class TestRecentActivity:
    def test_produces_output(self):
        out = gen_activity()
        assert "commit" in out.lower() or "_No commits" in out or "_unavailable" in out
