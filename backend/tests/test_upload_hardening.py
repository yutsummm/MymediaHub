"""
Загрузка файлов: имя с диска, память и норма на человека.

Три находки разбора приёма медиа, каждая с последствием, которое видно
снаружи:

* **имя файла на диске собиралось из имени, присланного человеком.** Файл
  `photo.html`, объявленный картинкой, ложился на диск как `…html` и
  отдавался браузером как веб-страница — со скриптом, на нашем домене.
  Модератор открывал «фотографию» из очереди и выполнял чужой код;
* **файл читался в память целиком до сверки с пределом.** Несколько роликов
  разом — это сотни мегабайт сверх обычной работы, а вместе с процессом
  падают публикации, планировщик и сбор обращений: они живут там же;
* **загружать мог любой вошедший, без единого ограничения.** Свежий аккаунт
  забивал общее хранилище за считанные минуты, после чего переставали
  грузиться и посты, и медиа у всех сразу.
"""
import io
import os

import pytest
from conftest import auth

import utils


def upload(client, token, *, name, content_type, data=b"\xff\xd8\xff\xe0proba"):
    return client.post(
        "/api/upload",
        files={"file": (name, io.BytesIO(data), content_type)},
        headers=auth(token),
    )


def stored_name(response) -> str:
    """Имя файла на диске из подписанной ссылки."""
    return utils.upload_filename(response.json()["url"])


# ── Имя на диске ────────────────────────────────────────────────────────────

def test_extension_comes_from_the_checked_type_not_the_name(client, group_with_post):
    """Имя, присланное человеком, на имя файла на диске больше не влияет."""
    r = upload(client, group_with_post["token"],
               name="photo.html", content_type="image/jpeg")
    assert r.status_code == 200, r.text
    assert stored_name(r).endswith(".jpg"), "расширение должно следовать типу"


@pytest.mark.parametrize("name", [
    "обычное.jpg", "без расширения", "две.точки.в.имени.jpeg", "../побег.jpg",
])
def test_no_name_can_change_the_extension(client, group_with_post, name):
    r = upload(client, group_with_post["token"], name=name, content_type="image/png")
    assert r.status_code == 200, r.text
    assert stored_name(r).endswith(".png")


def test_type_header_with_charset_is_still_accepted(client, group_with_post):
    """Довесок в заголовке — оформление, а не другой тип файла."""
    r = upload(client, group_with_post["token"],
               name="таблица.csv", content_type="text/csv; charset=utf-8")
    assert r.status_code == 200, r.text
    assert stored_name(r).endswith(".csv")


# ── Отдача наружу ───────────────────────────────────────────────────────────

def test_web_page_on_disk_is_served_as_bytes_not_as_a_page(tmp_path, monkeypatch):
    """
    Файлы, легшие на диск до правки, могут называться как угодно — и обязаны
    быть обезврежены при отдаче, а не только при записи.
    """
    media_type, inline = utils.serve_disposition("старый.html")
    assert media_type == "application/octet-stream"
    assert inline is False, "неизвестное расширение нельзя показывать в странице"


def test_pictures_stay_pictures():
    for name, expected in (("a.jpg", "image/jpeg"), ("a.jpeg", "image/jpeg"),
                           ("a.png", "image/png"), ("a.mp4", "video/mp4")):
        media_type, inline = utils.serve_disposition(name)
        assert (media_type, inline) == (expected, True), name


def test_documents_are_offered_as_downloads():
    media_type, inline = utils.serve_disposition("отчёт.pdf")
    assert media_type == "application/pdf"
    assert inline is False, "документ не должен разворачиваться прямо в странице"


def test_served_file_carries_nosniff_and_named_type(client, group_with_post):
    r = upload(client, group_with_post["token"], name="кадр.jpg", content_type="image/jpeg")
    got = client.get(r.json()["url"])
    assert got.status_code == 200, got.text
    assert got.headers["content-type"].startswith("image/jpeg")
    assert got.headers.get("x-content-type-options") == "nosniff"


# ── Память и предел размера ─────────────────────────────────────────────────

def test_oversized_file_is_refused_and_leaves_nothing_behind(client, group_with_post):
    before = set(os.listdir(utils.UPLOAD_DIR))
    too_big = b"\x89PNG" + b"0" * (utils.MAX_IMAGE_SIZE + 1024)
    r = upload(client, group_with_post["token"],
               name="огромная.png", content_type="image/png", data=too_big)
    assert r.status_code == 400
    assert "слишком большой" in r.json()["detail"]
    after = set(os.listdir(utils.UPLOAD_DIR))
    assert after == before, "недописанный файл должен убираться с диска"


def test_upload_is_written_in_chunks(client, group_with_post, monkeypatch):
    """
    Расход памяти обязан зависеть от размера куска, а не от размера файла.
    Стережём именно это: чтение целиком вернулось бы незаметно — тесты на
    размер проходили бы по-прежнему.
    """
    import starlette.datastructures as ds

    sizes: list[int] = []
    real_read = ds.UploadFile.read

    async def spy(self, size=-1):
        sizes.append(size)
        return await real_read(self, size)

    monkeypatch.setattr(ds.UploadFile, "read", spy)
    data = b"\x89PNG" + b"0" * (3 * 1024 * 1024)
    r = upload(client, group_with_post["token"],
               name="крупная.png", content_type="image/png", data=data)
    assert r.status_code == 200, r.text
    assert sizes, "чтение файла не наблюдалось"
    assert all(s == 1024 * 1024 for s in sizes), (
        f"файл читается не кусками, а целиком: {sizes}")


def test_empty_file_is_refused(client, group_with_post):
    r = upload(client, group_with_post["token"],
               name="пустышка.jpg", content_type="image/jpeg", data=b"")
    assert r.status_code == 400
    assert "пуст" in r.json()["detail"]


# ── Норма на человека ───────────────────────────────────────────────────────

def test_member_of_a_group_gets_the_working_allowance(client, group_with_post):
    conn = utils.get_db()
    try:
        assert utils.upload_allowance(group_with_post["user_id"], conn) == (30, 300)
    finally:
        conn.close()


def test_person_without_a_group_gets_a_narrow_one(client, make_user):
    """
    Полный запрет был бы неверен: часть людей работает без группы. Но норма у
    них штучная — сваливать гигабайты через свежий аккаунт бессмысленно.
    """
    _, uid = make_user("bez-gruppy")
    conn = utils.get_db()
    try:
        limit, window = utils.upload_allowance(uid, conn)
    finally:
        conn.close()
    assert (limit, window) == (5, 3600)


def test_exceeding_the_allowance_answers_429(client, make_user):
    token, _ = make_user("shchedryy")
    codes = [upload(client, token, name=f"{i}.jpg", content_type="image/jpeg").status_code
             for i in range(7)]
    assert codes[:5] == [200] * 5, codes
    assert 429 in codes[5:], f"после нормы должен быть отказ 429, получили {codes}"
