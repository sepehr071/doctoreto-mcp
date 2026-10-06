import pytest
from conftest import error, fixture, params

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"


async def test_dt_search_offers(client, api):
    api[f"{V1}/offers"] = fixture("offers.json")
    args = {
        "query": "اکو",
        "city": "tehran",
        "speciality": "cardiologist",
        "min_price": 1000000,
        "max_price": 2000000,
        "doctor": "https://doctoreto.com/doctor/dr-alireza-dadpay/MkaNbq",
        "center": "ZWpOLy",
        "limit": 1,
    }
    data = (await client.call_tool("dt_search_offers", args)).structured_content
    assert params(api.calls[0]) == {
        "query": ["اکو"],
        "city_slug": ["tehran"],
        "speciality_slug": ["cardiologist"],
        "min_price": ["1000000"],
        "max_price": ["2000000"],
        "doctor_id": ["MkaNbq"],
        "place_id": ["ZWpOLy"],
        "page": ["1"],
    }
    assert data["total"] == 43 and len(data["offers"]) == 1
    o = data["offers"][0]
    assert o["id"] == "YmexLx" and o["name"] == "نوار قلب"  # trailing arrow emoji dropped
    assert (o["price"], o["price_after_discount"], o["payment"], o["pay_online"]) == (
        413000,
        413000,
        "deposit_online",
        100000,
    )
    assert o["consultation_id"] == 408247 and o["next_free"] == {"at": "2026-10-06 11:00", "jalali_date": "1405-07-14"}
    assert o["doctor"]["id"] == "MdvEao" and o["url"] == "https://doctoreto.com/offer/YmexLx"


async def test_dt_offer(client, api):
    api[f"{V1}/offers/ArraJa"] = fixture("offer.json")
    data = (await client.call_tool("dt_offer", {"offer": "https://doctoreto.com/offer/ArraJa"})).structured_content
    assert data["name"] == "سونوگرافی واریس پا" and data["price"] == 3520000 and data["stars"] == 4.9
    assert data["available"] is True and data["expires"] == "2026-12-23"
    assert data["description"].startswith("درباره پزشک ارائه دهنده")
    v = data["variants"][0]
    assert (v["consultation_id"], v["visit_type"], v["deposit"]) == (650321, "clinic_in_person", 100000)
    assert data["doctor"]["url"] == "https://doctoreto.com/doctor/dr-alireza-dadpay/MkaNbq"


async def test_dt_offer_unknown(client, api):
    api[f"{V1}/offers/ZZZZZZ"] = {"items": [], "message": "", "errors": None}  # unknown ids answer 200 with a list
    assert "not found" in await error(client, "dt_offer", {"offer": "ZZZZZZ"})
