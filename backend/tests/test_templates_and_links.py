"""
Свои шаблоны постов и ссылки внутри текста.

**Ссылки.** Одна разметка обязана разворачиваться в две разные вещи: Telegram
умеет гиперссылки, ВКонтакте в тексте записи — нет вовсе, там ссылкой
становится только видимый адрес. Здесь стережётся, что каждая площадка
получает свой вид и что длинный текст не рвётся посреди тега: разорванный тег
Telegram не примет, и пост не выйдет вообще.

**Шаблоны.** Владелец — группа: шаблон описывает, как публикует учреждение, и
должен пережить ухода автора. Чужие шаблоны не видны и не удаляются, а
встроенные не правятся из группы — иначе правка одной группы меняла бы их всем.
"""
import uuid

import pytest
from conftest import auth

import richtext
import templates as tmpl_service
from utils import TG_CAPTION_LIMIT, TG_MESSAGE_LIMIT, get_db


def make_group(client, token: str) -> int:
    r = client.post("/api/groups", json={"name": f"Группа {uuid.uuid4().hex[:6]}"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    client.put(f"/api/groups/{gid}", json={"require_approval": False}, headers=auth(token))
    return gid


@pytest.fixture()
def group(client, make_user):
    token, uid = make_user("tmpl")
    return {"token": token, "user_id": uid, "gid": make_group(client, token)}


# ── Ссылки: две площадки, два вида ──────────────────────────────────────────

def test_vk_gets_the_address_because_it_cannot_hide_it():
    """
    ВКонтакте гиперссылок в тексте записи не умеет: ссылкой становится только
    видимый адрес. Спрятать его за подписью там физически нечем.
    """
    out = richtext.to_plain("Запись: [по ссылке](https://a.ru/reg)")
    assert out == "Запись: по ссылке (https://a.ru/reg)"


def test_vk_does_not_repeat_the_address_twice():
    """«https://a.ru (https://a.ru)» выглядит поломкой, а не ссылкой."""
    assert richtext.to_plain("[https://a.ru](https://a.ru)") == "https://a.ru"


def test_telegram_gets_a_real_hyperlink():
    out = richtext.to_html("Запись: [по ссылке](https://a.ru/reg)")
    assert out == 'Запись: <a href="https://a.ru/reg">по ссылке</a>'


def test_everything_else_is_escaped():
    """
    Как только включён parse_mode, любой «<» в тексте человека ломает отправку
    целиком — и пост не уходит вовсе.
    """
    out = richtext.to_html("Скидка 5 < 10 & дёшево")
    assert "&lt;" in out and "&amp;" in out
    assert "<" not in out.replace("&lt;", "")


def test_length_is_counted_without_markup():
    """У Telegram предел считается по видимым символам, а не по разметке."""
    text = "тут [очень длинная подпись](https://example.ru/очень/длинный/адрес)"
    assert richtext.visible_length(text) == len("тут очень длинная подпись")
    assert richtext.visible_length(text) < len(text)


def test_chunking_never_cuts_a_link_in_half():
    """
    Разорванный тег Telegram не примет: вместо публикации будет отказ.
    Ссылка целиком уезжает в следующий кусок.
    """
    text = "а" * 30 + "[подпись](https://a.ru)" + "б" * 30
    parts = richtext.chunks(text, 40)
    assert len(parts) > 1
    for part in parts:
        assert part.count("[") == part.count("]") == part.count("](")
        # И каждая часть даёт корректный HTML
        assert richtext.to_html(part).count("<a ") == richtext.to_html(part).count("</a>")


def test_chunks_together_keep_the_whole_text():
    text = "начало [ссылка](https://a.ru) " + "х" * 200 + " конец"
    assert "".join(richtext.chunks(text, 50)) == text


def test_truncate_drops_a_link_that_does_not_fit():
    """Половина адреса бесполезна, а оборванный тег Telegram отвергнет."""
    text = "к" * (TG_CAPTION_LIMIT - 5) + "[подпись](https://a.ru)"
    out = richtext.truncate(text, TG_CAPTION_LIMIT)
    assert richtext.visible_length(out) <= TG_CAPTION_LIMIT
    assert richtext.to_html(out).count("<a ") == richtext.to_html(out).count("</a>")


def test_published_text_differs_per_platform(client, group, monkeypatch):
    """Проверяем на стыке, а не в чистой функции: важно, что уходит наружу."""
    import publishing

    gid, token = group["gid"], group["token"]
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (gid,))
    c.execute("INSERT INTO tg_settings (workspace_id, bot_token, chat_id) "
              "VALUES (%s,'tkn','@chan') ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    r = client.post(f"/api/groups/{gid}/posts", headers=auth(token), json={
        "title": "Набор", "content": "Записаться [здесь](https://a.ru/reg)",
        "status": "draft", "platforms": ["vk", "telegram"]})
    pid = r.json()["id"]

    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(vk=a[2]), 1)[1])
    monkeypatch.setattr(publishing, "tg_send_post",
                        lambda *a, **kw: (sent.update(tg=a[2]), [2])[1])

    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()

    assert "здесь (https://a.ru/reg)" in sent["vk"], "во ВКонтакте адрес обязан быть виден"
    assert "[здесь]" not in sent["vk"], "разметка утекла в паблик как есть"
    # В Telegram уходит исходная разметка: в HTML её разворачивает сам отправщик,
    # потому что резать по длине нужно до превращения в теги.
    assert "[здесь](https://a.ru/reg)" in sent["tg"]


