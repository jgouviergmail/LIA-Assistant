"""Seal the parameters actually used before an efficacy contribution is recorded.

Experience is intentionally aggregated across the owner's assistant configurations;
this is provenance, not calibration of the currently selected model. No prompt,
response, tool payload or private comment is copied into the fingerprint envelope.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.analysis.efficacy_context import EfficacyTurnContext, read_turn_context
from src.domains.agents.services.efficacy_evidence import FIELD_EFFICACY
from src.domains.chat.models import TokenUsageLog
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.response_feedback import (
    get_assistant_message_for_user,
    lock_feedback_owner,
)

_MAX_CONFIGURATIONS = 256
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_OptionalFinite = Annotated[float | None, Field(strict=True, allow_inf_nan=False)]
_OptionalRecordedInt = Annotated[int | None, Field(strict=True)]


class InvocationProvenance(BaseModel):
    """Allowlisted persisted invocation fields; null remains unknown/unset."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Annotated[str | None, Field(strict=True, max_length=40)] = None
    model_name: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    llm_type: Annotated[str | None, Field(strict=True, max_length=64)] = None
    temperature: _OptionalFinite = None
    top_p: _OptionalFinite = None
    max_output_tokens: _OptionalRecordedInt = None
    reasoning_level: Annotated[str | None, Field(strict=True, max_length=20)] = None
    reasoning_budget_tokens: _OptionalRecordedInt = None
    params_digest: Annotated[str | None, Field(strict=True, pattern=r"^[0-9a-f]{64}$")] = None


def fingerprint_invocations(rows: Sequence[Mapping[str, object]]) -> str | None:
    """Canonicalize configurations, independent of log order or identical retries."""
    configurations: set[str] = set()
    try:
        for row in rows:
            invocation = InvocationProvenance.model_validate(row)
            configurations.add(invocation.model_dump_json())
            if len(configurations) > _MAX_CONFIGURATIONS:
                return None
    except ValidationError:
        return None
    if not configurations:
        return None
    payload = {
        "version": 1,
        "contract": "efficacy-coverage-v1",
        "configurations": sorted(configurations),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def eligible_message_context(
    row: ConversationMessage, user_id: UUID
) -> tuple[dict[str, object], EfficacyTurnContext] | None:
    """Validate a previously owner-scoped canonical row at its immutable final time."""
    metadata = row.message_metadata or {}
    if (
        row.role != "assistant"
        or row.hidden
        or any(
            metadata.get(key)
            for key in (
                "hitl_question",
                "interrupted",
                "hidden",
                "live_session_summary",
                "provisional",
            )
        )
    ):
        return None
    envelope = metadata.get(FIELD_EFFICACY)
    if not isinstance(envelope, dict) or envelope.get("version") != 1:
        return None
    context = read_turn_context(envelope.get("context"))
    if (
        context is None
        or context.owner_id != user_id
        or context.run_id != metadata.get("run_id")
        or not context.collection_enabled
        or not context.valid_at(row.created_at)
    ):
        return None
    return dict(envelope), context


async def _recorded_fingerprint(db: AsyncSession, user_id: UUID, run_id: str) -> str | None:
    statement = (
        select(
            TokenUsageLog.provider,
            TokenUsageLog.model_name,
            TokenUsageLog.llm_type,
            TokenUsageLog.temperature,
            TokenUsageLog.top_p,
            TokenUsageLog.max_output_tokens,
            TokenUsageLog.reasoning_level,
            TokenUsageLog.reasoning_budget_tokens,
            TokenUsageLog.params_digest,
        )
        .where(TokenUsageLog.user_id == user_id, TokenUsageLog.run_id == run_id)
        .distinct()
        .limit(_MAX_CONFIGURATIONS + 1)
    )
    result = await db.execute(statement)
    rows: list[Mapping[str, object]] = [
        {field: row[field] for field in InvocationProvenance.model_fields}
        for row in result.mappings()
    ]
    return fingerprint_invocations(rows)


async def finalize_provenance(db: AsyncSession, user_id: UUID, message_id: UUID) -> bool:
    """Seal once under the owner lock; caller commits with episode/feedback writes."""
    await lock_feedback_owner(db, user_id)
    row = await get_assistant_message_for_user(db, user_id, message_id)
    if row is None:
        return False
    canonical = eligible_message_context(row, user_id)
    if canonical is None:
        return False
    envelope, context = canonical
    if "config_fingerprint" in envelope:
        existing = envelope["config_fingerprint"]
        return isinstance(existing, str) and _FINGERPRINT.fullmatch(existing) is not None
    fingerprint = await _recorded_fingerprint(db, user_id, context.run_id)
    if fingerprint is None:
        return False
    envelope["config_fingerprint"] = fingerprint
    row.message_metadata = {**(row.message_metadata or {}), FIELD_EFFICACY: envelope}
    await db.flush()
    return True
