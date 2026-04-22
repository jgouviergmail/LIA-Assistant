"""Catalogue manifests for the Health Metrics agent and tools (v1.17.2).

Single ``health_agent`` owning seven hand-crafted tools (steps, heart
rate, cross-kind overview + change detection). Registered by
:func:`src.domains.agents.registry.catalogue_loader.initialize_catalogue`
behind the ``health_metrics_enabled`` feature flag.

Per-user opt-in is enforced at tool entry via
``_check_user_toggle_or_error`` in ``tools/health_tools.py`` — not at
catalogue level (mirrors the ``user_memory_enabled`` / ``journals_enabled``
pattern).

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from src.domains.agents.constants import AGENT_HEALTH, CONTEXT_DOMAIN_HEALTH_SIGNALS
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# Register the Health Signals context type at module import time.
# The catalogue_loader imports this module before it validates that every
# tool manifest's ``context_key`` is registered, so the registration
# must live here.
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_HEALTH_SIGNALS,
        agent_name=AGENT_HEALTH,
        # No item_schema — these tools return metric dicts (varied shapes
        # per tool). The domain registration exists primarily to satisfy
        # the tool-manifest context_key validator.
        primary_id_field="kind",
        display_name_field="kind",
        reference_fields=["kind", "unit", "from_ts", "to_ts"],
        icon="🩺",
    )
)


# ============================================================================
# Shared parameters
# ============================================================================

_TIME_MIN_PARAM = ParameterSchema(
    name="time_min",
    type="string",
    required=False,
    description="Start of search window (ISO 8601).",
)

_TIME_MAX_PARAM = ParameterSchema(
    name="time_max",
    type="string",
    required=False,
    description="End of search window (ISO 8601).",
)

_DAYS_PARAM = ParameterSchema(
    name="days",
    type="integer",
    required=False,
    description="Window length in days (1-30). Default 7.",
    constraints=[
        ParameterConstraint(kind="minimum", value=1),
        ParameterConstraint(kind="maximum", value=30),
    ],
)

_WINDOW_DAYS_PARAM = ParameterSchema(
    name="window_days",
    type="integer",
    required=False,
    description=(
        "Recent window length in days (1-14) to compare against the 28-day baseline. Default 7."
    ),
    constraints=[
        ParameterConstraint(kind="minimum", value=1),
        ParameterConstraint(kind="maximum", value=14),
    ],
)

_BASELINE_OUTPUTS = [
    OutputFieldSchema(path="kind", type="string", description="Kind discriminator"),
    OutputFieldSchema(path="unit", type="string", description="Unit label (bpm, steps...)"),
    OutputFieldSchema(
        path="mode", type="string", description="Baseline mode: empty / bootstrap / rolling"
    ),
    OutputFieldSchema(path="baseline_value", type="number", description="Median baseline value"),
    OutputFieldSchema(path="window_value", type="number", description="Recent window aggregate"),
    OutputFieldSchema(path="delta_pct", type="number", description="Signed delta in %"),
]


# ============================================================================
# Tool manifests (7 tools, all owned by health_agent)
# ============================================================================

get_steps_summary_catalogue_manifest = ToolManifest(
    name="get_steps_summary_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: get_steps_summary_tool** — Total step count for a time window.\n"
        "Returns the sum of steps between ``time_min`` and ``time_max`` "
        "(ISO 8601), plus freshness metadata (last sample timestamp, sample count).\n"
        "**Use for**: 'How many steps today?', 'Combien de pas cette semaine ?'.\n"
        "**Output**: `{kind, unit, total, samples_count, last_sample_at, from_ts, to_ts}`."
    ),
    semantic_keywords=[
        "how many steps today",
        "combien de pas cette semaine",
        "nombre de pas ce mois",
        "daily steps count",
        "total steps over a date range",
    ],
    parameters=[_TIME_MIN_PARAM, _TIME_MAX_PARAM],
    outputs=[
        OutputFieldSchema(path="kind", type="string", description="'steps'"),
        OutputFieldSchema(path="total", type="integer", description="Total steps (period)"),
        OutputFieldSchema(
            path="samples_count", type="integer", description="Number of raw samples"
        ),
        OutputFieldSchema(path="last_sample_at", type="string", description="ISO timestamp"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=150, est_cost_usd=0.0005, est_latency_ms=200),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="👟", i18n_key="get_steps_summary", visible=True, category="tool"
    ),
)

get_steps_daily_breakdown_catalogue_manifest = ToolManifest(
    name="get_steps_daily_breakdown_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: get_steps_daily_breakdown_tool** — Per-day step totals over N days.\n"
        "Returns one entry per day that has data, sorted ascending.\n"
        "**Use for**: 'Show my steps day by day', 'Evolution on the last 10 days'.\n"
        "**Output**: `{days: [{date, value}, ...], window}`."
    ),
    semantic_keywords=[
        "steps day by day",
        "évolution des pas sur la semaine",
        "steps breakdown by day",
        "steps trend over days",
    ],
    parameters=[_DAYS_PARAM],
    outputs=[
        OutputFieldSchema(path="days", type="array", description="Per-day entries"),
        OutputFieldSchema(path="window", type="integer", description="Window length (days)"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=250, est_cost_usd=0.0007, est_latency_ms=250),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📊", i18n_key="get_steps_daily_breakdown", visible=True, category="tool"
    ),
)

compare_steps_to_baseline_catalogue_manifest = ToolManifest(
    name="compare_steps_to_baseline_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: compare_steps_to_baseline_tool** — Delta vs the user's rolling baseline.\n"
        "Returns the baseline mode (bootstrap < 7 days / rolling ≥ 7 days), "
        "the baseline value, the recent window value, and the signed percent delta.\n"
        "**Use for**: 'Am I walking less than usual?', 'Par rapport à ma moyenne ?'.\n"
        "**Output**: `{kind, unit, mode, baseline_value, window_value, delta_pct, window_days}`."
    ),
    semantic_keywords=[
        "steps compared to baseline",
        "marcher moins que d'habitude",
        "am I walking more than usual",
        "baseline vs recent steps",
    ],
    parameters=[_WINDOW_DAYS_PARAM],
    outputs=_BASELINE_OUTPUTS,
    cost=CostProfile(est_tokens_in=80, est_tokens_out=200, est_cost_usd=0.0006, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📉", i18n_key="compare_steps_to_baseline", visible=True, category="tool"
    ),
)

get_heart_rate_summary_catalogue_manifest = ToolManifest(
    name="get_heart_rate_summary_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: get_heart_rate_summary_tool** — Heart rate avg/min/max for a time window.\n"
        "Returns the average, min, and max bpm between ``time_min`` and ``time_max`` "
        "(ISO 8601), plus freshness.\n"
        "**Use for**: 'What's my average heart rate today?', 'Fréquence cardiaque cette semaine'.\n"
        "**Output**: `{kind, unit, avg, min, max, samples_count, last_sample_at, from_ts, to_ts}`."
    ),
    semantic_keywords=[
        "average heart rate today",
        "fréquence cardiaque moyenne",
        "bpm over a date range",
        "resting pulse this month",
    ],
    parameters=[_TIME_MIN_PARAM, _TIME_MAX_PARAM],
    outputs=[
        OutputFieldSchema(path="kind", type="string", description="'heart_rate'"),
        OutputFieldSchema(path="avg", type="number", description="Average bpm"),
        OutputFieldSchema(path="min", type="integer", description="Min bpm"),
        OutputFieldSchema(path="max", type="integer", description="Max bpm"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=180, est_cost_usd=0.0005, est_latency_ms=200),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="❤️", i18n_key="get_heart_rate_summary", visible=True, category="tool"
    ),
)

compare_heart_rate_to_baseline_catalogue_manifest = ToolManifest(
    name="compare_heart_rate_to_baseline_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: compare_heart_rate_to_baseline_tool** — Delta vs the user's baseline HR.\n"
        "Returns baseline mode, baseline value, recent window value, and signed delta.\n"
        "**Use for**: 'Is my heart rate higher than usual?', 'FC vs ma moyenne'.\n"
        "**Output**: `{kind, unit, mode, baseline_value, window_value, delta_pct, window_days}`."
    ),
    semantic_keywords=[
        "heart rate compared to baseline",
        "fc plus élevée que d'habitude",
        "pulse trend vs average",
    ],
    parameters=[_WINDOW_DAYS_PARAM],
    outputs=_BASELINE_OUTPUTS,
    cost=CostProfile(est_tokens_in=80, est_tokens_out=200, est_cost_usd=0.0006, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📈", i18n_key="compare_heart_rate_to_baseline", visible=True, category="tool"
    ),
)

get_health_overview_catalogue_manifest = ToolManifest(
    name="get_health_overview_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: get_health_overview_tool** — Kind-by-kind summary for a time window.\n"
        "Cross-kind aggregation between ``time_min`` and ``time_max`` (ISO 8601): "
        "emits one summary entry per registered kind (steps, heart_rate, and any future additions).\n"
        "**Use for**: 'How's my health today?', 'Résume ma santé cette semaine'.\n"
        "**Output**: `{from_ts, to_ts, overview: {kind: {...}}}`."
    ),
    semantic_keywords=[
        "overall health today",
        "résumé santé de la semaine",
        "health summary",
        "état santé global",
    ],
    parameters=[_TIME_MIN_PARAM, _TIME_MAX_PARAM],
    outputs=[
        OutputFieldSchema(path="from_ts", type="string", description="Window start (ISO)"),
        OutputFieldSchema(path="to_ts", type="string", description="Window end (ISO)"),
        OutputFieldSchema(path="overview", type="object", description="Per-kind summary dict"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=400, est_cost_usd=0.0009, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🩺", i18n_key="get_health_overview", visible=True, category="tool"
    ),
)

detect_health_changes_catalogue_manifest = ToolManifest(
    name="detect_health_changes_tool",
    agent=AGENT_HEALTH,
    description=(
        "**Tool: detect_health_changes_tool** — Notable recent variations across kinds.\n"
        "Returns directional streaks (rising/falling over ≥ 3 days with ≥ 20% avg delta) "
        "and structural events (e.g. inactivity streak on steps).\n"
        "**Use for**: 'Has anything changed in my health recently?', 'Quelque chose d'inhabituel ?'.\n"
        "**Output**: `{window_days, variations: [{kind, trend/event, days, delta_pct?}, ...]}`."
    ),
    semantic_keywords=[
        "anything unusual in my health",
        "changes in my health",
        "quelque chose change dans ma santé",
        "notable variations",
    ],
    parameters=[_WINDOW_DAYS_PARAM],
    outputs=[
        OutputFieldSchema(path="variations", type="array", description="Variation/event entries"),
        OutputFieldSchema(path="window_days", type="integer", description="Window length"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=350, est_cost_usd=0.0008, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    context_key="health_signals",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🔍", i18n_key="detect_health_changes", visible=True, category="tool"
    ),
)


# ============================================================================
# Agent manifest (single health_agent owning all 7 tools)
# ============================================================================

HEALTH_AGENT_MANIFEST = AgentManifest(
    name=AGENT_HEALTH,
    description=(
        "Agent spécialisé dans les données de santé ingérées depuis l'iPhone : "
        "pas (steps) et fréquence cardiaque (heart_rate). "
        "Totaux par période, évolution jour par jour, comparaison à la baseline, "
        "vue d'ensemble multi-kinds et détection de variations notables. "
        "Répond avec des chiffres factuels uniquement. "
        "Jamais de diagnostic — rappelle au médecin si l'utilisateur demande un avis médical."
    ),
    tools=[
        "get_steps_summary_tool",
        "get_steps_daily_breakdown_tool",
        "compare_steps_to_baseline_tool",
        "get_heart_rate_summary_tool",
        "compare_heart_rate_to_baseline_tool",
        "get_health_overview_tool",
        "detect_health_changes_tool",
    ],
    max_parallel_runs=2,
    default_timeout_ms=5000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
)


HEALTH_AGENT_MANIFESTS = [HEALTH_AGENT_MANIFEST]

HEALTH_TOOL_MANIFESTS = [
    get_steps_summary_catalogue_manifest,
    get_steps_daily_breakdown_catalogue_manifest,
    compare_steps_to_baseline_catalogue_manifest,
    get_heart_rate_summary_catalogue_manifest,
    compare_heart_rate_to_baseline_catalogue_manifest,
    get_health_overview_catalogue_manifest,
    detect_health_changes_catalogue_manifest,
]
