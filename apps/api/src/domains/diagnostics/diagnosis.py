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
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_DIAGNOSIS_COST_PREFIX
from src.core.i18n import normalize_language
from src.core.i18n_types import get_language_name
from src.domains.diagnostics.context_collector import collect_diagnosis_context
from src.domains.diagnostics.models import Incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.telemetry.loki import LokiClient
from src.infrastructure.telemetry.prometheus import PrometheusClient

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


def count_runbooks() -> int:
    """How many per-alert runbooks the configured directory actually holds.

    Production ran for weeks with the mount point present and EMPTY — the
    bundle never staged ``docs/runbooks`` — and every stored diagnosis carried
    ``had_runbook=false`` without any surface saying why. The count turns that
    silence into a number: published on the overview, warned about at boot.

    Returns:
        Number of ``*.md`` files in ``diagnostics_runbooks_dir``; ``0`` when the
        directory is missing or unreadable — never raises.
    """
    path = Path(settings.diagnostics_runbooks_dir)
    try:
        return sum(1 for entry in path.glob("*.md") if entry.is_file())
    except OSError as exc:
        logger.debug("diagnostics_runbooks_unreadable", path=str(path), error=str(exc))
        return 0


async def _spent_today(redis_key: str) -> float:
    """Current UTC-day spend in USD (0.0 when the key is absent)."""
    redis = await get_redis_cache()
    raw = await redis.get(redis_key)
    try:
        return float(raw) if raw is not None else 0.0
    except TypeError, ValueError:
        return 0.0


async def _record_spend(redis_key: str, cost_usd: float) -> None:
    """Add one call's cost to today's budget, atomically.

    Server-side ``INCRBYFLOAT`` rather than read-modify-write: two ticks may
    diagnose concurrently, and a lost update here spends real money twice.
    """
    redis = await get_redis_cache()
    await redis.incrbyfloat(redis_key, float(cost_usd))
    await redis.expire(redis_key, _BUDGET_KEY_TTL_SECONDS)


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


#: Units that need no suffix: a count is read as a count.
_UNITLESS: frozenset[str] = frozenset({"", "count"})


def _series_text(series: list[Mapping[str, object]], unit: object = "") -> str:
    """``k=v,k=v → value unit`` per sample; bare value when a sample has no label."""
    suffix = f" {unit}" if isinstance(unit, str) and unit not in _UNITLESS else ""
    rendered: list[str] = []
    for sample in series:
        labels = sample.get("labels")
        value = sample.get("value")
        label_text = (
            ",".join(f"{key}={val}" for key, val in labels.items())
            if isinstance(labels, Mapping) and labels
            else ""
        )
        value_text = (f"{value:g}" if isinstance(value, int | float) else str(value)) + suffix
        rendered.append(f"{label_text} → {value_text}" if label_text else value_text)
    return "; ".join(rendered)


def _render_metrics(metrics: list[Mapping[str, object]], window: object) -> list[str]:
    """The breakdown section: one line per catalogue query, blind ones named."""
    lines = [f"Breakdown metrics over the last {window} min (quoted data):"]
    for metric in metrics:
        title = f"{metric.get('title')} [{metric.get('query_id')}]"
        if metric.get("status") != "ok":
            lines.append(f"- {title}: UNAVAILABLE ({metric.get('error')})")
            continue
        series = metric.get("series")
        body = (
            _series_text(series, metric.get("unit", ""))
            if isinstance(series, list) and series
            else "no series (zero of every label)"
        )
        suffix = " (more series, truncated)" if metric.get("truncated") else ""
        lines.append(f"- {title}: {body}{suffix}")
    return lines


