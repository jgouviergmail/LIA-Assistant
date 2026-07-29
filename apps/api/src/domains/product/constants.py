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
CHANNELS: frozenset[str] = frozenset({"web", "scheduler", "unknown"})

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


#: Human descriptions per event type — completeness asserted at import
#: (ADR-085): adding an event type without describing it fails the boot.
PRODUCT_EVENT_DESCRIPTIONS: dict[ProductEventType, str] = {
    ProductEventType.OUTCOME_PRODUCED: "A result was produced and presented (E3).",
    ProductEventType.OUTCOME_VALIDATED: "A result was validated (E1 feedback or E2 window).",
    ProductEventType.OUTCOME_REJECTED: "A result received explicit negative feedback.",
    ProductEventType.LANDING_VIEW: "Public landing page viewed (anonymous allowed).",
    ProductEventType.SIGNUP_STARTED: "Signup form interaction started (anonymous allowed).",
    ProductEventType.DEMO_STARTED: "Public demo started (anonymous allowed).",
    ProductEventType.DEMO_COMPLETED: "Public demo watched to the end (anonymous allowed).",
    ProductEventType.PWA_INSTALL_PROMPT: "PWA install prompt shown (arbitration c).",
    ProductEventType.PWA_INSTALLED: "PWA installed (arbitration c).",
}

#: Client-ingestable event types (the ONLY values POST /product/events accepts
#: as funnel events — outcome lifecycle events are server-emitted only).
CLIENT_EVENT_TYPES: frozenset[ProductEventType] = frozenset(
    {
        ProductEventType.LANDING_VIEW,
        ProductEventType.SIGNUP_STARTED,
        ProductEventType.DEMO_STARTED,
        ProductEventType.DEMO_COMPLETED,
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
        ProductEventType.DEMO_COMPLETED,
    }
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


def derive_result_type(intention: str | None, channel: str) -> str:
    """v1 result-type approximation from routing intention and channel.

    Documented in the program spec: scheduler runs are ``automation_run``,
    actionable turns are ``action``, everything else is ``answer``. Finer
    types (artifact, preparation, proactive_item, project_progress) require
    per-surface instrumentation (later lots).

    Args:
        intention: Router intention persisted in the assistant message
            metadata (e.g. ``conversation`` / ``actionable``), if any.
        channel: A ``CHANNELS`` value (from :func:`derive_channel`).

    Returns:
        One of ``RESULT_TYPES``.
    """
    if channel == "scheduler":
        return "automation_run"
    if intention == "actionable":
        return "action"
    return "answer"
