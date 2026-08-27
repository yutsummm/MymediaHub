"""Свои шаблоны постов у группы

Шаблонов было четыре, они лежали в общей таблице без владельца и правились
только миграцией. Центру, который каждую неделю выпускает «Клуб настольных игр
в субботу», приходилось набирать одну и ту же рыбу заново — при том что
механика подстановки полей в проекте уже была.

**Владелец — группа, а не пользователь.** Шаблон описывает, как публикует
учреждение, а не отдельный человек: заведённый редактором, он должен остаться,
когда редактор уйдёт. `group_id IS NULL` — встроенные шаблоны, общие для всех.

**Уникальность `type` разъезжается по областям.** Раньше она была глобальной,
и две группы не смогли бы завести шаблон с одинаковым названием. Теперь два
частичных индекса: встроенные уникальны между собой, групповые — внутри своей
группы. Одним ограничением это не выразить: NULL в UNIQUE не сравнивается сам
с собой, и встроенные перестали бы проверяться вовсе.

`title_template` — заготовка заголовка. Без неё у своего шаблона заголовок
брать неоткуда: у встроенных он собирается по захардкоженному правилу на
каждый тип, и для произвольного шаблона такого правила не существует.

Revision ID: a2e7b4f18c93
Revises: f7a3d1c95e28
"""
import sqlalchemy as sa
from alembic import op

revision = "a2e7b4f18c93"
down_revision = "f7a3d1c95e28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("group_id", sa.Integer(), nullable=True))
    op.add_column("templates", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("templates", sa.Column("title_template", sa.Text(), nullable=True))
    op.add_column("templates", sa.Column(
        "created_at", sa.DateTime(timezone=True),
        server_default=sa.text("NOW()"), nullable=False))

    # Содержимое группы уходит вместе с ней, следы человека остаются без автора —
    # те же правила, что у постов (см. миграцию e3b7d2f81a45).
    op.create_foreign_key("templates_group_fk", "templates", "groups",
                          ["group_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("templates_author_fk", "templates", "users",
                          ["created_by"], ["id"], ondelete="SET NULL")

    op.drop_constraint("templates_type_key", "templates", type_="unique")
    op.execute("CREATE UNIQUE INDEX uq_templates_builtin ON templates (type) "
               "WHERE group_id IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_templates_group ON templates (group_id, type) "
               "WHERE group_id IS NOT NULL")
    op.create_index("ix_templates_group", "templates", ["group_id"])


def downgrade() -> None:
    # Групповые шаблоны без области существовать не могут: глобальная
    # уникальность type их не пропустит, а молча слить их со встроенными
    # значило бы подменить чужой шаблон своим.
    op.execute("DELETE FROM templates WHERE group_id IS NOT NULL")
    op.drop_index("ix_templates_group", table_name="templates")
    op.execute("DROP INDEX IF EXISTS uq_templates_group")
    op.execute("DROP INDEX IF EXISTS uq_templates_builtin")
    op.create_unique_constraint("templates_type_key", "templates", ["type"])
    op.drop_constraint("templates_author_fk", "templates", type_="foreignkey")
    op.drop_constraint("templates_group_fk", "templates", type_="foreignkey")
    op.drop_column("templates", "created_at")
    op.drop_column("templates", "title_template")
    op.drop_column("templates", "created_by")
    op.drop_column("templates", "group_id")