# ── Шаблоны: поля выводятся из текста ───────────────────────────────────────

def test_fields_come_from_the_text_in_order():
    """Порядок вопросов должен совпадать с порядком в объявлении."""
    fields = tmpl_service.extract_fields("Ждём на {название} — {дата} в {место}")
    assert [f["key"] for f in fields] == ["название", "дата", "место"]


def test_repeated_field_is_asked_once():
    fields = tmpl_service.extract_fields("{дата}. Повторим: {дата}")
    assert len(fields) == 1


def test_group_variables_are_not_mistaken_for_fields():
    """{{ключ}} — подстановка группы, её заполняет система, а не человек."""
    fields = tmpl_service.extract_fields("Мы в {{центр}} на {адрес}")
    assert [f["key"] for f in fields] == ["адрес"]


def test_too_many_fields_is_refused():
    from fastapi import HTTPException

    text = " ".join(f"{{поле{i}}}" for i in range(20))
    with pytest.raises(HTTPException) as e:
        tmpl_service.extract_fields(text)
    assert e.value.status_code == 400


def test_unfilled_field_stays_visible():
    """Молча вырезанное поле уходит в паблик как оговорка автора."""
    out = tmpl_service.render("Ждём {когда} в {где}", {"когда": "субботу"})
    assert out == "Ждём субботу в {где}"


# ── Шаблоны: владение и доступ ──────────────────────────────────────────────

def test_group_template_is_created_and_listed(client, group):
    r = client.post(f"/api/groups/{group['gid']}/templates", headers=auth(group["token"]),
                    json={"name": "Клуб настольных игр",
                          "template_text": "В субботу в {время} ждём на игры в {место}.",
                          "title_template": "Настолки {время}"})
    assert r.status_code == 200, r.text
    created = r.json()
    assert [f["key"] for f in created["fields"]] == ["время", "место"]
    assert created["editable"] is True

    listed = client.get("/api/templates", headers=auth(group["token"])).json()
    assert any(t["type"] == created["type"] for t in listed)
    # Встроенные никуда не делись
    assert any(t["type"] == "announcement" and t["editable"] is False for t in listed)


