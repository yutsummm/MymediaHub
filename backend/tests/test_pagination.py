"""
Списки должны листаться.

Бэкенд всегда отдавал только первую страницу (limit=100 по умолчанию), а
интерфейс её не листал: на 101-м посте список молча обрывался, и понять это со
стороны было невозможно. Плюс limit ничем не ограничивался сверху — запросом
limit=1000000 можно было заставить сервер вытащить всю таблицу разом.
"""
import pytest
from conftest import auth

from utils import MAX_PAGE_SIZE, page_meta, paging

# ── Границы ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "given,expected",
    [((10, 0), (10, 0)), ((0, 0), (1, 0)), ((-5, -5), (1, 0)),
     ((10**6, 0), (MAX_PAGE_SIZE, 0)), ((50, 30), (50, 30))],
)
def test_paging_clamps_input(given, expected):
    assert paging(*given) == expected


def test_page_meta_reports_more():
    assert page_meta(100, 20, 0)["has_more"] is True
    assert page_meta(100, 20, 80)["has_more"] is False
    assert page_meta(5, 20, 0)["has_more"] is False


def test_huge_limit_is_refused_by_api(client, admin_token):
    r = client.get("/api/posts?limit=1000000", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["limit"] == MAX_PAGE_SIZE, "сервер не должен отдавать всё разом"


# ── Постраничная выдача постов ───────────────────────────────────────────────

@pytest.fixture()
def many_posts(client, group_with_post):
    """Больше одной страницы, чтобы обрыв был виден."""
    gid = group_with_post["group_id"]
    token = group_with_post["token"]
    ids = []
    for i in range(7):
        ids.append(client.post(
            f"/api/groups/{gid}/posts",
            json={"title": f"Пост {i:02d}", "content": "т", "platforms": []},
            headers=auth(token),
        ).json()["id"])
    return {"ids": ids, "gid": gid, "token": token}


def test_pages_do_not_overlap_and_cover_everything(client, many_posts):
    """Ключевое: страницы вместе дают весь список и не дублируют записи."""
    gid, token = many_posts["gid"], many_posts["token"]
    seen, offset = [], 0
    while True:
        page = client.get(
            f"/api/groups/{gid}/posts?limit=3&offset={offset}", headers=auth(token)
        ).json()
        seen += [p["id"] for p in page["posts"]]
        if not page["has_more"]:
            break
        offset += page["limit"]
        assert offset < 100, "защита от бесконечного цикла"

    assert len(seen) == len(set(seen)), "записи не должны повторяться между страницами"
    assert set(many_posts["ids"]).issubset(set(seen)), "ни один пост не должен потеряться"


def test_total_counts_everything_not_just_the_page(client, many_posts):
    gid, token = many_posts["gid"], many_posts["token"]
    page = client.get(f"/api/groups/{gid}/posts?limit=2", headers=auth(token)).json()
    assert len(page["posts"]) == 2
    assert page["total"] >= len(many_posts["ids"]), "total — про весь список, а не про страницу"
    assert page["has_more"] is True


def test_offset_past_the_end_returns_empty_not_error(client, many_posts):
    gid, token = many_posts["gid"], many_posts["token"]
    page = client.get(f"/api/groups/{gid}/posts?offset=9999", headers=auth(token)).json()
    assert page["posts"] == []
    assert page["has_more"] is False


# ── Фильтры и счётчик ────────────────────────────────────────────────────────

def test_total_respects_filters(client, many_posts):
    """
    Раньше total считался без фильтров: «показаны 1–20 из 250» врало бы при
    любом поиске.
    """
    gid, token = many_posts["gid"], many_posts["token"]
    filtered = client.get(f"/api/groups/{gid}/posts?q=Пост 03", headers=auth(token)).json()
    assert filtered["total"] == len(filtered["posts"])
    assert filtered["total"] < client.get(
        f"/api/groups/{gid}/posts", headers=auth(token)
    ).json()["total"]


def test_search_looks_beyond_the_current_page(client, many_posts):
    """
    Поиск ушёл на сервер: иначе он искал бы только по загруженной странице и
    «не найдено» означало бы «нет среди первых двадцати».
    """
    gid, token = many_posts["gid"], many_posts["token"]
    r = client.get(f"/api/groups/{gid}/posts?q=Пост 06&limit=2", headers=auth(token)).json()
    assert r["total"] == 1
    assert r["posts"][0]["title"] == "Пост 06"


def test_date_filter_works_server_side(client, group_with_post):
    """Фильтр по дате тоже переехал на сервер — по той же причине."""
    from utils import app_now_str

    gid, token = group_with_post["group_id"], group_with_post["token"]
    today = app_now_str()[:10]
    client.post(
        f"/api/groups/{gid}/posts",
        json={"title": "Сегодняшний", "content": "т", "platforms": []},
        headers=auth(token),
    )
    r = client.get(f"/api/groups/{gid}/posts?date={today}", headers=auth(token)).json()
    assert r["total"] >= 1
    assert all(
        (p["scheduled_at"] or p["published_at"] or p["created_at"]).startswith(today)
        for p in r["posts"]
    )

    r_none = client.get(f"/api/groups/{gid}/posts?date=1999-01-01", headers=auth(token)).json()
    assert r_none["total"] == 0


# ── Остальные списки ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,key", [
    ("/api/posts", "posts"),
    ("/api/users", "users"),
    ("/api/notifications", "items"),
])
def test_list_endpoints_report_page_meta(client, admin_token, path, key):
    r = client.get(f"{path}?limit=2", headers=auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert key in body
    for field in ("total", "limit", "offset", "has_more"):
        assert field in body, f"{path} не сообщает {field}"
    assert body["limit"] == 2


def test_volunteer_media_reports_page_meta(client, group_with_post):
    gid, token = group_with_post["group_id"], group_with_post["token"]
    r = client.get(f"/api/groups/{gid}/volunteer-media?limit=2", headers=auth(token))
    assert r.status_code == 200
    for field in ("total", "limit", "offset", "has_more"):
        assert field in r.json()
