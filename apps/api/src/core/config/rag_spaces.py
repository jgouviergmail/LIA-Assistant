"""
RAG Spaces configuration module.

Contains settings for:
- RAG Spaces feature toggle (enabled/disabled)
- Storage path and file size limits
- Chunking parameters (size, overlap)
- Retrieval parameters (limit, min score, max context tokens)
- Allowed MIME types (TXT, MD, PDF, DOCX)
- Embedding model configuration

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    RAG_DRIVE_MAX_SOURCES_PER_SPACE_DEFAULT,
    RAG_JOB_HEARTBEAT_INTERVAL_SECONDS_DEFAULT,
    RAG_JOB_LEASE_TTL_SECONDS_DEFAULT,
    RAG_JOB_MAX_ATTEMPTS_DEFAULT,
    RAG_JOB_REAPER_BATCH_SIZE_DEFAULT,
    RAG_JOB_REAPER_CONCURRENCY_DEFAULT,
    RAG_JOB_REAPER_GRACE_SECONDS_DEFAULT,
    RAG_JOB_REAPER_INTERVAL_SECONDS_DEFAULT,
    RAG_MAIL_MAX_SOURCES_PER_SPACE_DEFAULT,
    RAG_MAIL_MAX_THREAD_CHARS,
    RAG_MAIL_MAX_THREADS_PER_SYNC,
    RAG_REINDEX_LOCK_TTL_SECONDS_DEFAULT,
    RAG_SPACES_ALLOWED_TYPES_DEFAULT,
    RAG_SPACES_ARCHIVE_MAX_MB_DEFAULT,
    RAG_SPACES_BM25_BONUS_WEIGHT_DEFAULT,
    RAG_SPACES_CHUNK_OVERLAP_DEFAULT,
    RAG_SPACES_CHUNK_SIZE_DEFAULT,
    RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
    RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
    RAG_SPACES_MAX_CHUNKS_PER_DOCUMENT_DEFAULT,
    RAG_SPACES_MAX_CONTEXT_TOKENS_DEFAULT,
    RAG_SPACES_MAX_DOCS_PER_SPACE_DEFAULT,
    RAG_SPACES_MAX_FILE_SIZE_MB_DEFAULT,
    RAG_SPACES_MAX_SPACES_PER_USER_DEFAULT,
    RAG_SPACES_RETRIEVAL_LIMIT_DEFAULT,
    RAG_SPACES_RETRIEVAL_MIN_SCORE_DEFAULT,
    RAG_SPACES_STORAGE_PATH_DEFAULT,
    RAG_SPACES_SYSTEM_INDEX_EMBED_MAX_ATTEMPTS_DEFAULT,
    RAG_SPACES_SYSTEM_INDEX_EMBED_RETRY_BUDGET_SECONDS_DEFAULT,
    RAG_SPACES_SYSTEM_KNOWLEDGE_DIR_DEFAULT,
)


class RAGSpacesSettings(BaseSettings):
    """RAG Spaces settings for user knowledge document management."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    rag_spaces_enabled: bool = Field(
        default=True,
        description=(
            "Enable RAG Spaces feature. When true, users can create knowledge "
            "spaces, upload documents, and enrich AI responses with their content."
        ),
    )

    # ========================================================================
    # Storage Configuration
    # ========================================================================

    rag_spaces_storage_path: str = Field(
        default=RAG_SPACES_STORAGE_PATH_DEFAULT,
        description="Base storage path for uploaded RAG documents on disk.",
    )

    rag_spaces_max_file_size_mb: int = Field(
        default=RAG_SPACES_MAX_FILE_SIZE_MB_DEFAULT,
        ge=1,
        le=100,
        description="Maximum file size in MB for uploaded documents.",
    )

    rag_spaces_max_spaces_per_user: int = Field(
        default=RAG_SPACES_MAX_SPACES_PER_USER_DEFAULT,
        ge=1,
        le=50,
        description="Maximum number of RAG spaces per user.",
    )

    rag_spaces_max_docs_per_space: int = Field(
        default=RAG_SPACES_MAX_DOCS_PER_SPACE_DEFAULT,
        ge=1,
        le=200,
        description="Maximum number of documents per RAG space.",
    )

    rag_spaces_archive_max_mb: int = Field(
        default=RAG_SPACES_ARCHIVE_MAX_MB_DEFAULT,
        ge=1,
        le=2048,
        description=(
            "Maximum total size (MB) of the documents a single archive download may "
            "bundle (ADR-259); beyond it the request is refused with 413."
        ),
    )

    rag_reindex_lock_ttl_seconds: int = Field(
        default=RAG_REINDEX_LOCK_TTL_SECONDS_DEFAULT,
        ge=60,
        le=21600,
        description=(
            "TTL of the reindex distributed lock (F001). Renewed after each "
            "document, so a live reindex keeps it; a crash frees it within this "
            "window. Must exceed the slowest single-document re-embed."
        ),
    )

    rag_spaces_system_index_embed_max_attempts: int = Field(
        default=RAG_SPACES_SYSTEM_INDEX_EMBED_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=10,
        description=(
            "Attempts (including the first) for each embedding batch of the "
            "startup FAQ indexation. The Gemini SDK never retries by itself, so "
            "without this a single transient 429/5xx leaves the knowledge base "
            "stale until the next boot. 1 disables retrying."
        ),
    )
    rag_spaces_system_index_embed_retry_budget_seconds: float = Field(
        default=RAG_SPACES_SYSTEM_INDEX_EMBED_RETRY_BUDGET_SECONDS_DEFAULT,
        ge=0.0,
        le=600.0,
        description=(
            "Total wall-clock budget for retrying the startup FAQ embedding, "
            "across all batches and attempts. Also caps how long the exclusive "
            "claim on the space row is held, since retries happen under it."
        ),
    )

    # ========================================================================
    # Durable Jobs (audit F001): entity-as-job lease/heartbeat/retry + reaper
    # ========================================================================

    rag_job_lease_ttl_seconds: int = Field(
        default=RAG_JOB_LEASE_TTL_SECONDS_DEFAULT,
        ge=30,
        le=21600,
        description=(
            "How long a worker's claim on a document/sync job stays valid before "
            "the reaper may reclaim it. Must exceed the slowest single work unit."
        ),
    )
    rag_job_heartbeat_interval_seconds: int = Field(
        default=RAG_JOB_HEARTBEAT_INTERVAL_SECONDS_DEFAULT,
        ge=5,
        le=3600,
        description=(
            "How often a working worker renews its lease. MUST be strictly less "
            "than rag_job_lease_ttl_seconds (enforced) so a live job is never "
            "reclaimed."
        ),
    )
    rag_job_max_attempts: int = Field(
        default=RAG_JOB_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Bounded retry: after this many attempts a job is marked ERROR.",
    )
    rag_job_reaper_interval_seconds: int = Field(
        default=RAG_JOB_REAPER_INTERVAL_SECONDS_DEFAULT,
        ge=15,
        le=3600,
        description="How often the recovery reaper scans for stuck jobs.",
    )
    rag_job_reaper_grace_seconds: int = Field(
        default=RAG_JOB_REAPER_GRACE_SECONDS_DEFAULT,
        ge=5,
        le=3600,
        description=(
            "How long an unclaimed PENDING document may sit before the reaper "
            "treats it as orphaned (crash right after creation) and re-drives it."
        ),
    )
    rag_job_reaper_batch_size: int = Field(
        default=RAG_JOB_REAPER_BATCH_SIZE_DEFAULT,
        ge=1,
        le=1000,
        description="Max recoverable jobs re-driven per reaper tick (backlog bound).",
    )
    rag_job_reaper_concurrency: int = Field(
        default=RAG_JOB_REAPER_CONCURRENCY_DEFAULT,
        ge=1,
        le=64,
        description="Max concurrent re-drives within one reaper tick.",
    )

    @model_validator(mode="after")
    def _validate_heartbeat_below_lease(self) -> RAGSpacesSettings:
        """Enforce heartbeat < lease TTL (a live job must never be reclaimed)."""
        if self.rag_job_heartbeat_interval_seconds >= self.rag_job_lease_ttl_seconds:
            raise ValueError(
                "rag_job_heartbeat_interval_seconds must be < rag_job_lease_ttl_seconds "
                f"(got {self.rag_job_heartbeat_interval_seconds} >= "
                f"{self.rag_job_lease_ttl_seconds})"
            )
        return self

    # ========================================================================
    # Chunking Configuration
    # ========================================================================

    rag_spaces_chunk_size: int = Field(
        default=RAG_SPACES_CHUNK_SIZE_DEFAULT,
        ge=100,
        le=4000,
        description="Target chunk size in characters for document splitting.",
    )

    rag_spaces_chunk_overlap: int = Field(
        default=RAG_SPACES_CHUNK_OVERLAP_DEFAULT,
        ge=0,
        le=1000,
        description="Overlap between consecutive chunks in characters.",
    )

    rag_spaces_max_chunks_per_document: int = Field(
        default=RAG_SPACES_MAX_CHUNKS_PER_DOCUMENT_DEFAULT,
        ge=10,
        le=5000,
        description="Maximum number of chunks per document. Documents exceeding this limit are rejected.",
    )

    # ========================================================================
    # Retrieval Configuration
    # ========================================================================

    rag_spaces_retrieval_limit: int = Field(
        default=RAG_SPACES_RETRIEVAL_LIMIT_DEFAULT,
        ge=1,
        le=20,
        description="Maximum number of chunks injected per query.",
    )

    rag_spaces_retrieval_min_score: float = Field(
        default=RAG_SPACES_RETRIEVAL_MIN_SCORE_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum SEMANTIC cosine similarity for a chunk to be injected. "
            "Applies to the embedding score alone, before the BM25 bonus, so the "
            "value means the same thing whether or not the query shares "
            "vocabulary with the documents (ADR-242)."
        ),
    )

    rag_spaces_max_context_tokens: int = Field(
        default=RAG_SPACES_MAX_CONTEXT_TOKENS_DEFAULT,
        ge=500,
        le=8000,
        description="Hard cap on total RAG context tokens injected into the prompt.",
    )

    rag_spaces_bm25_bonus_weight: float = Field(
        default=RAG_SPACES_BM25_BONUS_WEIGHT_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Maximum bonus BM25 may add on top of the semantic score, to "
            "re-order the chunks that already passed the threshold. 0.0 "
            "disables lexical re-ordering entirely (ADR-242)."
        ),
    )

    # ========================================================================
    # MIME Types
    # ========================================================================

    rag_spaces_allowed_types: str = Field(
        default=RAG_SPACES_ALLOWED_TYPES_DEFAULT,
        description="Comma-separated list of allowed document MIME types.",
    )

    # ========================================================================
    # Embedding Configuration
    # ========================================================================

    rag_spaces_embedding_model: str = Field(
        default=RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
        description=(
            "Gemini embedding model for RAG document indexing and search. "
            "Default: gemini-embedding-001 (1536d)."
        ),
    )

    rag_spaces_embedding_dimensions: int = Field(
        default=RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
        ge=256,
        le=4096,
        description=(
            "Embedding vector dimensions for pgvector column. "
            "Must match the chosen embedding model output dimensions."
        ),
    )

    # ========================================================================
    # Drive Sync Configuration
    # ========================================================================

    rag_spaces_drive_sync_enabled: bool = Field(
        default=True,
        description="Enable Google Drive folder sync for RAG Spaces.",
    )

    rag_drive_max_sources_per_space: int = Field(
        default=RAG_DRIVE_MAX_SOURCES_PER_SPACE_DEFAULT,
        ge=1,
        le=20,
        description="Maximum number of Drive folder sources per space.",
    )

    # ------------------------------------------------------------------
    # Mail source (ADR-262): opt-in per Gmail label, OFF by default.
    # ------------------------------------------------------------------

    rag_spaces_mail_sync_enabled: bool = Field(
        default=False,
        description=(
            "Enable the Gmail label source for RAG Spaces: the threads carrying an "
            "opted-in label are indexed as documents, and follow the label (ADR-262). "
            "The INCREMENTAL path rides the push wake, so it also needs "
            "PUSH_WAKE_ENABLED; without it only the manual sync and the reaper "
            "feed a label source."
        ),
    )

    rag_mail_max_sources_per_space: int = Field(
        default=RAG_MAIL_MAX_SOURCES_PER_SPACE_DEFAULT,
        ge=1,
        le=20,
        description="Maximum number of Gmail label sources per space.",
    )

    rag_mail_max_threads_per_sync: int = Field(
        default=RAG_MAIL_MAX_THREADS_PER_SYNC,
        ge=1,
        le=2000,
        description="Threads read by one full label sync (the rest waits for the next run).",
    )

    rag_mail_max_thread_chars: int = Field(
        default=RAG_MAIL_MAX_THREAD_CHARS,
        ge=1000,
        le=500000,
        description="Size cap, in characters, of one rendered thread document.",
    )

    # ========================================================================
    # System Spaces (built-in knowledge bases)
    # ========================================================================

    rag_spaces_system_enabled: bool = Field(
        default=True,
        description="Enable system RAG spaces (built-in FAQ knowledge base).",
    )

    rag_spaces_system_knowledge_dir: str = Field(
        default=RAG_SPACES_SYSTEM_KNOWLEDGE_DIR_DEFAULT,
        description="Directory containing system knowledge Markdown files.",
    )
