"""Local runtime configuration; never expose credentials in representations."""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_EMBEDDING_VERSION = (
    "gemini-embedding-2:768:retrieval-format-v1:"
    "retrieval-unit-v2-structured"
)
DEFAULT_CHUNK_POLICY_VERSION = "retrieval-unit-v2-structured"
DEFAULT_RETRIEVAL_FORMAT_VERSION = "retrieval-format-v1"
DEFAULT_GCP_LOCATION = "australia-southeast1"
DEFAULT_PORT = 8081


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["local", "production", "test"] = "local"
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    cohere_api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""), repr=False
    )
    database_url: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    database_password: SecretStr = Field(
        default_factory=lambda: SecretStr(""), repr=False
    )
    database_name: str | None = None
    database_user: str | None = None
    model: str = Field(default=DEFAULT_GEMINI_MODEL, min_length=1)
    timeout_seconds: float = Field(default=20, gt=0, le=30)
    max_output_tokens: int = Field(default=4_096, gt=0, le=4_096)
    generation_thinking_level: Literal["low"] = "low"
    generation_max_retries: int = Field(default=2, ge=0, le=2)
    course_records_path: Path | None = None
    semantic_top_k: int = Field(default=20, ge=1, le=20)
    semantic_min_score: float = Field(default=0.2, gt=0, le=1)
    vector_top_k: int = Field(default=20, ge=1, le=20)
    vector_min_score: float = Field(default=0.35, gt=0, le=1)
    max_merged_candidates: int = Field(default=20, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1, le=1_000)
    rerank_provider: Literal["cohere"] = "cohere"
    rerank_model: str = Field(default="rerank-v4.0-fast", min_length=1)
    rerank_top_n: int = Field(default=5, ge=1, le=5)
    rerank_timeout_seconds: float = Field(default=5, gt=0, le=20)
    max_retrieval_unit_chars: int = Field(default=2_000, ge=256, le=20_000)
    max_retrieval_units_per_record: int = Field(default=20, ge=1, le=100)
    max_vector_units_per_record: int = Field(default=3, ge=1, le=20)
    embedding_provider: Literal["gemini"] = "gemini"
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)
    embedding_version: str = Field(default=DEFAULT_EMBEDDING_VERSION, min_length=1)
    retrieval_format_version: str = Field(
        default=DEFAULT_RETRIEVAL_FORMAT_VERSION, min_length=1
    )
    retrieval_policy_version: str = Field(
        default=DEFAULT_CHUNK_POLICY_VERSION, min_length=1
    )
    embedding_dimension: int = Field(default=768, ge=2, le=65_535)
    google_cloud_project: str | None = None
    google_cloud_location: str = Field(default=DEFAULT_GCP_LOCATION, min_length=1)
    cloud_sql_instance_connection_name: str | None = None
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65_535)
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    @model_validator(mode="after")
    def validate_embedding_identity(self) -> "Settings":
        expected = (
            f"{self.embedding_model}:{self.embedding_dimension}:"
            f"{self.retrieval_format_version}:{self.retrieval_policy_version}"
        )
        if self.embedding_version != expected:
            raise ValueError("embedding version does not match its compatibility identity")
        return self

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
            cohere_api_key=SecretStr(values.get("COHERE_API_KEY") or ""),
            database_url=SecretStr(values.get("DATABASE_URL") or ""),
            database_password=SecretStr(values.get("DB_PASSWORD") or ""),
            database_name=values.get("DB_NAME") or None,
            database_user=values.get("DB_USER") or None,
            model=(
                values.get("GENERATION_MODEL")
                or values.get("GEMINI_MODEL")
                or DEFAULT_GEMINI_MODEL
            ),
            timeout_seconds=(
                values.get("GENERATION_TIMEOUT_SECONDS")
                or values.get("REQUEST_TIMEOUT_SECONDS")
                or 20
            ),
            max_output_tokens=(
                values.get("GENERATION_MAX_OUTPUT_TOKENS")
                or values.get("MAX_OUTPUT_TOKENS")
                or 4_096
            ),
            generation_thinking_level=(
                values.get("GENERATION_THINKING_LEVEL") or "low"
            ),
            generation_max_retries=(
                values.get("GENERATION_MAX_RETRIES") or 2
            ),
            course_records_path=values.get("COURSE_RECORDS_PATH") or None,
            semantic_top_k=(
                values.get("SPARSE_CANDIDATE_K")
                or values.get("SEMANTIC_TOP_K")
                or 20
            ),
            semantic_min_score=values.get("SEMANTIC_MIN_SCORE") or 0.2,
            vector_top_k=(
                values.get("DENSE_CANDIDATE_K")
                or values.get("VECTOR_TOP_K")
                or 20
            ),
            vector_min_score=values.get("VECTOR_MIN_SCORE") or 0.35,
            max_merged_candidates=(
                values.get("FUSED_CANDIDATE_K")
                or values.get("MAX_MERGED_CANDIDATES")
                or 20
            ),
            rrf_k=values.get("RRF_K") or 60,
            rerank_provider=values.get("RERANK_PROVIDER") or "cohere",
            rerank_model=values.get("RERANK_MODEL") or "rerank-v4.0-fast",
            rerank_top_n=values.get("RERANK_TOP_N") or 5,
            rerank_timeout_seconds=values.get("RERANK_TIMEOUT_SECONDS") or 5,
            max_retrieval_unit_chars=(
                values.get("MAX_RETRIEVAL_UNIT_CHARS") or 2_000
            ),
            max_retrieval_units_per_record=(
                values.get("MAX_RETRIEVAL_UNITS_PER_RECORD") or 20
            ),
            max_vector_units_per_record=(
                values.get("MAX_VECTOR_UNITS_PER_RECORD") or 3
            ),
            embedding_provider=values.get("EMBEDDING_PROVIDER") or "gemini",
            embedding_model=(
                values.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
            ),
            embedding_version=(
                values.get("EMBEDDING_VERSION") or DEFAULT_EMBEDDING_VERSION
            ),
            retrieval_format_version=(
                values.get("RETRIEVAL_FORMAT_VERSION")
                or DEFAULT_RETRIEVAL_FORMAT_VERSION
            ),
            retrieval_policy_version=(
                values.get("CHUNK_POLICY_VERSION")
                or values.get("RETRIEVAL_POLICY_VERSION")
                or DEFAULT_CHUNK_POLICY_VERSION
            ),
            embedding_dimension=values.get("EMBEDDING_DIMENSION") or 768,
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