def test_saving_the_same_name_updates_instead_of_duplicating(client, group):
    body = {"name": "Афиша", "template_text": "Первый вариант {дата}"}
    first = client.post(f"/api/groups/{group['gid']}/templates",
                        headers=auth(group["token"]), json=body).json()
    body["template_text"] = "Второй вариант {дата}"
    second = client.post(f"/api/groups/{group['gid']}/templates",
                         headers=auth(group["token"]), json=body).json()
    assert first["id"] == second["id"]
    assert second["template_text"] == "Второй вариант {дата}"


def test_two_groups_may_have_templates_with_the_same_name(client, make_user):
    """Раньше уникальность type была глобальной — второй центр не смог бы завести «Афишу»."""
    a_token, _ = make_user("tmpl-a")
    b_token, _ = make_user("tmpl-b")
    a, b = make_group(client, a_token), make_group(client, b_token)
    body = {"name": "Афиша", "template_text": "Текст {дата}"}
    assert client.post(f"/api/groups/{a}/templates", headers=auth(a_token),
                       json=body).status_code == 200
    assert client.post(f"/api/groups/{b}/templates", headers=auth(b_token),
                       json=body).status_code == 200


def test_foreign_templates_are_invisible(client, group, make_user):
    """В тексте шаблона вполне может быть внутренняя формулировка."""
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Внутренний", "template_text": "секрет {x}"}).json()
    stranger, _ = make_user("tmpl-stranger")
    listed = client.get("/api/templates", headers=auth(stranger)).json()
    assert all(t["type"] != created["type"] for t in listed)
    # И собрать по нему текст тоже нельзя
    r = client.post("/api/generate-text", headers=auth(stranger),
                    json={"template_type": created["type"], "fields": {"x": "!"}})
    assert r.status_code == 404


def test_builtin_templates_cannot_be_deleted_through_a_group(client, group):
    """Они общие для всех: удаление одной группой сломало бы их всем остальным."""
    builtin = next(t for t in client.get("/api/templates", headers=auth(group["token"])).json()
                   if t["type"] == "announcement")
    r = client.delete(f"/api/groups/{group['gid']}/templates/{builtin['id']}",
                      headers=auth(group["token"]))
    assert r.status_code == 404
    still = client.get("/api/templates", headers=auth(group["token"])).json()
    assert any(t["type"] == "announcement" for t in still)


def test_group_template_is_deletable(client, group):
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Разовый", "template_text": "текст {x}"}).json()
    assert client.delete(f"/api/groups/{group['gid']}/templates/{created['id']}",
                         headers=auth(group["token"])).status_code == 200
    listed = client.get("/api/templates", headers=auth(group["token"])).json()
    assert all(t["type"] != created["type"] for t in listed)


def test_generate_text_uses_the_custom_template(client, group):
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Мастерская",
                                "template_text": "Мастерская {тема} — {дата}.",
                                "title_template": "Мастерская: {тема}"}).json()
    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": created["type"],
                          "fields": {"тема": "фотодело", "дата": "субботу"}})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "Мастерская фотодело — субботу."
    assert r.json()["title"] == "Мастерская: фотодело"


def test_template_without_title_falls_back_to_its_name(client, group):
    """«Новый пост» не говорит ничего; название шаблона хотя бы ближе к делу."""
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Объявление недели",
                                "template_text": "Текст {x}"}).json()
    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": created["type"], "fields": {"x": "!"}})
    assert r.json()["title"] == "Объявление недели"


def test_builtin_templates_still_work(client, group):
    """Старые шаблоны не должны пострадать от появления своих."""
    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": "announcement",
                          "fields": {"event_name": "Хакатон", "date": "25 апреля"}})
    assert r.status_code == 200, r.text
    assert "Хакатон" in r.json()["text"]
    assert r.json()["title"].startswith("Анонс:")


def test_empty_template_is_refused(client, group):
    for body in ({"name": "  ", "template_text": "текст"},
                 {"name": "Пустой", "template_text": "   "}):
        assert client.post(f"/api/groups/{group['gid']}/templates",
                           headers=auth(group["token"]), json=body).status_code == 400


