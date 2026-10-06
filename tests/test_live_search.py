import pytest
from conftest import live_call as call

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_dt_suggest(client):
    data = await call(client, "dt_suggest", {"query": "قلب", "city_id": 2200, "limit": 3})
    assert "cardiologist" in [s["slug"] for s in data["specialities"]] and data["centers"]


async def test_dt_search_doctors(client):
    args = {"city": "tehran", "speciality": "cardiologist", "has_free_slot": True, "sort": "earliest", "limit": 5}
    data = await call(client, "dt_search_doctors", args)
    assert data["total"] > 50 and len(data["doctors"]) == 5
    times = [d["earliest_free"]["at"] for d in data["doctors"]]
    assert times == sorted(times) and all(d["url"].startswith("https://doctoreto.com/doctor/") for d in data["doctors"])


async def test_dt_search_doctors_by_name_and_visit_type(client):
    data = await call(client, "dt_search_doctors", {"name": "پرآذران", "limit": 5})
    assert "xqbEWZ" in [d["id"] for d in data["doctors"]]
    video = await call(client, "dt_search_doctors", {"visit_type": "video", "limit": 3})
    assert video["total"] > 10 and all("video" in d["visit_types"] for d in video["doctors"])


async def test_dt_specialities(client):
    data = await call(client, "dt_specialities", {"query": "قلب"})
    assert "cardiologist" in [s["slug"] for s in data["specialities"]]


async def test_dt_cities(client):
    data = await call(client, "dt_cities", {"query": "شیراز"})
    assert data["cities"][0]["slug"] == "shiraz" and data["cities"][0]["id"] == 1553


async def test_dt_neighborhoods(client):
    data = await call(client, "dt_neighborhoods", {"city": "tehran", "query": "پاسداران"})
    assert "pasdaran" in [n["slug"] for n in data["neighborhoods"]] and data["nearby_cities"]


async def test_dt_insurances(client):
    data = await call(client, "dt_insurances", {"query": "تامین اجتماعی"})
    assert data["insurances"] and data["insurances"][0]["kind"] == "basic"
