"""tg_settings: смещение для чтения апдейтов Telegram

Реакции в Telegram нельзя запросить для уже опубликованного поста — Bot API
отдаёт их только как входящие апдейты message_reaction_count в момент
изменения. Значит, их надо вычитывать регулярно и не повторно: getUpdates
подтверждает прочитанное смещением, и это смещение надо где-то хранить.

Revision ID: a7d3f2e64c81
Revises: f4b2e8c15d93
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d3f2e64c81"
down_revision = "f4b2e8c15d93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tg_settings", sa.Column("updates_offset", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tg_settings", "updates_offset")
