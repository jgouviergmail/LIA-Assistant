"""Bounded vocabularies for the product analytics domain (ADR-178).

Every label exported to Prometheus and every enum-like column value MUST come
from these registries. Boot-time completeness asserts (ADR-085 doctrine) keep
the descriptions in sync with the vocabulary — an unknown value fails loudly
instead of silently creating an unbounded series.
"""

from enum import StrEnum

from src.core.constants import SCHEDULED_ACTIONS_SESSION_PREFIX

# ---------------------------------------------------------------------------
# Result vocabulary (spec §4 — normative value model)
# ---------------------------------------------------------------------------

RESULT_TYPES: frozenset[str] = frozenset(
    {
        "answer",
        "action",
        "preparation",
        "artifact",
        "automation_run",
        "proactive_item",
        "project_progress",
    }
)

EVIDENCE_LEVELS: frozenset[str] = frozenset({"E1", "E2", "E3"})

#: Canonical outcome states. ``corrected`` / ``reverted`` are orthogonal flags.
OUTCOME_STATES: frozenset[str] = frozenset({"produced", "validated", "rejected"})

#: v1 channels derivable server-side without new capture. ``voice`` / ``pwa`` /
#: ``channel`` (Telegram) join when their entry points carry attribution
#: (program spec, correction #4 dropped the nonexistent ``direct``).
#: ``web_showroom`` marks credential-less public-showroom rows (P0 program).
CHANNELS: frozenset[str] = frozenset({"web", "scheduler", "unknown", "web_showroom"})

DEVICE_CLASSES: frozenset[str] = frozenset({"mobile", "desktop", "unknown"})

# ---------------------------------------------------------------------------
# Gauge label bounds (metrics_product.py) — keep tiny, cardinality is a budget
# ---------------------------------------------------------------------------

GAUGE_WINDOWS: tuple[str, ...] = ("7d", "30d")
RETENTION_PERIODS: tuple[str, ...] = ("D1", "D7", "D30")
FUNNEL_STAGES: tuple[str, ...] = ("registered", "technical_result", "useful_result")
DATA_QUALITY_CHECKS: tuple[str, ...] = (
    "outcomes_with_domain",
    "outcomes_with_cost",
    "events_with_run",
)
PRODUCT_REFRESH_JOB: str = "product_rollup"

#: Evidence selector values for user-count gauges ("any" = E1 or E2).
USEFUL_EVIDENCE_SELECTORS: tuple[str, ...] = ("any", "E1", "E2")


