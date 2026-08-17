"""
Медиатека группы: всё, что уже загружено, — в одном месте.

Раньше каждый пост начинался с загрузки файлов заново. Снятое на прошлом
мероприятии лежало в базе, но добраться до него из редактора было нельзя:
выбор шёл только по загрузкам волонтёров, да и тот по недосмотру был закрыт
глобальной ролью `editor`, которой после разделения систем ролей не
существует, — то есть кнопку видели одни глобальные администраторы.

Источников два, и оба уже есть в базе:

* `volunteer_media` со статусом `approved` — то, что прислали волонтёры и что
  редактор уже посмотрел. Неодобренное в медиатеку не попадает: модерация
  затем и нужна.
* `posts.media` этой группы — файлы, уже использованные в постах. Именно их
  чаще всего и хотят переиспользовать: афишу к повтору мероприятия, логотип,
  фото площадки.

Один и тот же файл может лежать в обоих источниках (волонтёр прислал —
редактор вставил в пост). Наружу он уходит один раз: `DISTINCT ON (url)`
с самой свежей записью, иначе медиатека выглядела бы как склад дублей.

Ссылки подписываются на выдаче, как и везде: `/uploads` без подписи не отдаёт
ничего. В базу подпись при этом попасть не может — путь записи один и тот же,
`media_for_storage()`.
"""
from utils import fmt_dt, like_pattern, page_meta, paging, sign_media_list

# Выборка одинакова для списка и для счётчика — считать надо ровно то же, что
# показываем, иначе «показаны 1–20 из 250» врёт при любом фильтре.
_ITEMS_CTE = """
WITH items AS (
    SELECT m->>'url' AS url, m->>'type' AS type, m->>'filename' AS filename,
           'volunteer' AS source, vm.event_name AS label, u.name AS author,
           vm.created_at AS at
    FROM volunteer_media vm
    JOIN users u ON u.id = vm.user_id
    CROSS JOIN LATERAL jsonb_array_elements(vm.media) m
    WHERE vm.group_id = %(gid)s AND vm.status = 'approved'
      AND jsonb_typeof(vm.media) = 'array'
    UNION ALL
    SELECT m->>'url', m->>'type', m->>'filename',
           'post', p.title, u.name, COALESCE(p.published_at, p.created_at)
    FROM posts p
    LEFT JOIN users u ON u.id = p.author_id
    CROSS JOIN LATERAL jsonb_array_elements(p.media) m
    WHERE p.group_id = %(gid)s AND jsonb_typeof(p.media) = 'array'
),
uniq AS (
    -- Один файл — одна карточка, с самой свежей подписью о происхождении.
    SELECT DISTINCT ON (url) * FROM items
    WHERE url IS NOT NULL AND url <> ''
    ORDER BY url, at DESC NULLS LAST
)
"""


def _filters(q: str | None, kind: str | None, source: str | None) -> tuple[str, dict]:
    where = ["TRUE"]
    params: dict = {}
    if q:
        # Ищем и по имени файла, и по названию мероприятия/поста: человек
        # помнит «это было с фестиваля», а не «IMG_20260517.jpg».
        where.append("(filename ILIKE %(q)s OR label ILIKE %(q)s)")
        params["q"] = like_pattern(q)
    if kind:
        where.append("type = %(kind)s")
        params["kind"] = kind
    if source:
        where.append("source = %(source)s")
        params["source"] = source
    return " AND ".join(where), params


def browse(
    conn, gid: int, q: str | None = None, kind: str | None = None,
    source: str | None = None, limit: int = 60, offset: int = 0,
) -> dict:
    c = conn.cursor()
    where, extra = _filters(q, kind, source)
    limit, offset = paging(limit, offset)
    params = {"gid": gid, **extra}

    c.execute(f"{_ITEMS_CTE} SELECT COUNT(*) AS n FROM uniq WHERE {where}", params)
    total = c.fetchone()["n"]

    c.execute(
        f"{_ITEMS_CTE} SELECT * FROM uniq WHERE {where} "
        "ORDER BY at DESC NULLS LAST, url LIMIT %(limit)s OFFSET %(offset)s",
        {**params, "limit": limit, "offset": offset},
    )
    rows = [dict(r) for r in c.fetchall()]
    # Подписываем разом: sign_media_list ждёт список словарей с url — ровно то,
    # что здесь и лежит.
    items = sign_media_list(rows)
    for item in items:
        # Тот же формат даты, что у всей остальной выдачи (см. DATE_FIELDS).
        item["at"] = fmt_dt(item.get("at"))
    return {"items": items, **page_meta(total, limit, offset)}
