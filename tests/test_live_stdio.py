import json
import sys

import pytest
from mcp import Client, StdioServerParameters

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_stdio_server():
    """Start the real server as a subprocess, list the tools and call one over stdio."""
    server = StdioServerParameters(command=sys.executable, args=["-m", "doctoreto_mcp.server"])
    async with Client(server) as c:
        assert len((await c.list_tools()).tools) == 14
        result = await c.call_tool("dt_cities", {"query": "تهران", "limit": 3})
        assert not result.is_error and json.loads(result.content[0].text)["cities"][0]["slug"] == "tehran"
