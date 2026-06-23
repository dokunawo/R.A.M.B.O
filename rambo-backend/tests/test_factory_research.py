"""Tests for Tier 1 — Research subagent."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from factory.research import run_research, _normalize_query
from factory.schemas import SkillsReport
from factory.repo import FactoryRepo


def _make_emit_block(report_dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_skills_report"
    block.id = "tu_1"
    block.input = report_dict
    return block


def _make_text_block(text="thinking..."):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_search_block():
    block = MagicMock()
    block.type = "tool_use"
    block.name = "web_search"
    block.id = "ws_1"
    block.input = {"query": "test"}
    return block


VALID_REPORT = {
    "domain": "PDF text extraction",
    "competencies": [
        "Extract text from PDF",
        "Handle scanned PDFs via OCR",
        "Parse tables from PDF",
        "Extract metadata",
    ],
    "tools_available": ["read_file"],
    "tools_wishlist": [
        {"name": "pdf_parse", "purpose": "Native PDF parsing", "external_dependency": "PyMuPDF"},
    ],
    "design_patterns": [
        "Pipeline pattern for multi-stage extraction",
        "Fallback to OCR when text layer is missing",
    ],
    "sources": [
        {"url": "https://example.com/1", "title": "PDF Guide", "excerpt": "..."},
        {"url": "https://example.com/2", "title": "OCR Best Practices", "excerpt": "..."},
        {"url": "https://example.com/3", "title": "PyMuPDF Docs", "excerpt": "..."},
    ],
}


@pytest.mark.asyncio
async def test_immediate_emit():
    """LLM emits the report on the first iteration."""
    client = MagicMock()
    response = MagicMock()
    response.content = [_make_emit_block(VALID_REPORT)]
    response.stop_reason = "tool_use"
    client.messages.create = AsyncMock(return_value=response)

    report = await run_research(
        llm_client=client,
        role_description="PDF text extraction",
        factory_tool_names=["read_file", "write_file"],
    )
    assert isinstance(report, SkillsReport)
    assert report.domain == "PDF text extraction"
    assert len(report.competencies) == 4
    client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_search_then_emit():
    """LLM searches first, then emits on the second call."""
    client = MagicMock()

    search_resp = MagicMock()
    search_resp.content = [_make_search_block()]
    search_resp.stop_reason = "tool_use"

    emit_resp = MagicMock()
    emit_resp.content = [_make_emit_block(VALID_REPORT)]
    emit_resp.stop_reason = "tool_use"

    client.messages.create = AsyncMock(side_effect=[search_resp, emit_resp])

    report = await run_research(
        llm_client=client,
        role_description="PDF text extraction",
        factory_tool_names=["read_file"],
    )
    assert isinstance(report, SkillsReport)
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_forced_tool_choice_on_last_iteration():
    """On the final iteration, tool_choice forces emit_skills_report."""
    client = MagicMock()

    text_resp = MagicMock()
    text_resp.content = [_make_text_block()]
    text_resp.stop_reason = "end_turn"

    emit_resp = MagicMock()
    emit_resp.content = [_make_emit_block(VALID_REPORT)]
    emit_resp.stop_reason = "tool_use"

    client.messages.create = AsyncMock(
        side_effect=[text_resp] * 7 + [emit_resp],
    )

    report = await run_research(
        llm_client=client,
        role_description="test",
        factory_tool_names=[],
    )
    assert isinstance(report, SkillsReport)
    last_call = client.messages.create.call_args
    assert last_call.kwargs.get("tool_choice") == {
        "type": "tool", "name": "emit_skills_report",
    }


@pytest.mark.asyncio
async def test_cache_hit(tmp_path):
    """If a cached report exists, no LLM call is made."""
    repo = FactoryRepo(db_path=tmp_path / "test.db")
    await repo.init_db()
    await repo.save_report(
        report_id="cached-1",
        query_key="pdf text extraction",
        report=VALID_REPORT,
    )

    client = MagicMock()
    client.messages.create = AsyncMock()

    report = await run_research(
        llm_client=client,
        role_description="PDF text extraction",
        factory_tool_names=["read_file"],
        repo=repo,
    )
    assert isinstance(report, SkillsReport)
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_report_persisted(tmp_path):
    """When repo is provided, the report is saved."""
    repo = FactoryRepo(db_path=tmp_path / "test.db")
    await repo.init_db()

    client = MagicMock()
    response = MagicMock()
    response.content = [_make_emit_block(VALID_REPORT)]
    response.stop_reason = "tool_use"
    client.messages.create = AsyncMock(return_value=response)

    await run_research(
        llm_client=client,
        role_description="PDF text extraction",
        factory_tool_names=[],
        repo=repo,
    )
    cached = await repo.get_cached_report("pdf text extraction")
    assert cached is not None


def test_normalize_query():
    assert _normalize_query("  PDF  Text  Extraction  ") == "pdf text extraction"
    assert _normalize_query("Hello\n\tWorld") == "hello world"
