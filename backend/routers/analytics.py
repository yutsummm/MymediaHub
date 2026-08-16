import io
from datetime import datetime, timedelta
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from utils import app_now, get_current_user_id, get_db, posts_scope, require_group_member

router = APIRouter()

# Статистика лежит по площадкам отдельно (post_stats), поэтому «есть ли цифры»
# больше не захардкожено, а видно по данным: если по площадке нет ни одной
# собранной строки, отдаём None («нет данных»), а не 0 и не чужие числа. Как
# только сбор по площадке появится, признак переключится сам.
def _platform_row(platform: str, count: int, collected: int, views, reactions,
                  label: str | None = None) -> dict:
    known = bool(collected)
    return {
        "platform": label or platform,
        "count": count or 0,
        "collected": collected or 0,
        "views": (views or 0) if known else None,
        "reactions": (reactions or 0) if known else None,
        "stats_available": known,
    }


# Сумма по всем площадкам живёт в представлении post_totals (см. миграцию
# f4b2e8c15d93) — иначе одинаковый подзапрос разъехался бы по полутора десяткам мест.
TOTALS = "posts JOIN post_totals t ON t.post_id = posts.id"


def _platform_stats(c, where: str, params: list, label_upper: bool = False) -> list[dict]:
    """Разбивка по площадкам: сколько постов ушло и что по ним собрано."""
    rows = []
    for pl in ("vk", "telegram"):
        c.execute(
            f"SELECT COUNT(*) cnt FROM posts WHERE platforms ? %s AND {where}",
            [pl] + list(params),
        )
        count = c.fetchone()["cnt"]
        c.execute(
            "SELECT COUNT(*) collected, SUM(s.views) v, SUM(s.reactions) r "
            "FROM post_stats s JOIN posts ON posts.id = s.post_id "
            f"WHERE s.platform=%s AND {where}",
            [pl] + list(params),
        )
        got = c.fetchone()
        rows.append(_platform_row(pl, count, got["collected"], got["v"], got["r"],
                                  label=pl.upper() if label_upper else None))
    return rows


