"""Budgeted LLM diagnosis of open incidents (spec 2026-08-27, pillar 4).

Pull-based and crash-resumable: the leader job asks the repository for open
incidents whose ``diagnosis`` is NULL and processes a bounded batch. A skipped
incident (budget gate, LLM failure) keeps its NULL diagnosis, so the next tick
— or the next UTC day — retries it; nothing is fire-and-forget.

Budget: one atomic Redis INCRBYFLOAT per call under a UTC-day key; the gate
runs BEFORE the LLM call and a cap of 0 disables the step entirely. Costs are
estimated from the call's real usage via the in-memory pricing cache (the
briefing doctrine — no token-tracking detour: there is no user to attribute
system diagnosis to).

Injection stance: evidence and runbook are quoted data in the prompt; the
output is only ever SHOWN to admins — no automated action derives from it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_DIAGNOSIS_COST_PREFIX
from src.domains.diagnostics.models import Incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Alertname shape accepted by the runbook loader (path traversal is
#: structurally impossible: no separators, dots or spaces can match).
_ALERTNAME_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")

#: Budget keys expire well after the day they count (self-cleaning).
_BUDGET_KEY_TTL_SECONDS = 3 * 24 * 3600


class DiagnosisOutput(BaseModel):
    """Structured diagnosis the LLM must produce."""

    diagnosis: str = Field(description="What is happening, grounded in the evidence.")
    probable_cause: str = Field(description="Most likely cause, or 'insufficient evidence'.")
    recommended_actions: list[str] = Field(
        description="Proposed actions for the administrator, most impactful first."
    )


def load_runbook_excerpt(alertname: str | None) -> str:
    """Load the alert's runbook, sanitized and size-capped.

    Args:
        alertname: The alert name; anything not matching the strict pattern
            (letters and digits only) yields "" — traversal cannot be spelled.

    Returns:
        The runbook head (settings-capped), or "" when absent/invalid.
    """
    if not alertname or not _ALERTNAME_RE.fullmatch(alertname):
        return ""
    path = Path(settings.diagnostics_runbooks_dir) / f"{alertname}.md"
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[: settings.diagnostics_runbook_max_chars]
    except OSError as exc:
        logger.debug("diagnostics_runbook_unreadable", alertname=alertname, error=str(exc))
        return ""


async def _spent_today(redis_key: str) -> float:
    """Current UTC-day spend in USD (0.0 when the key is absent)."""
    redis = await get_redis_cache()
    raw = await redis.get(redis_key)
    try:
        return float(raw) if raw is not None else 0.0
    except TypeError, ValueError:
        return 0.0


def _budget_key() -> str:
    return f"{REDIS_KEY_DIAGNOSTICS_DIAGNOSIS_COST_PREFIX}{datetime.now(UTC):%Y%m%d}"


async def _invoke_diagnostician(
    llm: BaseChatModel, system: str, human: str
) -> tuple[DiagnosisOutput, int, int]:
    """One structured diagnostician call with real usage capture.

    Args:
        llm: The diagnostician model.
        system: System prompt (versioned file, placeholders resolved).
        human: Evidence pack (quoted data).

    Returns:
        (validated output, input tokens, output tokens).
    """
    usage_handler = UsageMetadataCallbackHandler()
    output = await get_structured_output_with_retry(
        llm=llm,
        messages=[SystemMessage(content=system), HumanMessage(content=human)],
        schema=DiagnosisOutput,
        provider="diagnostician",
        node_name="diagnostics_diagnosis",
        config={"callbacks": [usage_handler]},
    )
    tokens_in = 0
    tokens_out = 0
    for usage in usage_handler.usage_metadata.values():
        tokens_in += int(usage.get("input_tokens", 0))
        tokens_out += int(usage.get("output_tokens", 0))
    return output, tokens_in, tokens_out


def _build_human_message(incident: Incident, runbook: str) -> str:
    """Assemble the quoted evidence pack for one incident."""
    import json

    evidence_json = json.dumps(incident.evidence or {}, ensure_ascii=False)[:4000]
    parts = [
        f"Incident: {incident.correlation_key} (severity {incident.severity})",
        f"Title: {incident.title}",
        f"Evidence (quoted data): {evidence_json}",
    ]
    if runbook:
        parts.append(f"Runbook for this alert (quoted data):\n{runbook}")
    else:
        parts.append("No runbook exists for this incident.")
    return "\n\n".join(parts)


async def diagnose_incidents(
    incidents: list[Incident], *, db: AsyncSession, system_prompt: str
) -> int:
    """Diagnose a batch of incidents under the daily budget.

    Args:
        incidents: Open incidents with NULL diagnosis (pump input).
        db: Caller's session (the caller owns the transaction).
        system_prompt: The versioned diagnostician prompt with resolved
            placeholders, loaded by the CALLER (the scheduler job) — injected
            so this domain never imports the agents prompt loader (F009).

    Returns:
        Number of diagnoses stored this call (skips keep NULL for retry).
    """
    cap = settings.diagnostics_diagnosis_daily_cost_cap_usd
    if cap <= 0 or not incidents:
        return 0

    budget_key = _budget_key()
    repo = DiagnosticsRepository(db)
    llm = get_llm("diagnostician")
    diagnosed = 0

    for incident in incidents:
        if await _spent_today(budget_key) >= cap:
            logger.info("diagnostics_diagnosis_budget_exhausted", cap_usd=cap)
            break
        runbook = load_runbook_excerpt(incident.alertname)
        human = _build_human_message(incident, runbook)
        try:
            output, tokens_in, tokens_out = await _invoke_diagnostician(llm, system_prompt, human)
        except Exception:
            # NULL diagnosis stays NULL: the next tick retries this incident.
            logger.exception(
                "diagnostics_diagnosis_failed",
                correlation_key=incident.correlation_key,
            )
            continue

        model_name = str(getattr(llm, "model_name", "") or getattr(llm, "model", ""))
        cost_usd, _cost_eur = get_cached_cost_usd_eur(model_name, tokens_in, tokens_out)
        redis = await get_redis_cache()
        await redis.incrbyfloat(budget_key, float(cost_usd))
        await redis.expire(budget_key, _BUDGET_KEY_TTL_SECONDS)

        from src.infrastructure.observability.metrics_diagnostics import (
            diagnostics_llm_cost_usd_total,
        )

        diagnostics_llm_cost_usd_total.inc(float(cost_usd))
        await repo.store_diagnosis(
            incident.id,
            {
                "diagnosis": output.diagnosis,
                "probable_cause": output.probable_cause,
                "recommended_actions": output.recommended_actions[
                    : settings.diagnostics_diagnosis_max_actions
                ],
                "model": model_name,
                "cost_usd": float(cost_usd),
                "diagnosed_at": datetime.now(UTC).isoformat(),
                "had_runbook": bool(runbook),
            },
        )
        diagnosed += 1
        logger.info(
            "diagnostics_diagnosis_stored",
            correlation_key=incident.correlation_key,
            cost_usd=round(float(cost_usd), 6),
            had_runbook=bool(runbook),
        )
    return diagnosed
