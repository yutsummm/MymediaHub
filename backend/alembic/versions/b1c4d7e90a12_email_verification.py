"""email_verifications: токен приглашения в заявке на регистрацию

Регистрация стала двухшаговой: пользователь не создаётся, пока почта не
подтверждена, а заявка лежит в email_verifications. Ссылка-приглашение приходит
на первом шаге, а применять её нужно на втором — значит токен надо где-то
хранить между шагами.

Revision ID: b1c4d7e90a12
Revises: 3ee67a8c2e29
"""
import sqlalchemy as sa
from alembic import op

revision = "b1c4d7e90a12"
down_revision = "3ee67a8c2e29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_verifications", sa.Column("invite_token", sa.Text(), nullable=True))
    # Заявки ищутся и чистятся по email — на проде их будет немного, но индекс
    # заодно защищает от полного скана при переборе кодов.
    op.create_index(
        "ix_email_verifications_email", "email_verifications", ["email"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_email_verifications_email", table_name="email_verifications")
    op.drop_column("email_verifications", "invite_token")