def _build_workbook(dt_start, dt_end, summary: dict, timeline, pl_stats, top_posts):
    BLUE = "1D4ED8"
    WHITE = "FFFFFF"
    GRAY = "F1F5F9"
    DARK = "1E293B"

    header_font = Font(bold=True, color=WHITE, size=11)
    header_fill = PatternFill("solid", fgColor=BLUE)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_align = Alignment(vertical="center")
    thin_border = Border(
        bottom=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="E2E8F0"),
    )

    def style_header_row(ws, row, cols):
        for col in range(1, cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

    def style_data_row(ws, row, cols, shade=False):
        fill = PatternFill("solid", fgColor=GRAY) if shade else None
        for col in range(1, cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.alignment = cell_align
            cell.border = thin_border
            if shade:
                cell.fill = fill

    period_label = f"{dt_start.strftime('%d.%m.%Y')} — {dt_end.strftime('%d.%m.%Y')}"

    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Сводка"
    ws1.row_dimensions[1].height = 30
    ws1["A1"] = f"Отчёт по аналитике — {period_label}"
    ws1["A1"].font = Font(bold=True, size=14, color=DARK)
    ws1["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws1.merge_cells("A1:B1")
    ws1.append([])

    headers = ["Показатель", "Значение"]
    ws1.append(headers)
    style_header_row(ws1, 3, 2)
    ws1.row_dimensions[3].height = 24

    rows_data = [
        ("Всего постов", summary["total"]),
        ("Опубликовано", summary["published"]),
        ("Запланировано", summary["scheduled"]),
        ("Черновиков", summary["drafts"]),
        ("Всего просмотров", summary["total_views"]),
        ("Реакции", summary["total_reactions"]),
        ("Комментарии", summary["total_comments"]),
        ("Репосты", summary["total_shares"]),
        ("Средние просмотры", summary["avg_views"]),
        ("Вовлечённость, %", summary["eng"]),
    ]
    for i, (label, val) in enumerate(rows_data, start=4):
        ws1.append([label, val])
        ws1.row_dimensions[i].height = 20
        style_data_row(ws1, i, 2, shade=(i % 2 == 0))
    ws1.column_dimensions["A"].width = 28
    ws1.column_dimensions["B"].width = 18

    ws2 = wb.create_sheet("Динамика")
    ws2.append(["Дата", "Просмотры", "Реакции", "Публикаций"])
    style_header_row(ws2, 1, 4)
    ws2.row_dimensions[1].height = 24
    for i, row in enumerate(timeline, start=2):
        ws2.append([row["date"], row["views"], row["reactions"], row["posts"]])
        ws2.row_dimensions[i].height = 18
        style_data_row(ws2, i, 4, shade=(i % 2 == 0))
    for col, w in zip("ABCD", [14, 14, 12, 14], strict=False):
        ws2.column_dimensions[col].width = w

    ws3 = wb.create_sheet("Площадки")
    ws3.append(["Площадка", "Публикаций", "Просмотры", "Реакции"])
    style_header_row(ws3, 1, 4)
    ws3.row_dimensions[1].height = 24
    for i, pl in enumerate(pl_stats, start=2):
        # None → пустая ячейка выглядит как ноль; пишем словами, что данных нет
        views = pl["views"] if pl["views"] is not None else "нет данных"
        reactions = pl["reactions"] if pl["reactions"] is not None else "нет данных"
        ws3.append([pl["platform"], pl["count"], views, reactions])
        ws3.row_dimensions[i].height = 20
        style_data_row(ws3, i, 4, shade=(i % 2 == 0))
    for col, w in zip("ABCD", [16, 14, 14, 12], strict=False):
        ws3.column_dimensions[col].width = w

    ws4 = wb.create_sheet("Топ постов")
    ws4.append(["#", "Заголовок", "Просмотры", "Реакции", "Комментарии", "Репосты", "Дата публикации"])
    style_header_row(ws4, 1, 7)
    ws4.row_dimensions[1].height = 24
    for i, p in enumerate(top_posts, start=2):
        ws4.append([
            i - 1, p["title"], p["views"] or 0, p["reactions"] or 0,
            p["comments"] or 0, p["shares"] or 0, str(p["published_at"] or ""),
        ])
        ws4.row_dimensions[i].height = 20
        style_data_row(ws4, i, 7, shade=(i % 2 == 0))
    for col, w in zip("ABCDEFG", [4, 40, 12, 10, 14, 10, 22], strict=False):
        ws4.column_dimensions[col].width = w

    return wb


# ── Ядро: одно на глобальные и групповые ручки ──────────────────────────────
# Раньше это была пара почти дословных копий на каждый отчёт: глобальную и
# групповую отличало только условие выборки. Копии неизбежно разъезжаются —
# правку вносят в одну и забывают про вторую. Теперь различие сведено к паре
# (where, params), а логика одна.


def _summary(c, where: str, params: list) -> dict:
    def count(extra: str, extra_params: list | None = None) -> int:
        c.execute(f"SELECT COUNT(*) FROM posts WHERE {where}{extra}", params + (extra_params or []))
        return c.fetchone()["count"]

    total = count("")
    published = count(" AND status='published'")
    scheduled = count(" AND status='scheduled'")
    drafts = count(" AND status='draft'")

    c.execute(
        f"SELECT SUM(t.views) v,SUM(t.reactions) r,SUM(t.comments) cm,SUM(t.shares) sh "
        f"FROM {TOTALS} WHERE {where} AND status='published'",
        params,
    )
    s = c.fetchone()
    c.execute(
        f"SELECT id,title,t.views,t.reactions,t.comments,t.shares,published_at,vk_post_id "
        f"FROM {TOTALS} WHERE {where} AND status='published' "
        "ORDER BY (t.views+t.reactions*3+t.comments*2+t.shares*4) DESC LIMIT 5",
        params,
    )
    top = c.fetchall()
    pl_stats = _platform_stats(c, f"{where} AND status='published'", params)

    total_views = s["v"] or 0
    eng = round(((s["r"] or 0) + (s["cm"] or 0)) / max(total_views, 1) * 100, 1)
    return {
        "total_posts": total, "published": published, "scheduled": scheduled, "drafts": drafts,
        "total_views": total_views, "total_reactions": s["r"] or 0,
        "total_comments": s["cm"] or 0, "total_shares": s["sh"] or 0,
        "avg_views": round(total_views / max(published, 1)),
        "engagement_rate": eng,
        "top_posts": [dict(r) for r in top],
        "platform_stats": pl_stats,
    }


def _timeline(c, where: str, params: list, days: list) -> list[dict]:
    result = []
    for day in days:
        ds = day.strftime("%Y-%m-%d")
        c.execute(
            f"SELECT SUM(t.views) v, SUM(t.reactions) r, COUNT(*) p "
            f"FROM {TOTALS} WHERE {where} AND published_at::date = %s::date",
            params + [ds],
        )
        row = c.fetchone()
        result.append({
            "date": ds, "label": day.strftime("%d.%m"),
            "views": row["v"] or 0, "reactions": row["r"] or 0, "posts": row["p"] or 0,
        })
    return result


def _period_days(period: str) -> list:
    days = {"week": 7, "month": 30, "quarter": 90}.get(period, 30)
    now = app_now()
    return [now - timedelta(days=i) for i in range(days - 1, -1, -1)]


def _export(c, where: str, params: list, start_date: str, end_date: str):
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Формат дат: YYYY-MM-DD")

    end_next = (dt_end + timedelta(days=1)).strftime("%Y-%m-%d")
    start_str = dt_start.strftime("%Y-%m-%d")
    period = f"{where} AND published_at >= %s AND published_at < %s AND status='published'"
    period_params = params + [start_str, end_next]

    def count(sql: str, sql_params: list) -> int:
        c.execute(f"SELECT COUNT(*) FROM posts WHERE {sql}", sql_params)
        return c.fetchone()["count"]

    published = count(period, period_params)
    scheduled = count(f"{where} AND status='scheduled'", params)
    drafts = count(f"{where} AND status='draft'", params)
    total = count(f"{where} AND published_at >= %s AND published_at < %s",
                  params + [start_str, end_next])

    c.execute(
        f"SELECT SUM(t.views) v,SUM(t.reactions) r,SUM(t.comments) cm,SUM(t.shares) sh "
        f"FROM {TOTALS} WHERE {period}",
        period_params,
    )
    s = c.fetchone()
    total_views = s["v"] or 0
    eng = round(((s["r"] or 0) + (s["cm"] or 0)) / max(total_views, 1) * 100, 1)

    span = [dt_start + timedelta(days=i) for i in range((dt_end - dt_start).days + 1)]
    timeline = _timeline(c, where, params, span)
    pl_stats = _platform_stats(c, period, period_params, label_upper=True)

    c.execute(
        f"SELECT title,t.views,t.reactions,t.comments,t.shares,published_at "
        f"FROM {TOTALS} WHERE {period} "
        "ORDER BY (t.views+t.reactions*3+t.comments*2+t.shares*4) DESC LIMIT 10",
        period_params,
    )
    top_posts = c.fetchall()

    summary = {
        "total": total, "published": published, "scheduled": scheduled, "drafts": drafts,
        "total_views": total_views, "total_reactions": s["r"] or 0,
        "total_comments": s["cm"] or 0, "total_shares": s["sh"] or 0,
        "avg_views": round(total_views / max(published, 1)), "eng": eng,
    }
    wb = _build_workbook(dt_start, dt_end, summary, timeline, pl_stats, top_posts)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    month_ru = ["январь", "февраль", "март", "апрель", "май", "июнь",
                "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    fname = f"аналитика_{month_ru[dt_start.month - 1]}_{dt_start.year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8\'\'{quote(fname, safe='')}"},
    )


# ── Ручки: только выбор области, вся работа в ядре ──────────────────────────

@router.get("/api/analytics/summary")
def analytics_summary(user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        scope, sp = posts_scope(user_id, conn, alias="")
        return _summary(conn.cursor(), scope, list(sp))
    finally:
        conn.close()


@router.get("/api/analytics/timeline")
def analytics_timeline(period: str = "month", user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        scope, sp = posts_scope(user_id, conn, alias="")
        return _timeline(conn.cursor(), scope, list(sp), _period_days(period))
    finally:
        conn.close()


@router.get("/api/analytics/export")
def analytics_export(
    start_date: str = Query(...),
    end_date: str = Query(...),
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    try:
        scope, sp = posts_scope(user_id, conn, alias="")
        return _export(conn.cursor(), scope, list(sp), start_date, end_date)
    finally:
        conn.close()


# ── Group-scoped Analytics ──────────────────────────────────────────────────

@router.get("/api/groups/{gid}/analytics/summary")
def group_analytics_summary(gid: int, user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return _summary(conn.cursor(), "group_id=%s", [gid])
    finally:
        conn.close()


@router.get("/api/groups/{gid}/analytics/timeline")
def group_analytics_timeline(gid: int, period: str = "month", user_id: int = Depends(get_current_user_id)):
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return _timeline(conn.cursor(), "group_id=%s", [gid], _period_days(period))
    finally:
        conn.close()


@router.get("/api/groups/{gid}/analytics/export")
def group_analytics_export(
    gid: int,
    start_date: str = Query(...),
    end_date: str = Query(...),
    user_id: int = Depends(get_current_user_id),
):
    conn = get_db()
    try:
        require_group_member(gid, user_id, conn)
        return _export(conn.cursor(), "group_id=%s", [gid], start_date, end_date)
    finally:
        conn.close()
