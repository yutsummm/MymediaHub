"""Разводим глобальные роли с групповыми

В проекте было две системы ролей с одинаковыми названиями и разным смыслом:
users.role (глобальная) и group_members.role (внутри группы). Совпадали слова
«admin», «editor», «volunteer», а означали они разное — глобальный «editor» не
давал вообще ничего, а групповой давал право публикации.

При этом на бэкенде глобальная роль проверялась ровно в одном месте и ровно на
одно значение: require_admin() сравнивает с 'admin'. Значения 'editor' и
'volunteer' там не решали ничего и существовали только чтобы путаться с
групповыми — фронт по ним рисовал меню и показывал не те пункты тем, у кого
групповая роль другая.

Поэтому глобальная роль сводится к двум значениям: 'admin' (администратор
системы) и 'member' (обычный пользователь). Групповые роли остаются как были —
именно они определяют, что человек может делать с контентом.

Revision ID: b8e5c9a72f14
Revises: a7d3f2e64c81
"""
from alembic import op

revision = "b8e5c9a72f14"
down_revision = "a7d3f2e64c81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Никаких прав не теряется: на бэкенде эти значения не проверялись нигде,
    # а реальные права внутри групп лежат в group_members.role и не трогаются.
    op.execute("UPDATE users SET role='member' WHERE role <> 'admin'")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'member'")
    op.create_check_constraint(
        "users_role_check", "users", "role IN ('admin', 'member')"
    )


def downgrade() -> None:
    op.drop_constraint("users_role_check", "users", type_="check")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'editor'")
    # Обратно роли не восстановить: какая из двух прежних была у человека,
    # нигде не сохранилось. Всем не-администраторам ставим 'editor' — именно
    # его выдавала регистрация.
    op.execute("UPDATE users SET role='editor' WHERE role='member'")
