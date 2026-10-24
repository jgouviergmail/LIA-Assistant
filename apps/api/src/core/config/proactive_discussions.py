"""Proactive discussions configuration module (ADR-358, ADR-359, ADR-360).

An independent, opt-in personal initiative. Paid production needs all three
financial ceilings: a missing one closes it (``configured_limits``). Every bound an
operator may want to adjust lives here, its default in ``src.core.constants`` so
that this module never imports the domain. What a model can do (its window, its
output cap, its price) is never configured here: it is read from the configured
slot (ADR-244, ADR-278).
"""

from decimal import Decimal
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    DISCUSSION_ATTENTION_ALERT_GAP_MINUTES_DEFAULT,
    DISCUSSION_ATTENTION_OPENING_GAP_MINUTES_DEFAULT,
    DISCUSSION_ATTENTION_RECENT_TURN_MINUTES_DEFAULT,
    DISCUSSION_ATTENTION_REMINDER_AHEAD_MINUTES_DEFAULT,
    DISCUSSION_ATTENTION_UNANSWERED_OPENING_MINUTES_DEFAULT,
    DISCUSSION_BACKOFF_MINUTES_DEFAULT,
    DISCUSSION_CONTEXT_CALLS_PER_RUN_DEFAULT,
    DISCUSSION_CONTEXT_FACTS_PER_PASS_DEFAULT,
    DISCUSSION_CONTEXT_PURGE_BATCH_SIZE_DEFAULT,
    DISCUSSION_CONTEXT_RETENTION_DAYS_DEFAULT,
    DISCUSSION_DELIVERY_BATCH_SIZE_DEFAULT,
    DISCUSSION_DELIVERY_PROOF_MAX_AGE_MINUTES_DEFAULT,
    DISCUSSION_DIRECTIVES_MAX_TOKENS_DEFAULT,
    DISCUSSION_FULL_EXCERPT_CHARS,
    DISCUSSION_HISTORY_OPENINGS_DEFAULT,
    DISCUSSION_INTERVAL_MINUTES_DEFAULT,
    DISCUSSION_MAINTENANCE_BATCH_SIZE_DEFAULT,
    DISCUSSION_OPENING_PENDING_HOURS_DEFAULT,
    DISCUSSION_PAUSE_HOURS_DEFAULT,
    DISCUSSION_PEER_CONTEXT_RETENTION_DAYS_DEFAULT,
    DISCUSSION_READ_CALL_LIMIT_DEFAULT,
    DISCUSSION_READ_CALL_LIMIT_MAX,
    DISCUSSION_READ_TIMEOUT_SECONDS_DEFAULT,
    DISCUSSION_READ_TIMEOUT_SECONDS_MAX,
    DISCUSSION_REBUILD_CONTEXT_CALLS_DEFAULT,
    DISCUSSION_REBUILD_DEADLINE_SECONDS_DEFAULT,
    DISCUSSION_REPLY_GUARD_MAX_ROWS_DEFAULT,
    DISCUSSION_REPLY_GUARD_MAX_TOKENS_DEFAULT,
    DISCUSSION_REPLY_GUARD_TTL_HOURS_DEFAULT,
    DISCUSSION_RESEARCH_DEFAULT_WINDOW_DAYS_DEFAULT,
    DISCUSSION_RESEARCH_ITEM_LIMIT_DEFAULT,
    DISCUSSION_RESEARCH_ITEM_MAX_CHARS_DEFAULT,
    DISCUSSION_REUSED_ITEMS_MAX_DEFAULT,
    DISCUSSION_REUSED_PROOFS_MAX_DEFAULT,
    DISCUSSION_RULE_CACHE_HOURS_DEFAULT,
    DISCUSSION_RUN_DEADLINE_SECONDS_DEFAULT,
    DISCUSSION_RUN_LEASE_SECONDS_DEFAULT,
    DISCUSSION_RUN_READ_CALLS_MAX_DEFAULT,
    DISCUSSION_SENSITIVE_TOPICS,
    DISCUSSION_TICK_CANDIDATES_DEFAULT,
    DISCUSSION_TICK_CONCURRENCY_DEFAULT,
    DISCUSSION_TICK_OWNERS_DEFAULT,
)


