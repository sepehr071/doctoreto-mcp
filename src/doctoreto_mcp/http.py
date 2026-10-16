"""Shared async HTTP client for the Doctoreto APIs.

Every tool goes through `fetch`, which caps concurrency, sends the `app-version` header (some routes answer
HTTP 426 "you must update" without it), unwraps the `{items, message, errors}` envelope and turns HTTP failures
into `ToolError` messages the model can act on.
"""

from __future__ import annotations

import asyncio
import copy
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.doctoreto.com/api/web/patient/v1"
ROOT = "https://api.doctoreto.com"  # center search and map live here, without the /api/... prefix
SITE = "https://doctoreto.com"
STATICS = "https://statics.doctoreto.com"  # image proxy for s3:// avatar paths
BLOG = f"{SITE}/blog/wp-json/wp/v2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "app-version": "2.0.0",
}

MAX_CONCURRENCY = 4

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None
_cache: dict[tuple, tuple[float, Any]] = {}  # (url, sorted params) -> (expires, body), for static lookups only


class ApiError(ToolError):
    """A failed upstream call; `status` is the HTTP status (None for network errors)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit
    _transport, _client, _limit = transport, None, None
    _cache.clear()


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # Direct calls are fastest; ignore system proxy settings unless the user opts in
        # with DOCTORETO_MCP_PROXY.
        _client = httpx.AsyncClient(
            transport=_transport,
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
            trust_env=False,
            proxy=os.environ.get("DOCTORETO_MCP_PROXY") or None,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def fetch(url: str, params: dict[str, Any] | None = None, ttl: float = 0) -> Any:
    """GET an endpoint and return the parsed JSON body with the `{items, ...}` envelope unwrapped.

    `ttl` (seconds) caches the body for static lookups (specialities, cities, insurances); callers get a copy.
    """
    client, limit = _get_client()
    host = urlsplit(url).hostname
    params = {k: v for k, v in (params or {}).items() if v is not None}
    key = (url, tuple(sorted((k, str(v)) for k, v in params.items())))
    if ttl and (hit := _cache.get(key)) and hit[0] > time.monotonic():
        return copy.deepcopy(hit[1])
    r = None
    # A reused keep-alive connection is sometimes dropped; one retry after a short pause fixes it.
    for attempt in range(2):
        try:
            async with limit:
                r = await client.get(url, params=params)
            break
        except httpx.TimeoutException as e:
            raise ApiError(f"{host} did not answer in time. Try again in a moment.") from e
        except httpx.RequestError as e:
            if attempt == 0 and isinstance(e, (httpx.ConnectError, httpx.RemoteProtocolError)):
                await asyncio.sleep(1)
                continue
            raise ApiError(
                f"Could not reach {host} ({type(e).__name__}). Check the internet connection, or set DOCTORETO_MCP_PROXY."
            ) from e
    assert r is not None

    if r.status_code >= 400:
        raise ApiError(_status_message(r, host), r.status_code)
    if r.status_code == 204 or not r.content:  # some lookups answer 204 for "no data"
        return None
    try:
        body = r.json()
    except ValueError as e:
        raise ApiError(f"{host} returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    body = unwrap(body)
    if ttl:
        _cache[key] = (time.monotonic() + ttl, copy.deepcopy(body))
    return body


def unwrap(body: Any) -> Any:
    """The patient API wraps every body in {items, message, errors}; return `items`."""
    if isinstance(body, dict) and "items" in body and "errors" in body:
        return body["items"]
    return body


def _status_message(r: httpx.Response, host: str | None) -> str:
    code = r.status_code
    if code == 426:
        return f"{host} wants a newer app version (HTTP 426). The API changed; please report it."
    if code == 429:
        return f"{host} is rate limiting requests (HTTP 429). Wait a minute before retrying."
    if code == 401:
        return f"{host} needs a login for this (HTTP 401). This server is read-only and cannot log in."
    detail = error_text(r)
    if code == 404:
        return f"Not found on {host} (HTTP 404){': ' + detail if detail else ''}. Check the id or slug."
    if code >= 500:
        return f"{host} had a server error (HTTP {code}): {detail}. Try again later."
    return f"{host} rejected the request (HTTP {code}): {detail}"


def error_text(r: httpx.Response) -> str:
    """The Persian message plus the first field error, e.g. 'مقادیر نامعتبر است (start_date: ...)'."""
    try:
        body = r.json()
    except ValueError:
        return r.text[:200]
    if not isinstance(body, dict):
        return str(body)[:300]
    msg = str(body.get("message") or "")
    errors = body.get("errors")
    if isinstance(errors, dict) and errors:
        field, reasons = next(iter(errors.items()))
        reason = reasons[0] if isinstance(reasons, list) and reasons else reasons
        msg = f"{msg} ({field}: {reason})" if msg else f"{field}: {reason}"
    return msg[:300]
