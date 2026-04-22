"""LangChain tools for the Health Metrics agent (v1.17.2).

Seven hand-crafted tools under a single ``health_agent``, mirroring the
codebase convention (one agent per domain, many tools per agent — cf.
``weather_tools``, ``emails_tools``):

Steps :

- :func:`get_steps_summary_tool` — total step count over a period.
- :func:`get_steps_daily_breakdown_tool` — per-day totals over N days.
- :func:`compare_steps_to_baseline_tool` — delta vs the rolling baseline.

Heart rate :

- :func:`get_heart_rate_summary_tool` — avg / min / max heart rate.
- :func:`compare_heart_rate_to_baseline_tool` — delta vs the rolling baseline.

Cross-kind :

- :func:`get_health_overview_tool` — kind-by-kind summary for a period.
- :func:`detect_health_changes_tool` — notable variations + structural events.

All tools gate on the per-user ``health_metrics_agents_enabled`` toggle
via :func:`_check_user_toggle_or_error`.

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    HEALTH_METRICS_BASELINE_WINDOW_MAX_DAYS,
    HEALTH_METRICS_BREAKDOWN_MAX_DAYS,
    HEALTH_METRICS_USER_TOGGLE_ATTR,
)
from src.domains.agents.constants import AGENT_HEALTH
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    parse_user_id,
    validate_runtime_config,
)
from src.domains.users.repository import UserRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = get_logger(__name__)


# ============================================================================
# Shared helpers (private to this module)
# ============================================================================


async def _check_user_toggle_or_error(db: AsyncSession, user_id: UUID) -> UnifiedToolOutput | None:
    """Return a PERMISSION_DENIED output if the user has not opted in.

    Mirrors the gating pattern used across the health tool pack so the
    assistant never reads health data for users who did not enable the
    Settings → Health data → Assistant toggle.

    Args:
        db: Async DB session.
        user_id: Owner user UUID.

    Returns:
        ``None`` when allowed, else a :class:`UnifiedToolOutput` failure.
    """
    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        return UnifiedToolOutput.failure(
            message="User not found.",
            error_code="NOT_FOUND",
        )
    if not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
        return UnifiedToolOutput.failure(
            message=(
                "Health Metrics assistant access is disabled. "
                "Enable it in Settings → Health Metrics → Assistant."
            ),
            error_code="PERMISSION_DENIED",
            metadata={"toggle": HEALTH_METRICS_USER_TOGGLE_ATTR},
        )
    return None


def _parse_iso_ts(value: str | None, *, param: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware UTC datetime.

    Mirrors the ``time_min`` / ``time_max`` handling in
    :mod:`src.domains.agents.tools.calendar_tools`. The planner receives
    the pre-resolved temporal range from the QueryAnalyzer's
    ``resolved_references`` (e.g. "this week" -> "2026-04-20 to
    2026-04-26") and splits the two dates across the two params.

    Accepted shapes (``datetime.fromisoformat`` on Python 3.11+):

    - ``"2026-04-20"`` -> midnight UTC of that calendar day.
    - ``"2026-04-20T00:00:00+00:00"`` -> datetime as-is.
    - ``"2026-04-20T00:00:00Z"`` -> datetime as-is.

    Naive datetimes are coerced to UTC. Malformed inputs return ``None``
    (the caller then falls back to the service's own default window).

    Timezone handling: samples are stored in UTC in the DB, so no
    per-user timezone normalization is applied here (unlike
    ``calendar_tools`` which uses ``normalize_user_datetime``). The
    planner's resolved references already use user-local calendar
    boundaries (e.g. Mon-Sun for "this week"), and UTC-anchored bounds
    remain close enough for aggregate queries over hours-level samples.

    Args:
        value: Raw ISO string from the tool call, or ``None``.
        param: Parameter name (for structured logging).

    Returns:
        A timezone-aware UTC datetime, or ``None`` when input is empty
        or cannot be parsed.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        logger.warning("health_metrics_time_bound_invalid", param=param, value=value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _format_delta_pct(delta_pct: float | None) -> str:
    """Format a percent delta with an explicit sign and one decimal.

    Args:
        delta_pct: Signed percent value (can be None).

    Returns:
        ``"n/a"`` if None, else a string like ``"+12.5%"`` or ``"-3.0%"``.
    """
    if delta_pct is None:
        return "n/a"
    sign = "+" if delta_pct >= 0 else ""
    return f"{sign}{delta_pct:.1f}%"


# ============================================================================
# STEPS TOOLS
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_steps_summary",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_steps_summary_tool(
    time_min: Annotated[
        str | None, "Start of search window (ISO 8601). Defaults to today 00:00 UTC."
    ] = None,
    time_max: Annotated[
        str | None, "End of search window (ISO 8601). Defaults to now (UTC)."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Return the user's total step count over a time window.

    Use this when the user asks "how many steps today / this week / this
    month?". The planner should pass ISO 8601 bounds derived from the
    resolved temporal reference (e.g. ``"this week"`` -> ``time_min=2026-04-20``,
    ``time_max=2026-04-26``). Returns the total count, the last sample
    timestamp (freshness), and the raw sample count for transparency.
    """
    config = validate_runtime_config(runtime, "get_steps_summary_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    parsed_min = _parse_iso_ts(time_min, param="time_min")
    parsed_max = _parse_iso_ts(time_max, param="time_max")
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            summary = await service.compute_kind_summary(
                user_id, "steps", time_min=parsed_min, time_max=parsed_max
            )

        total = summary.get("total")
        if total is None:
            return UnifiedToolOutput.data_success(
                message="No steps data for the requested window.",
                structured_data=summary,
            )
        return UnifiedToolOutput.data_success(
            message=f"Steps total: {total} steps.",
            structured_data=summary,
        )
    except Exception as exc:
        return handle_tool_exception(
            exc,
            "get_steps_summary_tool",
            {"time_min": time_min, "time_max": time_max},
        )


@tool
@track_tool_metrics(
    tool_name="get_steps_daily_breakdown",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_steps_daily_breakdown_tool(
    days: Annotated[int, "Window length in days (1-30). Defaults to 7."] = 7,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Return per-day step totals over the last ``days`` days.

    Use this when the user asks for a trend or a day-by-day comparison
    (e.g. "show me my steps for the last 10 days").
    """
    config = validate_runtime_config(runtime, "get_steps_daily_breakdown_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    window = max(1, min(HEALTH_METRICS_BREAKDOWN_MAX_DAYS, int(days)))
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            breakdown = await service.compute_kind_daily_breakdown(user_id, "steps", days=window)

        if not breakdown:
            return UnifiedToolOutput.data_success(
                message=f"No steps data for the last {window} days.",
                structured_data={"days": breakdown, "window": window},
            )
        # Inline the per-day totals in the message — the Response LLM reads
        # the message field to compose its answer (see weather_tools for the
        # same pattern: factual data lives in the message string).
        entries = ", ".join(f"{day['date']}: {int(day['value'])}" for day in breakdown)
        return UnifiedToolOutput.data_success(
            message=f"Steps per day over {window} days — {entries}.",
            structured_data={"days": breakdown, "window": window},
        )
    except Exception as exc:
        return handle_tool_exception(exc, "get_steps_daily_breakdown_tool", {"days": days})


@tool
@track_tool_metrics(
    tool_name="compare_steps_to_baseline",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def compare_steps_to_baseline_tool(
    window_days: Annotated[
        int,
        "Recent window length in days to compare against the 28-day baseline. Defaults to 7.",
    ] = 7,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Compare the user's recent steps average to their rolling baseline.

    Returns the baseline mode (``bootstrap`` if fewer than 7 days of
    history, ``rolling`` otherwise), the baseline value, the recent
    window value, and the signed percent delta.
    """
    config = validate_runtime_config(runtime, "compare_steps_to_baseline_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    window = max(1, min(HEALTH_METRICS_BASELINE_WINDOW_MAX_DAYS, int(window_days)))
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            delta: dict[str, Any] = await service.compute_kind_baseline_delta(
                user_id, "steps", window_days=window
            )

        if delta["mode"] == "empty":
            return UnifiedToolOutput.data_success(
                message="No steps history to compute a baseline yet.",
                structured_data=delta,
            )
        return UnifiedToolOutput.data_success(
            message=(
                f"Steps {window}-day avg {delta['window_value']} vs baseline "
                f"{delta['baseline_value']} ({_format_delta_pct(delta['delta_pct'])}, "
                f"mode={delta['mode']})."
            ),
            structured_data=delta,
        )
    except Exception as exc:
        return handle_tool_exception(
            exc, "compare_steps_to_baseline_tool", {"window_days": window_days}
        )


# ============================================================================
# HEART RATE TOOLS
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_heart_rate_summary",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_heart_rate_summary_tool(
    time_min: Annotated[
        str | None, "Start of search window (ISO 8601). Defaults to today 00:00 UTC."
    ] = None,
    time_max: Annotated[
        str | None, "End of search window (ISO 8601). Defaults to now (UTC)."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Return the user's average, min, and max heart rate over a time window.

    Use this when the user asks "what is my average heart rate today /
    this week?". The planner should pass ISO 8601 bounds derived from
    the resolved temporal reference. Returns avg/min/max bpm plus
    freshness metadata.
    """
    config = validate_runtime_config(runtime, "get_heart_rate_summary_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    parsed_min = _parse_iso_ts(time_min, param="time_min")
    parsed_max = _parse_iso_ts(time_max, param="time_max")
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            summary = await service.compute_kind_summary(
                user_id, "heart_rate", time_min=parsed_min, time_max=parsed_max
            )

        if summary.get("avg") is None:
            return UnifiedToolOutput.data_success(
                message="No heart rate data for the requested window.",
                structured_data=summary,
            )
        return UnifiedToolOutput.data_success(
            message=(
                f"Heart rate avg {summary['avg']} bpm "
                f"(min {summary['min']}, max {summary['max']})."
            ),
            structured_data=summary,
        )
    except Exception as exc:
        return handle_tool_exception(
            exc,
            "get_heart_rate_summary_tool",
            {"time_min": time_min, "time_max": time_max},
        )


@tool
@track_tool_metrics(
    tool_name="compare_heart_rate_to_baseline",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def compare_heart_rate_to_baseline_tool(
    window_days: Annotated[
        int,
        "Recent window length in days to compare against the 28-day baseline. Defaults to 7.",
    ] = 7,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Compare the user's recent heart-rate average to their rolling baseline.

    Returns the baseline mode (``bootstrap`` / ``rolling``), the baseline
    value, the recent window value, and the signed percent delta.
    """
    config = validate_runtime_config(runtime, "compare_heart_rate_to_baseline_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    window = max(1, min(HEALTH_METRICS_BASELINE_WINDOW_MAX_DAYS, int(window_days)))
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            delta: dict[str, Any] = await service.compute_kind_baseline_delta(
                user_id, "heart_rate", window_days=window
            )

        if delta["mode"] == "empty":
            return UnifiedToolOutput.data_success(
                message="No heart rate history to compute a baseline yet.",
                structured_data=delta,
            )
        return UnifiedToolOutput.data_success(
            message=(
                f"Heart rate {window}-day avg {delta['window_value']} bpm vs baseline "
                f"{delta['baseline_value']} ({_format_delta_pct(delta['delta_pct'])}, "
                f"mode={delta['mode']})."
            ),
            structured_data=delta,
        )
    except Exception as exc:
        return handle_tool_exception(
            exc, "compare_heart_rate_to_baseline_tool", {"window_days": window_days}
        )


# ============================================================================
# CROSS-KIND TOOLS
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_health_overview",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_health_overview_tool(
    time_min: Annotated[
        str | None, "Start of search window (ISO 8601). Defaults to today 00:00 UTC."
    ] = None,
    time_max: Annotated[
        str | None, "End of search window (ISO 8601). Defaults to now (UTC)."
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Return a kind-by-kind summary of the user's health data for a time window.

    Use this when the user asks "show me my health overview" or "how is
    my health today?". The planner should pass ISO 8601 bounds derived
    from the resolved temporal reference. Emits one entry per registered
    kind (steps, heart_rate, and any future additions).
    """
    config = validate_runtime_config(runtime, "get_health_overview_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    parsed_min = _parse_iso_ts(time_min, param="time_min")
    parsed_max = _parse_iso_ts(time_max, param="time_max")
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            overview = await service.compute_overview(
                user_id, time_min=parsed_min, time_max=parsed_max
            )

        kinds_with_data = [k for k, v in overview.items() if v.get("samples_count", 0) > 0]
        payload = {"overview": overview}
        if not kinds_with_data:
            return UnifiedToolOutput.data_success(
                message="No health data yet for the requested window.",
                structured_data=payload,
            )
        # Inline each kind's aggregate into the message so the Response LLM
        # can surface factual figures (total steps, avg bpm, etc.) without
        # having to reach for the structured_data payload.
        summaries: list[str] = []
        for kind in kinds_with_data:
            data = overview[kind]
            if data.get("total") is not None:
                summaries.append(f"{kind}: total {data['total']} {data.get('unit', '')}")
            elif data.get("avg") is not None:
                summaries.append(
                    f"{kind}: avg {data['avg']} {data.get('unit', '')} "
                    f"(min {data.get('min')}, max {data.get('max')})"
                )
            elif data.get("last") is not None:
                summaries.append(f"{kind}: last {data['last']} {data.get('unit', '')}")
        return UnifiedToolOutput.data_success(
            message="Health overview — " + "; ".join(s.strip() for s in summaries) + ".",
            structured_data=payload,
        )
    except Exception as exc:
        return handle_tool_exception(
            exc,
            "get_health_overview_tool",
            {"time_min": time_min, "time_max": time_max},
        )


@tool
@track_tool_metrics(
    tool_name="detect_health_changes",
    agent_name=AGENT_HEALTH,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def detect_health_changes_tool(
    window_days: Annotated[
        int,
        "Recent window length in days to inspect for notable variations. Defaults to 7.",
    ] = 7,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Detect notable recent variations and structural events across all kinds.

    Returns a list of variation entries (rising/falling streaks over the
    configured threshold) plus structural events (e.g. inactivity streaks
    on steps). Empty list when nothing is notable.

    Use this when the user asks "has anything changed in my health
    recently?" or "am I doing better this week?".
    """
    config = validate_runtime_config(runtime, "detect_health_changes_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)
    window = max(1, min(HEALTH_METRICS_BASELINE_WINDOW_MAX_DAYS, int(window_days)))
    try:
        async with get_db_context() as db:
            gate = await _check_user_toggle_or_error(db, user_id)
            if gate is not None:
                return gate
            from src.domains.health_metrics.service import HealthMetricsService

            service = HealthMetricsService(db)
            variations = await service.detect_all_variations(user_id, window_days=window)

        if not variations:
            return UnifiedToolOutput.data_success(
                message=f"No notable health variations detected over the last {window} days.",
                structured_data={"window_days": window, "variations": []},
            )
        # Inline each variation in the message (pattern weather_tools).
        entries: list[str] = []
        for v in variations:
            kind = v.get("kind", "?")
            if "trend" in v:
                entries.append(
                    f"{kind} {v.get('trend')} for {v.get('days')}d "
                    f"({_format_delta_pct(v.get('delta_pct'))})"
                )
            elif "event" in v:
                entries.append(f"{kind} event={v.get('event')} ({v.get('days')}d)")
        # Defensive: if none of the variations matched the expected shapes,
        # surface the count without a dangling separator.
        suffix = f" — {'; '.join(entries)}" if entries else ""
        return UnifiedToolOutput.data_success(
            message=(
                f"Detected {len(variations)} notable change(s) over the last "
                f"{window} days{suffix}."
            ),
            structured_data={"window_days": window, "variations": variations},
        )
    except Exception as exc:
        return handle_tool_exception(
            exc, "detect_health_changes_tool", {"window_days": window_days}
        )
