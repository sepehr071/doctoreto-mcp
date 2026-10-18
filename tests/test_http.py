import asyncio
import sys

import httpx
import pytest

from doctoreto_mcp import http

pytestmark = pytest.mark.anyio

OK = {"items": [{"a": 1}], "message": "", "errors": None}


async def test_headers_per_host(api):
    api["/api/web/patient/v1/x"] = OK
    api["/blog/wp-json/wp/v2/posts"] = []
    await http.fetch(f"{http.API}/x")
    await http.fetch(f"{http.BLOG}/posts")
    h = api.calls[0].headers
    assert h["Origin"] == "https://doctoreto.com" and h["sec-fetch-site"] == "same-site" and h["app-version"] == "2.0.0"
    assert h["Accept-Language"].startswith("fa-IR") and h["sec-fetch-mode"] == "cors"
    assert "User-Agent" not in h or "Chrome" not in h["User-Agent"]  # the UA comes from the impersonated profile
    b = api.calls[1].headers
    assert b["sec-fetch-site"] == "same-origin" and "Origin" not in b and "app-version" not in b


def test_is_challenge():
    html = {"content-type": "text/html"}
    assert http._is_challenge(httpx.Response(403, text="<html>Just a moment...</html>", headers=html))
    assert http._is_challenge(httpx.Response(503, text="<!doctype html><title>ArvanCloud</title>"))
    assert not http._is_challenge(httpx.Response(403, text="<html>Access Denied</html>"))
    assert not http._is_challenge(httpx.Response(403, json={"message": "no"}))
    assert not http._is_challenge(httpx.Response(200, text="<html></html>", headers=html))


async def test_network_error_retried_twice(api):
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    api["/api/web/patient/v1/x"] = boom
    with pytest.raises(http.ApiError, match="Could not reach api.doctoreto.com"):
        await http.fetch(f"{http.API}/x")
    assert len(api.calls) == 3


async def test_5xx_retried_but_403_and_404_are_not(api):
    hits = []

    def flaky(request):
        hits.append(1)
        return httpx.Response(503, text="down") if len(hits) == 1 else httpx.Response(200, json=OK)

    api["/api/web/patient/v1/x"] = flaky
    assert await http.fetch(f"{http.API}/x") == [{"a": 1}] and len(hits) == 2
    for status in (403, 404):
        api["/api/web/patient/v1/y"] = (status, {"message": "no"})
        with pytest.raises(http.ApiError):
            await http.fetch(f"{http.API}/y")
    assert sum(r.url.path.endswith("/y") for r in api.calls) == 2


async def test_retry_after_is_honoured_and_capped(monkeypatch, api):
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(http.asyncio, "sleep", fake_sleep)
    hits = []

    def limited(request):
        hits.append(1)
        if len(hits) == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "3"})
        if len(hits) == 2:
            return httpx.Response(503, json={}, headers={"Retry-After": "999"})
        return httpx.Response(200, json=OK)

    api["/api/web/patient/v1/x"] = limited
    await http.fetch(f"{http.API}/x")
    assert len(hits) == 3 and [w for w in waits if w] == [3, http.MAX_RETRY_WAIT]
    api["/api/web/patient/v1/y"] = (429, {})
    with pytest.raises(http.ApiError):
        await http.fetch(f"{http.API}/y")
    assert sum(r.url.path.endswith("/y") for r in api.calls) == 3  # gives up after MAX_RETRIES


async def test_proxy_list_rotates_on_connect_error(monkeypatch, api):
    monkeypatch.setenv("DOCTORETO_MCP_PROXY", "http://p1:1, http://p2:2")
    assert http._proxies() == ["http://p1:1", "http://p2:2"]

    def boom(request):
        raise httpx.ConnectError("down", request=request)

    api["/api/web/patient/v1/x"] = boom
    http._get_client()
    with pytest.raises(http.ApiError):
        await http._get(f"{http.API}/x", {})
    assert http._proxy_index == 1 and http._client is None
    monkeypatch.setenv("DOCTORETO_MCP_PROXY", "http://p1:1")
    http._get_client()
    with pytest.raises(http.ApiError):
        await http._get(f"{http.API}/x", {})
    assert http._client is not None  # a single proxy never rotates


async def test_stale_client_does_not_rotate(monkeypatch, api):
    monkeypatch.setenv("DOCTORETO_MCP_PROXY", "http://p1:1, http://p2:2")
    old, _ = http._get_client()
    http._next_proxy(old)
    new, _ = http._get_client()
    assert http._proxy_index == 1 and new is not old
    http._next_proxy(old)
    assert http._proxy_index == 1 and http._client is new


async def test_challenge_cleared_by_browser_once(monkeypatch, api):
    runs = []

    async def fake_browser(proxy):
        runs.append(proxy)
        await asyncio.sleep(0.01)
        return [{"name": "clearance", "value": "ok", "domain": ".doctoreto.com", "path": "/"}]

    monkeypatch.setattr(http, "_browser_cookies", fake_browser)

    def guarded(request):
        if "clearance=ok" not in request.headers.get("cookie", ""):
            return httpx.Response(403, text="<html>Just a moment</html>", headers={"content-type": "text/html"})
        return httpx.Response(200, json=OK)

    api["/api/web/patient/v1/x"] = guarded
    await asyncio.gather(http.fetch(f"{http.API}/x", {"a": 1}), http.fetch(f"{http.API}/x", {"a": 2}))
    assert len(runs) == 1  # the second caller reused the cookies the first one fetched

    api["/api/web/patient/v1/y"] = lambda r: httpx.Response(403, text="<html>Just a moment</html>")
    with pytest.raises(http.ApiError) as e:  # still blocked after the one retry: final
        await http.fetch(f"{http.API}/y")
    assert e.value.status == 403 and sum(r.url.path.endswith("/y") for r in api.calls) == 2


async def test_challenge_without_patchright(monkeypatch, api):
    monkeypatch.setitem(sys.modules, "patchright.async_api", None)
    api["/api/web/patient/v1/x"] = lambda r: httpx.Response(403, text="<html>Just a moment</html>")
    with pytest.raises(http.ApiError, match=r"doctoreto-mcp\[browser\].*patchright install chromium"):
        await http.fetch(f"{http.API}/x")
