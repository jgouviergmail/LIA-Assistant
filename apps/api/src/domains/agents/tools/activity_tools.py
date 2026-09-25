"""Activity tool — what LIA did and consulted for the person (ADR-318).

« What did you do for me this week? », « did you send it? », « what did you do
on your own? » — the answers are in LIA's own registers (ADR-263), and the tool
reads them there rather than letting the model reconstruct them from a
conversation it may no longer hold. It answers with the registers' honesty
(``effects/activity``): the actions listed newest first under a published cap,
the EXACT totals beside them, the reads counted per domain, the authorship split
the tabs use.

The actions are worded in the person's language, from the label the register
recorded (``core/i18n_effects``), exactly as their register screen shows them.
Read-only, no HITL, no OAuth; the logs carry counts only.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.i18n_effects import render_effect_label
from src.core.i18n_treatments import render_treatment_domain
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.activity.catalogue_manifests import (
    ACTIVITY_END_DESCRIPTION,
    ACTIVITY_MAX_RESULTS_DESCRIPTION,
    ACTIVITY_ORIGIN_DESCRIPTION,
    ACTIVITY_START_DESCRIPTION,
    ACTIVITY_STATUS_DESCRIPTION,
    ActivityOrigin,
    ActivityStatus,
)
from src.domains.agents.constants import AGENT_ACTIVITY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.effects.activity import ActivityReport, read_activity
from src.domains.agents.effects.labels import readable_label
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.lookup_parameters import bounded_count, read_period
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


def _value(field: object) -> str:
    return str(getattr(field, "value", field))


def _local(moment: datetime, zone: tzinfo) -> str:
    return moment.astimezone(zone).isoformat(timespec="minutes")


def _action_item(row: AgentEffect, language: str, zone: tzinfo) -> dict[str, str | None]:
    """One action as the model reads it — worded as the person's register shows it."""
    key, values = readable_label(row)
    return {
        "when": _local(row.claimed_at, zone),
        "action": render_effect_label({"i18n_key": key, "values": values}, language),
        "capability": row.tool_name,
        "status": _value(row.status),
        "authorship": _value(row.source),
        "error_code": row.error_code,
    }


def _summary(
    report: ActivityReport,
    listed: int,
    period: dict[str, str | None],
    outcome: EffectStatus | None,
) -> str:
    """One technical English sentence stating every figure, and what was left out.

    The per-outcome breakdown covers every outcome of the period while the total
    follows the outcome filter: with a filter, the sentence names which total it
    states — « 1 action(s) (2 succeeded, 1 failed) » read as a contradiction.
    """
    outcomes = ", ".join(f"{count} {status}" for status, count in report.actions_by_status.items())
    breakdown = f" ({outcomes})" if outcomes else ""
    if outcome is None:
        actions = f"{report.actions_total} action(s) in the period{breakdown}"
    else:
        every = sum(report.actions_by_status.values())
        actions = (
            f"{report.actions_total} {outcome.value} action(s) out of {every} in the "
            f"period{breakdown}"
        )
    text = (
        f"From {period['from']} to {period['to']} ({period['timezone']}): {actions}; "
        f"{report.consultations_total} consultation(s) across "
        f"{len(report.consultations_by_domain)} kind(s) of data."
    )
    if listed < report.actions_total:
        text += (
            f" The {listed} most recent matching actions are listed; the "
            f"{report.actions_total - listed} others are counted, not listed."
        )
    return text


def _filters(
    origin: str | None, status: str | None
) -> tuple[RegisterOrigin, EffectStatus | None] | UnifiedToolOutput:
    """The authorship and the outcome asked for, or the typed refusal."""
    try:
        reading = RegisterOrigin(origin or RegisterOrigin.ALL.value)
        return reading, EffectStatus(status) if status else None
    except ValueError:
        return UnifiedToolOutput.failure(
            message=(
                "Unknown origin or status: origin is "
                f"{', '.join(member.value for member in RegisterOrigin)}; status is "
                f"{', '.join(member.value for member in EffectStatus)}."
            ),
            error_code=ToolErrorCode.INVALID_PARAM_VALUE.value,
        )


def _answer(
    report: ActivityReport,
    filters: tuple[RegisterOrigin, EffectStatus | None],
    language: str,
    zone: tzinfo,
    bounds: tuple[datetime | None, datetime | None],
) -> UnifiedToolOutput:
    """The report as the model reads it: the period, the actions, every exact figure."""
    since, until = bounds
    reading, outcome = filters
    actions = [_action_item(row, language, zone) for row in report.actions]
    period = {
        "from": _local(since, zone) if since else None,
        "to": _local(until, zone) if until else None,
        "timezone": str(zone),
    }
    return UnifiedToolOutput.data_success(
        message=_summary(report, len(actions), period, outcome),
        structured_data={
            "period": period,
            "origin": reading.value,
            "actions": actions,
            "actions_total": report.actions_total,
            "actions_by_status": report.actions_by_status,
            "consultations": [
                {"domain": domain, "label": render_treatment_domain(domain, language), "count": n}
                for domain, n in report.consultations_by_domain.items()
            ],
            "consultations_total": report.consultations_total,
            "count": report.actions_total + report.consultations_total,
        },
    )


@read_tool(name="get_my_activity", agent_name=AGENT_ACTIVITY)
async def get_my_activity_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    start_date: Annotated[str | None, ACTIVITY_START_DESCRIPTION] = None,
    end_date: Annotated[str | None, ACTIVITY_END_DESCRIPTION] = None,
    origin: Annotated[ActivityOrigin | None, ACTIVITY_ORIGIN_DESCRIPTION] = None,
    status: Annotated[ActivityStatus | None, ACTIVITY_STATUS_DESCRIPTION] = None,
    max_results: Annotated[int | None, ACTIVITY_MAX_RESULTS_DESCRIPTION] = None,
) -> UnifiedToolOutput:
    """What LIA did and consulted for the user over a period, from its own registers.

    The actions it performed, newest first, with their outcome and who initiated
    them; how many times it read each kind of data. Every total is exact, even
    when the list is shortened.

    Args:
        runtime: LangChain tool runtime (injected).
        start_date: First day of the period (the default window when omitted).
        end_date: Last day of the period, inclusive (now when omitted).
        origin: mine, initiative or all (the default).
        status: Only the actions with this outcome.
        max_results: How many actions to list, clamped to the setting.

    Returns:
        UnifiedToolOutput with the period, the listed actions, the exact totals
        and the reads per kind of data; a typed refusal on an unreadable period.
    """
    config = validate_runtime_config(runtime, "get_my_activity_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    context = tool_runtime_context(runtime)
    zone = resolve_user_timezone(context)
    period = read_period(
        start_date,
        end_date,
        zone,
        now=datetime.now(UTC),
        default_days=settings.effect_activity_window_days,
    )
    if isinstance(period, UnifiedToolOutput):
        return period
    filters = _filters(origin, status)
    if isinstance(filters, UnifiedToolOutput):
        return filters

    since, until = period
    reading, outcome = filters
    limit = bounded_count(max_results, settings.effect_activity_max_actions)
    user_id = UUID(str(config.user_id))
    async with get_db_context() as db:
        report = await read_activity(
            db, user_id, since=since, until=until, origin=reading, status=outcome, limit=limit
        )
    logger.info(
        "activity_tool_completed",
        user_id=str(user_id),
        actions_total=report.actions_total,
        listed=len(report.actions),
        consultations_total=report.consultations_total,
    )
    language = context.language if context is not None else settings.default_language
    return _answer(report, filters, language, zone, (since, until))


__all__ = ["get_my_activity_tool"]