class ProactiveDiscussionSettings(BaseSettings):
    """Operator switches, cadence, prompt versions, spending ceilings and run bounds."""

    discussion_context_prompt_version: str = Field(
        default="v1",
        description="Prompt version of the context interpretation and the read-rule compiler.",
    )
    discussion_decision_prompt_version: str = Field(
        default="v1", description="Prompt version of the engage/defer/skip decision."
    )
    discussion_message_prompt_version: str = Field(
        default="v1", description="Prompt version of the opening's wording."
    )
    discussion_interval_minutes: int = Field(
        default=DISCUSSION_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=1440,
        description=(
            "Minutes between two elected producer ticks; a short one serves a requested "
            "rebuild sooner (testing), and every tick may read every consented source."
        ),
    )
    discussion_tick_candidates: int = Field(
        default=DISCUSSION_TICK_CANDIDATES_DEFAULT,
        ge=1,
        le=10_000,
        description="Owners one tick examines at random before drawing the ones it can serve.",
    )
    discussion_tick_owners: int = Field(
        default=DISCUSSION_TICK_OWNERS_DEFAULT,
        ge=1,
        le=200,
        description="Owners one tick serves at most, a requested rebuild first.",
    )
    discussion_tick_concurrency: int = Field(
        default=DISCUSSION_TICK_CONCURRENCY_DEFAULT,
        ge=1,
        le=16,
        description="Runs one tick drives at once.",
    )
    discussion_delivery_batch_size: int = Field(
        default=DISCUSSION_DELIVERY_BATCH_SIZE_DEFAULT,
        ge=1,
        le=500,
        description="Pending openings one delivery sweep serves, oldest first.",
    )
    discussion_maintenance_batch_size: int = Field(
        default=DISCUSSION_MAINTENANCE_BATCH_SIZE_DEFAULT,
        ge=1,
        le=1000,
        description=(
            "Accounts whose context retention one tick enforces, and expired spending "
            "reservations it settles."
        ),
    )
    discussion_context_purge_batch_size: int = Field(
        default=DISCUSSION_CONTEXT_PURGE_BATCH_SIZE_DEFAULT,
        ge=1,
        le=5000,
        description="Observations a context purge streams per batch.",
    )
    discussion_backoff_minutes: int = Field(
        default=DISCUSSION_BACKOFF_MINUTES_DEFAULT,
        ge=1,
        le=1440,
        description="Minutes a run defers when a provider asks to wait without saying how long.",
    )
    discussion_reply_guard_ttl_hours: int = Field(
        default=DISCUSSION_REPLY_GUARD_TTL_HOURS_DEFAULT,
        ge=1,
        le=24 * 90,
        description=(
            "Hours a reply to an opening keeps restraining the producer while memory "
            "has not acknowledged it."
        ),
    )
    discussion_reply_guard_max_rows: int = Field(
        default=DISCUSSION_REPLY_GUARD_MAX_ROWS_DEFAULT,
        ge=1,
        le=1000,
        description="Live reply guards a run reads, all or none; past it every run defers.",
    )
    discussion_reply_guard_max_tokens: int = Field(
        default=DISCUSSION_REPLY_GUARD_MAX_TOKENS_DEFAULT,
        ge=100,
        le=200_000,
        description="Tokens the live reply guards may take; past it every run defers.",
    )
    proactive_discussions_enabled: bool = Field(
        default=True, description="Operator switch of the background producer."
    )
    discussion_owner_daily_budget_usd: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=8,
        description="Ceiling per account and UTC day, in USD; unset closes paid production.",
    )
    discussion_instance_daily_budget_usd: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=8,
        description="Ceiling for the whole instance per UTC day, in USD; unset closes it.",
    )
    discussion_run_budget_usd: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=8,
        description=(
            "Most one run may spend, in USD; a run reserves this or what is left of the "
            "day, whichever is smaller. Unset closes paid production."
        ),
    )
    discussion_default_sensitive_topics: str | list[str] = Field(
        default=",".join(DISCUSSION_SENSITIVE_TOPICS),
        description=(
            "Sensitive topics a new account consents to (comma-separated; empty for none). "
            "The person may withdraw each one in the settings."
        ),
    )
    discussion_attention_recent_turn_minutes: int = Field(
        default=DISCUSSION_ATTENTION_RECENT_TURN_MINUTES_DEFAULT,
        ge=0,
        le=1440,
        description="Minutes after the person last wrote during which no opening starts.",
    )
    discussion_attention_alert_gap_minutes: int = Field(
        default=DISCUSSION_ATTENTION_ALERT_GAP_MINUTES_DEFAULT,
        ge=0,
        le=1440,
        description=(
            "Minutes after a proactive notification or an interest alert during which no "
            "opening starts; 0 lets alerts and discussions coexist."
        ),
    )
    discussion_attention_opening_gap_minutes: int = Field(
        default=DISCUSSION_ATTENTION_OPENING_GAP_MINUTES_DEFAULT,
        ge=0,
        le=1440,
        description="Minutes between two openings, whatever became of the first.",
    )
    discussion_attention_unanswered_opening_minutes: int = Field(
        default=DISCUSSION_ATTENTION_UNANSWERED_OPENING_MINUTES_DEFAULT,
        ge=0,
        le=1440,
        description=(
            "Minutes an opening left unanswered holds the next one back, never past its "
            "reply window; 0 leaves only the gap between openings."
        ),
    )
    discussion_attention_reminder_ahead_minutes: int = Field(
        default=DISCUSSION_ATTENTION_REMINDER_AHEAD_MINUTES_DEFAULT,
        ge=0,
        le=1440,
        description="Minutes before a reminder rings during which no opening starts.",
    )
    discussion_run_lease_seconds: int = Field(
        default=DISCUSSION_RUN_LEASE_SECONDS_DEFAULT,
        ge=30,
        le=3600,
        description="Seconds a run holds its account before it must renew its claim.",
    )
    discussion_run_deadline_seconds: int = Field(
        default=DISCUSSION_RUN_DEADLINE_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Seconds after which an opening run stops, shorter than its lease.",
    )
    discussion_rebuild_deadline_seconds: int = Field(
        default=DISCUSSION_REBUILD_DEADLINE_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description=(
            "Seconds after which a requested rebuild stops and resumes at the next tick; "
            "never shorter than an opening's, and free to outlast the lease, which every "
            "read and every model call renews."
        ),
    )
    discussion_run_read_calls_max: int = Field(
        default=DISCUSSION_RUN_READ_CALLS_MAX_DEFAULT,
        ge=1,
        le=1000,
        description="Physical source calls one run may make across all its reads.",
    )
    discussion_context_calls_per_run: int = Field(
        default=DISCUSSION_CONTEXT_CALLS_PER_RUN_DEFAULT,
        ge=1,
        le=10,
        description=(
            "Context-phase model calls one run may buy; the read-rule compilation spends "
            "one of them when its cache is stale."
        ),
    )
    discussion_rebuild_context_calls: int = Field(
        default=DISCUSSION_REBUILD_CONTEXT_CALLS_DEFAULT,
        ge=1,
        le=20,
        description=(
            "Context-phase model calls a requested rebuild may buy: it interprets every "
            "admitted fact, a pass after another, and stops once none is left."
        ),
    )
    discussion_context_facts_per_pass: int = Field(
        default=DISCUSSION_CONTEXT_FACTS_PER_PASS_DEFAULT,
        ge=1,
        le=100,
        description="Facts one context call interprets, at most.",
    )
    discussion_read_call_limit: int = Field(
        default=DISCUSSION_READ_CALL_LIMIT_DEFAULT,
        ge=1,
        le=DISCUSSION_READ_CALL_LIMIT_MAX,
        description="Physical calls one source read may make.",
    )
    discussion_read_timeout_seconds: int = Field(
        default=DISCUSSION_READ_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=DISCUSSION_READ_TIMEOUT_SECONDS_MAX,
        description="Seconds one source read may take before its page is closed.",
    )
    discussion_research_item_limit: int = Field(
        default=DISCUSSION_RESEARCH_ITEM_LIMIT_DEFAULT,
        ge=1,
        le=100,
        description="Items one source page returns, at most.",
    )
    discussion_research_item_max_chars: int = Field(
        default=DISCUSSION_RESEARCH_ITEM_MAX_CHARS_DEFAULT,
        ge=100,
        le=DISCUSSION_FULL_EXCERPT_CHARS,
        description="Characters of one item's excerpt (the portrait is read whole).",
    )
    discussion_research_default_window_days: int = Field(
        default=DISCUSSION_RESEARCH_DEFAULT_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=31,
        description="Days before and after now a read covers when no date is named.",
    )
    discussion_reused_items_max: int = Field(
        default=DISCUSSION_REUSED_ITEMS_MAX_DEFAULT,
        ge=1,
        le=1000,
        description="Stored context items one run may reuse, the most recent first.",
    )
    discussion_reused_proofs_max: int = Field(
        default=DISCUSSION_REUSED_PROOFS_MAX_DEFAULT,
        ge=0,
        le=200,
        description="Stored proofs one run reads again before reusing their items.",
    )
    discussion_history_openings: int = Field(
        default=DISCUSSION_HISTORY_OPENINGS_DEFAULT,
        ge=0,
        le=100,
        description="Prior openings a decision is shown, so none is repeated.",
    )
    discussion_rule_cache_hours: int = Field(
        default=DISCUSSION_RULE_CACHE_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Hours a compiled read restriction is reused for the same inputs.",
    )
    discussion_opening_pending_hours: int = Field(
        default=DISCUSSION_OPENING_PENDING_HOURS_DEFAULT,
        ge=1,
        le=720,
        description=(
            "Hours an opening waits for a reply before it lapses; a newer opening closes it "
            "sooner."
        ),
    )
    discussion_pause_hours: int = Field(
        default=DISCUSSION_PAUSE_HOURS_DEFAULT,
        ge=1,
        le=720,
        description="Hours a pause lasts (the settings' button and the 'not now' reaction).",
    )
    discussion_context_retention_days: int = Field(
        default=DISCUSSION_CONTEXT_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=3650,
        description="Days a derived context item may outlive its read (capped by its source).",
    )
    discussion_peer_context_retention_days: int = Field(
        default=DISCUSSION_PEER_CONTEXT_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="The same, for what comes from a peer connection.",
    )
    discussion_directives_max_tokens: int = Field(
        default=DISCUSSION_DIRECTIVES_MAX_TOKENS_DEFAULT,
        ge=500,
        le=200_000,
        description="Tokens the complete procedural rules may take; past it the run defers.",
    )
    discussion_delivery_proof_max_age_minutes: int = Field(
        default=DISCUSSION_DELIVERY_PROOF_MAX_AGE_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="Minutes an opening's proofs stay fresh enough to be delivered.",
    )

    @field_validator("discussion_default_sensitive_topics", mode="after")
    @classmethod
    def known_sensitive_topics(cls, value: str | list[str]) -> list[str]:
        """Read the default topics, in vocabulary order, refusing an unknown one.

        Args:
            value: The configured list, or its comma-separated spelling.

        Returns:
            The topics, in the vocabulary's order, without duplicates.

        Raises:
            ValueError: An entry names no sensitive topic.
        """
        entries = value.split(",") if isinstance(value, str) else value
        chosen = {entry.strip().casefold() for entry in entries if entry.strip()}
        unknown = chosen - set(DISCUSSION_SENSITIVE_TOPICS)
        if unknown:
            raise ValueError(
                "DISCUSSION_DEFAULT_SENSITIVE_TOPICS entries must each name one of "
                f"{', '.join(DISCUSSION_SENSITIVE_TOPICS)}, got {sorted(unknown)!r}"
            )
        return [topic for topic in DISCUSSION_SENSITIVE_TOPICS if topic in chosen]

    @model_validator(mode="after")
    def _coherent_discussion_bounds(self) -> Self:
        """Refuse bounds that contradict each other (the boot fails, never a run)."""
        if self.discussion_run_deadline_seconds >= self.discussion_run_lease_seconds:
            raise ValueError("DISCUSSION_RUN_DEADLINE_SECONDS must be shorter than the lease")
        if self.discussion_rebuild_deadline_seconds < self.discussion_run_deadline_seconds:
            raise ValueError(
                "DISCUSSION_REBUILD_DEADLINE_SECONDS must not be shorter than "
                "DISCUSSION_RUN_DEADLINE_SECONDS"
            )
        if self.discussion_read_call_limit > self.discussion_run_read_calls_max:
            raise ValueError("DISCUSSION_READ_CALL_LIMIT exceeds DISCUSSION_RUN_READ_CALLS_MAX")
        if self.discussion_tick_candidates < self.discussion_tick_owners:
            raise ValueError("DISCUSSION_TICK_CANDIDATES is smaller than DISCUSSION_TICK_OWNERS")
        run = self.discussion_run_budget_usd
        for ceiling, name in (
            (self.discussion_owner_daily_budget_usd, "DISCUSSION_OWNER_DAILY_BUDGET_USD"),
            (self.discussion_instance_daily_budget_usd, "DISCUSSION_INSTANCE_DAILY_BUDGET_USD"),
        ):
            if run is not None and ceiling is not None and run > ceiling:
                raise ValueError(f"DISCUSSION_RUN_BUDGET_USD exceeds {name}")
        return self
