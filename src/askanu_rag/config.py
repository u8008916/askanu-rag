"""Local runtime configuration; never expose credentials in representations."""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), repr=False)
    model: str = Field(default=DEFAULT_GEMINI_MODEL, min_length=1)
    timeout_seconds: float = Field(default=30, gt=0, le=30)
    max_output_tokens: int = Field(default=800, gt=0, le=800)
    course_records_path: Path | None = None
    semantic_top_k: int = Field(default=3, ge=1, le=3)
    semantic_min_score: float = Field(default=0.2, gt=0, le=1)

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> "Settings":
        # Explicit CWD file only, no parent traversal or mutation of os.environ.
        values = {**dotenv_values(env_file or Path.cwd() / ".env"), **os.environ}
        return cls(
            api_key=SecretStr(values.get("GEMINI_API_KEY") or ""),
            model=values.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            timeout_seconds=values.get("REQUEST_TIMEOUT_SECONDS") or 30,
            max_output_tokens=values.get("MAX_OUTPUT_TOKENS") or 800,
            course_records_path=values.get("COURSE_RECORDS_PATH") or None,
            semantic_top_k=values.get("SEMANTIC_TOP_K") or 3,
            semantic_min_score=values.get("SEMANTIC_MIN_SCORE") or 0.2,
        )
