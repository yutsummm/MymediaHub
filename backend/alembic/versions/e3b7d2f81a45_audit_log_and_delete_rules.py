"""Журнал действий и внятные правила удаления

Revision ID: e3b7d2f81a45
Revises: f1d4c8b73e29

Удаление в проекте было устроено случайно, и это выяснилось на первом же
запросе.

Половина внешних ключей стояла с CASCADE (участники, приглашения, медиа
волонтёров), половина — без правила вовсе (посты, уведомления, интеграции).
Поэтому `DELETE FROM groups` вёл себя по-разному в зависимости от содержимого
группы: пустую он сносил вместе с участниками и приглашениями, а группу хотя бы
с одним постом не удалял вообще — запрос падал с ForeignKeyViolation, и наружу
уходила пятисотка без объяснений. То же самое с пользователем: удалить того,
кто написал хоть один пост или создал группу, было нельзя.

Здесь правила приводятся к осмысленным и разным по смыслу:

* содержимое группы уходит вместе с группой (CASCADE) — посты, уведомления,
  подключённые интеграции; они без неё не существуют;
* следы человека содержимое не забирают (SET NULL) — пост остаётся, у него
  просто пропадает автор. Удаление сотрудника не должно стирать работу
  организации.

И заводится `audit_log`: кто, что и когда удалил. Раньше от удаления не
оставалось ничего — ни записи, ни возможности спросить.
"""
import sqlalchemy as sa
from alembic import op

revision = "e3b7d2f81a45"
down_revision = "f1d4c8b73e29"
branch_labels = None
depends_on = None


# (желаемое имя ограничения, таблица, колонка, на что ссылается, правило)
#
# Имя здесь — то, которое ключ получит ПОСЛЕ пересоздания. Снимать старый ключ
# по этому же имени нельзя: как он называется сейчас, зависит от того, чем базу
# создавали. Базы, поднятые миграциями, несут имена из `op.create_foreign_key`
# (`posts_group_fk`); база, доставшаяся от старого `init_db()` с обычным
# CREATE TABLE, несёт имена по умолчанию от PostgreSQL (`posts_group_id_fkey`)
# и была помечена BASELINE_REVISION без повторного DDL — то есть до этой
# миграции её схему никто не переименовывал.
# Ровно на этом выкатка и остановилась: `constraint "posts_group_fk" of
# relation "posts" does not exist`. Поэтому фактическое имя спрашиваем у
# каталога, а не предполагаем.
FK_RULES = [
    # Содержимое группы живёт только вместе с ней.
    ("posts_group_fk", "posts", "group_id", "groups", "CASCADE"),
    ("notifications_group_fk", "notifications", "group_id", "groups", "CASCADE"),
    ("vk_settings_workspace_fk", "vk_settings", "workspace_id", "groups", "CASCADE"),
    ("tg_settings_workspace_fk", "tg_settings", "workspace_id", "groups", "CASCADE"),
    # Следы человека: сам он уходит, сделанное остаётся.
    ("posts_author_id_fkey", "posts", "author_id", "users", "SET NULL"),
    ("groups_created_by_fkey", "groups", "created_by", "users", "SET NULL"),
    ("invite_links_created_by_fkey", "invite_links", "created_by", "users", "SET NULL"),
]

# Колонки, которым SET NULL требует разрешения на NULL.
NULLABLE = [("groups", "created_by"), ("invite_links", "created_by")]


def _current_fk(table: str, column: str) -> str | None:
    """
    Как внешний ключ этой колонки называется в базе прямо сейчас.

    None означает, что ключа нет вовсе — такое бывает, и это не повод падать:
    нам нужно, чтобы после миграции ключ был с нужным правилом, а не чтобы
    до неё он непременно был с определённым именем.
    """
    row = op.get_bind().execute(
        sa.text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid "
            "                   AND a.attnum = ANY (c.conkey) "
            "WHERE c.contype = 'f' AND c.conrelid = to_regclass(:tbl) "
            "  AND a.attname = :col AND array_length(c.conkey, 1) = 1 "
            "LIMIT 1"
        ),
        {"tbl": table, "col": column},
    ).fetchone()
    return row[0] if row else None


def _rebuild_fk(name: str, table: str, column: str, ref: str, rule: str | None) -> None:
    """Пересоздать внешний ключ с нужным правилом удаления и каноничным именем."""
    existing = _current_fk(table, column)
    if existing:
        op.drop_constraint(existing, table, type_="foreignkey")
    op.create_foreign_key(name, table, ref, [column], ["id"], ondelete=rule)


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        # Почта и имя — снимок на момент действия. Ссылки мало: удалённого
        # пользователя по ней уже не найти, а журнал должен читаться и потом.
        sa.Column("actor_email", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("object_label", sa.Text(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    # Журнал читают «последние сверху» и «что было с этим объектом».
    op.create_index("ix_audit_log_created", "audit_log", [sa.text("created_at DESC")])
    op.create_index("ix_audit_log_object", "audit_log", ["object_type", "object_id"])
    op.create_index("ix_audit_log_group", "audit_log", ["group_id"])

    for table, column in NULLABLE:
        op.alter_column(table, column, existing_type=sa.Integer(), nullable=True)

    for name, table, column, ref, rule in FK_RULES:
        _rebuild_fk(name, table, column, ref, rule)


def downgrade() -> None:
    for name, table, column, ref, _ in FK_RULES:
        _rebuild_fk(name, table, column, ref, None)

    for table, column in NULLABLE:
        op.execute(f"UPDATE {table} SET {column} = (SELECT MIN(id) FROM users) WHERE {column} IS NULL")  # noqa: S608
        op.alter_column(table, column, existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_audit_log_group", table_name="audit_log")
    op.drop_index("ix_audit_log_object", table_name="audit_log")
    op.drop_index("ix_audit_log_created", table_name="audit_log")
    op.drop_table("audit_log")
