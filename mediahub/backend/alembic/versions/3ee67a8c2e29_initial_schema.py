"""initial_schema

Revision ID: 3ee67a8c2e29
Revises:
Create Date: 2026-05-31 04:02:03.277211
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3ee67a8c2e29"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="editor"),
        sa.Column("avatar", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # posts (without FK to groups — it's added via ALTER TABLE)
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("platforms", sa.Text(), nullable=False, server_default='["vk"]'),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("scheduled_at", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("template_type", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.Column("media", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("location_address", sa.Text(), nullable=True),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lng", sa.Float(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("vk_post_id", sa.Text(), nullable=True),
        sa.Column("tg_message_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("vk_stats_updated_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False, server_default="info"),
        sa.Column("is_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "vk_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False, server_default="1"),
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "connected_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tg_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False, server_default="1"),
        sa.Column("bot_token", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("chat_title", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "connected_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("avatar", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="editor"),
        sa.Column(
            "joined_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "user_id"),
    )

    op.create_table(
        "invite_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="editor"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "volunteer_media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("media", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD\"T\"HH24:MI')"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # FK for posts.group_id, added after groups table exists
    op.create_foreign_key("posts_group_fk", "posts", "groups", ["group_id"], ["groups.id"])
    op.create_foreign_key("notifications_group_fk", "notifications", "groups", ["group_id"], ["groups.id"])
    op.create_foreign_key("vk_settings_workspace_fk", "vk_settings", "groups", ["workspace_id"], ["groups.id"])
    op.create_foreign_key("tg_settings_workspace_fk", "tg_settings", "groups", ["workspace_id"], ["groups.id"])


def downgrade() -> None:
    op.drop_constraint("tg_settings_workspace_fk", "tg_settings", type_="foreignkey")
    op.drop_constraint("vk_settings_workspace_fk", "vk_settings", type_="foreignkey")
    op.drop_constraint("notifications_group_fk", "notifications", type_="foreignkey")
    op.drop_constraint("posts_group_fk", "posts", type_="foreignkey")
    op.drop_table("volunteer_media")
    op.drop_table("invite_links")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("password_resets")
    op.drop_table("email_verifications")
    op.drop_table("tg_settings")
    op.drop_table("vk_settings")
    op.drop_table("notifications")
    op.drop_table("templates")
    op.drop_table("posts")
    op.drop_table("users")
