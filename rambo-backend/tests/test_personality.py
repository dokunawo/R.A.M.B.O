import copy
import pytest

from personality import (
    append_voice_cue,
    build_system_prompt,
    load_personality,
    _VOICE_CUE,
)
from conversation import ConversationManager


class TestAppendVoiceCue:
    def test_cue_appears_in_last_user_message(self):
        msgs = [
            {"role": "user", "content": "What's the status?"},
        ]
        result = append_voice_cue(msgs)
        assert _VOICE_CUE in result[-1]["content"]

    def test_cue_not_stored_in_conversation_history(self):
        conv = ConversationManager()
        conv.add_user_message("Deploy the thing.")
        conv.add_assistant_message("Done.")
        conv.add_user_message("Status?")

        api_msgs = conv.get_messages_for_api()
        append_voice_cue(api_msgs)

        assert _VOICE_CUE in api_msgs[-1]["content"]
        for msg in conv.messages:
            assert _VOICE_CUE not in msg.get("content", "")

    def test_cue_skipped_for_block_list_content(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "abc", "content": "result"}
            ]},
        ]
        original = copy.deepcopy(msgs)
        result = append_voice_cue(msgs)
        assert result == original

    def test_cue_skipped_for_empty_messages(self):
        assert append_voice_cue([]) == []

    def test_cue_skipped_when_last_is_assistant(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey"},
        ]
        original = copy.deepcopy(msgs)
        result = append_voice_cue(msgs)
        assert result == original

    def test_cue_bans_generic_chatbot_filler(self):
        # The signature chatbot tells are still called out as things to avoid.
        assert "Great question" in _VOICE_CUE
        assert "I'd be happy to" in _VOICE_CUE

    def test_cue_directs_conversational_flow(self):
        cue = _VOICE_CUE.lower()
        assert "conversation" in cue or "flow" in cue or "natural" in cue
        assert "answer first" in cue

    def test_cue_contains_voice_examples(self):
        assert "All set" in _VOICE_CUE
        assert "a little vague" in _VOICE_CUE

    def test_cue_preserves_warmth_guardrail(self):
        cue_lower = _VOICE_CUE.lower()
        assert "never mock" in cue_lower or "cruel is not" in cue_lower or "never belittle" in cue_lower


class TestBuildSystemPrompt:
    def test_personality_block_is_cached(self):
        import cache_config
        blocks = build_system_prompt("personality text here")
        assert blocks[0]["cache_control"] == cache_config.cache_control()
        assert blocks[0]["cache_control"]["type"] == "ephemeral"
        assert blocks[0]["text"] == "personality text here"

    def test_tonal_checkpoint_is_uncached(self):
        blocks = build_system_prompt("personality")
        checkpoint_block = blocks[1]
        assert "cache_control" not in checkpoint_block
        assert "Tonal checkpoint" in checkpoint_block["text"]

    def test_checkpoint_contains_voice_discipline(self):
        blocks = build_system_prompt("personality")
        text = blocks[1]["text"]
        assert "FLOW" in text
        assert "LENGTH" in text
        assert "VOICE" in text

    def test_optional_context_appended(self):
        blocks = build_system_prompt("personality", context="Current time: noon")
        assert any("noon" in b["text"] for b in blocks)
        assert blocks[-1]["text"] == "Current time: noon"


class TestConversationManager:
    def test_deep_copy_isolation(self):
        conv = ConversationManager()
        conv.add_user_message("hello")
        api_msgs = conv.get_messages_for_api()
        api_msgs[0]["content"] = "MUTATED"
        assert conv.messages[0]["content"] == "hello"


class TestPersonalityFile:
    def test_personality_file_loads(self):
        text = load_personality()
        assert "R.A.M.B.O" in text
        assert "Sound like this" in text
        assert "Never sound like this" in text
