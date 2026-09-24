"""Shared byte-level limits for the stateless App-to-RAG ask transport."""

from __future__ import annotations

import json
from typing import Any

from pydantic_core import PydanticCustomError

STATE_MAX_BYTES = 128 * 1024
HISTORY_MAX_BYTES = 96 * 1024
QUESTION_MAX_UTF8_BYTES = 8 * 1024
ASK_REQUEST_MAX_BYTES = 256 * 1024

HISTORY_TURN_ID_MAX_CHARS = 128
HISTORY_TURN_CONTENT_MAX_CHARS = 10_000


def compact_json_utf8(value: Any) -> bytes:
    """Return the deterministic compact JSON representation used for limits."""

    def json_default(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        raise TypeError(f"{type(item).__name__} is not JSON serializable")

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
        default=json_default,
    ).encode("utf-8")


def serialized_utf8_size(value: Any) -> int:
    """Measure the compact contract JSON representation in UTF-8 bytes."""

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return len(compact_json_utf8(value))


def validate_utf8_text_limit(value: str, max_bytes: int, component: str) -> str:
    """Reject text above a byte limit without truncation."""

    actual_bytes = len(value.encode("utf-8"))
    if actual_bytes > max_bytes:
        raise PydanticCustomError(
            "bytes_too_long",
            "{component} must be at most {max_bytes} UTF-8 bytes",
            {
                "component": component,
                "max_bytes": max_bytes,
                "actual_bytes": actual_bytes,
            },
        )
    return value


def validate_serialized_limit(value: Any, max_bytes: int, component: str) -> Any:
    """Reject a component above its compact-JSON byte limit without truncation."""

    actual_bytes = serialized_utf8_size(value)
    if actual_bytes > max_bytes:
        raise PydanticCustomError(
            "bytes_too_long",
            "serialized {component} must be at most {max_bytes} UTF-8 bytes",
            {
                "component": component,
                "max_bytes": max_bytes,
                "actual_bytes": actual_bytes,
            },
        )
    return value


def state_fits_transport(value: Any) -> bool:
    """Return whether a state can be carried through the frozen transport."""

    return serialized_utf8_size(value) <= STATE_MAX_BYTES
