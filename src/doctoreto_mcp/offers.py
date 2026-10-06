"""Doctoreto clinic offers (دکترتو کلینیک): fixed-price services and packages such as ultrasound, laser, dental work."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .http import API, fetch
from .registry import tool
from .search import DoctorRef, Page, Slug, clip, fa, free_time, html_text, money, page_url, pages, ref, visit_type

PAYMENT = {0: "at_place", 1: "online", 2: "deposit_online", 3: "after_inspection"}
OfferRef = Annotated[
    str,
    Field(
        min_length=4,
        max_length=300,
        description="Offer hash id ('ArraJa'), numeric id ('129311') or page URL ('https://doctoreto.com/offer/ArraJa').",
    ),
]


@tool("Search clinic offers")
async def dt_search_offers(
    query: Annotated[
        str | None, Field(min_length=2, max_length=80, description="Service in Persian, e.g. 'سونوگرافی' or 'لیزر'.")
    ] = None,
    city: Annotated[Slug | None, Field(description="City slug from dt_cities, e.g. 'tehran'.")] = None,
    neighborhood: Annotated[Slug | None, Field(description="Neighborhood slug, e.g. 'pasdaran'.")] = None,
    speciality: Annotated[Slug | None, Field(description="Speciality slug, e.g. 'cardiologist'.")] = None,
    service_tag: Annotated[Slug | None, Field(description="Service tag slug, e.g. 'rhinoplasty'.")] = None,
    min_price: Annotated[
        int | None, Field(ge=0, le=10**10, description="Minimum price in Toman, e.g. 1000000.")
    ] = None,
    max_price: Annotated[
        int | None, Field(ge=0, le=10**10, description="Maximum price in Toman, e.g. 2000000.")
    ] = None,
    doctor: Annotated[DoctorRef | None, Field(description="Only offers of this doctor (hash id or page URL).")] = None,
    center: Annotated[
        str | None,
        Field(min_length=6, max_length=300, description="Only offers at this place (hash id), e.g. 'ZWpOLy'."),
    ] = None,
    page: Page = 1,
    limit: Annotated[
        int, Field(ge=1, le=40, description="Offers to return from the page (the API pages by about 40).")
    ] = 10,
) -> dict[str, Any]:
    """Search Doctoreto clinic offers: fixed-price procedures and packages (ultrasound, echo, laser, dental,
    check-ups) sold by doctors and centers.

    Each card has the price and price after discount (Toman), what is paid online (`pay_online`: the deposit
    when `payment` is deposit_online, the rest at the place), provider doctor, place, earliest free time,
    star rating and the default `consultation_id` for dt_free_slots. Unknown sort upstream: compare prices
    yourself. Next: dt_offer, dt_free_slots, dt_reviews(of='offer').
    """
    params = {
        "query": fa(query) if query else None,
        "city_slug": city,
        "neighborhood_slug": neighborhood,
        "speciality_slug": speciality,
        "service_tag_slug": service_tag,
        "min_price": min_price,
        "max_price": max_price,
        "doctor_id": ref(doctor, "doctor") if doctor else None,
        "place_id": ref(center, "center") if center else None,
        "page": page,
    }
    data = await fetch(f"{API}/offers", params) or {}
    return {**pages(data), "offers": [offer_card(o) for o in (data.get("data") or [])[:limit]]}


@tool("Clinic offer details")
async def dt_offer(offer: OfferRef) -> dict[str, Any]:
    """One clinic offer in full: price, discount, deposit, who performs it and where, description, terms,
    capacity, expiry, rating, and its bookable variants with `consultation_id` for dt_free_slots.

    Booking and payment need an SMS login on the site: give the user `url`.
    """
    oid = ref(offer, "offer")
    o = await fetch(f"{API}/offers/{oid}")
    if not isinstance(o, dict) or not o.get("id"):  # unknown ids answer 200 with items: []
        raise ToolError(f"Offer {oid} not found.")
    out = offer_card(o)
    out.update(
        {
            "available": o.get("is_available"),
            "remaining": o.get("remaining_capacity"),
            "description": clip(html_text(o.get("description")), 1500),
            "terms": clip(html_text(o.get("terms_of_use")), 600),
            "deposit_terms": clip(html_text(o.get("pre_payment_terms")), 400),
            "variants": [
                {
                    "consultation_id": v.get("consultation_id"),
                    "title": v.get("title"),
                    "visit_type": visit_type(v),
                    "price": money(v.get("price")),
                    "price_after_discount": money(v.get("discount_price")),
                    "deposit": money(v.get("pre_payment_price")),
                    "next_free": free_time(v.get("next_free_time")),
                    "place": (v.get("place") or {}).get("name"),
                }
                for v in o.get("consultations") or []
            ],
        }
    )
    return out


def offer_card(o: dict[str, Any]) -> dict[str, Any]:
    pay = o.get("payment_type")
    price, final = money(o.get("price")), money(o.get("discount_price"))
    deposit = money(o.get("pre_payment_price"))
    pr = o.get("price_range") or {}
    doc, place = o.get("doctor") or {}, o.get("place") or {}
    point = o.get("point") or {}
    return {
        "id": o.get("hash_id"),
        "name": (o.get("name") or "").replace("⬅️", "").strip() or None,
        "price": price,
        "price_after_discount": final,
        "discount_percent": o.get("discount") or 0,
        "payment": PAYMENT.get(pay),
        "pay_online": {0: 0, 1: final, 2: deposit}.get(pay),
        "price_range": {"min": pr.get("min"), "max": pr.get("max")} if pay == 3 else None,
        "doctor": {
            "id": doc.get("hash_id"),
            "name": doc.get("full_name"),
            "url": page_url("doctor", doc.get("slug"), doc.get("hash_id")),
        }
        if doc
        else None,
        "place": place.get("name"),
        "address": clip(place.get("address"), 160),
        "city": (o.get("city") or {}).get("name"),
        "next_free": free_time(o.get("next_free_time")),
        "stars": point.get("average"),
        "reviews": point.get("count"),
        "consultation_id": o.get("consultation_id")
        or next((c.get("consultation_id") for c in o.get("consultations") or []), None),
        "expires": (o.get("expire_at") or "")[:10] or None,
        "url": page_url("offer", None, o.get("hash_id")),
    }
