import pytest
from conftest import live_call as call

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_dt_health_articles(client):
    data = await call(client, "dt_health_articles", {"query": "فشار خون", "limit": 3, "text_chars": 300})
    a = data["articles"]
    assert len(a) == 3 and a[0]["url"].startswith("https://doctoreto.com/blog/") and a[0]["text"]
    assert any("فشار خون" in x["title"] for x in a)
