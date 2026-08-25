"""Обращения под постами и срок ответа на них

С 1 декабря 2022 года государственные и муниципальные учреждения обязаны не
только вести официальные страницы в соцсетях, но и **отвечать на вопросы
граждан прямо в комментариях**. За этим следит система «Инцидент менеджмент»,
и там есть сроки: на обычное обращение — от восьми часов до суток.

Ни один сервис отложенного постинга в этом не помогает: они все про то, как
опубликовать, и ни один — про то, что происходит под публикацией. А для
молодёжного центра это не удобство, а прямая обязанность, за которую
спрашивают.

`post_comments` хранит и обращения, и наши ответы: без ответов невозможно
определить, отвечено ли, а держать их в другом месте значило бы собирать одну
ветку обсуждения из двух таблиц.

`group_id` продублирован намеренно и намеренно же без внешнего ключа: по нему
идут все выборки очереди и отчёт, а джойн к постам ради одного поля на каждой
строке — лишняя работа в самом частом запросе.

`answered_at` — денормализация: «отвечено ли» можно каждый раз выводить из
соседних строк, но именно по этому полю считается просрочка, и оно должно
быть устойчивым, а не пересчитываться при каждом обращении к очереди.

Revision ID: f7a3d1c95e28
Revises: e6d2a91f4c73
"""
import sqlalchemy as sa
from alembic import op

revision = "f7a3d1c95e28"
down_revision = "e6d2a91f4c73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=False),
        # Идентификатор в самой соцсети. По нему же ловим повторное вычитывание.
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("parent_external_id", sa.Text(), nullable=True),
        sa.Column("author_external_id", sa.Text(), nullable=True),
        sa.Column("author_name", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Наш ответ от лица сообщества, а не обращение.
        sa.Column("from_group", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        # Кто ответил из нашего интерфейса. NULL и при ответе из самой соцсети:
        # человек там есть, но у нас его учётной записи может не быть вовсе.
        sa.Column("answered_by", sa.Integer(), nullable=True),
        # Когда предупредили о приближении срока — чтобы не слать одно и то же
        # каждые пять минут.
        sa.Column("warned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["answered_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # Идентификатор комментария уникален в пределах записи, а не всего
        # ВКонтакте: у двух разных сообществ спокойно окажутся комментарии с
        # одним и тем же номером. Уникальность по паре (площадка, номер)
        # означала бы, что комментарий под чужим постом вытесняет наш.
        sa.UniqueConstraint("post_id", "platform", "external_id",
                            name="uq_post_comments_external"),
    )

    # Очередь обращений — «что не отвечено в этой группе, по возрастанию
    # давности». Частичный индекс: отвеченных со временем станет на порядки
    # больше, чем ждущих, и держать их в индексе очереди незачем.
    op.execute(
        "CREATE INDEX ix_post_comments_pending ON post_comments (group_id, created_at) "
        "WHERE answered_at IS NULL AND from_group = false"
    )
    # Отчёт считает и отвеченные тоже — по группе и периоду.
    op.create_index("ix_post_comments_group", "post_comments", ["group_id", "created_at"])

    op.add_column("groups", sa.Column(
        "reply_sla_hours", sa.Integer(), nullable=False, server_default=sa.text("8")))


def downgrade() -> None:
    op.drop_column("groups", "reply_sla_hours")
    op.drop_index("ix_post_comments_group", table_name="post_comments")
    op.execute("DROP INDEX IF EXISTS ix_post_comments_pending")
    op.drop_table("post_comments")
