from fastapi import APIRouter, Depends
from utils import get_db, get_current_user_id

router = APIRouter()


@router.get("/api/notifications")
def get_notifications(
    user_id: int = Depends(get_current_user_id),
    limit: int = 50,
    offset: int = 0,
):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset),
    )
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s", (user_id,))
    total = c.fetchone()["count"]
    conn.close()
    return {"items": [dict(r) for r in rows], "total": total}


@router.put("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE id=%s", (notif_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
