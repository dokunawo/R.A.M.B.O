"""Tests for the tool registry."""

import pytest
from factory.tool_registry import ToolRegistry, ToolDef, build_default_registry


async def _noop(**kwargs):
    return "ok"


def test_register_and_list():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="test_tool", description="A test",
        input_schema={"type": "object", "properties": {}},
        execute=_noop,
    ))
    assert len(reg.list_all()) == 1
    assert reg.get("test_tool") is not None


def test_unregister():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="tmp", description="temp",
        input_schema={"type": "object", "properties": {}},
        execute=_noop,
    ))
    reg.unregister("tmp")
    assert reg.get("tmp") is None
    assert len(reg.list_all()) == 0


def test_factory_allowed_filter():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="public", description="ok",
        input_schema={"type": "object", "properties": {}},
        execute=_noop, factory_allowed=True,
    ))
    reg.register(ToolDef(
        name="secret", description="internal",
        input_schema={"type": "object", "properties": {}},
        execute=_noop, factory_allowed=False,
    ))
    allowed = reg.list_factory_allowed()
    assert len(allowed) == 1
    assert allowed[0].name == "public"


def test_to_anthropic_tools_format():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="my_tool", description="Does stuff",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        execute=_noop,
    ))
    tools = reg.to_anthropic_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "my_tool"
    assert "input_schema" in tools[0]
    assert "execute" not in tools[0]


def test_to_anthropic_tools_filtered_by_names():
    reg = ToolRegistry()
    for name in ("a", "b", "c"):
        reg.register(ToolDef(
            name=name, description=name,
            input_schema={"type": "object", "properties": {}},
            execute=_noop,
        ))
    tools = reg.to_anthropic_tools(names=["a", "c"])
    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert names == {"a", "c"}


def test_default_registry_has_tools():
    reg = build_default_registry()
    names = [t.name for t in reg.list_all()]
    assert "read_file" in names
    assert "write_file" in names
    assert "http_get" in names
    assert "list_files" in names
    assert "summarize_text" in names
    assert all(t.factory_allowed for t in reg.list_all())
