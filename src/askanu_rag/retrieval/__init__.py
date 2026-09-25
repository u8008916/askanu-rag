"""Deterministic retrieval interfaces."""

from askanu_rag.retrieval.identifiers import (
    COURSE_CODE_PATTERN,
    normalize_course_code,
    normalize_program_code,
    normalize_subplan_code,
)
from askanu_rag.retrieval.repository import (
    CourseProgramReader,
    CourseProgramRepository,
    CoursesEntityType,
    EventReader,
    JobLookupResult,
    JobReader,
    LookupResult,
    ResourceReader,
    ScholarshipReader,
    create_default_course_program_repository,
    load_common_record_file,
    load_common_records,
    load_common_records_directory,
    load_course_program_record_file,
    load_course_program_records,
    load_course_program_records_directory,
    normalize_job_title,
)
from askanu_rag.retrieval.postgres import (
    PostgresCourseProgramRepository,
    UnavailableCourseProgramRepository,
)
from askanu_rag.retrieval.embeddings import (
    DeterministicFakeEmbedder,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
)
from askanu_rag.retrieval.hybrid import (
    CandidateTier,
    RankedCandidate,
    SharedHybridRetriever,
)
from askanu_rag.retrieval.reranking import (
    CohereReranker,
    Reranker,
    RerankerError,
    RerankerUnavailableError,
)
from askanu_rag.retrieval.semantic import LocalBm25Retriever
from askanu_rag.retrieval.units import RetrievalUnit, RetrievalUnitBuilder
from askanu_rag.retrieval.vector import (
    EmbeddingIndexService,
    BackfillReport,
    InMemoryVectorRepository,
    PersistedSemanticRetriever,
    PostgresVectorRepository,
    VectorHit,
    VectorRepository,
    VectorReadiness,
)

__all__ = [
    "COURSE_CODE_PATTERN",
    "CourseProgramReader",
    "CourseProgramRepository",
    "CoursesEntityType",
    "CandidateTier",
    "DeterministicFakeEmbedder",
    "GeminiEmbeddingProvider",
    "EmbeddingIndexService",
    "BackfillReport",
    "EmbeddingProvider",
    "EventReader",
    "JobLookupResult",
    "JobReader",
    "InMemoryVectorRepository",
    "LookupResult",
    "LocalBm25Retriever",
    "PostgresCourseProgramRepository",
    "PostgresVectorRepository",
    "PersistedSemanticRetriever",
    "RankedCandidate",
    "ResourceReader",
    "ScholarshipReader",
    "SharedHybridRetriever",
    "CohereReranker",
    "Reranker",
    "RerankerError",
    "RerankerUnavailableError",
    "UnavailableCourseProgramRepository",
    "RetrievalUnit",
    "RetrievalUnitBuilder",
    "VectorHit",
    "VectorRepository",
    "VectorReadiness",
    "create_default_course_program_repository",
    "load_common_record_file",
    "load_common_records",
    "load_common_records_directory",
    "load_course_program_record_file",
    "load_course_program_records",
    "load_course_program_records_directory",
    "normalize_job_title",
    "normalize_course_code",
    "normalize_program_code",
    "normalize_subplan_code",
]
