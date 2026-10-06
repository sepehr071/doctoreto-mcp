import pytest
from conftest import error, fixture, params

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"


async def test_dt_search_centers(client, api):
    api["/search/places"] = fixture("centers.json")
    args = {
        "type": "laboratory",
        "city": "tehran",
        "name": "قلهك",
        "ownership": "private",
        "online_lab_admission": True,
    }
    data = (await client.call_tool("dt_search_centers", {**args, "open_24h": True, "limit": 1})).structured_content
    assert api.calls[0].url.host == "api.doctoreto.com" and api.calls[0].url.path == "/search/places"
    assert params(api.calls[0]) == {
        "type": ["laboratory"],
        "city_slug": ["tehran"],
        "query": ["قلهک"],
        "is_open_24_hours": ["1"],
        "ownership_type": ["2"],
        "active_laboratories": ["true"],
        "page": ["1"],
    }
    assert (data["total"], data["pages"]) == (791, 40) and len(data["centers"]) == 1
    c = data["centers"][0]
    assert c["id"] == "Yrrrqo" and c["type"] == "laboratory" and c["ownership"] == "private"
    assert c["areas"][0] == "قلهک" and c["lat"] == 35.77269104 and c["online_booking"] is True
    assert (c["reviews"], c["recommend_percent"]) == (212, 93)
    assert c["url"] == "https://doctoreto.com/center/gholhak-tehran-lab/Yrrrqo"


async def test_dt_search_centers_near(client, api):
    api["/search/places-geo"] = fixture("centers_geo.json")
    args = {"type": "hospital", "near_lat": 35.7, "near_lon": 51.4, "radius_km": 3}
    data = (await client.call_tool("dt_search_centers", args)).structured_content
    sent = params(api.calls[0])
    assert sent["min_latitude"] == ["35.672973"] and sent["max_latitude"] == ["35.727027"]
    assert sent["min_longitude"] == ["51.366719"] and sent["zoom"] == ["14"] and sent["type"] == ["hospital"]
    assert [c["id"] for c in data["centers"]] == ["AVrnak", "MnqaDl"]  # nearest first
    assert [c["distance_km"] for c in data["centers"]] == [5.2, 6.1]
    assert data["more_in_area"] == 74


async def test_dt_center(client, api):
    api[f"{V1}/places/YNrrOb"] = fixture("center.json")
    api[f"{V1}/places/YNrrOb/consultation"] = fixture("center_consultation.json")
    api[f"{V1}/places/YNrrOb/working-hours"] = fixture("center_hours.json")
    api[f"{V1}/places/YNrrOb/configs"] = fixture("center_configs.json")
    api[f"{V1}/doctors/places/YNrrOb"] = fixture("center_doctors.json")
    data = (await client.call_tool("dt_center", {"center": "YNrrOb", "doctors": 2})).structured_content
    assert data["name"] == "آزمایشگاه راز شیراز" and data["type"] == "laboratory" and data["city"] == "شیراز"
    assert data["hours"][0] == {"day": "شنبه تا چهارشنبه", "time": "06:30-23:59"}
    assert data["lab_rules"] == {
        "id_card_required": False,
        "prescription_file_allowed": True,
        "no_prescription_allowed": True,
    }
    assert data["insurances"][0] == "بیمه تکمیلی آتیه سازان" and data["departments"][0] == "پاتولوژی"
    lab = data["bookable"][0]
    assert (lab["consultation_id"], lab["visit_type"], lab["fee"]) == (201221, "lab_admission", 0)
    assert lab["next_free"] == "2026-10-06 06:30" and lab["place"]["id"] == "YNrrOb"
    assert data["doctors"]["total"] == 43 and data["doctors"]["list"][0]["id"] == "nqjvOq"
    assert data["url"] == "https://doctoreto.com/center/raz-shiraz-lap/YNrrOb"
    assert params(next(c for c in api.calls if c.url.path.startswith(f"{V1}/doctors/"))) == {
        "page": ["1"],
        "per_page": ["2"],
    }


async def test_dt_center_side_lists_are_optional(client, api):
    api[f"{V1}/places/YNrrOb"] = fixture("center.json")
    api[f"{V1}/places/YNrrOb/consultation"] = []
    data = (await client.call_tool("dt_center", {"center": "YNrrOb", "doctors": 0})).structured_content
    assert data["hours"] == [] and "lab_rules" not in data and data["bookable"] == [] and data["doctors"] == 0
    assert not any(c.url.path.startswith(f"{V1}/doctors/") for c in api.calls)


async def test_dt_center_office(client, api):
    api[f"{V1}/places/AVnxNA"] = {"items": {"type": 0, "status": 1, "city": None}, "message": "", "errors": None}
    api[f"{V1}/places/AVnxNA/consultation"] = []
    assert "private office" in await error(client, "dt_center", {"center": "AVnxNA"})
