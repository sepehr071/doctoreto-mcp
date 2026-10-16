import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.anyio

README = Path(__file__).parent.parent / "README.md"


async def test_readme_tool_tables_match_list_tools(client):
    """Every tool appears once in the README tables, and the tables list no tool the server lacks."""
    listed = re.findall(r"^\| `(dt_\w+)` \|", README.read_text(encoding="utf-8"), flags=re.M)
    tools = [t.name for t in (await client.list_tools()).tools]
    assert sorted(listed) == sorted(tools)
    assert f"All {len(tools)} tools" in README.read_text(encoding="utf-8")


async def test_tools_are_read_only_and_documented(client):
    for t in (await client.list_tools()).tools:
        assert t.annotations.read_only_hint and not t.annotations.destructive_hint, t.name
        assert t.title and t.description, t.name
        for name, prop in t.input_schema.get("properties", {}).items():
            assert prop.get("description"), f"{t.name}.{name} has no description"


async def test_tools_have_no_output_schema(client):
    assert all(t.output_schema is None for t in (await client.list_tools()).tools)
