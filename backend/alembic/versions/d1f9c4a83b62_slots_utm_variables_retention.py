"""Очередь по слотам, UTM, переменные и хештеги группы, автоснятие поста

Пять вещей, у которых общий знаменатель — «настройка живёт на группе, а не на
посте», плюс одна колонка про судьбу уже вышедшего поста.

**Слоты публикации.** Дата у каждого поста — это ручная работа, которую
центр делает по десять раз в месяц, каждый раз заново вспоминая, когда он
обычно публикует. Слот описывает привычку («пн, ср, пт в 12:00»), а пост
просто встаёт в ближайшее свободное окно. Отдельного статуса под это нет
сознательно: сервер считает конкретное время и записывает обычный
`scheduled_at`, дальше работает тот же планировщик. Пост с настоящей датой
виден в календаре и понятен человеку, а «очередь» не становится вторым
механизмом публикации рядом с существующим.

**UTM.** Без меток любой переход из соцсети выглядит в статистике сайта как
«прямой заход», и вопрос «сколько людей к нам пришло» остаётся без ответа
навсегда. Метки проставляются на выпуске, в хранимый текст не попадают:
человек написал ссылку — он же должен видеть её в редакторе такой, какой
написал.

**Переменные и наборы хештегов.** Название центра, адрес и телефон
повторяются в каждом втором посте, а хештеги набираются заново каждый раз.
`variables` — словарь подстановок `{{ключ}}`, `hashtag_sets` — именованные
наборы.

**Автоснятие.** Анонс прошедшего мероприятия висит в ленте и путает людей.
`auto_delete_at` — когда убрать запись из соцсети; `removed_at` — когда
убрали на самом деле. Пост при этом остаётся у нас: он был опубликован, и в
отчёте за период обязан посчитаться. Из ленты исчезает запись, а не факт.

Revision ID: d1f9c4a83b62
Revises: c8b3f5d21a70
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1f9c4a83b62"
down_revision = "c8b3f5d21a70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publishing_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        # 0 — понедельник, 6 — воскресенье. ISO-порядок, тот же, что у
        # datetime.weekday(): считать дни недели двумя способами в одном
        # проекте — верный путь к посту, вышедшему не в тот день.
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="publishing_slots_weekday_range"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Один и тот же слот дважды — это не «два поста в это время», а
        # опечатка: расписание описывает привычку, а не количество мест.
        sa.UniqueConstraint("group_id", "weekday", "at", name="uq_publishing_slots"),
    )
    op.create_index("ix_publishing_slots_group", "publishing_slots", ["group_id", "weekday", "at"])

    op.add_column("groups", sa.Column(
        "utm_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("groups", sa.Column(
        "variables", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("groups", sa.Column(
        "hashtag_sets", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

    op.add_column("posts", sa.Column("auto_delete_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("posts", sa.Column("remove_error", sa.Text(), nullable=True))

    # Выборка автоснятия — «кому пора и кого ещё не снимали». Частичный индекс:
    # таких постов всегда единицы, а полный индекс по колонке, которая почти
    # везде NULL, не нужен никому.
    op.execute(
        "CREATE INDEX ix_posts_auto_delete ON posts (auto_delete_at) "
        "WHERE auto_delete_at IS NOT NULL AND removed_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_auto_delete")
    op.drop_column("posts", "remove_error")
    op.drop_column("posts", "removed_at")
    op.drop_column("posts", "auto_delete_at")
    op.drop_column("groups", "hashtag_sets")
    op.drop_column("groups", "variables")
    op.drop_column("groups", "utm_enabled")
    op.drop_index("ix_publishing_slots_group", table_name="publishing_slots")
    op.drop_table("publishing_slots")
