"""vk_settings/tg_settings: id должен быть автоинкрементом

id в обеих таблицах был объявлен как INTEGER NOT NULL DEFAULT 1 — то есть
последовательности не было вовсе. Глобальные настройки пишутся с явным id=1,
а групповые id не указывают и получают тот же самый 1. В результате вторая по
счёту интеграция падала с UniqueViolation по первичному ключу: подключить VK
или Telegram больше чем к одной группе было невозможно в принципе.

Заводим настоящие последовательности и подтягиваем их к максимальному
существующему id, чтобы уже записанные строки не мешали новым.

Revision ID: c7f2a5b30d84
Revises: b1c4d7e90a12
"""
from alembic import op

revision = "c7f2a5b30d84"
down_revision = "b1c4d7e90a12"
branch_labels = None
depends_on = None

TABLES = ("vk_settings", "tg_settings")


def upgrade() -> None:
    for table in TABLES:
        seq = f"{table}_id_seq"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} OWNED BY {table}.id")
        # id=1 навсегда закреплён за глобальными (легаси) настройками: они
        # пишутся с явным id и последовательность не двигают. Поэтому выдавать
        # единицу нельзя ни при каких условиях — стартуем минимум с двойки.
        # false третьим аргументом: следующий nextval вернёт именно это число,
        # а не следующее за ним.
        op.execute(
            f"SELECT setval('{seq}', "
            f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 0), 1) + 1, false)"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq}')")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT 1")
        op.execute(f"DROP SEQUENCE IF EXISTS {table}_id_seq")