def test_watchers_cannot_create_templates(client, group, make_user):
    watcher, _ = make_user("tmpl-watcher")
    link = client.post(f"/api/groups/{group['gid']}/invites",
                       json={"role": "volunteer", "expires_hours": 24},
                       headers=auth(group["token"])).json()
    client.post(f"/api/invites/{link['token']}/accept", headers=auth(watcher))
    r = client.post(f"/api/groups/{group['gid']}/templates", headers=auth(watcher),
                    json={"name": "Нельзя", "template_text": "текст {x}"})
    assert r.status_code == 403


# ── Ссылки внутри шаблона ───────────────────────────────────────────────────

def test_template_keeps_link_markup_through_rendering(client, group):
    """
    Разметка ссылки в шаблоне должна дожить до поста нетронутой: подстановка
    полей и ссылки живут в одном тексте и не должны мешать друг другу.
    """
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Набор",
                                "template_text": "Ждём на {название}. "
                                                 "Записаться [по ссылке](https://s.ru/reg)."}).json()
    assert [f["key"] for f in created["fields"]] == ["название"], \
        "адрес ссылки приняли за поле шаблона"

    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": created["type"], "fields": {"название": "фестивале"}})
    assert r.json()["text"] == "Ждём на фестивале. Записаться [по ссылке](https://s.ru/reg)."


def test_field_inside_a_link_address_is_substituted(client, group):
    """Адрес вполне может зависеть от поля — например, номера смены."""
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Смена",
                                "template_text": "[Запись](https://s.ru/reg?smena={номер})"}).json()
    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": created["type"], "fields": {"номер": "7"}})
    assert r.json()["text"] == "[Запись](https://s.ru/reg?smena=7)"


def test_field_as_a_link_label_is_substituted(client, group):
    created = client.post(f"/api/groups/{group['gid']}/templates",
                          headers=auth(group["token"]),
                          json={"name": "Подпись",
                                "template_text": "[{куда}](https://s.ru)"}).json()
    r = client.post("/api/generate-text", headers=auth(group["token"]),
                    json={"template_type": created["type"], "fields": {"куда": "на сайт"}})
    assert r.json()["text"] == "[на сайт](https://s.ru)"


def test_title_never_reaches_the_platforms(client, group, monkeypatch):
    """
    Заголовок — служебное название для списка и календаря, и в публикацию он
    не попадает. У записи во ВКонтакте и в Telegram нет заголовка как
    сущности: там просто текст, и первой строкой каждого поста оказывалось
    то, что автор писал себе для ориентирования.

    Заодно это снимало дублирование: встроенные шаблоны начинают текст с
    названия мероприятия, а заголовок собирался как «Анонс: то же самое».
    """
    import publishing

    gid, token = group["gid"], group["token"]
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (gid,))
    c.execute("INSERT INTO tg_settings (workspace_id, bot_token, chat_id) "
              "VALUES (%s,'tkn','@chan') ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    r = client.post(f"/api/groups/{gid}/posts", headers=auth(token), json={
        "title": "Набор [открыт](https://s.ru/reg)", "content": "Подробности ниже.",
        "status": "draft", "platforms": ["vk", "telegram"]})
    pid = r.json()["id"]

    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(vk=a[2]), 1)[1])
    monkeypatch.setattr(publishing, "tg_send_post",
                        lambda *a, **kw: (sent.update(tg=a[2]), [2])[1])
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()

    assert sent["vk"].strip() == "Подробности ниже."
    assert sent["tg"].strip() == "Подробности ниже."
    for message in (sent["vk"], sent["tg"]):
        assert "Набор" not in message, "служебный заголовок ушёл в публикацию"
        assert "открыт" not in message