def _render_logs(logs: Mapping[str, object], window: object) -> list[str]:
    """The log section: counts by event with the failure's head, then samples."""
    import json

    status = logs.get("status")
    if status == "skipped":
        return ["No log excerpt was fetched for this incident (its recipe declares none)."]
    if status != "ok":
        return [f"Recent log lines: UNAVAILABLE ({logs.get('error')})"]
    lines = [
        f"Recent log lines from service {logs.get('service')} over the last {window} min "
        f"(quoted data): {logs.get('lines_kept')} kept of {logs.get('lines_read')} read"
    ]
    counts = logs.get("counts")
    if isinstance(counts, list) and counts:
        for entry in counts:
            event = entry.get("event") or "<raw line>"
            lines.append(
                f"- {entry.get('count')} × {event} [{entry.get('level') or '-'}]: {entry.get('head')}"
            )
        if logs.get("counts_truncated"):
            lines.append("- (more distinct lines, truncated)")
    else:
        lines.append("- no line matched the recipe in the window")
    samples = logs.get("samples")
    if isinstance(samples, list) and samples:
        lines.append("Sample lines (quoted data, newest first):")
        lines.extend(json.dumps(sample, ensure_ascii=False) for sample in samples)
    return lines


def _render_context(context: Mapping[str, object]) -> str:
    """The evidence pack as the model reads it: runtime, breakdowns, logs.

    Every section is framed as quoted data, and a source that could not be
    read is NAMED with its reason — a blind source and a quiet source are
    different facts, and the prompt tells the model to keep them apart.
    """
    window = context.get("window_minutes")
    parts: list[str] = []
    runtime = context.get("runtime")
    if isinstance(runtime, Mapping):
        parts.append(
            "Runtime (quoted data): version "
            f"{runtime.get('version')}, commit {runtime.get('commit') or 'unknown'}, built "
            f"{runtime.get('build_date') or 'unknown'}, up for {runtime.get('uptime_seconds')} s; "
            f"evidence window {window} min"
        )
    if context.get("recipe") is None:
        parts.append("No evidence recipe is declared for this incident: only the runtime is known.")
    metrics = context.get("metrics")
    if isinstance(metrics, list) and metrics:
        parts.append("\n".join(_render_metrics(metrics, window)))
    logs = context.get("logs")
    if isinstance(logs, Mapping):
        parts.append("\n".join(_render_logs(logs, window)))
    return "\n\n".join(parts)


def _build_human_message(
    incident: Incident, runbook: str, context: Mapping[str, object] | None = None
) -> str:
    """Assemble the quoted evidence pack for one incident.

    Args:
        incident: The incident (its stored evidence is quoted verbatim).
        runbook: Runbook excerpt, or "" when none exists.
        context: The pack collected at diagnosis time (ADR-266), or None when
            collection was impossible — the message is produced either way.

    Returns:
        The human message: incident, evidence, the pack, the runbook.
    """
    import json

    evidence_json = json.dumps(incident.evidence or {}, ensure_ascii=False)[:4000]
    parts = [
        f"Incident: {incident.correlation_key} (severity {incident.severity})",
        f"Title: {incident.title}",
        f"Evidence (quoted data): {evidence_json}",
    ]
    if context:
        # A collector that failed outright leaves only a status: that is a
        # BLIND pack, and must not read as "an incident with no recipe".
        if context.get("status") == "unavailable":
            parts.append(f"Evidence pack: UNAVAILABLE ({context.get('error')})")
        else:
            rendered = _render_context(context)
            if rendered:
                parts.append(rendered)
    if runbook:
        parts.append(f"Runbook for this alert (quoted data):\n{runbook}")
    else:
        parts.append("No runbook exists for this incident.")
    return "\n\n".join(parts)


#: Language used when no administrator declares one — a fresh install has no
#: superuser yet, and producing nothing would make the panel look broken on the
#: very first incident.
_FALLBACK_LANGUAGE = "en"


async def admin_languages(repo: object) -> list[str]:
    """Distinct languages the administrators of this instance read.

    A diagnosis is written by a scheduler tick with no reader in sight, so the
    only way to satisfy "in the language of the admin who displays it" without
    an LLM call on every page view is to write it in the languages the admins
    actually read. With one administrator — the normal case for a self-hosted
    instance — that is exactly one language and exactly one call.

    Args:
        repo: Diagnostics repository exposing ``distinct_admin_languages``.

    Returns:
        Distinct language codes, never empty. Falls back to a single default
        when the instance has no administrator or the table cannot be read: a
        diagnosis in the wrong language beats no diagnosis at all.
    """
    try:
        languages = await repo.distinct_admin_languages()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 — diagnosis must not depend on this
        logger.warning("diagnostics_admin_languages_failed", error=str(exc))
        return [_FALLBACK_LANGUAGE]
    # Through the single chokepoint, never on the raw column: two admins
    # spelling French `fr` and `fr-FR` would otherwise be two languages, and
    # the tick would pay for the same diagnosis twice — then hand each reader
    # only the spelling that happened to match theirs.
    unique: list[str] = sorted({normalize_language(language) for language in languages if language})
    return unique or [_FALLBACK_LANGUAGE]


