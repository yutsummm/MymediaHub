"""Согласование постов перед публикацией

Редактор публиковал прямо в официальные каналы учреждения, без чьего-либо
ведома. Для молодёжного центра это странно: у публикации от лица организации
есть ответственный, и он должен успеть увидеть текст до того, как тот выйдет.

Отсюда статус `on_review` и три колонки при нём: кто посмотрел, когда и что
сказал, если вернул на доработку. Отдельного «намерения автора» не храним —
после одобрения пост уходит туда, куда собирался: есть будущая `scheduled_at`
значит в расписание, нет — сразу в очередь публикации. Лишняя колонка здесь
означала бы второй источник правды о том же самом.

`groups.require_approval` — выключатель, и он нужен. Молча включить
согласование во всех существующих группах нельзя: там, где единственный
активный человек — редактор, публиковать стало бы физически некому, и группа
встала бы намертво без единого сообщения об ошибке. Поэтому новые группы
получают согласование включённым (это правильное поведение по умолчанию), а
уже заведённые — выключенным, и включают его сами, когда захотят.

CHECK на posts.status намеренно не заводим: в базе, пришедшей из старого
init_db, статусы никто не проверял, и миграция упала бы на первом же значении,
которого мы не ждём. Набор статусов стережёт приложение (POST_STATUSES).

Revision ID: c8b3f5d21a70
Revises: b2e6a3d95f41
"""
import sqlalchemy as sa
from alembic import op

revision = "c8b3f5d21a70"
down_revision = "b2e6a3d95f41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("review_comment", sa.Text(), nullable=True))
    # Рецензент уходит — пост остаётся: удаление сотрудника не должно уносить
    # работу организации. То же правило, что у posts.author_id.
    op.create_foreign_key(
        "posts_reviewed_by_fk", "posts", "users", ["reviewed_by"], ["id"], ondelete="SET NULL"
    )

    op.add_column(
        "groups",
        sa.Column(
            "require_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Уже существующие группы работали без согласования — оставляем как было.
    op.execute("UPDATE groups SET require_approval = false")

    # Очередь согласования — это выборка «status='on_review' в такой-то группе».
    # Частичный индекс: строк с этим статусом всегда мало, а полный индекс по
    # status тут ничего не даёт.
    op.execute(
        "CREATE INDEX ix_posts_on_review ON posts (group_id, submitted_at) "
        "WHERE status = 'on_review'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_on_review")
    # Статуса on_review после отката не существует — посты в нём стали бы
    # невидимы для всех фильтров разом. Возвращаем их в черновики.
    op.execute("UPDATE posts SET status='draft' WHERE status='on_review'")
    op.drop_column("groups", "require_approval")
    op.drop_constraint("posts_reviewed_by_fk", "posts", type_="foreignkey")
    op.drop_column("posts", "review_comment")
    op.drop_column("posts", "reviewed_by")
    op.drop_column("posts", "reviewed_at")
    op.drop_column("posts", "submitted_at")