def test_media_caption_does_not_leak_the_internal_title(client, group):
    """
    Название видео и документа во ВКонтакте видит зритель. Служебный заголовок
    там был бы такой же утечкой, как и в тексте, — берём первую строку самого
    текста, она публичная.
    """
    import publishing

    caption = publishing._public_caption(
        {"title": "служебное имя", "content": "  \n\nПриглашаем на фестиваль!\nВторая строка"},
        "video.mp4")
    assert caption == "Приглашаем на фестиваль!"
    # Текста нет вовсе — остаётся имя файла, но не заголовок
    assert publishing._public_caption({"title": "служебное имя", "content": "  "},
                                      "video.mp4") == "video.mp4"


def test_title_is_still_kept_for_our_own_lists(client, group):
    """
    Наружу заголовок не идёт, но у нас он остаётся: по нему пост ищут в
    списке, календаре и отчёте.
    """
    r = client.post(f"/api/groups/{group['gid']}/posts", headers=auth(group["token"]),
                    json={"title": "Внутреннее имя", "content": "текст", "status": "draft"})
    assert r.json()["title"] == "Внутреннее имя"
    listed = client.get(f"/api/groups/{group['gid']}/posts",
                        headers=auth(group["token"])).json()["posts"]
    assert any(p["title"] == "Внутреннее имя" for p in listed)


def test_group_variables_are_applied_to_the_body(client, group, monkeypatch):
    """Подстановки применяются к тексту — заголовок наружу не идёт вовсе."""
    import publishing

    gid, token = group["gid"], group["token"]
    client.put(f"/api/groups/{gid}", json={"variables": {"центр": "«Спектр»"}},
               headers=auth(token))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    r = client.post(f"/api/groups/{gid}/posts", headers=auth(token), json={
        "title": "служебное имя", "content": "Новости {{центр}}",
        "status": "draft", "platforms": ["vk"]})
    pid = r.json()["id"]
    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(vk=a[2]), 1)[1])
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()

    assert "Новости «Спектр»" in sent["vk"]
    assert "{{центр}}" not in sent["vk"]
    assert "служебное имя" not in sent["vk"]


# ── Предпросмотр ────────────────────────────────────────────────────────────

def test_preview_shows_what_each_platform_will_actually_get(client, group):
    """
    Предпросмотр обязан считать тот же код, что и публикация. Отдельная сборка
    на клиенте была бы второй копией правил — она разошлась бы с настоящей, и
    человек увидел бы одно, а в паблик ушло другое.
    """
    gid, token = group["gid"], group["token"]
    client.put(f"/api/groups/{gid}", headers=auth(token),
               json={"variables": {"центр": "«Спектр»"}, "utm_enabled": True})

    r = client.post(f"/api/groups/{gid}/posts/preview", headers=auth(token), json={
        "title": "служебное имя",
        "content": "Набор в {{центр}}. Записаться [по ссылке](https://s.ru/reg).",
        "tags": ["вакансии"],
        "platforms": ["vk", "telegram"],
    })
    assert r.status_code == 200, r.text
    by_platform = {p["platform"]: p for p in r.json()["previews"]}

    def flat(preview: dict) -> str:
        return "".join(s["text"] for s in preview["segments"])

    # Подстановка сработала на обеих площадках
    assert "«Спектр»" in flat(by_platform["vk"])
    assert "«Спектр»" in flat(by_platform["telegram"])
    # А служебный заголовок в предпросмотр не попал — как и в публикацию
    assert "служебное имя" not in flat(by_platform["vk"])

    # ВКонтакте: адрес виден, ссылки как куска нет — там её не бывает
    vk_text = flat(by_platform["vk"])
    assert "по ссылке (https://s.ru/reg" in vk_text
    assert all(s["kind"] == "text" for s in by_platform["vk"]["segments"])

    # Telegram: ссылка приходит отдельным куском, адрес в тексте не виден
    links = [s for s in by_platform["telegram"]["segments"] if s["kind"] == "link"]
    assert len(links) == 1
    assert links[0]["text"] == "по ссылке"
    assert "s.ru/reg" in links[0]["url"]
    assert "https://s.ru/reg" not in flat(by_platform["telegram"])


