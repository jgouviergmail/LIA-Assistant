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

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    RAG_DRIVE_MAX_SOURCES_PER_SPACE_DEFAULT,
    RAG_SPACES_ALLOWED_TYPES_DEFAULT,
    RAG_SPACES_CHUNK_OVERLAP_DEFAULT,
    RAG_SPACES_CHUNK_SIZE_DEFAULT,
    RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
    RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
    RAG_SPACES_HYBRID_ALPHA_DEFAULT,
    RAG_SPACES_MAX_CHUNKS_PER_DOCUMENT_DEFAULT,
    RAG_SPACES_MAX_CONTEXT_TOKENS_DEFAULT,
    RAG_SPACES_MAX_DOCS_PER_SPACE_DEFAULT,
    RAG_SPACES_MAX_FILE_SIZE_MB_DEFAULT,
    RAG_SPACES_MAX_SPACES_PER_USER_DEFAULT,
    RAG_SPACES_RETRIEVAL_LIMIT_DEFAULT,
    RAG_SPACES_RETRIEVAL_MIN_SCORE_DEFAULT,
    RAG_SPACES_STORAGE_PATH_DEFAULT,
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
        description="Minimum hybrid score threshold to include a chunk.",
    )

    rag_spaces_max_context_tokens: int = Field(
        default=RAG_SPACES_MAX_CONTEXT_TOKENS_DEFAULT,
        ge=500,
        le=8000,
        description="Hard cap on total RAG context tokens injected into the prompt.",
    )

    rag_spaces_hybrid_alpha: float = Field(
        default=RAG_SPACES_HYBRID_ALPHA_DEFAULT,
        ge=0.0,
        le=1.0,
        description=("Weight for hybrid search fusion. " "1.0 = pure semantic, 0.0 = pure BM25."),
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
