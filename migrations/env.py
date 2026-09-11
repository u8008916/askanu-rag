"""Alembic environment using the same protected Day 6 configuration boundary."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL, make_url

from askanu_rag.config import Settings
from askanu_rag.database import DatabaseConfigurationError

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> URL:
    settings = Settings.from_environment()
    protected_url = settings.database_url.get_secret_value()
    if protected_url:
        url = make_url(protected_url)
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg")
        return url

    password = settings.database_password.get_secret_value()
    if not all(
        (
            settings.database_name,
            settings.database_user,
            password,
            settings.cloud_sql_instance_connection_name,
        )
    ):
        raise DatabaseConfigurationError()
    return URL.create(
        "postgresql+psycopg",
        username=settings.database_user,
        password=password,
        database=settings.database_name,
        query={
            "host": (
                f"/cloudsql/{settings.cloud_sql_instance_connection_name}"
            )
        },
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
