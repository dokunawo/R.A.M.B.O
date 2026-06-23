import pytest
from pathlib import Path
from self_knowledge.drift import check, _load_allowlist


class TestDriftChecker:
    def test_clean_doc_no_findings(self):
        findings = check()
        assert findings == []

    def test_detects_broken_link(self, tmp_path):
        doc = tmp_path / "test.md"
        doc.write_text(
            "# Test\n\n"
            "See [broken](../../nonexistent_file.py) for details.\n\n"
            "<!-- AUTO-START: cap -->\nauto\n<!-- AUTO-END: cap -->\n"
        )
        findings = check(doc)
        assert len(findings) == 1
        assert findings[0].kind == "link"
        assert "nonexistent_file.py" in findings[0].reference

    def test_allowlist_suppresses(self, tmp_path):
        doc = tmp_path / "test.md"
        doc.write_text(
            "# Test\n\nSee [broken](../../nonexistent_file.py)\n"
        )
        allowlist = tmp_path / ".test-allowlist.txt"
        allowlist.write_text("../../nonexistent_file.py\n")
        findings = check(doc)
        assert findings == []

    def test_auto_blocks_skipped(self, tmp_path):
        doc = tmp_path / "test.md"
        doc.write_text(
            "# Test\n\n"
            "<!-- AUTO-START: cap -->\n"
            "See [broken](../../nonexistent_file.py)\n"
            "<!-- AUTO-END: cap -->\n"
        )
        findings = check(doc)
        assert findings == []


class TestAllowlist:
    def test_empty_when_missing(self, tmp_path):
        doc = tmp_path / "test.md"
        assert _load_allowlist(doc) == set()

    def test_loads_entries(self, tmp_path):
        doc = tmp_path / "test.md"
        al = tmp_path / ".test-allowlist.txt"
        al.write_text("# comment\nsome/path.py\n\nanother/file.ts\n")
        entries = _load_allowlist(doc)
        assert entries == {"some/path.py", "another/file.ts"}
