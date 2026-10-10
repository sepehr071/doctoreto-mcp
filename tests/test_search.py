import pytest
from conftest import error, fixture, params
from mcp.server.mcpserver.exceptions import ToolError

from doctoreto_mcp.search import local, money, ref

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"


async def test_dt_suggest(client, api):
    api[f"{V1}/suggestions/search"] = fixture("suggest.json")
    data = (await client.call_tool("dt_suggest", {"query": " قلب ", "city_id": 2200, "limit": 2})).structured_content
    assert data["specialities"][0] == {"slug": "cardiologist", "name": "قلب و عروق", "level": "تخصص"}
    assert data["doctors"][0]["url"] == "https://doctoreto.com/doctor/alireza-pak-ghalb/MVgkAZ"
    assert data["centers"][0] == {
        "id": "YwQkzM",
        "name": "کلینیک قلب و عروق بهار",
        "type": "clinic",
        "city": "تهران",
        "url": "https://doctoreto.com/center/bahar-heart-clinic/YwQkzM",
    }
    assert data["service_tags"][0]["slug"] == "cardia-ct-scan" and data["totals"]["places"] == 58
    assert params(api.calls[0]) == {"q": ["قلب"], "city_id": ["2200"], "per_page": ["2"]}


async def test_dt_search_doctors(client, api):
    api[f"{V1}/doctors"] = fixture("doctors.json")
    args = {
        "city": "tehran",
        "speciality": "cardiologist",
        "neighborhood": "pasdaran",
        "gender": "female",
        "insurance_ids": [1, 46],
        "visit_type": "phone",
        "has_free_slot": True,
        "sort": "earliest",
        "near_lat": 35.76,
        "near_lon": 51.46,
        "limit": 2,
    }
    data = (await client.call_tool("dt_search_doctors", args)).structured_content
    assert params(api.calls[0]) == {
        "city_slug": ["tehran"],
        "neighborhood_slug": ["pasdaran"],
        "speciality_slug": ["cardiologist"],
        "gender": ["2"],
        "insurances_id[]": ["1", "46"],
        "consultation_types[]": ["1", "11"],
        "has_free_time": ["true"],
        "sort": ["free_time"],
        "location": ["35.76,51.46"],
        "page": ["1"],
        "per_page": ["2"],
    }
    assert (data["total"], data["page"], data["pages"]) == (499, 1, 167)
    d = data["doctors"][1]
    assert d["id"] == "MdPdaM" and d["visit_types"] == ["office", "phone"]
    assert d["earliest_free"] == {"at": "2026-10-06 08:00", "jalali_date": "1405-07-14", "visit_type": "phone"}
    assert d["offices"][0]["areas"] == ["سهروردی"] and "phone" not in str(d["offices"])
    assert (d["reviews"], d["recommend_percent"], d["bookings"]) == (11, 91, 47)
    assert d["url"] == "https://doctoreto.com/doctor/dr-fatemeh-mottaghi-zadeh/MdPdaM"
    assert d["image"] == (
        "https://statics.doctoreto.com/rt:fit/s:300/plain/s3://drto/avatar/doctor/2024/12/yAXCUQ5u72i2AUX0ryWw1ViFaQ4MldQGBibqghU9.jpg"
    )
    first = data["doctors"][0]  # its earliest slot is at office 51805
    assert first["earliest_free"]["place_id"] == 51805 == first["offices"][0]["id"]


async def test_dt_search_doctors_keeps_limit(client, api):
    # Pages mixed with sponsored doctors return per_page + 1 cards (Tehran cardiologists page 2: 11 of 10).
    api[f"{V1}/doctors"] = fixture("doctors.json")
    data = (await client.call_tool("dt_search_doctors", {"limit": 1})).structured_content
    assert [d["id"] for d in data["doctors"]] == [fixture("doctors.json")["items"]["data"][0]["id"]]


async def test_dt_search_doctors_by_name(client, api):
    api[f"{V1}/doctors"] = fixture("doctors_byname.json")
    data = (await client.call_tool("dt_search_doctors", {"name": "مقدادي", "visit_type": "instant"})).structured_content
    sent = params(api.calls[0])
    assert sent["query"] == ["مقدادی"] and sent["show_ads"] == ["false"] and sent["is_on_call"] == ["true"]
    assert "consultation_types[]" not in sent
    d = data["doctors"][0]
    assert d["id"] == "ZpyYmq" and d["office_fee"] is None  # name-search cards carry no prices
    assert d["earliest_free"]["at"] == "2026-10-06 12:00"  # ISO 'T' form normalised
    assert d["visit_types"] == ["office", "phone"]


