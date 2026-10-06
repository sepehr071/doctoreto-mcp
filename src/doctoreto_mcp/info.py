"""Health magazine (مجله سلامت دکترتو, WordPress) search."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .http import BLOG, fetch
from .registry import tool
from .search import clip, fa, html_text


@tool("Health articles")
async def dt_health_articles(
    query: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            description="Disease, test, drug or treatment in Persian, e.g. 'فشار خون' or 'آزمایش تیروئید'.",
        ),
    ],
    limit: Annotated[int, Field(ge=1, le=10, description="Max articles.")] = 5,
    text_chars: Annotated[
        int, Field(ge=0, le=8000, description="Characters of article text to include per article; 0 = summary only.")
    ] = 0,
) -> dict[str, Any]:
    """Search Doctoreto's health magazine (about 5,000 articles) for background on a condition, test or treatment.

    Returns title, link, publish date and a summary; set text_chars to read the articles. General information
    only, not medical advice: for a diagnosis book a doctor (dt_search_doctors).
    """
    fields = "id,date,link,title,excerpt" + (",content" if text_chars else "")
    params = {"search": fa(query), "orderby": "relevance", "per_page": limit, "_fields": fields}  # default is newest
    posts = await fetch(f"{BLOG}/posts", params) or []
    out = []
    for p in posts:
        a = {
            "title": html_text((p.get("title") or {}).get("rendered")),
            "url": p.get("link"),
            "published": (p.get("date") or "")[:10] or None,
            "summary": clip(html_text((p.get("excerpt") or {}).get("rendered")), 300),
        }
        if text_chars:
            a["text"] = clip(html_text((p.get("content") or {}).get("rendered")), text_chars)
        out.append(a)
    return {"articles": out}
