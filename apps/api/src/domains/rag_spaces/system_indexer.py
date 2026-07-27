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

import asyncio
import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_SPACES_SYSTEM_EMBEDDING_USER_ID,
    RAG_SPACES_SYSTEM_FAQ_DESCRIPTION_DEFAULT,
    RAG_SPACES_SYSTEM_FAQ_NAME_DEFAULT,
    RAG_SPACES_SYSTEM_INDEX_EMBED_RETRY_BASE_SECONDS,
    RAG_SPACES_SYSTEM_INDEX_EMBED_RETRYABLE_STATUS,
)
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.embedding import get_rag_embeddings
from src.domains.rag_spaces.models import RAGChunk, RAGDocumentStatus, RAGSpace
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

if TYPE_CHECKING:
    from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings

logger = get_logger(__name__)


class _CorpusVerdict(NamedTuple):
    """Outcome of judging a stored corpus against the knowledge files.

    ``stored_chunks`` and ``stored_documents`` are None when the content hash
    already settled the question, so the counts were never queried — which is
    also how the caller tells "the files changed" apart from "the files did not
    change but the corpus is wrong".
    """

    is_current: bool
    stored_chunks: int | None
    stored_documents: int | None


def _retry_reason(exc: BaseException) -> str | None:
    """Why an embedding failure is worth another attempt, or None.

    Classified on the ``code`` attribute the Gemini SDK sets on its API errors
    (``google.genai.errors.APIError.code``), walking ``__cause__`` because
    langchain re-raises every failure wrapped in ``GoogleGenerativeAIError``.
    Structural on purpose: matching text inside an exception message is how a
    provider's wording change silently turns a retry into a hard failure.

    Transport-level timeouts and connection resets are also retryable — on the
    production host (a Raspberry Pi on WiFi) they are ordinary events.

    Args:
        exc: Exception raised by the embedding call.

    Returns:
        A short reason label for logging, or None when the failure is permanent.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, int) and code in RAG_SPACES_SYSTEM_INDEX_EMBED_RETRYABLE_STATUS:
            return f"http_{code}"
        if isinstance(current, TimeoutError | ConnectionError):
            return type(current).__name__
        current = current.__cause__
    return None


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

        Single-writer by construction. Every uvicorn worker runs this at boot;
        the space row is claimed with ``FOR UPDATE SKIP LOCKED``, so exactly one
        worker indexes and the others return "skipped" without waiting. Before
        that claim existed, the staleness check was a plain read and all four
        workers passed it — each embedding and inserting the full corpus, whose
        surviving rows accumulated (measured in production on 2026-07-27: 807
        chunks for 269 distinct contents, so retrieval returned each answer three
        times and the top-5 held two distinct answers instead of five).

        Embeddings are computed *before* the first destructive statement. A quota
        rejection therefore costs nothing, holds no lock on ``rag_chunks``, and
        cannot leave the space empty; the delete/insert swap that follows is a
        sub-second transaction.

        Returns:
            Dict with keys: status, chunks_created, content_hash, space_id, and
            "reason" when skipped. status is one of: "success", "skipped",
            "error".
        """
        # monotonic, not wall clock: this measures a duration that is observed
        # into a Prometheus histogram, and a clock step during boot (NTP settling
        # on the production host) would otherwise record a negative one.
        start_time = time.monotonic()
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
                space = await self._create_or_adopt_space(space_name)

            # 3. Parse before claiming. Local file I/O, and the hash above already
            #    read every byte — but it gives us the expected corpus size, which
            #    the staleness check needs.
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

            # 4. Staleness check on the row we just read. It is what makes a
            #    no-op boot report "up_to_date" on every worker instead of
            #    three of them reporting a contended claim over no work at all.
            if (await self._assess_corpus(space, current_hash, len(all_chunks))).is_current:
                return self._skipped(space_name, space.id, current_hash, "up_to_date")

            # 5. Claim the re-indexation. A worker that loses this does nothing.
            claimed = await self.service.space_repo.claim_system_space_for_reindex(space.id)
            if claimed is None:
                logger.info(
                    "system_indexer_claim_declined",
                    space_name=space_name,
                    space_id=str(space.id),
                )
                rag_system_indexation_total.labels(space_name=space_name, status="skipped").inc()
                return {
                    "status": "skipped",
                    "reason": "claimed_by_another_worker",
                    "chunks_created": 0,
                    "content_hash": current_hash,
                    "space_id": str(space.id),
                }

            # 6. Re-check under the claim: the winner of a previous round may have
            #    committed between our read at step 4 and our claim at step 5.
            verdict = await self._assess_corpus(claimed, current_hash, len(all_chunks))
            if verdict.is_current:
                return self._skipped(space_name, space.id, current_hash, "up_to_date")

            # Reported once, here, by the single worker that will act on it: an
            # unchanged hash over the wrong number of rows is a repair, not a
            # routine refresh, and a silent self-repair would hide a recurring
            # cause.
            if verdict.stored_chunks is not None:
                logger.warning(
                    "system_indexer_corpus_diverged",
                    space_name=space_name,
                    stored_chunks=verdict.stored_chunks,
                    expected_chunks=len(all_chunks),
                    stored_documents=verdict.stored_documents,
                    expected_documents=1,
                    remediation="re-indexing to restore exactly one chunk per parsed entry",
                )

            # 7. Embed BEFORE writing anything. This is what makes a quota
            #    rejection free: no rows deleted, no locks on rag_chunks held
            #    across a network call, previous corpus still serving.
            set_embedding_context(
                user_id=RAG_SPACES_SYSTEM_EMBEDDING_USER_ID,
                session_id="system_rag_index",
            )
            try:
                vectors = await self._embed_chunk_texts(self._chunk_texts(all_chunks))
            finally:
                clear_embedding_context()

            # 8. Destructive swap: delete old → create doc → store → update hash,
            #    in one short transaction. Rollback on failure preserves old data.
            try:
                await self.chunk_repo.delete_by_space(space.id)
                old_docs = await self.doc_repo.get_all_for_space(space.id)
                for doc in old_docs:
                    await self.doc_repo.delete(doc)
                await self.db.flush()

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

                chunks_created = await self._store_chunks(
                    all_chunks, vectors, space.id, system_doc.id
                )

                # Commits, which is also what releases the claim on the row.
                await self.service.update_system_space_hash(space.id, current_hash)

            except Exception:
                await self.db.rollback()
                raise

            duration = time.monotonic() - start_time
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

    async def _assess_corpus(
        self, space: RAGSpace, current_hash: str, expected_chunks: int
    ) -> _CorpusVerdict:
        """Judge whether the stored corpus is both up to date *and* intact.

        A matching hash is not sufficient, and assuming it was is what would have
        frozen the production damage in place: the space carried the correct hash
        over 807 chunks and 3 documents for 269 parsed entries — the residue of
        four workers indexing concurrently — so a hash-only check skipped every
        boot and the triplicated corpus would have served for good. Counting what
        is actually stored turns the next boot into the repair.

        It also covers an insert that died halfway: fewer chunks than entries is
        just as wrong as more, and equally invisible to a hash.

        Deliberately silent. This runs twice per indexation — once before the
        claim, once under it — so reporting from here would file the same
        divergence up to five times across four workers for a single event. The
        caller reports once, where the repair is decided.

        Args:
            space: Space to inspect.
            current_hash: Hash of the knowledge files on disk.
            expected_chunks: Number of entries parsed from those files.

        Returns:
            The verdict, with the observed counts when they were consulted.
        """
        if space.content_hash != current_hash:
            return _CorpusVerdict(is_current=False, stored_chunks=None, stored_documents=None)

        stored_chunks = await self.chunk_repo.count_for_space(space.id)
        stored_documents = await self.doc_repo.count_for_space(space.id)
        return _CorpusVerdict(
            is_current=stored_chunks == expected_chunks and stored_documents == 1,
            stored_chunks=stored_chunks,
            stored_documents=stored_documents,
        )

    async def _create_or_adopt_space(self, space_name: str) -> RAGSpace:
        """Create the system space, adopting a concurrent creator's row instead.

        On a brand new database every worker finds no space and tries to create
        one. The partial unique index ``uq_rag_spaces_system_name`` lets exactly
        one succeed and the service turns the others' ``IntegrityError`` into a
        409 — which, left alone, made three of four workers log a failure for a
        benign race on the very first boot. The winner's row is what they wanted
        anyway.

        The outcome is re-read rather than inferred from the error's status code:
        if the space still does not exist, the failure was real and must surface.

        Args:
            space_name: Name of the system space.

        Returns:
            The created space, or the one a concurrent worker just created.

        Raises:
            BaseAPIException: When creation failed for any reason other than the
                row already existing.
        """
        try:
            return await self.service.create_system_space(
                name=space_name,
                description=RAG_SPACES_SYSTEM_FAQ_DESCRIPTION_DEFAULT,
            )
        except BaseAPIException:
            existing = await self.service.space_repo.get_system_space_by_name(space_name)
            if existing is None:
                raise
            logger.info(
                "system_indexer_adopted_concurrent_space",
                space_name=space_name,
                space_id=str(existing.id),
            )
            return existing

    @staticmethod
    def _skipped(space_name: str, space_id: UUID, content_hash: str, reason: str) -> dict:
        """Build the "nothing to do" result and record it.

        Args:
            space_name: System space name.
            space_id: System space identifier.
            content_hash: Hash of the current knowledge files.
            reason: Machine-readable cause, surfaced to the caller.

        Returns:
            The skipped result dict.
        """
        logger.info(
            "system_indexer_up_to_date",
            space_name=space_name,
            content_hash=content_hash,
        )
        rag_system_indexation_total.labels(space_name=space_name, status="skipped").inc()
        return {
            "status": "skipped",
            "reason": reason,
            "chunks_created": 0,
            "content_hash": content_hash,
            "space_id": str(space_id),
        }

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

    @staticmethod
    def _chunk_texts(parsed_chunks: list[dict]) -> list[str]:
        """Render the text that gets embedded for each parsed chunk.

        Args:
            parsed_chunks: Chunks from :meth:`_parse_all_markdown`.

        Returns:
            One ``"Q: ...\\nA: ..."`` string per chunk, in the same order.
        """
        return [f"Q: {c['question']}\nA: {c['answer']}" for c in parsed_chunks]

    async def _embed_chunk_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed every chunk text, batching and retrying transient failures.

        The retry budget is a single deadline shared by all batches, so the
        worst case is bounded by one setting instead of multiplying attempts by
        batches. It matters here because the exclusive claim on the space row is
        held for the whole call.

        Args:
            texts: Texts to embed, in chunk order.

        Returns:
            One vector per input text, in the same order.

        Raises:
            Exception: The last embedding failure, once the attempts or the time
                budget are exhausted, or immediately for a permanent error.
        """
        embeddings = get_rag_embeddings()
        deadline = time.monotonic() + settings.rag_spaces_system_index_embed_retry_budget_seconds

        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + EMBEDDING_BATCH_SIZE]
            all_embeddings.extend(await self._embed_batch(embeddings, batch, deadline))
        return all_embeddings

    @staticmethod
    async def _embed_batch(
        embeddings: GeminiRetrievalEmbeddings,
        batch: list[str],
        deadline: float,
    ) -> list[list[float]]:
        """Embed one batch, retrying only what is worth retrying.

        The Gemini SDK is configured with no retry options, which selects its
        "never retry" strategy — so without this loop a single 429 aborts the
        whole indexation. The original exception is re-raised rather than wrapped:
        its status code is the diagnosis.

        Args:
            embeddings: Embedding client.
            batch: Texts of this batch.
            deadline: ``time.monotonic()`` value past which no further attempt is
                made.

        Returns:
            One vector per text in ``batch``.

        Raises:
            Exception: The failure of the final attempt.
        """
        max_attempts = settings.rag_spaces_system_index_embed_max_attempts
        attempt = 0
        while True:
            attempt += 1
            try:
                return await embeddings.aembed_documents(batch)
            except Exception as exc:
                reason = _retry_reason(exc)
                remaining = deadline - time.monotonic()
                if attempt >= max_attempts or reason is None or remaining <= 0:
                    raise
                delay = min(
                    RAG_SPACES_SYSTEM_INDEX_EMBED_RETRY_BASE_SECONDS * 2 ** (attempt - 1),
                    remaining,
                )
                logger.warning(
                    "system_indexer_embed_retry",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    reason=reason,
                    batch_size=len(batch),
                    delay_seconds=round(delay, 2),
                    budget_remaining_seconds=round(remaining, 2),
                )
                await asyncio.sleep(delay)

    async def _store_chunks(
        self,
        parsed_chunks: list[dict],
        all_embeddings: list[list[float]],
        space_id: UUID,
        document_id: UUID,
    ) -> int:
        """Persist already-embedded chunks.

        Args:
            parsed_chunks: Chunks from :meth:`_parse_all_markdown`.
            all_embeddings: Vectors from :meth:`_embed_chunk_texts`, same order.
            space_id: Owning space.
            document_id: Owning system document.

        Returns:
            Number of chunks written.
        """
        model_name = settings.rag_spaces_embedding_model

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
