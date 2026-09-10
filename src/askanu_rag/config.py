"""Local runtime configuration; never expose credentials in representations."""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GCP_LOCATION = "australia-southeast1"
DEFAULT_PORT = 8081


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["local", "production", "test"] = "local"
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    database_url: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    database_password: SecretStr = Field(
        default_factory=lambda: SecretStr(""), repr=False
    )
    database_name: str | None = None
    database_user: str | None = None
    model: str = Field(default=DEFAULT_GEMINI_MODEL, min_length=1)
    timeout_seconds: float = Field(default=30, gt=0, le=30)
    max_output_tokens: int = Field(default=800, gt=0, le=800)
    course_records_path: Path | None = None
    semantic_top_k: int = Field(default=3, ge=1, le=3)
    semantic_min_score: float = Field(default=0.2, gt=0, le=1)
    google_cloud_project: str | None = None
    google_cloud_location: str = Field(default=DEFAULT_GCP_LOCATION, min_length=1)
    cloud_sql_instance_connection_name: str | None = None
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65_535)
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> "Settings":
        # Production is process-environment only so an image-local file cannot
        # override the Secret Manager/Cloud Run configuration boundary.
        environment = (os.environ.get("ASKANU_ENV") or "local").strip().lower()
        file_values = (
            {}
            if environment == "production"
            else dotenv_values(env_file or Path.cwd() / ".env")
        )
        # Explicit CWD file only, no parent traversal or os.environ mutation.
        values = {**file_values, **os.environ}
        return cls(
            environment=environment,
            api_key=SecretStr(values.get("GEMINI_API_KEY") or ""),
            database_url=SecretStr(values.get("DATABASE_URL") or ""),
            database_password=SecretStr(values.get("DB_PASSWORD") or ""),
            database_name=values.get("DB_NAME") or None,
            database_user=values.get("DB_USER") or None,
            model=values.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            timeout_seconds=values.get("REQUEST_TIMEOUT_SECONDS") or 30,
            max_output_tokens=values.get("MAX_OUTPUT_TOKENS") or 800,
            course_records_path=values.get("COURSE_RECORDS_PATH") or None,
            semantic_top_k=values.get("SEMANTIC_TOP_K") or 3,
            semantic_min_score=values.get("SEMANTIC_MIN_SCORE") or 0.2,
            google_cloud_project=values.get("GOOGLE_CLOUD_PROJECT") or None,
            google_cloud_location=(
                values.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_GCP_LOCATION
            ),
            cloud_sql_instance_connection_name=(
                values.get("CLOUD_SQL_INSTANCE_CONNECTION_NAME") or None
            ),
            port=values.get("PORT") or DEFAULT_PORT,
            log_level=(values.get("LOG_LEVEL") or "info").strip().lower(),
        )
