"""Medical centers: hospitals, clinics, infirmaries, laboratories, imaging centers, pharmacies. Search, map and detail."""

from __future__ import annotations

import asyncio
import math
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .doctor import service
from .http import API, ROOT, ApiError, fetch
from .registry import tool
from .search import (
    PLACE_TYPES,
    Lat,
    Lon,
    Page,
    Slug,
    areas,
    clip,
    doctor_card,
    fa,
    html_text,
    num,
    page_url,
    pages,
    ref,
)

CenterType = Literal["hospital", "clinic", "infirmary", "laboratory", "imaging", "pharmacy"]
CenterRef = Annotated[
    str,
    Field(
        min_length=6,
        max_length=300,
        description="Center hash id from a search ('YNrrOb') or its page URL ('https://doctoreto.com/center/raz-shiraz-lap/YNrrOb').",
    ),
]


@tool("Search centers")
async def dt_search_centers(
    type: Annotated[CenterType | None, Field(description="Kind of center, e.g. 'laboratory'.")] = None,
    city: Annotated[Slug | None, Field(description="City slug from dt_cities, e.g. 'tehran'.")] = None,
    neighborhood: Annotated[
        Slug | None, Field(description="Neighborhood slug from dt_neighborhoods, with city only, e.g. 'pasdaran'.")
    ] = None,
    speciality: Annotated[
        Slug | None, Field(description="Department / speciality slug from dt_specialities, e.g. 'ophthalmologist'.")
    ] = None,
    service_tag: Annotated[Slug | None, Field(description="Service tag slug from dt_suggest, e.g. 'mri'.")] = None,
    name: Annotated[
        str | None, Field(min_length=2, max_length=80, description="Part of the center's name in Persian, e.g. 'قلب'.")
    ] = None,
    open_24h: Annotated[bool, Field(description="Only centers open around the clock (pharmacies, hospitals).")] = False,
    ownership: Annotated[Literal["state", "private"] | None, Field(description="State (public) or private.")] = None,
    online_lab_admission: Annotated[
        bool, Field(description="Only laboratories that take online admission bookings.")
    ] = False,
    near_lat: Lat = None,
    near_lon: Lon = None,
    radius_km: Annotated[
        float, Field(ge=0.3, le=20, description="With near_lat/near_lon: half-width of the square searched, in km.")
    ] = 2,
    page: Page = 1,
    limit: Annotated[int, Field(ge=1, le=20, description="Centers per page (the API pages by 20).")] = 10,
) -> dict[str, Any]:
    """Find hospitals, clinics, infirmaries, laboratories, imaging centers and pharmacies with filters.

    Each card has the hash `id` (input of dt_center), kind, state/private, 24h flag, address, coordinates,
    review count and recommend percent, doctor count and whether it takes online bookings. With near_lat and
    near_lon it searches a square around the point (map search) and sorts by distance; dense areas return only
    part of the centers as cards and count the rest in `more_in_area`. Insurance filters have no effect
    upstream: check `insurances` in dt_center. Next: dt_center, dt_reviews(of='center').
    """
    if neighborhood and not city:
        raise ToolError("neighborhood needs city too, e.g. city='tehran', neighborhood='pasdaran'.")
    if (near_lat is None) != (near_lon is None):
        raise ToolError("Give both near_lat and near_lon, or neither.")
    params: dict[str, Any] = {
        "type": type,
        "city_slug": city,
        "neighborhood_slug": neighborhood,
        "speciality_slug": speciality,
        "service_tag_slug": service_tag,
        "query": fa(name) if name else None,
        "is_open_24_hours": 1 if open_24h else None,
        "ownership_type": {"state": 1, "private": 2}.get(ownership or ""),
        "active_laboratories": "true" if online_lab_admission else None,
    }
    if near_lat is None or near_lon is None:
        data = await fetch(f"{ROOT}/search/places", {**params, "page": page}) or {}
        return {**pages(data), "centers": [center_card(c) for c in (data.get("data") or [])[:limit]]}

    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(near_lat)))
    box = {
        "min_latitude": round(near_lat - dlat, 6),
        "max_latitude": round(near_lat + dlat, 6),
        "min_longitude": round(near_lon - dlon, 6),
        "max_longitude": round(near_lon + dlon, 6),
        "zoom": 15 if radius_km <= 1 else 14 if radius_km <= 3 else 13 if radius_km <= 7 else 12,
    }
    data = await fetch(f"{ROOT}/search/places-geo", {**params, **box}) or {}
    cards = [center_card(c) for c in data.get("data") or []]
    for c in cards:
        c["distance_km"] = _km(near_lat, near_lon, c["lat"], c["lon"])
    cards.sort(key=lambda c: c["distance_km"] if c["distance_km"] is not None else 1e9)
    return {
        "centers": cards[:limit],
        "more_in_area": sum(k.get("count") or 0 for k in data.get("clusters") or []),
    }