class ProductEventType(StrEnum):
    """Lifecycle + client events recorded in ``product_events`` (bounded log)."""

    OUTCOME_PRODUCED = "outcome_produced"
    OUTCOME_VALIDATED = "outcome_validated"
    OUTCOME_REJECTED = "outcome_rejected"
    # Client funnel events (Phase 4) — DB rows, user nullable for pre-auth.
    LANDING_VIEW = "landing_view"
    SIGNUP_STARTED = "signup_started"
    DEMO_STARTED = "demo_started"
    DEMO_COMPLETED = "demo_completed"
    PWA_INSTALL_PROMPT = "pwa_install_prompt"
    PWA_INSTALLED = "pwa_installed"
    # Public showroom funnel (P0 program) — credential-less collector ONLY.
    # DEMO_COMPLETED moved to this vocabulary: it was declared on the ordinary
    # route but never emitted there (audited 2026-08-06), so the move breaks no
    # producer while keeping the two vocabularies strictly disjoint.
    DEMO_VIEWED = "demo_viewed"
    DEMO_MISSION_STARTED = "demo_mission_started"
    DEMO_FIRST_HITL_DECIDED = "demo_first_hitl_decided"
    DEMO_HITL_CONFIRM = "demo_hitl_confirm"
    DEMO_HITL_EDIT = "demo_hitl_edit"
    DEMO_HITL_CANCEL = "demo_hitl_cancel"
    DEMO_FIRST_PROOF_OPENED = "demo_first_proof_opened"
    DEMO_SOURCE_CLICKED = "demo_source_clicked"
    DEMO_RELEASE_CLICKED = "demo_release_clicked"
    DEMO_INSTALL_GUIDE_CLICKED = "demo_install_guide_clicked"
    # Per-mission breakdown (multi-mission showroom): which mission engages
    # and which converts. Aggregate DEMO_MISSION_STARTED / DEMO_COMPLETED
    # keep firing unchanged; these add the bounded mission dimension without
    # a free-text property (the collector stays enum-only by construction).
    DEMO_MISSION_STARTED_OVERLOADED_MORNING = "demo_mission_started_overloaded_morning"
    DEMO_MISSION_STARTED_PROACTIVE_ALERT = "demo_mission_started_proactive_alert"
    DEMO_MISSION_STARTED_MEMORY_DINNER = "demo_mission_started_memory_dinner"
    DEMO_MISSION_STARTED_PHONE_BOOKING = "demo_mission_started_phone_booking"
    DEMO_MISSION_STARTED_DAILY_BRIEFING = "demo_mission_started_daily_briefing"
    DEMO_MISSION_STARTED_CONFIG_TOUR = "demo_mission_started_config_tour"
    DEMO_COMPLETED_OVERLOADED_MORNING = "demo_completed_overloaded_morning"
    DEMO_COMPLETED_PROACTIVE_ALERT = "demo_completed_proactive_alert"
    DEMO_COMPLETED_MEMORY_DINNER = "demo_completed_memory_dinner"
    DEMO_COMPLETED_PHONE_BOOKING = "demo_completed_phone_booking"
    DEMO_COMPLETED_DAILY_BRIEFING = "demo_completed_daily_briefing"
    DEMO_COMPLETED_CONFIG_TOUR = "demo_completed_config_tour"


#: Human descriptions per event type — completeness asserted at import
#: (ADR-085): adding an event type without describing it fails the boot.
PRODUCT_EVENT_DESCRIPTIONS: dict[ProductEventType, str] = {
    ProductEventType.OUTCOME_PRODUCED: "A result was produced and presented (E3).",
    ProductEventType.OUTCOME_VALIDATED: "A result was validated (E1 feedback or E2 window).",
    ProductEventType.OUTCOME_REJECTED: "A result received explicit negative feedback.",
    ProductEventType.LANDING_VIEW: "Public landing page viewed (anonymous allowed).",
    ProductEventType.SIGNUP_STARTED: "Signup form interaction started (anonymous allowed).",
    ProductEventType.DEMO_STARTED: "Public demo started (anonymous allowed).",
    ProductEventType.DEMO_COMPLETED: "Guided mission first reached its receipt (showroom).",
    ProductEventType.PWA_INSTALL_PROMPT: "PWA install prompt shown (arbitration c).",
    ProductEventType.PWA_INSTALLED: "PWA installed (arbitration c).",
    ProductEventType.DEMO_VIEWED: "Showroom demo page mounted (non-attributed attempt).",
    ProductEventType.DEMO_MISSION_STARTED: "Guided mission explicitly started (per run).",
    ProductEventType.DEMO_FIRST_HITL_DECIDED: "First accepted HITL decision of a run.",
    ProductEventType.DEMO_HITL_CONFIRM: "A showroom decision was confirmed (action mix).",
    ProductEventType.DEMO_HITL_EDIT: "The showroom email decision was edited (action mix).",
    ProductEventType.DEMO_HITL_CANCEL: "A showroom decision was refused (action mix).",
    ProductEventType.DEMO_FIRST_PROOF_OPENED: "Proof drawer first opened after completion.",
    ProductEventType.DEMO_SOURCE_CLICKED: "Source CTA outbound attempt after completion.",
    ProductEventType.DEMO_RELEASE_CLICKED: "Release CTA outbound attempt after completion.",
    ProductEventType.DEMO_INSTALL_GUIDE_CLICKED: "Install-guide CTA outbound attempt.",
    ProductEventType.DEMO_MISSION_STARTED_OVERLOADED_MORNING: (
        "Overloaded-morning mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_MISSION_STARTED_PROACTIVE_ALERT: (
        "Proactive-alert mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_MISSION_STARTED_MEMORY_DINNER: (
        "Memory-dinner mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_MISSION_STARTED_PHONE_BOOKING: (
        "Phone-booking mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_MISSION_STARTED_DAILY_BRIEFING: (
        "Daily-briefing mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_MISSION_STARTED_CONFIG_TOUR: (
        "Config-tour mission started (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_OVERLOADED_MORNING: (
        "Overloaded-morning mission reached its receipt (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_PROACTIVE_ALERT: (
        "Proactive-alert mission reached its receipt (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_MEMORY_DINNER: (
        "Memory-dinner mission reached its receipt (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_PHONE_BOOKING: (
        "Phone-booking mission reached its receipt (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_DAILY_BRIEFING: (
        "Daily-briefing mission reached its receipt (per-mission breakdown)."
    ),
    ProductEventType.DEMO_COMPLETED_CONFIG_TOUR: (
        "Config-tour mission reached its receipt (per-mission breakdown)."
    ),
}

