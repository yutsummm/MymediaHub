import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from alembic import context

load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Тот же дефолт, что и в utils.DATABASE_URL — для локального запуска `alembic`
# из командной строки без .env. Дублируется намеренно: импорт utils потянул бы
# за собой побочные эффекты (создание uploads/, предупреждение про JWT_SECRET).
DEFAULT_DATABASE_URL = "postgresql://mediahub:mediahub123@localhost:5432/mediahub"


def get_database_url() -> str:
    """
    URL берётся в обход alembic.ini намеренно. ConfigParser интерполирует «%»,
    и URL-encoded пароль (Railway отдаёт, например, %40 вместо @) либо ломает
    запуск с `invalid interpolation syntax`, либо тихо искажается.
    """
    return (
        config.attributes.get("db_url")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Логирование настраивает приложение (backend/logs.py), а не alembic.ini.
#
# Здесь стоял fileConfig(config.config_file_name). Так делать нельзя: миграции
# катятся из startup-хука, то есть уже после того, как модули завели свои
# логгеры, а fileConfig по умолчанию все существующие логгеры выключает и
# заодно переустанавливает уровень корневого. Приложение после старта замолкало
# целиком — и заметить это, не имея логов, было бы особенно нечем.
#
# Сообщения самого alembic никуда не деваются: они уходят в корневой логгер
# и печатаются нашим обработчиком.

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(get_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
