"""
RAG Spaces SQLAlchemy models.

Defines the data model for user knowledge spaces, uploaded documents,
and vector-indexed chunks for retrieval-augmented generation.

Tables:
    - rag_spaces: User-owned knowledge spaces with name/description
    - rag_documents: Uploaded documents within spaces (lifecycle tracked)
    - rag_chunks: Vector-indexed text chunks for similarity search (pgvector)

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.infrastructure.database.models import BaseModel

# --- Domain constants (str, not Enum — avoids _CHECKPOINT_ALLOWED_MODULES registration) ---


class RAGDocumentStatus:
    """Lifecycle status values for RAG documents."""

    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    REINDEXING = "reindexing"


class RAGSpace(BaseModel):
    """
    User-owned knowledge space for RAG document management.

    A space groups related documents under a name and description.
    Users can activate/deactivate spaces to control which documents
    enrich the AI assistant's responses.

    Security:
        - All queries filter by user_id for strict isolation
        - Space names are unique per user (UniqueConstraint)
    """

    __tablename__ = "rag_spaces"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Relationships
    documents: Mapped[list["RAGDocument"]] = relationship(
        "RAGDocument",
        back_populates="space",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_rag_spaces_user_id_is_active", "user_id", "is_active"),
        Index(
            "uq_rag_spaces_user_id_name",
            "user_id",
            "name",
            unique=True,
        ),
    )


class RAGDocument(BaseModel):
    """
    Uploaded document within a RAG space.

    Lifecycle:
        processing → ready (after chunking + embedding)
        processing → error (extraction/embedding failure)
        ready → reindexing (admin changes embedding model)
        reindexing → ready (re-embedding complete)

    Security:
        - Files stored as UUID-based filenames (anti-traversal)
        - Physical directory segmentation by user_id/space_id
        - user_id denormalized for direct ownership checks
    """

    __tablename__ = "rag_documents"

    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_spaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="UUID-based stored filename (anti-path-traversal)",
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename for display only",
    )

    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RAGDocumentStatus.PROCESSING,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
        comment="Embedding model used for indexing (mismatch detection)",
    )

    embedding_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total tokens consumed for embedding this document",
    )

    embedding_cost_eur: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Total embedding cost in EUR for this document",
    )

    # Relationships
    space: Mapped["RAGSpace"] = relationship(
        "RAGSpace",
        back_populates="documents",
    )

    chunks: Mapped[list["RAGChunk"]] = relationship(
        "RAGChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_rag_documents_space_id_status", "space_id", "status"),
        Index("ix_rag_documents_user_id", "user_id"),
    )


class RAGChunk(BaseModel):
    """
    Vector-indexed text chunk from a RAG document.

    Each chunk stores the raw text content alongside its embedding vector
    for cosine similarity search via pgvector. Denormalized fields (space_id,
    user_id) enable efficient multi-space queries without JOINs.

    The embedding column uses pgvector's Vector type with configurable
    dimensions (default 1536 for text-embedding-3-small).
    """

    __tablename__ = "rag_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_spaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="Denormalized for query performance (avoid JOIN)",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Denormalized for user isolation (avoid JOIN)",
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(
        Vector(
            RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
        ),  # Reindex ALTERs column if dimensions change
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Embedding model that produced this vector",
    )

    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
        comment="Extra metadata: original_filename, space_name, page_number, etc.",
    )

    # Relationships
    document: Mapped["RAGDocument"] = relationship(
        "RAGDocument",
        back_populates="chunks",
    )

    __table_args__ = (
        Index("ix_rag_chunks_document_id", "document_id"),
        Index("ix_rag_chunks_space_id", "space_id"),
        Index("ix_rag_chunks_user_id_space_id", "user_id", "space_id"),
    )
