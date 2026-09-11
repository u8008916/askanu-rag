"""Protected PostgreSQL connection construction for Cloud SQL and migrations."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from pydantic import SecretStr

from askanu_rag.config import Settings


class DatabaseConfigurationError(RuntimeError):
    """Safe configuration error that never contains connection values."""

    def __init__(self) -> None:
        super().__init__("Database configuration is incomplete.")


class RepositoryUnavailableError(RuntimeError):
    """Safe persistence boundary failure for controlled HTTP handling."""

    def __init__(self) -> None:
        super().__init__("The configured repository is unavailable.")


@dataclass(frozen=True, repr=False)
class DatabaseConnectionConfig:
    """Connection material kept out of repr/log output."""

    database_url: SecretStr | None = None
    database_name: str | None = None
    database_user: str | None = None
    database_password: SecretStr | None = None
    cloud_sql_instance_connection_name: str | None = None
    connect_timeout_seconds: int = 5

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabaseConnectionConfig":
        url = settings.database_url.get_secret_value()
        if url:
            return cls(database_url=SecretStr(url))

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

        return cls(
            database_name=settings.database_name,
            database_user=settings.database_user,
            database_password=SecretStr(password),
            cloud_sql_instance_connection_name=(
                settings.cloud_sql_instance_connection_name
            ),
        )

    @property
    def cloud_sql_socket(self) -> str | None:
        if self.cloud_sql_instance_connection_name is None:
            return None
        return f"/cloudsql/{self.cloud_sql_instance_connection_name}"

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        """Open one short-lived psycopg connection with dictionary rows."""

        if self.database_url is not None:
            conninfo = self.database_url.get_secret_value()
            if conninfo.startswith("postgresql+psycopg://"):
                conninfo = "postgresql://" + conninfo.removeprefix(
                    "postgresql+psycopg://"
                )
            return psycopg.connect(
                conninfo,
                connect_timeout=self.connect_timeout_seconds,
                row_factory=dict_row,
            )

        if (
            self.database_name is None
            or self.database_user is None
            or self.database_password is None
            or self.cloud_sql_socket is None
        ):
            raise DatabaseConfigurationError()

        return psycopg.connect(
            dbname=self.database_name,
            user=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.cloud_sql_socket,
            connect_timeout=self.connect_timeout_seconds,
            row_factory=dict_row,
        )


ConnectionFactory = Callable[[], Any]
