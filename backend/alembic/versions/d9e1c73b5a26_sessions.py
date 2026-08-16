"""Сессии: токен должен быть отзываемым

JWT подписан и проверяется без обращения к базе — отозвать его было нельзя
ничем. Выход из аккаунта существовал только на клиенте: приложение забывало
токен, а сам токен оставался действительным ещё до 72 часов. Украденный токен
работал всё это время, и сменить пароль не помогало.

Теперь у каждого токена есть идентификатор (jti), которому соответствует строка
в sessions. Проверка на запросе — точечный поиск по первичному ключу, а выход,
смена пароля и «выйти на всех устройствах» реально гасят токены.

Revision ID: d9e1c73b5a26
Revises: c2f8a4d16b73
"""
import sqlalchemy as sa
from alembic import op

revision = "d9e1c73b5a26"
down_revision = "c2f8a4d16b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_foreign_key(
        "sessions_user_fk", "sessions", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    # «Выйти на всех устройствах» и чистка просроченных ходят по этим двум полям
    op.create_index("ix_sessions_user", "sessions", ["user_id"], unique=False)
    op.create_index("ix_sessions_expires", "sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sessions_expires", table_name="sessions")
    op.drop_index("ix_sessions_user", table_name="sessions")
    op.drop_table("sessions")
