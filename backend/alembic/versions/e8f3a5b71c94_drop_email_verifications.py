"""email_verifications больше не нужна: аккаунт создаётся сразу

Регистрация снова одношаговая: POST auth/register создаёт пользователя и сразу
выдаёт сессию. Подтверждение почты кодом убрано — письма не доходили, коды
протухали, и новые люди застревали между шагами. Таблица заявок с хешами
паролей опустела бы и стала мёртвым грузом.

Сброс пароля остаётся почтовым: таблица password_resets не трогается.

Revision ID: e8f3a5b71c94
Revises: a2e7b4f18c93
"""
import sqlalchemy as sa
from alembic import op

revision = "e8f3a5b71c94"
down_revision = "a2e7b4f18c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_email_verifications_email", table_name="email_verifications")
    op.drop_table("email_verifications")


def downgrade() -> None:
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True,
                  server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_verifications_email", "email_verifications", ["email"], unique=False
    )
    # invite_token из миграции b1c4d7e90a12 не восстанавливаем: он был нужен
    # только двухшаговой регистрации. Сами данные при downgrade не вернуть.
