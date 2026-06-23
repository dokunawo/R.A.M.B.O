import pytest
import pytest_asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from usage_capture import record_usage, set_usage_repo, _repo


@pytest_asyncio.fixture
async def mock_repo():
    repo = AsyncMock()
    repo.record = AsyncMock()
    set_usage_repo(repo)
    yield repo
    set_usage_repo(None)


@pytest.mark.asyncio
async def test_record_usage_computes_cost_and_calls_repo(mock_repo):
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=500,
        cache_creation_input_tokens=200,
        cache_read_input_tokens=300,
    )
    await record_usage("claude-sonnet-4-6", usage)

    mock_repo.record.assert_called_once()
    call_kwargs = mock_repo.record.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["input_tokens"] == 1000
    assert call_kwargs["output_tokens"] == 500
    assert call_kwargs["cache_creation_input_tokens"] == 200
    assert call_kwargs["cache_read_input_tokens"] == 300
    assert call_kwargs["cost_usd"] > 0
    assert call_kwargs["source"] == "conversation"


@pytest.mark.asyncio
async def test_none_cache_fields_handled(mock_repo):
    usage = SimpleNamespace(
        input_tokens=500,
        output_tokens=200,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
    )
    await record_usage("claude-sonnet-4", usage)

    call_kwargs = mock_repo.record.call_args.kwargs
    assert call_kwargs["cache_creation_input_tokens"] == 0
    assert call_kwargs["cache_read_input_tokens"] == 0


@pytest.mark.asyncio
async def test_missing_cache_fields_handled(mock_repo):
    usage = SimpleNamespace(input_tokens=500, output_tokens=200)
    await record_usage("claude-sonnet-4", usage)

    call_kwargs = mock_repo.record.call_args.kwargs
    assert call_kwargs["cache_creation_input_tokens"] == 0
    assert call_kwargs["cache_read_input_tokens"] == 0


@pytest.mark.asyncio
async def test_repo_exception_swallowed(mock_repo):
    mock_repo.record.side_effect = RuntimeError("DB is on fire")
    usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    # Must not raise
    await record_usage("claude-sonnet-4", usage)


@pytest.mark.asyncio
async def test_no_repo_set_does_nothing():
    set_usage_repo(None)
    usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    await record_usage("claude-sonnet-4", usage)


@pytest.mark.asyncio
async def test_custom_source(mock_repo):
    usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    await record_usage("claude-sonnet-4", usage, source="summarizer")
    assert mock_repo.record.call_args.kwargs["source"] == "summarizer"
