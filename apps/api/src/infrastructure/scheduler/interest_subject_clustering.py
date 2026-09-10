"""Batch LLM subject clustering for interest notifications (ADR-131).

Assigns a "subject" label to every active interest of a user in ONE LLM call.
Incremental (per-extraction) labeling was empirically refuted (order-dependent
drift, 89% agreement, aberrant merges); batch labeling measured 98.2% stable.
Subjects are derived data: recomputed wholesale, safe to relabel at any time.

Two triggers, registered in startup/schedulers.py (leader-elected):
- Stale scan (default every 30 min): users with any active interest whose
  subject IS NULL (new interests, renames, merges).
- Nightly full re-cluster (default 04:15, after the 03:00 cleanup+merge):
  heals residual label drift.
"""

import json
import re
import uuid as uuid_module
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select

from src.core.config import settings
from src.core.i18n_types import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.interests.models import InterestStatus, UserInterest
from src.infrastructure.database import get_db_context
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.usage_metadata import model_name_of, tokens_from_response
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_registry import (
    interest_subject_recluster_total,
)
from src.infrastructure.proactive.tracking import track_proactive_tokens

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_assignments(
    raw_text: str,
    expected_indexes: set[int],
    max_length: int,
) -> dict[int, str]:
    """Parse and sanitize the LLM's index -> subject assignments.

    Tolerates code fences and surrounding prose; ignores unknown indexes;
    missing indexes are simply absent (the caller keeps previous labels).

    Args:
        raw_text: Raw LLM output.
        expected_indexes: Valid indexes for this batch.
        max_length: Hard cap for a subject label.

    Returns:
        Mapping of index to sanitized subject label; empty dict on any
        structural failure (fail-open: previous labels survive).
    """
    text = _FENCE_RE.sub("", raw_text.strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    assignments = data.get("assignments")
    if not isinstance(assignments, list):
        return {}

    out: dict[int, str] = {}
    for item in assignments:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        subject = item.get("subject")
        if not isinstance(index, int) or isinstance(index, bool):
            continue
        if index not in expected_indexes or not isinstance(subject, str):
            continue
        label = _WHITESPACE_RE.sub(" ", subject).strip()[:max_length].strip()
        if label:
            out[index] = label
    return out


async def recluster_user_subjects(user_id: UUID) -> int:
    """Re-label all active interests of one user in a single LLM call.

    Args:
        user_id: User whose active interests get (re)labeled.

    Returns:
        Number of interests whose subject was written (0 on failure —
        previous labels are kept, selection fail-opens on NULLs).
    """
    async with get_db_context() as db:
        result = await db.execute(
            select(UserInterest).where(
                UserInterest.user_id == user_id,
                UserInterest.status == InterestStatus.ACTIVE.value,
            )
        )
        interests = list(result.scalars().all())
        if not interests:
            return 0

        from src.domains.users.models import User

        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        language = getattr(user, "language", None) or settings.default_language

        indexed = list(enumerate(interests, start=1))
        interests_block = "\n".join(f"{idx}. {i.topic} ({i.category})" for idx, i in indexed)
        prompt = load_prompt("interest_subject_clustering_prompt").format(
            interests=interests_block,
            user_language=get_language_name(language),
        )

        llm = get_llm("interest_extraction")
        # The real account, not "system". Re-clustering runs FOR this person's
        # interests, so passing a placeholder made the Layer-2 usage guard
        # unable to resolve anyone — no quota was consulted — and left the
        # spend attributed to nobody.
        llm_result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="interest_subject_clustering",
            messages=prompt,
            session_id=f"subj_cluster_{uuid_module.uuid4().hex[:8]}",
            user_id=str(user_id),
        )
        usage = tokens_from_response(llm_result)
        await track_proactive_tokens(
            user_id=user_id,
            task_type="interest_subject_clustering",
            target_id=str(user_id),
            conversation_id=None,
            tokens_in=usage.prompt,
            tokens_out=usage.completion,
            tokens_cache=usage.cached,
            model_name=model_name_of(llm),
            source="proactive",
        )
        assignments = parse_assignments(
            llm_result.text,
            expected_indexes={idx for idx, _ in indexed},
            max_length=settings.interest_subject_max_length,
        )
        if not assignments:
            logger.warning(
                "interest_subject_clustering_parse_failed",
                user_id=str(user_id),
                interests_count=len(interests),
            )
            interest_subject_recluster_total.labels(outcome="parse_failed").inc()
            return 0

        labeled = 0
        for idx, interest in indexed:
            label = assignments.get(idx)
            if label is not None:
                interest.subject = label
                labeled += 1
        await db.commit()

        logger.info(
            "interest_subjects_reclustered",
            user_id=str(user_id),
            interests_count=len(interests),
            labeled=labeled,
            distinct_subjects=len(set(assignments.values())),
        )
        interest_subject_recluster_total.labels(outcome="success").inc()
        return labeled