async def test_dt_search_doctors_validation(client, api):
    assert "neighborhood needs city" in await error(client, "dt_search_doctors", {"neighborhood": "pasdaran"})
    assert "near_lat and near_lon" in await error(client, "dt_search_doctors", {"near_lat": 35.7})
    api[f"{V1}/doctors"] = (422, {"message": "city slug انتخاب شده، معتبر نیست."})
    assert "HTTP 422): city slug" in await error(client, "dt_search_doctors", {"city": "nowhere-x"})


async def test_dt_specialities(client, api):
    api[f"{V1}/specialities"] = fixture("specialities.json")
    data = (await client.call_tool("dt_specialities", {})).structured_content
    rows = data["specialities"]
    assert "medical" not in [r["slug"] for r in rows]  # root categories are skipped
    assert rows[0] == {"slug": "orthopedist", "name": "ارتوپدی", "level": "تخصص", "parent": None}
    assert rows[1] == {"slug": "knee-surgeon", "name": "جراحی زانو", "level": "فلوشیپ", "parent": "orthopedist"}
    knee = (await client.call_tool("dt_specialities", {"query": "زانو"})).structured_content
    assert [r["slug"] for r in knee["specialities"]] == ["knee-surgeon"]


async def test_dt_cities(client, api):
    api[f"{V1}/regions/cities/available"] = fixture("cities.json")
    api[f"{V1}/doctors/cities"] = fixture("doctor_cities.json")
    data = (await client.call_tool("dt_cities", {"limit": 2})).structured_content
    assert data["cities"] == [
        {"slug": "tehran", "name": "تهران", "id": 2200, "province": "تهران"},
        {"slug": "shiraz", "name": "شیراز", "id": 1553, "province": "فارس"},
    ]
    found = (await client.call_tool("dt_cities", {"query": "mashhad"})).structured_content
    assert [c["id"] for c in found["cities"]] == [1718]
    spec = (await client.call_tool("dt_cities", {"speciality": "cardiologist"})).structured_content
    assert spec["cities"][0] == {"slug": "tehran", "name": "تهران", "id": 2200, "doctors": 1041}
    assert params(api.calls[-1]) == {"speciality_slug": ["cardiologist"]}


async def test_dt_neighborhoods(client, api):
    api[f"{V1}/doctors/nearby-areas"] = fixture("areas.json")
    data = (
        await client.call_tool("dt_neighborhoods", {"city": "tehran", "speciality": "cardiologist", "limit": 2})
    ).structured_content
    assert data["city"] == "تهران"
    assert data["neighborhoods"] == [
        {"slug": "west", "name": "غرب", "doctors": 163},
        {"slug": "mantaghe2", "name": "منطقه 2", "doctors": 155},
    ]
    assert data["nearby_cities"][0] == {"slug": "eslamshahr", "name": "اسلامشهر", "doctors": 23}
    assert params(api.calls[0]) == {"city_slug": ["tehran"], "speciality_slug": ["cardiologist"]}


async def test_dt_insurances(client, api):
    api[f"{V1}/insurances"] = fixture("insurances.json")
    data = (await client.call_tool("dt_insurances", {"query": "ارتش"})).structured_content
    assert data == {"insurances": [{"id": 46, "name": "بیمه ارتش", "kind": "basic"}]}
    assert params(api.calls[0]) == {"sort": ["[name=asc]"]}


def test_ref():
    assert ref("xqbEWZ", "doctor") == "xqbEWZ"
    assert ref("https://doctoreto.com/doctor/dr-kambiz-parazaran/xqbEWZ?x=1", "doctor") == "xqbEWZ"
    assert ref("doctoreto.com/center/raz-shiraz-lap/YNrrOb/", "center") == "YNrrOb"
    assert ref("https://doctoreto.com/offer/ArraJa", "offer") == "ArraJa"
    assert ref("129311", "offer") == "129311"
    for bad, kind in [("dr-kambiz-parazaran", "doctor"), ("https://doctoreto.com/center/a/YNrrOb", "doctor")]:
        with pytest.raises(ToolError, match="slug alone cannot be resolved"):
            ref(bad, kind)


def test_money_and_local():
    assert money({"price": 750000, "unit": "تومان"}) == 750000
    assert money({"price": -1}) is None and money({"price": None}) is None and money(None) is None
    assert local("2026-10-06 10:00:00") == "2026-10-06 10:00" == local("2026-10-06T10:00:00")
