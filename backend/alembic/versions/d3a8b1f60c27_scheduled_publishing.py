"""posts: служебные поля для автопубликации отложенных постов

Планировщика в проекте не было вовсе: статус scheduled и поле scheduled_at
существовали, календарь позволял двигать посты по датам, но публиковать их в
назначенное время было некому. На проде так и висели шесть постов, просроченных
на три месяца.

publish_attempts служит атомарной «заявкой» на публикацию: воркер увеличивает
счётчик одним запросом с FOR UPDATE SKIP LOCKED и берёт пост в работу только
если это удалось — иначе два процесса опубликовали бы один пост дважды.
publish_error хранит причину неудачи, чтобы её было видно не только в уведомлении.

Revision ID: d3a8b1f60c27
Revises: c7f2a5b30d84
"""
import sqlalchemy as sa
from alembic import op

revision = "d3a8b1f60c27"
down_revision = "c7f2a5b30d84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("posts", sa.Column("publish_error", sa.Text(), nullable=True))
    # Планировщик каждую минуту ищет ровно по этим двум колонкам
    op.create_index(
        "ix_posts_scheduled", "posts", ["status", "scheduled_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_posts_scheduled", table_name="posts")
    op.drop_column("posts", "publish_error")
    op.drop_column("posts", "publish_attempts")