#: Client-ingestable event types (the ONLY values POST /product/events accepts
#: as funnel events — outcome lifecycle events are server-emitted only).
#: DEMO_COMPLETED left this registry for SHOWROOM_EVENT_TYPES (P0 program):
#: it was declared here but never emitted, and the two vocabularies must stay
#: disjoint so the showroom funnel cannot be polluted through this route.
CLIENT_EVENT_TYPES: frozenset[ProductEventType] = frozenset(
    {
        ProductEventType.LANDING_VIEW,
        ProductEventType.SIGNUP_STARTED,
        ProductEventType.DEMO_STARTED,
        ProductEventType.PWA_INSTALL_PROMPT,
        ProductEventType.PWA_INSTALLED,
    }
)

#: Subset accepted WITHOUT a session (arbitration a — pre-signup funnel).
ANONYMOUS_EVENT_TYPES: frozenset[ProductEventType] = frozenset(
    {
        ProductEventType.LANDING_VIEW,
        ProductEventType.SIGNUP_STARTED,
        ProductEventType.DEMO_STARTED,
    }
)

#: Showroom funnel accepted ONLY by the credential-less collector
#: (POST /product/showroom-events). Guarded disjoint from the two ordinary
#: registries by test_showroom_telemetry.py.
#: Bounded mission identifiers of the multi-mission guided showroom. The
#: frontend registry mirrors this tuple (guarded on both sides); a mission id
#: exists here IFF its two per-mission events exist in the vocabulary below.
SHOWROOM_MISSION_IDS: tuple[str, ...] = (
    "overloaded_morning",
    "proactive_alert",
    "memory_dinner",
    "phone_booking",
    "daily_briefing",
    "config_tour",
)

SHOWROOM_EVENT_TYPES: frozenset[ProductEventType] = frozenset(
    {
        ProductEventType.DEMO_VIEWED,
        ProductEventType.DEMO_MISSION_STARTED,
        ProductEventType.DEMO_FIRST_HITL_DECIDED,
        ProductEventType.DEMO_HITL_CONFIRM,
        ProductEventType.DEMO_HITL_EDIT,
        ProductEventType.DEMO_HITL_CANCEL,
        ProductEventType.DEMO_COMPLETED,
        ProductEventType.DEMO_FIRST_PROOF_OPENED,
        ProductEventType.DEMO_SOURCE_CLICKED,
        ProductEventType.DEMO_RELEASE_CLICKED,
        ProductEventType.DEMO_INSTALL_GUIDE_CLICKED,
    }
    | {ProductEventType(f"demo_mission_started_{m}") for m in SHOWROOM_MISSION_IDS}
    | {ProductEventType(f"demo_completed_{m}") for m in SHOWROOM_MISSION_IDS}
)

