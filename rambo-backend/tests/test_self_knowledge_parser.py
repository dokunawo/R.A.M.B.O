import pytest
from self_knowledge.parser import parse, serialize, render, Block


SAMPLE_DOC = """\
# Title

Hand-written intro paragraph.

## Capabilities

<!-- AUTO-START: capabilities -->
old generated content
<!-- AUTO-END: capabilities -->

## Middle Section

This is hand-written and should survive round-trips.

## Sub-agents

<!-- AUTO-START: subagents -->
old subagent content
line two
<!-- AUTO-END: subagents -->

## Footer

Hand-written footer."""


class TestParse:
    def test_identifies_auto_blocks(self):
        blocks = parse(SAMPLE_DOC)
        auto = [b for b in blocks if b.is_auto]
        assert len(auto) == 2
        assert auto[0].name == "capabilities"
        assert auto[1].name == "subagents"

    def test_identifies_hand_blocks(self):
        blocks = parse(SAMPLE_DOC)
        hand = [b for b in blocks if not b.is_auto]
        assert len(hand) == 3

    def test_auto_block_content_includes_markers(self):
        blocks = parse(SAMPLE_DOC)
        cap = [b for b in blocks if b.name == "capabilities"][0]
        assert "<!-- AUTO-START: capabilities -->" in cap.content
        assert "<!-- AUTO-END: capabilities -->" in cap.content
        assert "old generated content" in cap.content


class TestRoundTrip:
    def test_parse_serialize_is_noop(self):
        result = serialize(parse(SAMPLE_DOC))
        assert result == SAMPLE_DOC

    def test_hand_written_survives_render(self):
        def cap_gen():
            return "new capabilities content"

        rendered = render(SAMPLE_DOC, {"capabilities": cap_gen})
        assert "new capabilities content" in rendered
        assert "This is hand-written and should survive round-trips." in rendered
        assert "Hand-written intro paragraph." in rendered
        assert "Hand-written footer." in rendered

    def test_unregistered_auto_block_unchanged(self):
        rendered = render(SAMPLE_DOC, {})
        assert "old generated content" in rendered
        assert "old subagent content" in rendered

    def test_multiple_generators(self):
        rendered = render(SAMPLE_DOC, {
            "capabilities": lambda: "CAP_NEW",
            "subagents": lambda: "SUB_NEW",
        })
        assert "CAP_NEW" in rendered
        assert "SUB_NEW" in rendered
        assert "old generated content" not in rendered
        assert "old subagent content" not in rendered

    def test_render_then_roundtrip_stable(self):
        rendered = render(SAMPLE_DOC, {
            "capabilities": lambda: "stable content",
        })
        re_rendered = render(rendered, {
            "capabilities": lambda: "stable content",
        })
        assert rendered == re_rendered


class TestEdgeCases:
    def test_empty_doc(self):
        assert serialize(parse("")) == ""

    def test_no_auto_blocks(self):
        doc = "# Just text\n\nNo auto blocks here."
        assert serialize(parse(doc)) == doc

    def test_crlf_handling(self):
        crlf_doc = SAMPLE_DOC.replace("\n", "\r\n")
        normalized = crlf_doc.replace("\r\n", "\n")
        result = serialize(parse(normalized))
        assert result == SAMPLE_DOC

    def test_generator_failure_produces_placeholder(self):
        def bad_gen():
            raise RuntimeError("boom")

        rendered = render(SAMPLE_DOC, {"capabilities": bad_gen})
        assert "_unavailable" in rendered
        assert "This is hand-written and should survive round-trips." in rendered

    def test_hand_between_two_auto_blocks_survives(self):
        doc = (
            "<!-- AUTO-START: a -->\nA content\n<!-- AUTO-END: a -->\n"
            "Hand-written middle\n"
            "<!-- AUTO-START: b -->\nB content\n<!-- AUTO-END: b -->"
        )
        rendered = render(doc, {"a": lambda: "NEW_A", "b": lambda: "NEW_B"})
        assert "Hand-written middle" in rendered
        assert "NEW_A" in rendered
        assert "NEW_B" in rendered
