import pytest
from conftest import live_call as call

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_dt_search_offers(client):
    args = {"city": "tehran", "min_price": 1000000, "max_price": 2000000, "limit": 5}
    data = await call(client, "dt_search_offers", args)
    assert data["total"] > 0 and all(1000000 <= o["price"] <= 2000000 for o in data["offers"])


async def test_dt_offer(client):
    data = await call(client, "dt_offer", {"offer": "https://doctoreto.com/offer/ArraJa"})
    assert data["id"] == "ArraJa" and data["price"] > 0 and data["variants"][0]["consultation_id"]
