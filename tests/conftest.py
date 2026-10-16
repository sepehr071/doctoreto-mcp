import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
from mcp import Client

from doctoreto_mcp import http, search
from doctoreto_mcp.server import mcp

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = date(2026, 10, 6)  # the day (Tehran) the fixtures were recorded


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def params(request: httpx.Request) -> dict[str, list[str]]:
    """Query string as {key: [values]} (repeated keys such as consultation_types[] keep every value)."""
    out: dict[str, list[str]] = {}
    for k, v in request.url.params.multi_items():
        out.setdefault(k, []).append(v)
    return out


async def error(client, name: str, args: dict) -> str:
    """Call a tool that must fail and return its error text."""
    result = await client.call_tool(name, args)
    assert result.is_error, result.structured_content
    return result.content[0].text


async def live_call(client, name: str, args: dict) -> dict:
    """Call a tool against the real site, about one request per second, and fail on tool errors."""
    await asyncio.sleep(1)
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_http_client():
    """The shared httpx client is bound to one event loop; each test gets a new loop."""
    http.set_transport(None)
    yield
    http.set_transport(None)


@pytest.fixture
def api(monkeypatch):
    """Route table for a fake upstream keyed by URL path: api["/path"] = JSON body, (status, JSON body),
    or a callable(request) -> httpx.Response.

    Unknown paths return 404. Every request is appended to api.calls so tests can assert on what was sent.
    """

    class Routes(dict):
        calls: list[httpx.Request]

    routes = Routes()
    routes.calls = []
    # Fixture dates are judged against the day they were recorded (just after midnight, Tehran).
    monkeypatch.setattr(search, "today", lambda: RECORDED)
    monkeypatch.setattr(search, "now", lambda: datetime(2026, 10, 6, 1, 10))

    def handler(request: httpx.Request) -> httpx.Response:
        routes.calls.append(request)
        target = routes.get(request.url.path)
        if target is None:
            return httpx.Response(404, json={"items": [], "message": "", "errors": None})
        if callable(target):
            return target(request)
        if isinstance(target, tuple):
            return httpx.Response(target[0], json=target[1])
        return httpx.Response(200, json=target)

    http.set_transport(httpx.MockTransport(handler))
    return routes


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        call_tool = c.call_tool

        async def parsed(*args, **kwargs):
            result = await call_tool(*args, **kwargs)
            if not result.is_error:
                result.structured_content = json.loads(result.content[0].text)
            return result

        c.call_tool = parsed
        yield c