def test_preview_includes_the_utm_marks_because_vk_shows_them(client, group):
    """
    Во ВКонтакте адрес виден целиком, и метки делают его заметно длиннее.
    Прятать их в предпросмотре значило бы показывать не то, что выйдет.
    """
    gid, token = group["gid"], group["token"]
    client.put(f"/api/groups/{gid}", json={"utm_enabled": True}, headers=auth(token))
    r = client.post(f"/api/groups/{gid}/posts/preview", headers=auth(token), json={
        "content": "Запись [тут](https://s.ru/reg)", "tags": ["мероприятия"],
        "platforms": ["vk"]})
    text = "".join(s["text"] for s in r.json()["previews"][0]["segments"])
    assert "utm_source=vk" in text


def test_preview_uses_the_platform_specific_text(client, group):
    r = client.post(f"/api/groups/{group['gid']}/posts/preview",
                    headers=auth(group["token"]), json={
                        "content": "Общий текст",
                        "content_overrides": {"telegram": "Текст для канала"},
                        "platforms": ["vk", "telegram"]})
    by_platform = {p["platform"]: "".join(s["text"] for s in p["segments"])
                   for p in r.json()["previews"]}
    assert by_platform["vk"] == "Общий текст"
    assert by_platform["telegram"] == "Текст для канала"


def test_preview_warns_when_the_message_will_not_fit(client, group):
    """Сообщение длиннее предела Telegram обрежется при отправке."""
    r = client.post(f"/api/groups/{group['gid']}/posts/preview",
                    headers=auth(group["token"]),
                    json={"content": "я" * 5000, "platforms": ["vk", "telegram"]})
    by_platform = {p["platform"]: p for p in r.json()["previews"]}
    assert by_platform["telegram"]["over_limit"] is True
    assert by_platform["telegram"]["limit"] == 4096
    assert by_platform["vk"]["over_limit"] is False


def test_preview_matches_what_publishing_sends(client, group, monkeypatch):
    """
    Главная проверка: предпросмотр и публикация обязаны совпасть до символа.
    Разойдутся — и предпросмотр начнёт врать, а полагаться на него будут.
    """
    import publishing

    gid, token = group["gid"], group["token"]
    client.put(f"/api/groups/{gid}", headers=auth(token),
               json={"variables": {"центр": "«Спектр»"}, "utm_enabled": True})
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vk_settings (workspace_id, group_id, access_token) "
              "VALUES (%s,'42','tkn') ON CONFLICT DO NOTHING", (gid,))
    conn.commit()

    draft = {"title": "Набор в {{центр}}",
             "content": "Записаться [по ссылке](https://s.ru/reg).",
             "tags": ["вакансии"], "platforms": ["vk"]}

    preview = client.post(f"/api/groups/{gid}/posts/preview",
                          headers=auth(token), json=draft).json()["previews"][0]
    shown = "".join(s["text"] for s in preview["segments"])

    r = client.post(f"/api/groups/{gid}/posts", headers=auth(token),
                    json={**draft, "status": "draft"})
    pid = r.json()["id"]
    sent: dict = {}
    monkeypatch.setattr(publishing, "vk_wall_post",
                        lambda *a, **kw: (sent.update(vk=a[2]), 1)[1])
    c.execute("SELECT * FROM posts WHERE id=%s", (pid,))
    publishing.perform_publish(conn, c.fetchone(), group_id=gid)
    conn.close()

    assert shown == sent["vk"], "предпросмотр разошёлся с тем, что реально ушло"


def test_preview_is_closed_to_outsiders(client, group, make_user):
    stranger, _ = make_user("prev-stranger")
    r = client.post(f"/api/groups/{group['gid']}/posts/preview",
                    headers=auth(stranger), json={"content": "текст", "platforms": ["vk"]})
    assert r.status_code == 403
