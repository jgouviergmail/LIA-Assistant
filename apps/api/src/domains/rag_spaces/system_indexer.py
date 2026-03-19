"""
System RAG Space indexer.

Indexes system knowledge Markdown files (docs/knowledge/*.md) into
system RAG spaces for app self-knowledge (FAQ, help content).

Pipeline: parse markdown → embed → store chunks.
Does NOT reuse process_document() which is designed for user uploads.

Phase: evolution — System RAG Spaces (App Self-Knowledge)
Created: 2026-03-19
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_SPACES_SYSTEM_EMBEDDING_USER_ID,
    RAG_SPACES_SYSTEM_FAQ_DESCRIPTION_DEFAULT,
    RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT,
)
from src.domains.rag_spaces.embedding import get_rag_embeddings
from src.domains.rag_spaces.models import RAGChunk, RAGDocumentStatus
from src.domains.rag_spaces.processing import EMBEDDING_BATCH_SIZE
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_system_indexation_duration_seconds,
    rag_system_indexation_total,
)

logger = get_logger(__name__)


class SystemSpaceIndexer:
    """Indexes system knowledge Markdown files into system RAG spaces.

    Uses RAGSpaceService for space lifecycle (create, update hash) and
    repositories directly for bulk chunk operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.service = RAGSpaceService(db)
        # Direct repo access for bulk operations not covered by service
        self.doc_repo = RAGDocumentRepository(db)
        self.chunk_repo = RAGChunkRepository(db)

    async def index_faq_space(self) -> dict:
        """Parse docs/knowledge/*.md, embed, and store chunks.

        The entire re-indexation (delete old + insert new) runs within a
        single transaction.  If embedding or storage fails, the transaction
        is rolled back so the previous chunks remain intact.

        Returns:
            Dict with keys: status, chunks_created, content_hash, space_id.
            status is one of: "success", "skipped", "error".
        """
        start_time = time.time()
        space_name = RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT

        try:
            knowledge_dir = self._resolve_knowledge_dir()
            if not knowledge_dir.is_dir():
                logger.warning(
                    "system_indexer_knowledge_dir_missing",
                    path=str(knowledge_dir),
                )
                rag_system_indexation_total.labels(space_name=space_name, status="error").inc()
                return {
                    "status": "error",
                    "error": f"Knowledge directory not found: {knowledge_dir}",
                    "chunks_created": 0,
                    "content_hash": "",
                }

            # 1. Compute content hash
            current_hash = self.compute_content_hash(knowledge_dir)

            # 2. Get or create system space
            space = await self.service.space_repo.get_system_space_by_name(space_name)
            if not space:
                space = await self.service.create_system_space(
                    name=space_name,
                    description=RAG_SPACES_SYSTEM_FAQ_DESCRIPTION_DEFAULT,
                )

            # 3. Check staleness — skip if up to date
            if space.content_hash == current_hash:
                logger.info(
                    "system_indexer_up_to_date",
                    space_name=space_name,
                    content_hash=current_hash,
                )
                rag_system_indexation_total.labels(space_name=space_name, status="skipped").inc()
                return {
                    "status": "skipped",
                    "chunks_created": 0,
                    "content_hash": current_hash,
                    "space_id": str(space.id),
                }

            # 4. Parse all markdown files
            all_chunks = self._parse_all_markdown(knowledge_dir)
            if not all_chunks:
                logger.warning("system_indexer_no_chunks_parsed", space_name=space_name)
                rag_system_indexation_total.labels(space_name=space_name, status="error").inc()
                return {
                    "status": "error",
                    "error": "No chunks parsed from knowledge files",
                    "chunks_created": 0,
                    "content_hash": current_hash,
                }

            # 5-8. Atomic re-indexation: delete old → create doc → embed → store → update hash.
            # All within a single transaction — rollback on any failure preserves old data.
            try:
                # 5. Delete old documents and chunks
                await self.chunk_repo.delete_by_space(space.id)
                old_docs = await self.doc_repo.get_all_for_space(space.id)
                for doc in old_docs:
                    await self.doc_repo.delete(doc)
                await self.db.flush()

                # 6. Create a single system document record
                system_doc = await self.doc_repo.create(
                    {
                        "space_id": space.id,
                        "user_id": None,
                        "filename": f"{space_name}.md",
                        "original_filename": f"{space_name}.md",
                        "file_size": 0,
                        "content_type": "text/markdown",
                        "status": RAGDocumentStatus.READY,
                        "chunk_count": len(all_chunks),
                        "embedding_model": settings.rag_spaces_embedding_model,
                    }
                )
                await self.db.flush()

                # 7. Embed chunks in batches
                set_embedding_context(
                    user_id=RAG_SPACES_SYSTEM_EMBEDDING_USER_ID,
                    session_id="system_rag_index",
                )
                try:
                    chunks_created = await self._embed_and_store_chunks(
                        all_chunks, space.id, system_doc.id
                    )
                finally:
                    clear_embedding_context()

                # 8. Update content hash and commit
                await self.service.update_system_space_hash(space.id, current_hash)

            except Exception:
                await self.db.rollback()
                raise

            duration = time.time() - start_time
            rag_system_indexation_total.labels(space_name=space_name, status="success").inc()
            rag_system_indexation_duration_seconds.observe(duration)

            logger.info(
                "system_indexer_complete",
                space_name=space_name,
                chunks_created=chunks_created,
                content_hash=current_hash,
                duration_seconds=round(duration, 2),
            )

            return {
                "status": "success",
                "chunks_created": chunks_created,
                "content_hash": current_hash,
                "space_id": str(space.id),
            }

        except Exception as e:
            rag_system_indexation_total.labels(space_name=space_name, status="error").inc()
            logger.error(
                "system_indexer_failed",
                space_name=space_name,
                error=str(e),
            )
            raise

    def compute_content_hash(self, knowledge_dir: Path) -> str:
        """SHA-256 hash of sorted concatenated markdown files."""
        md_files = sorted(knowledge_dir.glob("*.md"))
        hasher = hashlib.sha256()
        for f in md_files:
            hasher.update(f.read_bytes())
        return hasher.hexdigest()

    def parse_faq_markdown(self, file_path: Path) -> list[dict]:
        """Parse a single markdown file into Q/A chunks.

        Each ## heading is treated as a question, with the following text
        as the answer. Returns a list of dicts with keys:
        question, answer, section, metadata.
        """
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Extract section title from first # heading
        section_title = file_path.stem
        for line in lines:
            if line.startswith("# ") and not line.startswith("## "):
                section_title = line[2:].strip()
                break

        chunks: list[dict] = []
        current_question: str | None = None
        current_answer_lines: list[str] = []

        for line in lines:
            if line.startswith("## "):
                # Save previous Q/A if any
                self._flush_chunk(
                    chunks,
                    current_question,
                    current_answer_lines,
                    section_title,
                    file_path.name,
                )
                current_question = line[3:].strip()
                current_answer_lines = []
            elif current_question is not None:
                current_answer_lines.append(line)

        # Don't forget the last Q/A
        self._flush_chunk(
            chunks,
            current_question,
            current_answer_lines,
            section_title,
            file_path.name,
        )

        return chunks

    async def check_staleness(self, space_name: str) -> dict:
        """Compare stored hash vs current file hash.

        Returns:
            Dict with keys: is_stale, current_hash, stored_hash.
        """
        knowledge_dir = self._resolve_knowledge_dir()
        current_hash = self.compute_content_hash(knowledge_dir) if knowledge_dir.is_dir() else ""

        space = await self.service.space_repo.get_system_space_by_name(space_name)
        stored_hash = space.content_hash if space else None

        return {
            "is_stale": current_hash != stored_hash,
            "current_hash": current_hash,
            "stored_hash": stored_hash,
        }

    # ========================================================================
    # Private helpers
    # ========================================================================

    @staticmethod
    def _resolve_knowledge_dir() -> Path:
        """Resolve the knowledge directory path.

        Tries the configured path first (absolute or relative to CWD).
        Falls back to project-root-relative resolution for dev environments
        where CWD is apps/api/ but docs/ is at the monorepo root.
        """
        configured = Path(settings.rag_spaces_system_knowledge_dir)
        if configured.is_dir():
            return configured

        # Fallback: resolve relative to project root
        # __file__ = apps/api/src/domains/rag_spaces/system_indexer.py → 6 parents = project root
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        fallback = project_root / settings.rag_spaces_system_knowledge_dir
        if fallback.is_dir():
            return fallback

        # Return configured path (will trigger "not found" error in caller)
        return configured

    @staticmethod
    def _flush_chunk(
        chunks: list[dict],
        question: str | None,
        answer_lines: list[str],
        section_title: str,
        filename: str,
    ) -> None:
        """Append a parsed Q/A chunk if both question and answer are present."""
        if not question or not answer_lines:
            return
        answer = "\n".join(answer_lines).strip()
        if not answer:
            return
        chunks.append(
            {
                "question": question,
                "answer": answer,
                "section": section_title,
                "metadata": {
                    "section": section_title,
                    "source": "faq",
                    "question": question,
                    "file": filename,
                },
            }
        )

    def _parse_all_markdown(self, knowledge_dir: Path) -> list[dict]:
        """Parse all markdown files in the knowledge directory."""
        all_chunks: list[dict] = []
        for md_file in sorted(knowledge_dir.glob("*.md")):
            chunks = self.parse_faq_markdown(md_file)
            all_chunks.extend(chunks)
        return all_chunks

    async def _embed_and_store_chunks(
        self,
        parsed_chunks: list[dict],
        space_id: UUID,
        document_id: UUID,
    ) -> int:
        """Embed parsed chunks and store them in the database."""
        embeddings = get_rag_embeddings()
        model_name = settings.rag_spaces_embedding_model

        # Build chunk texts for embedding: "Q: {question}\nA: {answer}"
        texts = [f"Q: {c['question']}\nA: {c['answer']}" for c in parsed_chunks]

        # Embed in batches (reuses EMBEDDING_BATCH_SIZE from processing module)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await embeddings.aembed_documents(batch)
            all_embeddings.extend(batch_embeddings)

        # Create RAGChunk objects
        chunk_objects: list[RAGChunk] = []
        for idx, (parsed, embedding) in enumerate(zip(parsed_chunks, all_embeddings, strict=True)):
            chunk_objects.append(
                RAGChunk(
                    id=uuid4(),
                    document_id=document_id,
                    space_id=space_id,
                    user_id=None,
                    chunk_index=idx,
                    content=f"Q: {parsed['question']}\nA: {parsed['answer']}",
                    embedding=embedding,
                    embedding_model=model_name,
                    metadata_=parsed["metadata"],
                )
            )

        count = await self.chunk_repo.bulk_create_chunks(chunk_objects)
        await self.db.flush()

        return count
