"""Статистика — отдельно по каждой площадке

posts.views / reactions / comments / shares были одним набором на пост, общим
для всех площадок. Писала их только синхронизация ВК, и писала целиком —
поэтому появись сбор по Telegram, две площадки начали бы затирать цифры друг
друга, и понять, чьи числа сейчас в колонке, стало бы невозможно.

Заводим post_stats с ключом (post_id, platform). NULL в счётчике означает
«не собирали», ноль — «собрали, там ноль»: разница принципиальная, из-за неё
раньше вконтактовские просмотры показывались как телеграмные.

Старые значения переносим в строку платформы «vk» — эти колонки заполняла
только она.

Revision ID: f4b2e8c15d93
Revises: e5c9d4a71b38
"""
import sqlalchemy as sa
from alembic import op

revision = "f4b2e8c15d93"
down_revision = "e5c9d4a71b38"
branch_labels = None
depends_on = None

LEGACY = ("views", "reactions", "comments", "shares")


def upgrade() -> None:
    op.create_table(
        "post_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        # NULL — не собирали. Ноль — собрали, там ноль.
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("reactions", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "platform", name="uq_post_stats_post_platform"),
    )
    op.create_foreign_key(
        "post_stats_post_fk", "post_stats", "posts", ["post_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_post_stats_platform", "post_stats", ["platform"], unique=False)

    # Переносим накопленное. Берём только опубликованные и только те, где хоть
    # что-то ненулевое: нули у черновиков — это server_default, а не измерение.
    op.execute(
        "INSERT INTO post_stats (post_id, platform, views, reactions, comments, shares, updated_at) "
        "SELECT id, 'vk', views, reactions, comments, shares, vk_stats_updated_at "
        "FROM posts "
        "WHERE status='published' "
        "  AND (COALESCE(views,0) + COALESCE(reactions,0) "
        "     + COALESCE(comments,0) + COALESCE(shares,0)) > 0"
    )

    for column in LEGACY:
        op.drop_column("posts", column)

    # Аналитике почти везде нужна сумма по всем площадкам. Представление держит
    # это знание в одном месте — иначе одинаковый подзапрос разъехался бы по
    # полутора десяткам мест, как когда-то разъехалась сама публикация.
    op.execute(
        "CREATE VIEW post_totals AS "
        "SELECT p.id AS post_id, "
        "       COALESCE(SUM(s.views), 0) AS views, "
        "       COALESCE(SUM(s.reactions), 0) AS reactions, "
        "       COALESCE(SUM(s.comments), 0) AS comments, "
        "       COALESCE(SUM(s.shares), 0) AS shares "
        "FROM posts p LEFT JOIN post_stats s ON s.post_id = p.id "
        "GROUP BY p.id"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS post_totals")
    for column in LEGACY:
        op.add_column(
            "posts", sa.Column(column, sa.Integer(), nullable=True, server_default="0")
        )
    op.execute(
        "UPDATE posts p SET views=s.views, reactions=s.reactions, "
        "comments=s.comments, shares=s.shares "
        "FROM post_stats s WHERE s.post_id = p.id AND s.platform='vk'"
    )
    op.drop_index("ix_post_stats_platform", table_name="post_stats")
    op.drop_table("post_stats")
