"""post_totals отличает «собрали ноль» от «не собирали»

Проект держится на разнице между NULL («счётчик не собирали») и нулём
(«собрали, там ноль») — см. post_stats. Представление post_totals эту разницу
теряло: COALESCE(SUM(s.views), 0) отдаёт ноль и для поста, по которому никто
ничего не синхронизировал.

Одному потребителю это было безразлично (сумма просмотров и есть ноль), а вот
производным показателям — нет. Вовлечённость считалась как отклики / просмотры,
и при нуле в знаменателе выдавала либо трёхзначные проценты, либо ровные
«0,0 %», неотличимые от честного «людям не заходит».

Сами суммы оставляем как есть — на них завязана сортировка топа и выдача
наружу. Рядом добавляем счётчики собранных значений: COUNT игнорирует NULL,
поэтому ноль в такой колонке означает ровно «по этому посту цифр нет».

Revision ID: b2e6a3d95f41
Revises: a9d4f1c60b72
"""
from alembic import op

revision = "b2e6a3d95f41"
down_revision = "a9d4f1c60b72"
branch_labels = None
depends_on = None

FIELDS = ("views", "reactions", "comments", "shares")

SUMS = ", ".join(f"COALESCE(SUM(s.{f}), 0) AS {f}" for f in FIELDS)
SAMPLES = ", ".join(f"COUNT(s.{f}) AS {f}_samples" for f in FIELDS)


def _create(with_samples: bool) -> None:
    columns = SUMS + (f", {SAMPLES}" if with_samples else "")
    op.execute(
        "CREATE OR REPLACE VIEW post_totals AS "
        f"SELECT p.id AS post_id, {columns} "
        "FROM posts p LEFT JOIN post_stats s ON s.post_id = p.id "
        "GROUP BY p.id"
    )


def upgrade() -> None:
    # CREATE OR REPLACE VIEW умеет дописывать колонки в конец — прежние
    # остаются на своих местах, и запросы, которые их выбирают, не ломаются.
    _create(with_samples=True)


def downgrade() -> None:
    # Убрать колонку заменой нельзя — только пересозданием.
    op.execute("DROP VIEW IF EXISTS post_totals")
    _create(with_samples=False)