def build_diagnosis_record(
    *,
    diagnosis: str,
    probable_cause: str,
    recommended_actions: list[str],
    language: str,
    model: str,
    cost_usd: float,
    had_runbook: bool,
) -> dict[str, object]:
    """One stored diagnosis, stamped with the language it was written in.

    The stamp is what lets a reader know whether the text is theirs, and what
    lets a later tick add a second language without guessing what the first
    one was.
    """
    return {
        "diagnosis": diagnosis,
        "probable_cause": probable_cause,
        "recommended_actions": recommended_actions,
        "language": language,
        "model": model,
        "cost_usd": cost_usd,
        "diagnosed_at": datetime.now(UTC).isoformat(),
        "had_runbook": had_runbook,
    }


def diagnosis_for_language(
    stored: dict[str, object] | None, language: str
) -> dict[str, object] | None:
    """The stored diagnosis as THIS reader should see it.

    **The returned shape does not depend on which branch resolved it.** The
    record's metadata (model, cost, timestamp) always travels, only the three
    written fields are swapped for the reader's language, and ``by_language``
    never leaves the server — a reader has no use for the other admins'
    languages, and shipping them would grow the payload with every admin added.

    Resolution order, and each step earns its place:

    1. the reader's own language under ``by_language`` — the exact answer;
    2. the record's own text, when it was written in that language or when the
       row predates ``by_language`` entirely;
    3. the record's own text regardless. Showing nothing because nobody
       generated German would hide a real incident behind a translation gap.

    Args:
        stored: The JSONB diagnosis, or None when none was produced yet.
        language: The reader's language code.

    Returns:
        The diagnosis to render, or None when there is no diagnosis at all.
    """
    if not stored:
        return None
    resolved = {key: value for key, value in stored.items() if key != "by_language"}
    by_language = stored.get("by_language")
    if isinstance(by_language, dict):
        # Normalised on BOTH sides or the lookup is a coin toss: the variants
        # were keyed canonically, and a reader's raw locale need not be.
        canonical = normalize_language(language)
        variant = by_language.get(canonical)
        if isinstance(variant, dict):
            resolved.update(variant)
            resolved["language"] = canonical
    return resolved


async def _evidence_pack(
    incident: Incident, *, prom_client: PrometheusClient, loki_client: LokiClient
) -> dict[str, object]:
    """The pack for one incident; a collector failure is data, never a crash."""
    try:
        return await collect_diagnosis_context(
            incident, prom_client=prom_client, loki_client=loki_client
        )
    except Exception as exc:  # noqa: BLE001 — the pack is best-effort, the diagnosis is not
        logger.warning(
            "diagnostics_context_unavailable",
            correlation_key=incident.correlation_key,
            error=str(exc),
        )
        return {"status": "unavailable", "error": type(exc).__name__}


