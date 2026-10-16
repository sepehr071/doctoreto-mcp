"""One doctor: profile with bookable services and prices, free appointment slots, and reviews (doctor, center, offer)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from . import search
from .http import API, fetch
from .registry import tool
from .search import (
    PLACE_TYPES,
    TEHRAN,
    DoctorRef,
    FullText,
    Page,
    areas,
    avatar,
    clip,
    html_text,
    local,
    money,
    num,
    page_url,
    pages,
    ref,
    visit_type,
)

BOOKED_HERE = "نوبت گرفته از دکترتو"  # review tag: the visit was booked through Doctoreto


@tool("Doctor profile")
async def dt_doctor(doctor: DoctorRef, full_text: FullText = False) -> dict[str, Any]:
    """A doctor's profile with every bookable service, its price in Toman and its next free time.

    `services[]` lists each office and online visit with `consultation_id` (input of dt_free_slots), `fee`
    (office visit: paid at the office; online: the online price), `pay_online_now` (charged when booking),
    the office address and coordinates, and `next_free`. Also about text, review summary (count, recommend
    percent, 1-5 category averages), office waiting time, treated conditions and photo.
    Long texts are cut (about 800 chars); full_text returns them whole.
    Next: dt_free_slots, dt_reviews.
    """
    hid = ref(doctor, "doctor")
    profile, services = await asyncio.gather(
        fetch(f"{API}/doctors/{hid}"),
        fetch(f"{API}/doctors/{hid}/consultation", {"search": "[type != 4]"}),  # the site hides clinic offers here
    )
    if not isinstance(profile, dict) or not profile.get("id"):
        raise ToolError(f"Doctor {hid} not found.")
    rate = profile.get("rate") or {}
    wait = profile.get("presence_waiting_time") or {}
    return {
        "id": profile.get("id"),
        "name": profile.get("full_name"),
        "title": profile.get("title"),
        "medical_number": profile.get("medical_number"),
        "specialities": [{"slug": s.get("slug"), "name": s.get("name")} for s in profile.get("specialities") or []],
        "about": clip(html_text(profile.get("about")), 800, full_text),
        "reviews": rate.get("count"),
        "recommend_percent": rate.get("percent"),
        "category_stars": {r.get("title"): r.get("rate") for r in profile.get("rate_avg") or []},
        "office_wait": {"average": (wait.get("average") or "").strip() or None, "range": wait.get("range")}
        if wait
        else None,
        "bookings": profile.get("count_done_orders"),
        "services": [service(c, full_text) for c in services or []],
        "treats": [t.get("name") for t in profile.get("service_tags") or []][:20],
        "insurances": [i.get("name") for i in profile.get("insurances") or []],
        "url": page_url("doctor", profile.get("slug"), profile.get("id")),
        "image": avatar(profile.get("avatar_url")),
    }


@tool("Free appointment slots")
async def dt_free_slots(
    consultation_id: Annotated[
        int,
        Field(
            ge=1,
            le=10**11,
            description="Consultation id from dt_doctor services[], dt_center bookable[] or dt_offer variants[], e.g. 1943.",
        ),
    ],
    start_date: Annotated[
        date | None, Field(description="First day, Gregorian YYYY-MM-DD; default today (Tehran), e.g. '2026-10-14'.")
    ] = None,
    days: Annotated[int, Field(ge=1, le=31, description="Number of days to check from start_date.")] = 7,
) -> dict[str, Any]:
    """Free appointment times of one service (office visit, phone/video call, clinic offer, lab admission).

    Returns only days with free times: date, weekday, Jalali date and free start times (HH:MM, Tehran local).
    Past times today are dropped. `bookable_until` is the last day opened (often ~30 days ahead). Text
    consultations usually have no slots.
    """
    start = start_date or search.today()
    if start.year < 1900:
        raise ToolError("Dates must be Gregorian (YYYY-MM-DD), not Jalali: e.g. 1405-07-22 is 2026-10-14.")
    if start < search.today():
        raise ToolError(f"start_date {start} is in the past (today in Iran is {search.today()}).")
    last = start + timedelta(days=days - 1)
    found: dict[str, dict[str, Any]] = {}
    info: dict[str, Any] = {}

    async def window(cur: date) -> dict[str, Any]:  # the API returns at most 8 days per call (day_navigate max 7)
        info = await fetch(
            f"{API}/consultation-times/days",
            {"consultation_id": consultation_id, "start_date": str(cur), "day_navigate": 7},
        )
        return info or {}

    # The first window tells how far the doctor has opened days; the rest are independent, so fetch them together.
    infos = [await window(start)]
    end = infos[0].get("end_date") or ""
    later = [c for k in range(1, 4) if (c := start + timedelta(days=8 * k)) <= last and (not end or str(c) <= end)]
    infos += await asyncio.gather(*(window(c) for c in later))
    info = infos[0]
    for i in infos:
        for d in i.get("days") or []:
            if d.get("date"):
                found.setdefault(d["date"], d)
    now = local(info.get("now")) or search.now().strftime("%Y-%m-%d %H:%M")
    out = []
    for key in sorted(found):
        if not str(start) <= key <= str(last):
            continue
        times = [t for t in found[key].get("times") or [] if t.get("status") == 1 and f"{key} {t.get('time')}" > now]
        if times:
            out.append(
                {
                    "date": key,
                    "weekday": date.fromisoformat(key).strftime("%A"),
                    "jalali_date": times[0].get("shamsi_date"),
                    "free": [t.get("time") for t in times],
                }
            )
    result: dict[str, Any] = {
        "consultation_id": consultation_id,
        "checked": f"{start} .. {min(str(last), info.get('end_date') or str(last))}",
        "bookable_until": info.get("end_date"),
        "free_total": sum(len(d["free"]) for d in out),
        "days": out,
    }
    if not out:
        result["hint"] = (
            "No free times in this range. Try a later start_date (up to bookable_until) or another service."
        )
    return result


@tool("Reviews")
async def dt_reviews(
    of: Annotated[
        Literal["doctor", "center", "offer"], Field(description="Whose reviews: a doctor, a center or a clinic offer.")
    ],
    id: Annotated[
        str,
        Field(
            min_length=4,
            max_length=300,
            description="Hash id or page URL of the doctor, center or offer, e.g. 'xqbEWZ'.",
        ),
    ],
    page: Page = 1,
    limit: Annotated[int, Field(ge=1, le=30, description="Reviews per page.")] = 10,
    full_text: FullText = False,
) -> dict[str, Any]:
    """Patient reviews (doctors and centers newest first, offers oldest first): stars 1-5, recommends, text
    (cut at 400 chars unless full_text), labels, visit type, reason, office waiting time, date (Gregorian + Jalali) and reply.

    No sort or filter upstream: to find low ratings, page through (pages = total / limit).
    The summary (count, recommend percent, category averages) is in dt_doctor.
    """
    hid = ref(id, of)
    path = {"doctor": "doctors", "center": "places", "offer": "offers"}[of]
    data = await fetch(f"{API}/{path}/{hid}/reaction", {"page": page, "per_page": limit}) or {}
    return {**pages(data), "reviews": [_review(r, full_text) for r in data.get("data") or []]}


def service(c: dict[str, Any], full_text: bool = False) -> dict[str, Any]:
    """One bookable service from /doctors/{id}/consultation or /places/{id}/consultation."""
    kind = visit_type(c)
    p = c.get("place") or {}
    nf = c.get("next_free_time") or {}
    out: dict[str, Any] = {
        "consultation_id": c.get("id"),
        "visit_type": kind,
        "title": c.get("title"),
        "fee": money(c.get("total_price")),
        "pay_online_now": money(c.get("price")),
        "pays": {0: "at_office", 1: "online"}.get((c.get("pay_type") or {}).get("value")),
        "call_minutes": c.get("call_duration"),
        "next_free": local(nf.get("datetime")),
    }
    if nf.get("open_at") and not nf.get("is_next_free_time"):
        out["booking_opens_at"] = local(nf["open_at"])
    if kind == "office" or p.get("name"):
        loc = p.get("location") or {}
        out["fee_shown_on_site"] = c.get("show_price") == 1
        out["place"] = {
            "id": p.get("id"),
            "name": p.get("name"),
            "type": PLACE_TYPES.get(p.get("type")),
            "city": (p.get("city") or {}).get("name"),
            "areas": areas(p),
            "address": clip(p.get("full_address") or p.get("address"), 200, full_text),
            "lat": num(loc.get("lat")),
            "lon": num(loc.get("lon")),
            "center_url": page_url("center", p.get("slug"), p.get("id")) if p.get("type") else None,
        }
    notes = clip(html_text(c.get("description")), 300, full_text)
    if notes:
        out["notes"] = notes
    if c.get("insurances"):
        out["insurances"] = [i.get("name") for i in c["insurances"]]
    return out


def _review(r: dict[str, Any], full_text: bool = False) -> dict[str, Any]:
    text = r.get("comment_to_doctor") or r.get("comment_to_place") or r.get("comment_to_offer")
    if isinstance(text, dict):
        text = text.get("value")
    recommends = next((r[k] for k in ("rate_to_doctor", "suggest_the_place", "suggest_the_offer") if k in r), None)
    reply = r.get("reply")
    if isinstance(reply, dict):
        reply = reply.get("value") or reply.get("comment") or reply.get("text")
    return {
        "stars": r.get("rate") if r.get("rate") is not None else r.get("rate_to_offer"),
        "recommends": recommends,
        "text": clip(text, 400, full_text),
        "labels": r.get("labels") or r.get("badges") or [],
        "visit": r.get("consultation_type") or r.get("type"),
        "reason": r.get("reason_sickness"),
        "waiting": r.get("waiting_time_office"),
        "booked_here": r.get("tag") == BOOKED_HERE if r.get("tag") else None,
        "date": _tehran_day(r.get("created_at")),
        "jalali_date": r.get("shamsi_created_at"),
        "reply": clip(html_text(reply), 300, full_text) if isinstance(reply, str) else None,
    }


def _tehran_day(s: Any) -> str | None:
    """Review `created_at` is UTC ('2026-10-01T22:54:59.000000Z'): return the Tehran day ('2026-10-02'),
    which matches `shamsi_created_at` and the page."""
    if not isinstance(s, str) or not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10]
    return (t.astimezone(TEHRAN) if t.tzinfo else t).date().isoformat()
