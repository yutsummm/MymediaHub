"""Свой текст под площадку и первый комментарий

**Один текст на все площадки — неверно по существу.** У Telegram другая
длина сообщения и другая разметка, хештеги там выглядят чужеродно, а ВКонтакте
режет охват записям со ссылками. Автор был вынужден писать под одну площадку
и мириться с тем, что на второй это смотрится хуже.

`content_overrides` — словарь «площадка → текст». Пустое переопределение
означает «взять общий текст», как было до сих пор: договор с интерфейсом не
меняется, а у постов, написанных раньше, поведение остаётся прежним.
Отдельной строки на каждую площадку не заводим — переопределение есть у
меньшинства постов, и таблица «пост × площадка» на девять десятых состояла бы
из NULL.

**Первый комментарий** — приём против того же среза охвата: ссылка уходит не
в тело записи, а первым комментарием под ней. Хранится одним полем, а не
словарём по площадкам: приём касается ВКонтакте, где ссылки бьют по охвату.
В Telegram ссылки охват не режут, а комментарии живут в отдельной группе
обсуждений, куда бот попадает не всегда — обещать там первый комментарий
значило бы обещать то, что работает через раз.

`vk_comment_id` хранит, что именно мы оставили: без этого расхождение между
нашей записью и стеной потом не объяснить.

Revision ID: e6d2a91f4c73
Revises: d1f9c4a83b62
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e6d2a91f4c73"
down_revision = "d1f9c4a83b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column(
        "content_overrides", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'{}'::jsonb")))
    op.add_column("posts", sa.Column("first_comment", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("vk_comment_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "vk_comment_id")
    op.drop_column("posts", "first_comment")
    op.drop_column("posts", "content_overrides")
