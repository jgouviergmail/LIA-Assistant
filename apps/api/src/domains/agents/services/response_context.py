"""Response-context fetching shared by the response and initiative nodes.

The response node injects user context (long-term memory profile, user RAG,
system RAG, journal, portrait, psyche) into its synthesis prompt. These are
independent I/O-bound lookups that depend only on the user message — never on
tool execution results — so they can be computed while the initiative node's
LLM evaluation runs (typically several seconds).

Flow:
    - ``initiative_node`` calls :func:`start_response_context_prefetch` early,
      launching :func:`fetch_response_context` as a background task registered
      in a bounded per-process registry keyed by ``run_id``.
    - ``response_node`` calls :func:`pop_response_context`; on a hit the
      injections are already resolved (latency overlap), on a miss it calls
      :func:`fetch_response_context` inline — the exact same code path, so
      turns that never traverse the initiative node behave as before.

The registry is process-local, which is safe because a single graph run always
executes in one process (no interrupt exists between initiative and response).

Kill-switch: ``RESPONSE_CONTEXT_PREFETCH_ENABLED`` (see AgentsSettings).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.context.runtime_context import (
    runtime_context_if_running,
    runtime_user_id_str,
)
from src.domains.agents.middleware.memory_injection import build_psychological_profile
from src.domains.shared.extraction_targets import is_synthetic_message

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)


@dataclass
class ResponseContextBundle:
    """Resolved user-context injections for the response prompt.

    Field names mirror the historical local variables of ``response_node`` so
    the unpacking site reads one-to-one against the previous inline version.
    """

    psychological_profile: str | None = None
    memory_injection_debug: dict[str, Any] | None = None
    rag_context: str | None = None
    rag_injection_debug: dict[str, Any] | None = None
    app_knowledge_context: str = ""
    journal_context: str = ""
    journal_injection_debug: dict[str, Any] | None = None
    journal_injected_ids: list[str] = field(default_factory=list)
    user_model_block: str = ""
    psyche_context: str = ""
    #: Local CRM facts about a connected user named in the turn (lot 6).
    peer_context: str = ""
    user_msg_is_trivial: bool = True
    user_message_embedding: list[float] | None = None
    prefetched: bool = False
    # Latency lot R2 (2026-07): True when the bundle was fetched before the
    # query analyzer ran (router-entry prefetch) — the QI-dependent system-RAG
    # injection was skipped and the response node must resolve it inline.
    system_rag_deferred: bool = False


def extract_last_user_message(state: MessagesState) -> str:
    """Extract the last human message text from state (response-node convention).

    Skips messages the system fabricated. On a tool-level HITL refusal the
    resumption layer injects a ``HumanMessage`` carrying localized instructions
    for the response LLM; treating it as the user's message made this function
    the origin of three wrong decisions at once — the triviality verdict, the
    embedding paid for and cached, and the memory/journal context injected for
    the turn. The extractors already target the genuine message, so leaving this
    one unfiltered also desynchronized the embedding from what it embeds.
    """
    # Literal key: MessagesState is a TypedDict — a variable key degrades
    # mypy's inference of the value type to ``object``.
    messages: list[Any] = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and msg.content and not is_synthetic_message(msg):
            # `.text` is a `TextAccessor`, a `str` SUBCLASS kept by langchain-core
            # for the deprecated `.text()` form. Handed raw to google-genai it
            # became an EMPTY request (2026-09-05: `500 INTERNAL` on every RAG
            # query). The embedding funnel normalises too; the chokepoint that
            # names "the user's message" hands out the exact type its five
            # readers expect.
            return str(msg.text)
    return ""


async def fetch_app_knowledge_context(
    state: MessagesState | dict[str, Any],
    last_user_message: str,
    run_id: str,
) -> str:
    """Resolve the system-RAG (App FAQ) context for app-help queries.

    Reads ``is_app_help_query`` from the state's query_intelligence: when
    True, always returns at least the ``APP_HELP_QUERY`` marker (so
    ``get_response_prompt`` loads the app identity prompt), enriched with
    system-RAG chunks when ``rag_spaces_system_enabled`` finds matches.

    Standalone (latency lot R2, 2026-07): the router-entry prefetch cannot
    evaluate this injection (query_intelligence does not exist yet at router
    entry) — the response node calls this directly when the bundle carries
    ``system_rag_deferred=True``.

    Args:
        state: Graph state (query_intelligence source, dict or object form).
        last_user_message: Last human message text (system-RAG search query).
        run_id: Current run identifier (logging correlation).

    Returns:
        The system-RAG prompt context, ``"APP_HELP_QUERY"`` marker, or ``""``.
    """
    is_app_help = get_qi_attr(cast("dict[str, Any]", state), "is_app_help_query", default=False)
    if not is_app_help:
        return ""
    # Mark as app help so get_response_prompt() loads app_identity_prompt
    context = "APP_HELP_QUERY"

    # Optionally enrich with system RAG chunks (FAQ search results)
    if getattr(settings, "rag_spaces_system_enabled", False) and last_user_message:
        try:
            from src.domains.rag_spaces.retrieval import (
                retrieve_rag_context as _sys_retrieve,
            )
            from src.infrastructure.database.session import (
                get_db_context as _sys_get_db,
            )

            async with _sys_get_db() as sys_db:
                sys_result = await _sys_retrieve(
                    user_id=None,
                    query=last_user_message,
                    db=sys_db,
                    system_only=True,
                )
            if sys_result and sys_result.chunks:
                context = sys_result.to_prompt_context()
                logger.info(
                    "system_rag_injection_completed",
                    run_id=run_id,
                    chunks_injected=len(sys_result.chunks),
                )
        except Exception as e:
            logger.warning(
                "system_rag_injection_failed",
                run_id=run_id,
                error=str(e),
            )
    return context


async def fetch_response_context(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
    *,
    include_system_rag: bool = True,
) -> ResponseContextBundle:
    """Fetch all user-context injections for the response prompt.

    Computes the user-message embedding once, then resolves the six
    injections concurrently (briefing pattern: each acquires its OWN
    ``AsyncSession``). Every injection keeps its historical try/except
    semantics — a failure degrades to its neutral default, never raises.

    Args:
        state: Current graph state (messages, query_intelligence, timezone).
        config: RunnableConfig carrying user/thread ids and feature flags.
        run_id: Current run identifier (logging correlation).
        include_system_rag: False when called before the query analyzer ran
            (router-entry prefetch, latency lot R2): the QI-dependent
            system-RAG injection is skipped and the bundle is flagged
            ``system_rag_deferred`` so the response node resolves it inline
            via :func:`fetch_app_knowledge_context`.

    Returns:
        Fully resolved :class:`ResponseContextBundle` (``prefetched=False``;
        the prefetch registry flips it on a hit).
    """
    last_user_message = extract_last_user_message(state)
    user_timezone = state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)

    # =====================================================================
    # CENTRALIZED USER MESSAGE EMBEDDING (shared across injection + extraction)
    # =====================================================================
    # Compute embedding ONCE, reuse for memory injection, journal injection,
    # memory extraction dedup, and journal extraction pre-filter.
    # Skip entirely on trivial messages (saves embedding API call + extraction LLM calls).
    from src.infrastructure.llm.user_message_embedding import (
        get_or_compute_embedding,
        is_trivial_message,
    )

    _user_id_for_embed = runtime_user_id_str(None)
    _thread_id_for_embed = config.get("configurable", {}).get("thread_id")
    user_msg_is_trivial = is_trivial_message(last_user_message) if last_user_message else True
    user_message_embedding: list[float] | None = None

    if not user_msg_is_trivial and last_user_message and _user_id_for_embed:
        from src.infrastructure.llm.embedding_context import (
            clear_embedding_context as _clear_embed_ctx,  # noqa: I001
        )
        from src.infrastructure.llm.embedding_context import (
            set_embedding_context as _set_embed_ctx,
        )

        _set_embed_ctx(
            user_id=_user_id_for_embed,
            session_id=_thread_id_for_embed or "unknown",
            run_id=run_id,
        )
        try:
            user_message_embedding = await get_or_compute_embedding(
                message=last_user_message,
                user_id=_user_id_for_embed,
                session_id=_thread_id_for_embed,
                is_conversational=True,
            )
        except Exception as _embed_err:
            logger.warning(
                "user_message_embedding_failed",
                run_id=run_id,
                error=str(_embed_err),
            )
        finally:
            _clear_embed_ctx()

    # =====================================================================
    # PARALLEL CONTEXT INJECTIONS (TTFT optimization)
    # =====================================================================
    # Memory, user RAG, system RAG, journal, portrait and psyche are
    # independent I/O-bound lookups — only memory and journal consume the
    # user-message embedding computed above. Briefing pattern (see CLAUDE.md):
    # each injection acquires its OWN AsyncSession — a session is never shared
    # between concurrent coroutines. Each closure keeps its original
    # try/except semantics: an injection failure degrades to its neutral
    # default, and cancellation (CancelledError) propagates through gather
    # untouched.
    _ctx = runtime_context_if_running()
    user_memory_enabled = _ctx.memory_enabled if _ctx is not None else True
    user_journals_enabled = _ctx.journals_enabled if _ctx is not None else False
    user_psyche_enabled = _ctx.psyche_enabled if _ctx is not None else False

    async def _inject_memory() -> tuple[str | None, dict[str, Any] | None]:
        """Long-term memory injection: psychological profile from semantic memory."""
        if not user_memory_enabled:
            return None, None
        user_id = runtime_user_id_str(None)
        if not (user_id and last_user_message):
            return None, None
        try:
            thread_id_for_memory = config.get("configurable", {}).get("thread_id")
            (
                profile_result,
                emotional_state,
                memory_debug_details,
            ) = await build_psychological_profile(
                user_id=user_id,
                query=last_user_message,
                query_embedding=user_message_embedding,
                limit=settings.memory_max_results,
                min_score=settings.memory_min_search_score,
                session_id=thread_id_for_memory,
                conversation_id=thread_id_for_memory,
                include_debug=True,
            )
            injection_debug = {
                "memory_count": len(memory_debug_details) if memory_debug_details else 0,
                "emotional_state": emotional_state.value,
                "settings": {
                    "max_results": settings.memory_max_results,
                    "min_score": settings.memory_min_search_score,
                },
                "memories": memory_debug_details or [],
            }
            logger.info(
                "memory_injection_completed",
                run_id=run_id,
                user_id=user_id,
                has_profile=profile_result is not None,
                emotional_state=emotional_state.value if profile_result else None,
                used_embedding=user_message_embedding is not None,
            )
            return profile_result, injection_debug
        except (ValueError, KeyError, RuntimeError, AttributeError, OSError) as e:
            logger.warning(
                "memory_injection_failed",
                run_id=run_id,
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, None

    async def _inject_user_rag() -> tuple[str | None, dict[str, Any] | None]:
        """RAG Spaces context injection (user documents, own DB session)."""
        if not getattr(settings, "rag_spaces_enabled", False):
            return None, None
        try:
            from uuid import UUID as _UUID

            from src.domains.rag_spaces.retrieval import retrieve_rag_context
            from src.infrastructure.database.session import get_db_context

            user_id_for_rag = runtime_user_id_str(None)
            thread_id_for_rag = config.get("configurable", {}).get("thread_id")
            if not (user_id_for_rag and last_user_message):
                return None, None
            async with get_db_context() as rag_db:
                rag_result = await retrieve_rag_context(
                    user_id=_UUID(user_id_for_rag),
                    query=last_user_message,
                    db=rag_db,
                    session_id=thread_id_for_rag,
                    conversation_id=thread_id_for_rag,
                    run_id=run_id,
                )
            if rag_result and rag_result.chunks:
                injection_debug = {
                    "spaces_searched": rag_result.spaces_searched,
                    "chunks_found": rag_result.total_results,
                    "chunks_injected": len(rag_result.chunks),
                    # Publish the bounds that produced this result: a threshold
                    # the retrieval enforced is meaningless to a reader who
                    # cannot see it (same doctrine as the memory-injection
                    # payload, and as ADR-184 for the planner catalogue).
                    "settings": {
                        "min_score": settings.rag_spaces_retrieval_min_score,
                        "max_results": settings.rag_spaces_retrieval_limit,
                    },
                    "chunks": [
                        {
                            "space": c.space_name,
                            "file": c.original_filename,
                            "score": c.score,
                        }
                        for c in rag_result.chunks
                    ],
                }
                logger.info(
                    "rag_injection_completed",
                    run_id=run_id,
                    user_id=user_id_for_rag,
                    chunks_injected=len(rag_result.chunks),
                    spaces_searched=rag_result.spaces_searched,
                )
                return rag_result.to_prompt_context(), injection_debug
            return None, None
        except Exception as e:
            logger.warning(
                "rag_injection_failed",
                run_id=run_id,
                error=str(e),
            )
            return None, None

    async def _inject_system_rag() -> str:
        """System RAG context (App FAQ) — lazy loading based on is_app_help_query.

        When is_app_help_query=True, we ALWAYS inject the app identity prompt
        (describing LIA's capabilities). System RAG chunks are added on top
        if available. Skipped (deferred to the response node) when the bundle
        is prefetched before the query analyzer ran — see
        :func:`fetch_app_knowledge_context`.
        """
        if not include_system_rag:
            return ""
        return await fetch_app_knowledge_context(state, last_user_message, run_id)

    async def _inject_journal() -> tuple[str, dict[str, Any] | None, list[str]]:
        """Journal context injection (semantic relevance search, own DB session)."""
        if not (settings.journals_enabled and user_journals_enabled):
            return "", None, []
        try:
            user_id_for_journal = runtime_user_id_str(None)
            if not (user_id_for_journal and last_user_message):
                return "", None, []
            from src.domains.journals.context_builder import (
                build_journal_context,
            )
            from src.infrastructure.database.session import get_db_context

            thread_id_for_journal = config.get("configurable", {}).get("thread_id")
            async with get_db_context() as journal_db:
                (
                    journal_context_result,
                    journal_debug,
                    injected_ids,
                ) = await build_journal_context(
                    user_id=user_id_for_journal,
                    query=last_user_message,
                    db=journal_db,
                    query_embedding=user_message_embedding,
                    include_debug=True,
                    run_id=run_id,
                    session_id=thread_id_for_journal,
                )
                return journal_context_result or "", journal_debug, injected_ids
        except Exception as e:
            logger.warning(
                "journal_context_injection_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return "", None, []

    async def _inject_portrait() -> str:
        """User-model portrait — ambient diffusion of the compiled portrait
        (ADR-079, commit 3). Always injected when journals are enabled.
        Format depends on the turn: trivial → brief (~60 tokens),
        otherwise → full (~200 tokens)."""
        if not (settings.journals_enabled and user_journals_enabled):
            return ""
        try:
            _uid_for_portrait = runtime_user_id_str(None)
            if not _uid_for_portrait:
                return ""
            from src.domains.journals.portrait_builder import (
                build_journal_user_model_block,
            )

            portrait_format: Literal["brief", "full"] = "brief" if user_msg_is_trivial else "full"
            return await build_journal_user_model_block(
                user_id=_uid_for_portrait,
                format=portrait_format,
                flow="response",
            )
        except Exception as e:
            logger.warning(
                "journal_user_model_block_failed_response",
                run_id=run_id,
                error=str(e),
            )
            return ""

    async def _inject_psyche() -> str:
        """Psyche Engine: pre-response expression profile (Iteration 1).

        Loads psyche state, applies temporal decay + circadian modulation,
        compiles ExpressionProfile, and returns compact XML for prompt
        injection. Own DB session (it commits the decayed state).
        """
        if not (settings.psyche_enabled and user_psyche_enabled and not user_msg_is_trivial):
            return ""
        try:
            from src.domains.psyche.service import PsycheService
            from src.infrastructure.database.session import get_db_context

            _user_id_for_psyche = runtime_user_id_str(None)
            if not _user_id_for_psyche:
                return ""
            async with get_db_context() as _psyche_db:
                _psyche_svc = PsycheService(_psyche_db)
                context, _psyche_summary = await _psyche_svc.process_pre_response(
                    user_id=UUID(_user_id_for_psyche),
                    user_timezone=user_timezone,
                )
                await _psyche_db.commit()
                return context
        except Exception as e:
            logger.warning(
                "psyche_pre_response_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return ""

    async def _inject_peer_context() -> str:
        """Local facts about a CONNECTED user named in this turn (lot 6).

        Database-only, so it costs no provider quota; the user's 360° scope
        decides which blocks may be read. Own failure boundary, like every
        other injection here.
        """
        user_id_for_peer = runtime_user_id_str(None)
        if not (user_id_for_peer and last_user_message):
            return ""

        # Inside the try, `UUID(...)` included — same shape as `_inject_psyche`
        # above. The conversion used to sit OUTSIDE it, so a malformed id raised
        # through `asyncio.gather` and cost the user the whole answer for the
        # sake of an enrichment.
        try:
            from src.domains.agents.middleware.peer_context_injection import build_peer_context

            # The name may be nowhere in what the user typed ("ma femme"): the
            # English pivot and the resolved references carry it instead.
            intelligence = state.get("query_intelligence") or {}
            texts: list[str | None] = [last_user_message]
            if isinstance(intelligence, dict):
                texts.append(intelligence.get("english_query"))
                resolved = intelligence.get("resolved_references") or {}
                if isinstance(resolved, dict):
                    texts.extend(str(value) for value in resolved.values())
            return await build_peer_context(UUID(user_id_for_peer), texts)
        except Exception as exc:  # noqa: BLE001 - enrichment, never fatal
            logger.warning(
                "peer_context_injection_failed",
                run_id=run_id,
                error_type=type(exc).__name__,
            )
            return ""

    async def _inject_psyche_and_peer() -> tuple[str, str]:
        """Both string injections, launched together.

        ``asyncio.gather`` is typed through overloads that stop at SIX
        awaitables; a seventh degrades the result to ``list[union]`` and every
        unpacked value loses its type. Pairing the two keeps the outer gather
        at six — and both still run concurrently.
        """
        psyche, peer = await asyncio.gather(_inject_psyche(), _inject_peer_context())
        return psyche, peer

    async def _inject_habits_rhythm() -> str:
        """Ambient rhythm block (ADR-214, Lot 5) — portrait's sibling.

        Self-labelled ``<UserRhythmContext>`` XML, so it travels appended to
        the existing ``user_model_block`` field: no bundle change, no
        response-node change (that file is frozen). Own gates + graceful ""
        live inside the builder.
        """
        try:
            _uid = runtime_user_id_str(None)
            if not _uid:
                return ""
            from src.domains.habits.ambient import build_habits_rhythm_block

            return await build_habits_rhythm_block(_uid, flow="response")
        except Exception as e:
            logger.warning(
                "habits_rhythm_block_failed_response",
                run_id=run_id,
                error=str(e),
            )
            return ""

    async def _inject_portrait_and_rhythm() -> str:
        """Portrait + rhythm, launched together (same six-slot pairing trick
        as psyche+peer). Both are ambient user-model diffusion; the rhythm
        block rides in the same prompt field."""
        portrait, rhythm = await asyncio.gather(_inject_portrait(), _inject_habits_rhythm())
        if portrait and rhythm:
            return f"{portrait}\n{rhythm}"
        return portrait or rhythm

    (
        (psychological_profile, memory_injection_debug),
        (rag_context, rag_injection_debug),
        app_knowledge_context,
        (journal_context, journal_injection_debug, current_journal_injected_ids),
        user_model_block,
        (psyche_context, peer_context),
    ) = await asyncio.gather(
        _inject_memory(),
        _inject_user_rag(),
        _inject_system_rag(),
        _inject_journal(),
        _inject_portrait_and_rhythm(),
        _inject_psyche_and_peer(),
    )

    return ResponseContextBundle(
        psychological_profile=psychological_profile,
        memory_injection_debug=memory_injection_debug,
        rag_context=rag_context,
        rag_injection_debug=rag_injection_debug,
        app_knowledge_context=app_knowledge_context,
        journal_context=journal_context,
        journal_injection_debug=journal_injection_debug,
        journal_injected_ids=current_journal_injected_ids,
        user_model_block=user_model_block,
        psyche_context=psyche_context,
        peer_context=peer_context,
        user_msg_is_trivial=user_msg_is_trivial,
        user_message_embedding=user_message_embedding,
        system_rag_deferred=not include_system_rag,
    )


# =============================================================================
# Prefetch registry (process-local, bounded)
# =============================================================================

_prefetch_tasks: OrderedDict[str, asyncio.Task[ResponseContextBundle]] = OrderedDict()


def start_response_context_prefetch(
    state: MessagesState,
    config: RunnableConfig,
    run_id: str,
    *,
    include_system_rag: bool = True,
) -> None:
    """Launch the response-context fetch as a background task for this run.

    Idempotent per ``run_id`` (initiative loop iterations reuse the first
    task; the initiative-node start is a no-op when the router already
    started the prefetch — latency lot R2). Never raises — a failed launch
    simply means the response node falls back to its inline fetch. Bounded
    registry: oldest entries are cancelled and evicted beyond
    ``response_context_prefetch_max_entries`` (leak guard for runs that
    never reach the response node).

    Args:
        state: Current graph state.
        config: RunnableConfig carrying user/thread ids and feature flags.
        run_id: Current run identifier (registry key).
        include_system_rag: False for the router-entry prefetch (query
            intelligence not computed yet) — see :func:`fetch_response_context`.
    """
    if not settings.response_context_prefetch_enabled:
        return
    if not run_id or run_id == "unknown" or run_id in _prefetch_tasks:
        return
    try:
        task = asyncio.create_task(
            fetch_response_context(state, config, run_id, include_system_rag=include_system_rag),
            name=f"response_context_prefetch_{run_id}",
        )
        _prefetch_tasks[run_id] = task
        while len(_prefetch_tasks) > settings.response_context_prefetch_max_entries:
            evicted_id, evicted_task = _prefetch_tasks.popitem(last=False)
            evicted_task.cancel()
            logger.warning("response_context_prefetch_evicted", run_id=evicted_id)
        logger.debug("response_context_prefetch_started", run_id=run_id)
    except Exception as exc:
        logger.warning("response_context_prefetch_start_failed", run_id=run_id, error=str(exc))


async def pop_response_context(run_id: str) -> ResponseContextBundle | None:
    """Retrieve (and consume) the prefetched context bundle for this run.

    Args:
        run_id: Current run identifier.

    Returns:
        The resolved bundle with ``prefetched=True``, or None when no
        prefetch was started, it failed, or it exceeded the await timeout
        (caller falls back to the inline fetch in every None case).
    """
    task = _prefetch_tasks.pop(run_id, None)
    if task is None:
        return None
    try:
        bundle = await asyncio.wait_for(
            task, timeout=settings.response_context_prefetch_await_timeout_seconds
        )
        bundle.prefetched = True
        logger.info("response_context_prefetch_hit", run_id=run_id)
        return bundle
    except asyncio.CancelledError:
        raise  # outer cancellation — propagate untouched
    except Exception as exc:
        logger.warning(
            "response_context_prefetch_failed",
            run_id=run_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


def reset_response_context_prefetch() -> None:
    """Cancel and drop all in-flight prefetch tasks (test isolation helper)."""
    while _prefetch_tasks:
        _, task = _prefetch_tasks.popitem(last=False)
        task.cancel()