@tool("Center details")
async def dt_center(
    center: CenterRef,
    doctors: Annotated[int, Field(ge=0, le=30, description="How many of its doctors to list (0 = none).")] = 10,
) -> dict[str, Any]:
    """A center's page: address, coordinates, departments, services, accepted insurances, attributes, opening
    hours, lab admission rules, bookable services with `consultation_id` (for dt_free_slots) and its doctors
    (hash ids for dt_doctor, with each doctor's earliest free slot).

    Doctor private offices (type office) have no center page: use dt_doctor for them. Booking needs an SMS
    login on the site: give the user `url`. Next: dt_free_slots, dt_doctor, dt_reviews(of='center').
    """
    hid = ref(center, "center")
    detail, services, hours, configs, docs = await asyncio.gather(
        fetch(f"{API}/places/{hid}"),
        fetch(f"{API}/places/{hid}/consultation", {"per_page": 100}),
        _optional(fetch(f"{API}/places/{hid}/working-hours")),
        _optional(fetch(f"{API}/places/{hid}/configs")),
        _optional(fetch(f"{API}/doctors/places/{hid}", {"page": 1, "per_page": doctors})) if doctors else _none(),
    )
    if not isinstance(detail, dict) or not detail.get("id"):
        if isinstance(detail, dict) and detail.get("type") == 0:
            raise ToolError(f"{hid} is a doctor's private office, which has no center page. Use dt_doctor.")
        raise ToolError(f"Center {hid} not found.")
    out = center_card(detail)
    out.update(
        {
            "description": clip(html_text(detail.get("description")), 800),
            "departments": [s.get("name") for s in detail.get("specialities") or []],
            "services": [t.get("name") for t in detail.get("tags") or []][:30],
            "insurances": [i.get("name") for i in detail.get("insurances") or []],
            "attributes": [a.get("title") for a in detail.get("place_attributes") or []],
            "hours": [{"day": h.get("day"), "time": h.get("time")} for h in hours or []],
            "bookable": [service(c) for c in services or []],
        }
    )
    if detail.get("type") == 2 and isinstance(configs, dict):
        out["lab_rules"] = {
            "id_card_required": configs.get("id_card_required"),
            "prescription_file_allowed": configs.get("prescription_file_allowed"),
            "no_prescription_allowed": configs.get("no_prescription_allowed"),
        }
    if isinstance(docs, dict):
        out["doctors"] = {
            "total": docs.get("total", 0),
            "list": [
                {k: v for k, v in doctor_card(d).items() if k in ("id", "name", "title", "earliest_free", "url")}
                for d in docs.get("data") or []
            ],
        }
    return out


def center_card(c: dict[str, Any]) -> dict[str, Any]:
    loc = c.get("location") or {}
    rate = c.get("rate") or {}
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "type": PLACE_TYPES.get(c.get("type")),
        "ownership": {1: "state", 2: "private"}.get(c.get("ownership_type")),
        "open_24h": bool(c.get("is_open_24_hours")),
        "city": (c.get("city") or {}).get("name"),
        "areas": areas(c),
        "address": clip(c.get("full_address") or c.get("address"), 200),
        "lat": num(loc.get("lat")),
        "lon": num(loc.get("lon")),
        "reviews": rate.get("count"),
        "recommend_percent": rate.get("percent"),
        "doctors": c.get("doctor_count"),
        "online_booking": bool(
            c.get("has_active_consultations")
            or c.get("laboratory_has_active_consultations")
            or c.get("has_free_consultation_time")
        ),
        "url": page_url("center", c.get("slug"), c.get("id")),
    }


async def _optional(coro: Any) -> Any:
    """Side lists (hours, rules, doctors) must not sink the whole center page."""
    try:
        return await coro
    except ApiError:
        return None


async def _none() -> None:
    return None


def _km(lat: float, lon: float, lat2: float | None, lon2: float | None) -> float | None:
    """Great-circle distance in km, 0.1 km precision."""
    if lat2 is None or lon2 is None:
        return None
    p1, p2 = math.radians(lat), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon) / 2) ** 2
    return round(12742 * math.asin(math.sqrt(a)), 1)