async def _run_for_users(user_ids: list[UUID], trigger: str) -> dict[str, Any]:
    """Sequentially re-cluster a list of users (one LLM call each).

    Args:
        user_ids: Users to process.
        trigger: "stale" or "full" (for logging/stats).

    Returns:
        Stats dict: trigger, users processed, interests labeled.
    """
    stats: dict[str, Any] = {"trigger": trigger, "users": len(user_ids), "labeled": 0}
    for user_id in user_ids:
        try:
            stats["labeled"] += await recluster_user_subjects(user_id)
        except Exception as e:
            logger.error(
                "interest_subject_clustering_user_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            interest_subject_recluster_total.labels(outcome="error").inc()
    logger.info("interest_subject_clustering_completed", **stats)
    return stats


def _batch_size(limit: int | None) -> int:
    """The cap for one sweep — the setting unless a caller injects one.

    Args:
        limit: Explicit cap, or None to read the setting.

    Returns:
        The number of users one run may serve.
    """
    return settings.interest_subject_recluster_batch_size if limit is None else limit


def _candidates(
    *conditions: ColumnElement[bool],
    order_by: Sequence[ColumnElement[Any]],
    limit: int | None,
) -> Select[tuple[UUID]]:
    """The capped list of users one sweep serves, in a DECLARED order.

    A ``LIMIT`` with nothing deciding which rows is the defect this exists to
    remove: measured 2026-09-10, both sweeps read ``.distinct().limit(50)``
    with no ``ORDER BY``, so PostgreSQL returned whatever the plan yielded —
    and on a table that is not moving, that is the SAME fifty every night.

    ``GROUP BY`` rather than ``DISTINCT`` because the order is an aggregate
    over each candidate's own rows.

    Args:
        *conditions: What makes a row a candidate.
        order_by: The ordering clauses, in order — never empty.
        limit: Cap, or None to read the setting.

    Returns:
        The statement.
    """
    return (
        select(UserInterest.user_id)
        .where(*conditions)
        .group_by(UserInterest.user_id)
        .order_by(*order_by)
        .limit(_batch_size(limit))
    )


def stale_candidates_statement(limit: int | None = None) -> Select[tuple[UUID]]:
    """Users carrying an unlabelled active interest, longest-waiting first.

    This backlog DRAINS — labelling a user's interests removes them from it —
    so it is served oldest-first: a deterministic order, ending on the
    grouping key so it is total and a cap can never split a tie at random.

    Args:
        limit: Cap, or None to read the setting.

    Returns:
        The statement.
    """
    return _candidates(
        UserInterest.status == InterestStatus.ACTIVE.value,
        UserInterest.subject.is_(None),
        order_by=(func.min(UserInterest.updated_at).asc(), UserInterest.user_id.asc()),
        limit=limit,
    )


def refresh_candidates_statement(limit: int | None = None) -> Select[tuple[UUID]]:
    """A fair sample of users with active interests, for the nightly refresh.

    Unlike the backlog, this set NEVER drains: every user with an active
    interest is a candidate every night, forever. Any stable order therefore
    starves everyone past the cap — including one by ``updated_at``, because
    re-clustering that assigns the same labels writes nothing and so bumps no
    timestamp, leaving the very users the refresh serves pinned at the front.

    Sampling is what makes the cap a budget instead of a boundary.

    Args:
        limit: Cap, or None to read the setting.

    Returns:
        The statement.
    """
    return _candidates(
        UserInterest.status == InterestStatus.ACTIVE.value,
        order_by=(func.random(),),
        limit=limit,
    )


async def run_subject_clustering_stale() -> dict[str, Any]:
    """Job: re-cluster users having any active interest with subject IS NULL.

    Serves at most one batch, longest-waiting first; the backlog drains across
    runs.

    Returns:
        Stats dict from the run.
    """
    async with get_db_context() as db:
        rows = await db.execute(stale_candidates_statement())
        user_ids = [row[0] for row in rows.all()]
    return await _run_for_users(user_ids, trigger="stale")


async def run_subject_clustering_full() -> dict[str, Any]:
    """Job: nightly refresh of a fair sample of users with active interests.

    Not "every user": the run is capped by
    ``interest_subject_recluster_batch_size`` because each user costs one LLM
    call. The sample is drawn at random so the cap starves nobody — the
    docstring used to promise every user and the code served an arbitrary,
    unchanging fifty.

    Returns:
        Stats dict from the run.
    """
    async with get_db_context() as db:
        rows = await db.execute(refresh_candidates_statement())
        user_ids = [row[0] for row in rows.all()]
    return await _run_for_users(user_ids, trigger="full")
