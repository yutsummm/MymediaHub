"""Данные одной группы не должны утекать пользователю из другой."""
from conftest import auth


def test_foreign_post_hidden_from_list(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    titles = [p["title"] for p in client.get("/api/posts", headers=auth(other)).json()["posts"]]
    assert group_with_post["post"]["title"] not in titles


def test_own_post_visible_in_list(client, group_with_post):
    titles = [
        p["title"]
        for p in client.get("/api/posts", headers=auth(group_with_post["token"])).json()["posts"]
    ]
    assert group_with_post["post"]["title"] in titles


def test_foreign_post_read_forbidden(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    pid = group_with_post["post"]["id"]
    assert client.get(f"/api/posts/{pid}", headers=auth(other)).status_code == 403


def test_foreign_post_update_forbidden(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    pid = group_with_post["post"]["id"]
    r = client.put(f"/api/posts/{pid}", json={"title": "взлом"}, headers=auth(other))
    assert r.status_code == 403
    # заголовок не изменился
    owner = auth(group_with_post["token"])
    assert client.get(f"/api/posts/{pid}", headers=owner).json()["title"] != "взлом"


def test_foreign_post_delete_forbidden(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    pid = group_with_post["post"]["id"]
    assert client.delete(f"/api/posts/{pid}", headers=auth(other)).status_code == 403
    assert client.get(f"/api/posts/{pid}", headers=auth(group_with_post["token"])).status_code == 200


def test_foreign_post_publish_forbidden(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    pid = group_with_post["post"]["id"]
    assert client.post(f"/api/posts/{pid}/publish", headers=auth(other)).status_code == 403


def test_owner_can_read_own_post(client, group_with_post):
    pid = group_with_post["post"]["id"]
    r = client.get(f"/api/posts/{pid}", headers=auth(group_with_post["token"]))
    assert r.status_code == 200


def test_foreign_group_posts_forbidden(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    gid = group_with_post["group_id"]
    assert client.get(f"/api/groups/{gid}/posts", headers=auth(other)).status_code == 403


def test_calendar_scoped_to_own_groups(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    r = client.get("/api/calendar?start=2000-01-01&end=2100-01-01", headers=auth(other))
    assert r.status_code == 200
    assert group_with_post["post"]["title"] not in [p["title"] for p in r.json()]


def test_analytics_scoped_to_own_groups(client, group_with_post, make_user):
    other, _ = make_user("stranger")
    owner_total = client.get(
        "/api/analytics/summary", headers=auth(group_with_post["token"])
    ).json()["total_posts"]
    other_total = client.get("/api/analytics/summary", headers=auth(other)).json()["total_posts"]
    assert owner_total > other_total


def test_author_id_taken_from_token_not_body(client, make_user):
    token, uid = make_user("author")
    r = client.post(
        "/api/posts",
        json={"title": "подделка", "content": "x", "author_id": 999999},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["author_id"] == uid


def test_foreign_notification_cannot_be_marked_read(client, db, make_user):
    owner, owner_id = make_user("notif-owner")
    other, _ = make_user("notif-stranger")
    c = db.cursor()
    c.execute(
        "INSERT INTO notifications (user_id, message) VALUES (%s, 'тест') RETURNING id",
        (owner_id,),
    )
    nid = c.fetchone()["id"]
    db.commit()

    assert client.put(f"/api/notifications/{nid}/read", headers=auth(other)).status_code == 404
    assert client.put(f"/api/notifications/{nid}/read", headers=auth(owner)).status_code == 200


def test_notifications_list_scoped_to_user(client, db, make_user):
    owner, owner_id = make_user("notif-list")
    other, _ = make_user("notif-list-other")
    c = db.cursor()
    c.execute("INSERT INTO notifications (user_id, message) VALUES (%s, 'приватное')", (owner_id,))
    db.commit()

    messages = [n["message"] for n in client.get("/api/notifications", headers=auth(other)).json()["items"]]
    assert "приватное" not in messages
