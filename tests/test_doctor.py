import copy
import json

import httpx
import pytest
from conftest import error, fixture, params

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"
SLOTS = f"{V1}/consultation-times/days"


async def test_dt_doctor(client, api):
    api[f"{V1}/doctors/xqbEWZ"] = fixture("profile.json")
    api[f"{V1}/doctors/xqbEWZ/consultation"] = fixture("consultation.json")
    url = "https://doctoreto.com/doctor/dr-kambiz-parazaran/xqbEWZ"
    data = (await client.call_tool("dt_doctor", {"doctor": url})).structured_content
    assert params(api.calls[1]) == {"search": ["[type != 4]"]}
    assert all(c.headers["app-version"] == "2.0.0" for c in api.calls)
    assert data["url"] == url and data["medical_number"] == "97706"
    assert data["about"].startswith("بورد تخصصی") and "<" not in data["about"]
    assert (data["reviews"], data["recommend_percent"]) == (408, 92)
    assert data["category_stars"]["نحوه برخورد پزشک"] == 4.74
    assert data["office_wait"] == {"average": "36 دقیقه", "range": "15-45 دقیقه"}
    office = next(s for s in data["services"] if s["consultation_id"] == 1943)
    assert office["visit_type"] == "office" and office["fee"] == 250000 and office["pay_online_now"] == 0
    assert office["fee_shown_on_site"] is False and office["next_free"] == "2026-10-06 10:00"
    assert office["place"]["id"] == "AVnxNA" and office["place"]["lat"] == 35.76801155
    assert office["place"]["areas"][:2] == ["قلهک", "پاسداران"]  # real neighborhoods before districts
    building = data["services"][0]["place"]
    assert building["type"] == "medical_building"
    assert building["center_url"] == "https://doctoreto.com/center/ghaem-tehran-center/ZElKeK"
    phone = next(s for s in data["services"] if s["visit_type"] == "phone")
    # The profile says 2,250,000 for this call; the booking page and /consultation say 750,000.
    assert (phone["consultation_id"], phone["fee"], phone["pay_online_now"]) == (279292, 750000, 750000)
    assert phone["call_minutes"] == 15 and phone["pays"] == "online" and "place" not in phone
    assert "*******" not in json.dumps(data)  # no phone numbers (masked in the fixture)


async def test_dt_doctor_rejects_slug_and_unknown(client, api):
    assert "slug alone" in await error(client, "dt_doctor", {"doctor": "dr-kambiz-parazaran"})
    assert "HTTP 404" in await error(client, "dt_doctor", {"doctor": "ZZZZZZ"})


async def test_dt_free_slots(client, api):
    api[SLOTS] = fixture("slots.json")
    data = (await client.call_tool("dt_free_slots", {"consultation_id": 1943, "days": 3})).structured_content
    assert params(api.calls[0]) == {"consultation_id": ["1943"], "start_date": ["2026-10-06"], "day_navigate": ["7"]}
    assert len(api.calls) == 1
    assert data["checked"] == "2026-10-06 .. 2026-10-08" and data["bookable_until"] == "2026-11-05"
    # 2026-10-08 has no free time and is left out; 13:30 on the 7th is taken (status 2).
    assert [d["date"] for d in data["days"]] == ["2026-10-06", "2026-10-07"]
    first = data["days"][0]
    assert first == {
        "date": "2026-10-06",
        "weekday": "Tuesday",
        "jalali_date": "1405-07-14",
        "free": ["10:00", "10:10", "10:20", "10:30", "10:40", "10:50"],
    }
    assert data["days"][1]["free"][0] == "13:40" and data["free_total"] == 11


async def test_dt_free_slots_pages_windows_and_drops_past_times(client, api):
    first = fixture("slots.json")
    first["items"]["now"] = "2026-10-06 10:25:00"
    second = copy.deepcopy(first)
    second["items"]["days"] = [{**d, "date": f"2026-10-{14 + i}"} for i, d in enumerate(first["items"]["days"][:2])]

    def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params["start_date"]
        return httpx.Response(200, json=first if start == "2026-10-06" else second)

    api[SLOTS] = handler
    data = (await client.call_tool("dt_free_slots", {"consultation_id": 1943, "days": 10})).structured_content
    assert [c.url.params["start_date"] for c in api.calls] == ["2026-10-06", "2026-10-14"]
    assert data["days"][0]["free"][0] == "10:30"  # 10:00..10:20 are already past
    assert data["days"][-1]["date"] == "2026-10-15"


async def test_dt_free_slots_validation(client, api):
    assert "not Jalali" in await error(client, "dt_free_slots", {"consultation_id": 1943, "start_date": "1405-07-22"})
    assert "in the past" in await error(client, "dt_free_slots", {"consultation_id": 1943, "start_date": "2026-10-05"})
    api[SLOTS] = (404, {"items": [], "message": "مقدار مورد نظر یافت نشد یا آدرس اشتباه هست", "errors": None})
    assert "یافت نشد" in await error(client, "dt_free_slots", {"consultation_id": 1})


async def test_dt_free_slots_none_free(client, api):
    empty = fixture("slots.json")
    for d in empty["items"]["days"]:
        d["times"] = [{**t, "status": 2} for t in d["times"]]
    api[SLOTS] = empty
    data = (await client.call_tool("dt_free_slots", {"consultation_id": 1943})).structured_content
    assert data["days"] == [] and data["free_total"] == 0 and "later start_date" in data["hint"]


async def test_dt_reviews(client, api):
    api[f"{V1}/doctors/xqbEWZ/reaction"] = fixture("reviews.json")
    data = (await client.call_tool("dt_reviews", {"of": "doctor", "id": "xqbEWZ", "limit": 3})).structured_content
    assert params(api.calls[0]) == {"page": ["1"], "per_page": ["3"]}
    assert (data["total"], data["pages"]) == (408, 136)
    r = data["reviews"][2]
    assert (r["stars"], r["recommends"], r["text"], r["waiting"]) == (1, False, "عدم رضایت", "بیش از 90 دقیقه")
    assert r["date"] == "2026-09-26" and r["jalali_date"] == "1405/07/04" and r["booked_here"] is True
    assert "first_name" not in json.dumps(data) and "redacted" not in json.dumps(data)


async def test_dt_reviews_center_and_offer(client, api):
    api[f"{V1}/places/YNrrOb/reaction"] = fixture("center_reviews.json")
    api[f"{V1}/offers/ArraJa/reaction"] = fixture("offer_reviews.json")
    center = (
        await client.call_tool(
            "dt_reviews", {"of": "center", "id": "https://doctoreto.com/center/raz-shiraz-lap/YNrrOb"}
        )
    ).structured_content
    assert center["total"] == 359 and center["reviews"][1]["stars"] == 4.8
    # created_at 2026-10-01T22:54:59Z is 02:24 on the 2nd in Tehran, matching shamsi_created_at 1405/07/10.
    assert (center["reviews"][1]["date"], center["reviews"][1]["jalali_date"]) == ("2026-10-02", "1405/07/10")
    assert center["reviews"][0]["visit"] == "مشاوره پذیرش آنلاین آزمایشگاه" and center["reviews"][0]["recommends"]
    offer = (await client.call_tool("dt_reviews", {"of": "offer", "id": "ArraJa"})).structured_content
    assert offer["total"] == 78 and offer["reviews"][0]["text"] == "بسیار دقیق و با اخلاق هستن"
    assert offer["reviews"][0]["recommends"] is True and offer["reviews"][0]["stars"] is None
