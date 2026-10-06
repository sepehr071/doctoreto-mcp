import pytest
from conftest import live_call as call

pytestmark = [pytest.mark.anyio, pytest.mark.live]

DOCTOR = "xqbEWZ"  # cardiologist in Tehran: two offices and a phone consultation, 400+ reviews


async def test_dt_doctor(client):
    data = await call(client, "dt_doctor", {"doctor": f"https://doctoreto.com/doctor/dr-kambiz-parazaran/{DOCTOR}"})
    assert data["id"] == DOCTOR and data["reviews"] > 100 and data["category_stars"]
    kinds = {s["visit_type"] for s in data["services"]}
    assert "office" in kinds and all(s["consultation_id"] for s in data["services"])
    phone = [s for s in data["services"] if s["visit_type"] == "phone"]
    assert not phone or phone[0]["fee"] == phone[0]["pay_online_now"] > 0


async def test_dt_free_slots(client):
    found = await call(
        client, "dt_search_doctors", {"city": "tehran", "has_free_slot": True, "sort": "earliest", "limit": 5}
    )
    doctor = await call(client, "dt_doctor", {"doctor": found["doctors"][0]["id"]})
    service = next(s for s in doctor["services"] if s["next_free"])
    data = await call(client, "dt_free_slots", {"consultation_id": service["consultation_id"], "days": 10})
    assert data["free_total"] > 0 and data["days"][0]["free"]
    assert all(d["date"] >= data["checked"][:10] for d in data["days"])


async def test_dt_reviews(client):
    data = await call(client, "dt_reviews", {"of": "doctor", "id": DOCTOR, "limit": 5})
    assert data["total"] > 100 and len(data["reviews"]) == 5
    assert all(1 <= r["stars"] <= 5 and r["date"] for r in data["reviews"])
