"""Static contract tests for append-only V6 revision 0005."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
REVISION = ROOT / "migrations/versions/20260915_0005_shared_hybrid_embeddings.py"
PREVIOUS = ROOT / "migrations/versions/20260914_0004_jobs_records.py"


def load_revision():
    spec = importlib.util.spec_from_file_location("v6_revision", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v6_revision_is_append_only_after_0004():
    revision = load_revision()

    assert revision.revision == "20260915_0005"
    assert revision.down_revision == "20260914_0004"
    assert PREVIOUS.exists()


def test_v6_migration_has_shared_chunk_capable_vector_storage_and_no_ann():
    text = REVISION.read_text(encoding="utf-8")

    for expected in (
        "source_record_embeddings",
        "source_record_id",
        "retrieval_unit_id",
        "source_content_hash",
        "retrieval_content_hash",
        "embedding_model",
        "embedding_version",
        "embedding vector NOT NULL",
        "ON DELETE CASCADE",
        "role_requirements",
        "accommodation_anu_study",
        "support_anusa_student_assistance",
    ):
        assert expected in text
    assert "hnsw" not in text.casefold()
    assert "ivfflat" not in text.casefold()
    assert "20260914_0004_jobs_records" not in text


def test_v6_downgrade_preserves_extension_and_refuses_resource_data_loss():
    text = REVISION.read_text(encoding="utf-8")

    assert "DROP EXTENSION" not in text
    assert "Cannot downgrade while Accommodation/Support records exist" in text
    assert "metadata_json - 'role_requirements'" in text
