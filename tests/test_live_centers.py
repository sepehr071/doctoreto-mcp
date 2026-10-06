import pytest
from conftest import live_call as call

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_dt_search_centers(client):
    data = await call(client, "dt_search_centers", {"type": "pharmacy", "city": "tehran", "open_24h": True, "limit": 3})
    assert data["total"] > 20 and all(c["type"] == "pharmacy" and c["open_24h"] for c in data["centers"])


async def test_dt_search_centers_near(client):
    args = {"type": "hospital", "near_lat": 35.7, "near_lon": 51.4, "radius_km": 3, "limit": 5}
    data = await call(client, "dt_search_centers", args)
    dist = [c["distance_km"] for c in data["centers"]]
    assert dist and dist == sorted(dist) and dist[0] < 5


async def test_dt_center(client):
    found = await call(client, "dt_search_centers", {"type": "laboratory", "city": "tehran", "limit": 1})
    data = await call(client, "dt_center", {"center": found["centers"][0]["url"], "doctors": 3})
    assert data["type"] == "laboratory" and data["insurances"] and "lab_rules" in data
    assert data["url"].startswith("https://doctoreto.com/center/")
