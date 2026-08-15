"""Рейт-лимит и очередь публикации в базе

Две вещи, которые жили только внутри процесса и от этого не работали:

  * **Рейт-лимит** был обычным словарём в памяти. Он обнулялся при каждой
    выкатке (а их бывает несколько подряд) и не знал ничего о втором инстансе:
    при двух процессах лимит на подбор пароля фактически удваивался.

  * **Публикация** шла прямо внутри HTTP-запроса. Загрузка видео в ВК с
    таймаутом 120 секунд означала, что тяжёлый пост либо подвешивал запрос,
    либо отваливался по таймауту прокси — причём пост при этом уже мог уйти.

Обе таблицы намеренно в базе: это единственное, что у сервисов общее.

Revision ID: c2f8a4d16b73
Revises: b8e5c9a72f14
"""
import sqlalchemy as sa
from alembic import op

revision = "c2f8a4d16b73"
down_revision = "b8e5c9a72f14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("key"),
    )
    # Старые окна вычищаются пачкой, по времени
    op.create_index("ix_rate_limits_window", "rate_limits", ["window_start"], unique=False)

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        # queued → running → done | failed
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(
        "publish_jobs_post_fk", "publish_jobs", "posts", ["post_id"], ["id"], ondelete="CASCADE"
    )
    # Воркер каждую секунду ищет ровно по состоянию
    op.create_index("ix_publish_jobs_state", "publish_jobs", ["state"], unique=False)
    # Один пост не должен стоять в очереди дважды: два клика по «Опубликовать»
    # не должны дать две записи на стене.
    op.execute(
        "CREATE UNIQUE INDEX uq_publish_jobs_active ON publish_jobs (post_id) "
        "WHERE state IN ('queued', 'running')"
    )


def downgrade() -> None:
    op.drop_index("ix_publish_jobs_state", table_name="publish_jobs")
    op.execute("DROP INDEX IF EXISTS uq_publish_jobs_active")
    op.drop_table("publish_jobs")
    op.drop_index("ix_rate_limits_window", table_name="rate_limits")
    op.drop_table("rate_limits")
