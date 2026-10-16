import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

V1 = "/api/web/patient/v1"
LONG = "الف" * 1000


def env(items):
    return {"items": items, "message": "", "errors": None}


async def test_dt_reviews_full_text(client, api):
    body = {"data": [{"comment_to_doctor": {"value": LONG}, "reply": {"value": LONG}}], "total": 1}
    api[f"{V1}/doctors/xqbEWZ/reaction"] = env(body)
    args = {"of": "doctor", "id": "xqbEWZ"}
    short = (await client.call_tool("dt_reviews", args)).structured_content["reviews"][0]
    full = (await client.call_tool("dt_reviews", {**args, "full_text": True})).structured_content["reviews"][0]
    assert (len(short["text"]), len(short["reply"])) == (400, 300)
    assert (full["text"], full["reply"]) == (LONG, LONG)


async def test_dt_doctor_full_text(client, api):
    profile = fixture("profile.json")
    profile["items"]["about"] = f"<p>{LONG}</p>"
    api[f"{V1}/doctors/xqbEWZ"] = profile
    api[f"{V1}/doctors/xqbEWZ/consultation"] = fixture("consultation.json")
    short = (await client.call_tool("dt_doctor", {"doctor": "xqbEWZ"})).structured_content
    full = (await client.call_tool("dt_doctor", {"doctor": "xqbEWZ", "full_text": True})).structured_content
    assert len(short["about"]) == 800 and full["about"] == LONG


async def test_dt_offer_full_text(client, api):
    offer = {"id": 1, "hash_id": "ArraJa", "description": LONG, "terms_of_use": LONG, "pre_payment_terms": LONG}
    api[f"{V1}/offers/ArraJa"] = env(offer)
    short = (await client.call_tool("dt_offer", {"offer": "ArraJa"})).structured_content
    full = (await client.call_tool("dt_offer", {"offer": "ArraJa", "full_text": True})).structured_content
    assert (len(short["description"]), len(short["terms"]), len(short["deposit_terms"])) == (800, 400, 300)
    assert (full["description"], full["terms"], full["deposit_terms"]) == (LONG, LONG, LONG)


async def test_dt_center_full_text(client, api):
    center = {"id": 7, "description": LONG, "full_address": LONG}
    api[f"{V1}/places/YNrrOb"] = env(center)
    api[f"{V1}/places/YNrrOb/consultation"] = env([])
    short = (await client.call_tool("dt_center", {"center": "YNrrOb", "doctors": 0})).structured_content
    full = (
        await client.call_tool("dt_center", {"center": "YNrrOb", "doctors": 0, "full_text": True})
    ).structured_content
    assert (len(short["description"]), len(short["address"])) == (800, 200)
    assert (full["description"], full["address"]) == (LONG, LONG)
