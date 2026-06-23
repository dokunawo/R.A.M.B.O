import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.orchestrator import Orchestrator


class FakeWS:
    """Captures all broadcast_json calls for assertion."""
    def __init__(self):
        self.messages = []
        self.active = []

    async def broadcast(self, message: str):
        pass

    async def broadcast_json(self, data: dict):
        self.messages.append(data)

    def segments(self):
        return [m for m in self.messages if m.get("t") == "speak_segment"]


def make_orchestrator():
    o = Orchestrator.__new__(Orchestrator)
    o.ws = FakeWS()
    o.llm = None
    o.conversation = MagicMock()
    o.conversation.add_user_message = MagicMock()
    o.conversation.add_assistant_message = MagicMock()
    o.conversation.get_messages_for_api = MagicMock(return_value=[{"role": "user", "content": "test"}])
    o.personality_text = ""
    return o


class FakeStreamEvent:
    def __init__(self, text):
        self.type = "content_block_delta"
        self.delta = MagicMock()
        self.delta.type = "text_delta"
        self.delta.text = text


class FakeUsage:
    input_tokens = 100
    output_tokens = 50
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class FakeStream:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def get_final_message(self):
        return MagicMock(model="claude-sonnet-4-6", usage=FakeUsage())


def setup_llm(orch, text_chunks):
    orch.llm = MagicMock()
    events = [FakeStreamEvent(chunk) for chunk in text_chunks]
    orch.llm.messages.stream = MagicMock(return_value=FakeStream(events))


class TestSingleSentence:
    def test_single_sentence_one_final_segment(self):
        o = make_orchestrator()
        setup_llm(o, ["Hello there."])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        assert len(segs) == 1
        assert segs[0]["is_final"] is True
        assert segs[0]["seq"] == 0
        assert "Hello there." in segs[0]["text"]


class TestMultiSentence:
    def test_multi_sentence_segments(self):
        o = make_orchestrator()
        setup_llm(o, [
            "First sentence. ",
            "Second sentence. ",
            "Third sentence.",
        ])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        assert len(segs) == 3
        assert segs[0]["seq"] == 0
        assert segs[1]["seq"] == 1
        assert segs[2]["seq"] == 2
        assert segs[0]["is_final"] is False
        assert segs[1]["is_final"] is False
        assert segs[2]["is_final"] is True

    def test_all_share_same_base_turn_id(self):
        o = make_orchestrator()
        setup_llm(o, ["One. ", "Two. ", "Three."])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        base_ids = {s["base_turn_id"] for s in segs}
        assert len(base_ids) == 1

    def test_is_final_only_on_last(self):
        o = make_orchestrator()
        setup_llm(o, ["A. ", "B. ", "C. ", "D."])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        for s in segs[:-1]:
            assert s["is_final"] is False
        assert segs[-1]["is_final"] is True


class TestTokenByTokenStreaming:
    def test_tokens_accumulate_into_sentences(self):
        o = make_orchestrator()
        setup_llm(o, ["Hel", "lo ", "there. ", "How ", "are ", "you?"])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        assert len(segs) == 2
        assert "Hello there." in segs[0]["text"]
        assert "How are you?" in segs[1]["text"]
        assert segs[0]["is_final"] is False
        assert segs[1]["is_final"] is True


class TestNoLLM:
    def test_no_llm_emits_zero_segments(self):
        o = make_orchestrator()
        o.llm = None
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        assert len(segs) == 0


class TestSentenceSplitter:
    def test_abbreviations_not_split(self):
        o = make_orchestrator()
        setup_llm(o, ["Mr. Smith went home. He was tired."])
        asyncio.run(
            o._speak("test", ["plan"], ["result"])
        )
        segs = o.ws.segments()
        assert len(segs) == 2
        assert "Mr. Smith went home." in segs[0]["text"]
        assert "He was tired." in segs[1]["text"]
