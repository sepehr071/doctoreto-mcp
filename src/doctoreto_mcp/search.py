"""Doctor search and the lookups that feed it: suggestions, specialities, cities, neighborhoods, insurances.

Also holds the helpers shared by the other tool modules (ids and page URLs, prices, dates, text).
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .http import API, SITE, STATICS, fetch
from .registry import tool

TEHRAN = timezone(timedelta(hours=3, minutes=30))  # Iran has no daylight saving time since 2022

# Consultation `type.value` -> visit type name used in every tool output.
VISIT_TYPES = {
    0: "office",
    1: "phone",
    2: "text",
    3: "video",
    4: "clinic_in_person",
    5: "triage",
    6: "clinic_phone",
    7: "clinic_text",
    8: "clinic_video",
    9: "clinic_triage",
    10: "lab_admission",
    11: "instant_phone",
    12: "instant_text",
}
# dt_search_doctors visit_type -> consultation_types[] values the site sends.
VISIT_FILTER = {"office": [0], "phone": [1, 11], "text": [2, 12], "video": [3], "any_online": [1, 2, 3, 11, 12]}
SORTS = {"popular": "rate", "earliest": "free_time", "most_booked": "max_orders"}

TTL = 3600  # seconds to cache the static lookups (specialities, cities, insurances)

Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)]
Page = Annotated[int, Field(ge=1, le=500, description="1-based page number.")]
FullText = Annotated[bool, Field(description="Return complete texts instead of cutting long ones.")]
Lat = Annotated[float | None, Field(ge=24, le=40, description="Latitude of a point in Iran, e.g. 35.7575.")]
Lon = Annotated[float | None, Field(ge=44, le=64, description="Longitude of a point in Iran, e.g. 51.4100.")]
DoctorRef = Annotated[
    str,
    Field(
        min_length=6,
        max_length=300,
        description="Doctor hash id ('xqbEWZ') or page URL ('https://doctoreto.com/doctor/dr-kambiz-parazaran/xqbEWZ').",
    ),
]


@tool("Suggest doctors, specialities and centers")
async def dt_suggest(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=100,
            description="What the user typed, in Persian: a doctor's name, a speciality or a symptom, e.g. 'قلب' or 'پرآذران'.",
        ),
    ],
    city_id: Annotated[
        int | None,
        Field(ge=1, le=99999, description="Numeric city id from dt_cities to rank one city first, e.g. 2200 (Tehran)."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=10, description="Max items of each kind.")] = 5,
) -> dict[str, Any]:
    """Search-box suggestions: doctors (hash id), speciality slugs, service tags and centers for a free phrase.

    E.g. 'قلب' -> speciality 'cardiologist'. Doctors match by name, so for a speciality use the slug.
    Next: dt_search_doctors, dt_doctor or dt_center.
    """
    data = await fetch(f"{API}/suggestions/search", {"q": fa(query), "city_id": city_id, "per_page": limit}) or {}
    return {
        "doctors": [
            {
                "id": d.get("id"),
                "name": d.get("full_name"),
                "specialities": [s.get("name") for s in d.get("specialities") or []],
                "reviews": (d.get("rate") or {}).get("count"),
                "url": page_url("doctor", d.get("slug"), d.get("id")),
            }
            for d in data.get("doctors") or []
        ],
        "specialities": [
            {"slug": s.get("slug"), "name": s.get("name"), "level": s.get("type_name")}
            for s in data.get("specialities") or []
        ],
        "service_tags": [
            {"slug": t.get("slug"), "name": t.get("name"), "doctors": t.get("count")}
            for t in data.get("service_tags") or []
        ],
        "centers": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "type": PLACE_TYPES.get(p.get("type")),
                "city": (p.get("city") or {}).get("name"),
                "url": page_url("center", p.get("slug"), p.get("id")),
            }
            for p in data.get("places") or []
        ],
        "totals": data.get("total_counts"),
    }


@tool("Search doctors")
async def dt_search_doctors(
    city: Annotated[
        Slug | None, Field(description="City slug from dt_cities, e.g. 'tehran'. Omit for the whole country.")
    ] = None,
    speciality: Annotated[
        Slug | None, Field(description="Speciality slug from dt_specialities or dt_suggest, e.g. 'cardiologist'.")
    ] = None,
    neighborhood: Annotated[
        Slug | None, Field(description="Neighborhood slug from dt_neighborhoods, with city only, e.g. 'pasdaran'.")
    ] = None,
    service_tag: Annotated[
        Slug | None, Field(description="Service or symptom tag slug from dt_suggest, e.g. 'echocardiography'.")
    ] = None,
    name: Annotated[
        str | None,
        Field(min_length=2, max_length=80, description="Doctor's name in Persian (part is enough), e.g. 'پرآذران'."),
    ] = None,
    gender: Annotated[Literal["male", "female"] | None, Field(description="Only male or only female doctors.")] = None,
    insurance_ids: Annotated[
        list[Annotated[int, Field(ge=1, le=9999)]] | None,
        Field(
            max_length=10,
            description="Insurance ids from dt_insurances (any of them), e.g. [1]. Few doctors list insurances.",
        ),
    ] = None,
    visit_type: Annotated[
        Literal["office", "phone", "text", "video", "instant", "any_online"] | None,
        Field(description="Only doctors offering this visit; instant = on-call phone/text now."),
    ] = None,
    has_free_slot: Annotated[bool, Field(description="Only doctors with a free appointment slot.")] = False,
    sort: Annotated[
        Literal["default", "popular", "earliest", "most_booked"],
        Field(description="default = site ranking (sponsored first); popular = reviews and recommend rate."),
    ] = "default",
    near_lat: Lat = None,
    near_lon: Lon = None,
    page: Page = 1,
    limit: Annotated[int, Field(ge=1, le=25, description="Doctors per page (about 1 KB each).")] = 10,
) -> dict[str, Any]:
    """Search doctors by city, speciality, neighborhood, service tag, name, gender, insurance and visit type.

    Cards carry the hash `id` for dt_doctor; online prices are not in cards (use dt_doctor).
    Next: dt_doctor -> dt_free_slots.
    """
    if neighborhood and not city:
        raise ToolError("neighborhood needs city too, e.g. city='tehran', neighborhood='pasdaran'.")
    if (near_lat is None) != (near_lon is None):
        raise ToolError("Give both near_lat and near_lon, or neither.")
    params: dict[str, Any] = {
        "city_slug": city,
        "neighborhood_slug": neighborhood,
        "speciality_slug": speciality,
        "service_tag_slug": service_tag,
        "query": fa(name) if name else None,
        "gender": {"male": 1, "female": 2}.get(gender or ""),
        "insurances_id[]": insurance_ids or None,
        "consultation_types[]": VISIT_FILTER.get(visit_type or ""),
        "is_on_call": "true" if visit_type == "instant" else None,
        "has_free_time": "true" if has_free_slot else None,
        "sort": SORTS.get(sort),
        "location": f"{near_lat},{near_lon}" if near_lat is not None else None,
        "show_ads": "false" if name else None,
        "page": page,
        "per_page": limit,
    }
    data = await fetch(f"{API}/doctors", params) or {}
    # Pages mixed with sponsored doctors can carry one extra card, repeated on the next page.
    return {**pages(data), "doctors": [doctor_card(d) for d in (data.get("data") or [])[:limit]]}


@tool("Specialities")
async def dt_specialities(
    query: Annotated[
        str | None,
        Field(max_length=50, description="Part of the name or slug, e.g. 'قلب' or 'cardio'. Omit for all."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=300, description="Max entries (about 100 exist).")] = 150,
) -> dict[str, Any]:
    """List specialities with the slug dt_search_doctors needs; `total` counts all matches.

    `level` is specialist, subspecialist, fellowship or general; `parent` is the broader speciality
    (interventional cardiology -> cardiologist). Prefer `query`. Next: dt_search_doctors(speciality=slug).
    """
    tree = await fetch(f"{API}/specialities", ttl=TTL) or []
    q = fa(query).lower() if query else ""
    out = []
    for node, parent in _walk(tree, None):
        if node.get("type") == 1:  # root categories (medical, paramedical, dental) are not search filters
            continue
        hay = f"{node.get('name')} {node.get('full_name')} {node.get('slug')}".lower()
        if q and q not in hay:
            continue
        out.append(
            {
                "slug": node.get("slug"),
                "name": node.get("name"),
                "level": node.get("type_name"),
                "parent": parent.get("slug") if parent and parent.get("type") != 1 else None,
            }
        )
    return {"total": len(out), "specialities": out[:limit]}


@tool("Cities")
async def dt_cities(
    query: Annotated[
        str | None, Field(max_length=50, description="Part of the city name in Persian or the slug, e.g. 'شیراز'.")
    ] = None,
    speciality: Annotated[
        Slug | None,
        Field(description="Only cities that have doctors of this speciality, with counts, e.g. 'cardiologist'."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100, description="Max cities.")] = 20,
) -> dict[str, Any]:
    """Find a city's slug (for search filters) and numeric id (for dt_suggest); main cities first.

    With `speciality`: only main cities that have such doctors, with counts (a search may find more elsewhere).
    Next: dt_search_doctors(city=slug) or dt_neighborhoods.
    """
    if speciality:
        rows = await fetch(f"{API}/doctors/cities", {"speciality_slug": speciality}) or []
        cities = [
            {"slug": c.get("slug"), "name": c.get("name"), "id": c.get("id"), "doctors": c.get("count")} for c in rows
        ]
    else:
        rows = await fetch(f"{API}/regions/cities/available", ttl=TTL) or []
        rows = sorted(rows, key=lambda c: -(c.get("priority") or 0))
        cities = [
            {
                "slug": c.get("slug"),
                "name": c.get("name"),
                "id": c.get("id"),
                "province": (c.get("province") or {}).get("name"),
            }
            for c in rows
        ]
    if query:
        q = fa(query).lower()
        cities = [c for c in cities if q in f"{c['name']} {c['slug']}".lower()]
    return {"cities": cities[:limit]}


@tool("Neighborhoods")
async def dt_neighborhoods(
    city: Annotated[Slug, Field(description="City slug from dt_cities, e.g. 'tehran'.")],
    speciality: Annotated[
        Slug | None, Field(description="Count only doctors of this speciality, e.g. 'cardiologist'.")
    ] = None,
    query: Annotated[
        str | None,
        Field(max_length=50, description="Part of the neighborhood name in Persian or slug, e.g. 'پاسداران'."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=200, description="Max neighborhoods.")] = 30,
) -> dict[str, Any]:
    """Neighborhoods of a city (most doctors first) and nearby cities, each with a doctor count.

    District groupings (منطقه 3, غرب) are filters too. Next: dt_search_doctors(city=..., neighborhood=slug).
    """
    data = await fetch(f"{API}/doctors/nearby-areas", {"city_slug": city, "speciality_slug": speciality}) or {}
    hoods = sorted(data.get("nearby_neighborhoods") or [], key=lambda n: -(n.get("doctor_count") or 0))
    if query:
        q = fa(query).lower()
        hoods = [n for n in hoods if q in f"{n.get('name')} {n.get('slug')}".lower()]
    near = sorted(data.get("nearby_cities") or [], key=lambda n: -(n.get("doctor_count") or 0))
    return {
        "city": (data.get("city") or {}).get("name"),
        "neighborhoods": [
            {"slug": n.get("slug"), "name": n.get("name"), "doctors": n.get("doctor_count")} for n in hoods[:limit]
        ],
        "nearby_cities": [
            {"slug": c.get("slug"), "name": c.get("name"), "doctors": c.get("doctor_count")} for c in near[:10]
        ],
    }


@tool("Insurances")
async def dt_insurances(
    query: Annotated[
        str | None, Field(max_length=50, description="Part of the insurer's name in Persian, e.g. 'تامین' or 'آتیه'.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=200, description="Max insurers (about 84 exist).")] = 100,
) -> dict[str, Any]:
    """List basic and supplementary insurers with the ids dt_search_doctors(insurance_ids=...) takes.

    `total` counts all matches. Few doctors list insurances, so the filter narrows a search a lot; centers list
    theirs in dt_center.
    """
    rows = await fetch(f"{API}/insurances", {"sort": "[name=asc]"}, ttl=TTL) or []
    q = fa(query) if query else ""
    found = [
        {"id": i.get("id"), "name": i.get("name"), "kind": {1: "basic", 2: "supplementary"}.get(i.get("type"))}
        for i in rows
        if q in (i.get("name") or "")
    ]
    return {"total": len(found), "insurances": found[:limit]}


# Shared helpers -------------------------------------------------------------------------------------------

PLACE_TYPES = {
    0: "office",
    1: "infirmary",
    2: "laboratory",
    3: "hospital",
    4: "clinic",
    5: "imaging",
    6: "pharmacy",
    7: "medical_building",
}


def doctor_card(d: dict[str, Any]) -> dict[str, Any]:
    """Compact doctor card from a search, center or suggestion list item (their shapes differ a little)."""
    cons = d.get("consultations") or []
    fees = [money(c.get("offline_price")) for c in cons if visit_type(c) == "office"]
    offices = []
    for c in cons:
        p = c.get("place") or {}
        if visit_type(c) == "office" and p.get("name") and len(offices) < 3:
            offices.append(
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "city": (p.get("city") or {}).get("name"),
                    "areas": areas(p),
                    "address": clip(p.get("address"), 120),
                }
            )
    rate = d.get("rate") or {}
    earliest = free_time(d.get("free_next_consultation_time"))
    if earliest and (place_id := (d["free_next_consultation_time"].get("place") or {}).get("id")):
        earliest["place_id"] = place_id  # the office of that slot: `offices[].id`
    return {
        "id": d.get("id"),
        "name": d.get("full_name"),
        "title": d.get("title"),
        "specialities": [s.get("name") for s in d.get("specialities") or []],
        "visit_types": sorted({t for c in cons if (t := visit_type(c))}),
        "office_fee": min([f for f in fees if f], default=None),
        "offices": offices,
        "earliest_free": earliest,
        "reviews": rate.get("count"),
        "recommend_percent": rate.get("percent"),
        "bookings": d.get("count_done_orders"),
        "sponsored": bool(d.get("ads")),
        "url": page_url("doctor", d.get("slug"), d.get("id")),
        "image": avatar(d.get("avatar_url")),
    }


def avatar(s: Any) -> str | None:
    """Photo URL: the API gives 's3://drto/avatar/...' paths that the site serves through its image proxy."""
    if isinstance(s, str) and s.startswith("s3://"):
        return f"{STATICS}/rt:fit/s:300/plain/{s}"
    return s if isinstance(s, str) and s.startswith("https://") else None


def free_time(f: Any) -> dict[str, Any] | None:
    """`free_next_consultation_time` -> {at, jalali_date, visit_type}; the Persian relative word is dropped (it goes stale)."""
    if not isinstance(f, dict) or not f.get("date"):
        return None
    out = {"at": local(f.get("date")), "jalali_date": f.get("shamsi_day")}
    if kind := visit_type(f.get("consultation_type")):
        out["visit_type"] = kind
    return out


def visit_type(c: Any) -> str | None:
    """Visit type name from a consultation (or its `type`): {type: {value}} / {type: 3} / {value}."""
    if isinstance(c, dict) and "type" in c:
        c = c["type"]
    if isinstance(c, dict):
        c = c.get("value")
    return VISIT_TYPES.get(c) if isinstance(c, int) else None


def areas(place: dict[str, Any]) -> list[str]:
    """Neighborhood names of a place, real neighborhoods before district groupings (zero coordinates)."""
    hoods = place.get("neighborhoods") or []
    hoods = sorted(hoods, key=lambda n: str(n.get("latitude") or (n.get("location") or {}).get("lat")).startswith("0"))
    return [n.get("name") for n in hoods if n.get("name")]


def ref(value: str, kind: Literal["doctor", "center", "offer"]) -> str:
    """Hash id from a hash id or a doctoreto.com page URL (/doctor/<slug>/<id>, /center/<slug>/<id>, /offer/<id>)."""
    v = value.strip()
    if "/" in v:
        parts = [p for p in urlsplit(v if "//" in v else f"https://x/{v.lstrip('/')}").path.split("/") if p]
        v = parts[-1] if kind in parts[:-1] else ""
    if re.fullmatch(r"[A-Za-z0-9]{6}", v) or (kind == "offer" and re.fullmatch(r"\d{1,10}", v)):
        return v
    example = {"doctor": "/doctor/<slug>/<id>", "center": "/center/<slug>/<id>", "offer": "/offer/<id>"}[kind]
    raise ToolError(
        f"'{value}' is not a {kind} id. Pass the 6-character id from a search (e.g. 'xqbEWZ') or the page URL "
        f"(https://doctoreto.com{example}); a slug alone cannot be resolved, search by name instead."
    )


def page_url(kind: str, slug: Any, hash_id: Any) -> str | None:
    """Public page where a human books: doctoreto.com/doctor/<slug>/<id>, /center/<slug>/<id>, /offer/<id>."""
    if not hash_id:
        return None
    if kind == "offer":
        return f"{SITE}/offer/{hash_id}"
    return f"{SITE}/{kind}/{slug}/{hash_id}" if slug else None


def money(p: Any) -> int | None:
    """Toman amount from a price object {price, unit: 'تومان', format_price}; None when missing or negative (-1 = n/a)."""
    v = p.get("price") if isinstance(p, dict) else p
    return int(v) if isinstance(v, (int, float)) and v >= 0 else None


def num(v: Any) -> float | None:
    """Coordinates come as strings or floats; '0.00000000' (district groupings) means unknown."""
    try:
        return float(v) or None
    except (TypeError, ValueError):
        return None


def pages(data: dict[str, Any]) -> dict[str, Any]:
    return {"total": data.get("total", 0), "page": data.get("current_page", 1), "pages": data.get("last_page", 1)}


def local(s: Any) -> str | None:
    """'2026-10-06 10:00:00' or '2026-10-06T10:00:00' (Tehran local, no offset) -> '2026-10-06 10:00'."""
    return s[:16].replace("T", " ") if isinstance(s, str) and s else None


def today() -> date:
    return datetime.now(TEHRAN).date()


def now() -> datetime:
    return datetime.now(TEHRAN).replace(tzinfo=None)


def fa(s: str) -> str:
    """Arabic yeh/kaf -> Persian (the API stores Persian letters), outer spaces dropped."""
    return s.strip().replace("ي", "ی").replace("ك", "ک")


def clip(s: Any, n: int, full: bool = False) -> str | None:
    s = (s or "").strip() if isinstance(s, str) else ""
    return (s[: n - 1] + "…" if len(s) > n and not full else s) or None


def html_text(s: Any) -> str:
    """Plain text from HTML: tags dropped, entities decoded, blank lines collapsed."""
    text = re.sub(r"<(br|/p|/div|/li|/h\d)\s*/?>", "\n", s or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\r]+", " ", text)).strip()


def _walk(nodes: list[dict[str, Any]], parent: dict[str, Any] | None):
    for n in nodes:
        yield n, parent
        yield from _walk(n.get("nested_children") or [], n)