#: Bounded Web Vitals vocabulary (Phase 4). Seconds-valued vs ratio-valued
#: metrics feed two distinct histogram families. INP deferred (documented).
WEB_VITAL_SECONDS_METRICS: frozenset[str] = frozenset({"lcp"})
WEB_VITAL_RATIO_METRICS: frozenset[str] = frozenset({"cls"})

#: Bounded search telemetry vocabulary (SEA-*, Phase 4).
SEARCH_SURFACES: frozenset[str] = frozenset({"settings"})
SEARCH_OUTCOMES: frozenset[str] = frozenset({"results", "zero_results", "result_used"})


def assert_product_registries_complete() -> None:
    """Fail loudly when a vocabulary and its registry drift apart.

    Raises:
        RuntimeError: If an event type has no description entry.
    """
    missing = [e.value for e in ProductEventType if e not in PRODUCT_EVENT_DESCRIPTIONS]
    if missing:
        raise RuntimeError(f"PRODUCT_EVENT_DESCRIPTIONS missing entries: {missing}")


assert_product_registries_complete()

# ---------------------------------------------------------------------------
# Bounded derivations (no new capture — ADR-144 minimization)
# ---------------------------------------------------------------------------

_MOBILE_OS_FAMILIES = frozenset({"android", "ios"})
_DESKTOP_OS_FAMILIES = frozenset({"windows", "macos", "linux"})


def derive_device_class(os_family: str | None) -> str:
    """Map a bounded session ``os_family`` (ADR-144) to a device class.

    Tablets are not distinguished (signed-off decision #3 — no new client
    capture; iPadOS reports as ios → mobile).

    Args:
        os_family: Coarse OS family from ``core.client_metadata``.

    Returns:
        One of ``DEVICE_CLASSES``.
    """
    if os_family in _MOBILE_OS_FAMILIES:
        return "mobile"
    if os_family in _DESKTOP_OS_FAMILIES:
        return "desktop"
    return "unknown"


def derive_channel(session_id: str | None) -> str:
    """Derive the outcome channel from existing session attribution.

    Args:
        session_id: The run's session identifier.

    Returns:
        One of ``CHANNELS`` — ``scheduler`` for automated scheduled-action
        sessions (existing prefix convention), ``web`` otherwise.
    """
    if not session_id:
        return "unknown"
    if session_id.startswith(SCHEDULED_ACTIONS_SESSION_PREFIX):
        return "scheduler"
    return "web"


#: Router intention marking an actionable (tool-using) turn. The router node
#: emits ``"action"`` (``INTENTION_ACTION`` in ``domains.agents.constants``);
#: the string is duplicated here because a runtime agents import would create
#: the agents<->product cycle the coupling ratchet forbids. Pinned on both
#: sides by ``test_product_constants.py::test_router_vocabulary_contract``.
#: (Until 2026-08-16 this compared against ``"actionable"``, a value no router
#: ever emitted — every chat run was recorded as ``answer`` and the dashboard
#: "actions" tile stayed at zero.)
_ACTIONABLE_INTENTION = "action"


def derive_result_type(intention: str | None, channel: str) -> str:
    """v1 result-type approximation from routing intention and channel.

    Documented in the program spec: scheduler runs are ``automation_run``,
    actionable turns are ``action``, everything else is ``answer``. Finer
    types (artifact, preparation, proactive_item, project_progress) require
    per-surface instrumentation (later lots).

    Args:
        intention: Router intention persisted in the assistant message
            metadata (``action`` / ``conversation``), if any.
        channel: A ``CHANNELS`` value (from :func:`derive_channel`).

    Returns:
        One of ``RESULT_TYPES``.
    """
    if channel == "scheduler":
        return "automation_run"
    if intention == _ACTIONABLE_INTENTION:
        return "action"
    return "answer"
