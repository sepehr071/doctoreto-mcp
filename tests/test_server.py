import json

import pytest
from conftest import fixture
from mcp import Client

from doctoreto_mcp.server import mcp, strip_empty, untitle

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"


async def test_wire_format_is_one_compact_text_block(api):
    api[f"{V1}/specialities"] = fixture("specialities.json")
    async with Client(mcp) as c:  # the raw client: conftest's `client` fixture re-parses the text
        result = await c.call_tool("dt_specialities", {"query": "زانو"})
        tools = (await c.list_tools()).tools
    assert len(result.content) == 1 and result.structured_content is None
    text = result.content[0].text
    assert "\n" not in text and "null" not in text and ": " not in text
    assert json.loads(text)["specialities"][0]["slug"] == "knee-surgeon"
    assert all(t.output_schema is None for t in tools)
    assert not any("title" in p for t in tools for p in t.input_schema["properties"].values())


def test_strip_empty_and_untitle():
    assert strip_empty({"a": None, "b": "", "c": [], "d": {}, "e": False, "f": 0, "g": [{"h": None, "i": 1}]}) == {
        "e": False,
        "f": 0,
        "g": [{"i": 1}],
    }
    assert untitle({"title": "X", "properties": {"title": {"title": "T", "type": "string"}}}) == {
        "properties": {"title": {"type": "string"}}
    }