async def diagnose_incidents(
    incidents: list[Incident],
    *,
    db: AsyncSession,
    system_prompt: str,
    prom_client: PrometheusClient | None = None,
    loki_client: LokiClient | None = None,
) -> int:
    """Diagnose a batch of incidents under the daily budget.

    Args:
        incidents: Open incidents with NULL diagnosis (pump input).
        db: Caller's session (the caller owns the transaction).
        system_prompt: The versioned diagnostician prompt with resolved
            placeholders, loaded by the CALLER (the scheduler job) — injected
            so this domain never imports the agents prompt loader (F009).
        prom_client: Prometheus reader for the evidence pack (ADR-266);
            built from settings when omitted.
        loki_client: Loki reader for the evidence pack; built from settings
            when omitted.

    Returns:
        Number of diagnoses stored this call (skips keep NULL for retry).
    """
    cap = settings.diagnostics_diagnosis_daily_cost_cap_usd
    if cap <= 0 or not incidents:
        return 0

    budget_key = _budget_key()
    repo = DiagnosticsRepository(db)
    llm = get_llm("diagnostician")
    prom = prom_client or PrometheusClient(
        base_url=settings.diagnostics_prometheus_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    )
    loki = loki_client or LokiClient(
        base_url=settings.diagnostics_loki_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    )
    languages: list[str] | None = None
    diagnosed = 0

    for incident in incidents:
        if await _spent_today(budget_key) >= cap:
            logger.info("diagnostics_diagnosis_budget_exhausted", cap_usd=cap)
            break
        if languages is None:
            # Resolved once per batch, and only once a diagnosis is actually
            # going to be produced: the admin population does not change between
            # two incidents of the same tick, and a tick whose budget is already
            # spent must not query it to decide nothing.
            languages = await admin_languages(repo)
        runbook = load_runbook_excerpt(incident.alertname)
        # Collected ONCE per incident, after the budget gate: the pack is the
        # same in every language, and a tick whose budget is spent must not
        # read Loki to decide nothing.
        context = await _evidence_pack(incident, prom_client=prom, loki_client=loki)
        human = _build_human_message(incident, runbook, context)
        model_name = str(getattr(llm, "model_name", "") or getattr(llm, "model", ""))
        variants: dict[str, dict[str, Any]] = {}
        cost_usd = 0.0
        failed = False
        for language in languages:
            # Re-read per LANGUAGE, not per incident. One incident now costs one
            # call per admin language, so gating once per incident would let a
            # single incident overshoot the daily cap by every language after
            # the first — and this module's contract is that the cap gates
            # BEFORE any LLM call, not before most of them.
            if await _spent_today(budget_key) >= cap:
                logger.info("diagnostics_diagnosis_budget_exhausted", cap_usd=cap)
                break
            try:
                # `.replace`, not `.format`: the caller resolves `{max_actions}`
                # the same way, and a brace added to the prompt one day (a JSON
                # example, a set literal) would make `.format` raise and take
                # the whole diagnosis pump down with it.
                rendered = system_prompt.replace("{language}", get_language_name(language))
                output, used_in, used_out = await _invoke_diagnostician(llm, rendered, human)
            except Exception:
                # NULL diagnosis stays NULL: the next tick retries this incident.
                logger.exception(
                    "diagnostics_diagnosis_failed",
                    correlation_key=incident.correlation_key,
                    language=language,
                )
                failed = True
                break
            # Billed as it is spent: a language that ran has been paid for,
            # whether or not the languages after it get to run.
            call_cost, _call_eur = get_cached_cost_usd_eur(model_name, used_in, used_out)
            cost_usd += call_cost
            await _record_spend(budget_key, call_cost)
            variants[language] = {
                "diagnosis": output.diagnosis,
                "probable_cause": output.probable_cause,
                "recommended_actions": output.recommended_actions[
                    : settings.diagnostics_diagnosis_max_actions
                ],
            }
        if failed or not variants:
            continue

        from src.infrastructure.observability.metrics_diagnostics import (
            diagnostics_llm_cost_usd_total,
        )

        diagnostics_llm_cost_usd_total.inc(float(cost_usd))
        # The first language is stored flat as well as under `by_language`:
        # every existing reader — the list endpoint, an old client, a row
        # written before this change — keeps finding the keys where they were.
        primary = languages[0]
        record = build_diagnosis_record(
            diagnosis=str(variants[primary]["diagnosis"]),
            probable_cause=str(variants[primary]["probable_cause"]),
            recommended_actions=list(variants[primary]["recommended_actions"]),
            language=primary,
            model=model_name,
            cost_usd=float(cost_usd),
            had_runbook=bool(runbook),
        )
        record["by_language"] = variants
        # What the model saw travels with what it said: an administrator can
        # check a diagnosis against its evidence instead of taking it on faith.
        record["context"] = context
        await repo.store_diagnosis(incident.id, record)
        diagnosed += 1
        logger.info(
            "diagnostics_diagnosis_stored",
            correlation_key=incident.correlation_key,
            cost_usd=round(float(cost_usd), 6),
            had_runbook=bool(runbook),
        )
    return diagnosed
