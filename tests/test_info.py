import pytest
from conftest import fixture, params

from doctoreto_mcp.search import html_text

pytestmark = pytest.mark.anyio

POSTS = "/blog/wp-json/wp/v2/posts"


async def test_dt_health_articles(client, api):
    api[POSTS] = fixture("blog.json")
    data = (
        await client.call_tool("dt_health_articles", {"query": "فشار خون", "limit": 2, "text_chars": 120})
    ).structured_content
    assert api.calls[0].url.host == "doctoreto.com"
    assert params(api.calls[0]) == {
        "search": ["فشار خون"],
        "orderby": ["relevance"],
        "per_page": ["2"],
        "_fields": ["id,date,link,title,excerpt,content"],
    }
    a = data["articles"][0]
    assert a["title"] == "بهترین قرص برای ورم پا کدام است؟" and a["published"] == "2026-10-05"
    assert a["url"] == "https://doctoreto.com/blog/pill-feet-edema/"
    assert len(a["text"]) <= 120 and "<" not in a["text"] and "<" not in a["summary"]


async def test_dt_health_articles_summary_only(client, api):
    api[POSTS] = []
    data = (await client.call_tool("dt_health_articles", {"query": "zz"})).structured_content
    assert data == {"articles": []}
    assert params(api.calls[0])["_fields"] == ["id,date,link,title,excerpt"]


def test_html_text():
    assert html_text("<p>a&amp;b</p><p>c<br/>d&nbsp;e</p>") == "a&b\nc\nd e"
