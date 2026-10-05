"""What the administrators' user table shows and sorts by, declared once.

The table lists every account with its switches — « voice enabled », « memory
enabled »… — and it had drifted the way hand-kept lists do: three switches out
of twenty-two were shown, and the sort accepted ANY attribute of ``User``
(``getattr`` with a fallback), so ``sort_by=hashed_password`` ordered the
directory by password hash while ``sort_by=typo`` silently fell back to the
creation date.

One declaration now serves the three readers that must agree:

- :data:`ADMIN_USER_SWITCHES` — the per-account on/off preferences the table
  shows, in display order, each a boolean column of ``users`` and a field of
  ``UserProfileWithStats`` (both checked by a test);
- :data:`ADMIN_USER_SORT_KEYS` — every column the listing may be sorted by, the
  whitelist the route enforces before the repository sees it;
- :func:`admin_user_switches` — the values the builder copies from the row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from src.domains.users.models import User

#: The per-account switches, in the table's display order: what LIA knows and
#: keeps, how she speaks, what she starts on her own, what she creates, what
#: the account shares with other people, and what the screen shows.
ADMIN_USER_SWITCHES: Final[tuple[str, ...]] = (
    "memory_enabled",
    "psyche_enabled",
    "psyche_display_avatar",
    "habits_enabled",
    "journals_enabled",
    "journal_consolidation_enabled",
    "journal_consolidation_with_history",
    "voice_enabled",
    "speaking_avatar_enabled",
    "voice_mode_enabled",
    "phone_rich_context_enabled",
    "heartbeat_enabled",
    "interests_enabled",
    "relation_debrief_enabled",
    "image_generation_enabled",
    "image_generation_prompt_enhancement",
    "discovery_enabled",
    "peer_email_visible",
    "use_last_known_location",
    "login_notifications_enabled",
    "health_metrics_agents_enabled",
    "tokens_display_enabled",
    "debug_panel_enabled",
)

#: Boolean columns of ``users`` that are NOT a switch, each with the reason.
#: Every other boolean column must be listed above: a switch added to the
#: model without a column in the table is the drift this module ends.
ADMIN_USER_NON_SWITCHES: Final[dict[str, str]] = {
    "is_active": "The account's lifecycle, shown in the status column.",
    "is_verified": "The address's verification, a fact about the account.",
    "is_superuser": "A role, marked beside the status.",
    "onboarding_completed": "Where the account stands in its onboarding.",
}

#: Columns of ``users`` the listing sorts by directly.
ADMIN_USER_COLUMN_SORTS: Final[tuple[str, ...]] = (
    "email",
    "full_name",
    "created_at",
    "is_active",
    "language",
    *ADMIN_USER_SWITCHES,
)

#: Sums read from ``user_statistics`` (the repository computes each one).
ADMIN_USER_STATISTIC_SORTS: Final[tuple[str, ...]] = (
    "total_messages",
    "total_tokens",
    "total_google_api_requests",
    "total_cost_eur",
    "cycle_messages",
    "cycle_tokens",
    "cycle_google_api_requests",
    "cycle_cost_eur",
)

#: Values the listing query selects as labelled subqueries.
ADMIN_USER_SUBQUERY_SORTS: Final[tuple[str, ...]] = (
    "active_connectors_count",
    "last_message_at",
    "skills_count",
    "mcp_servers_count",
    "scheduled_actions_count",
    "rag_spaces_count",
    "is_usage_blocked",
    "memories_count",
    "interests_count",
)

#: Everything ``GET /users/admin/search`` accepts as ``sort_by``.
ADMIN_USER_SORT_KEYS: Final[frozenset[str]] = frozenset(
    (*ADMIN_USER_COLUMN_SORTS, *ADMIN_USER_STATISTIC_SORTS, *ADMIN_USER_SUBQUERY_SORTS)
)


def admin_user_switches(user: User) -> dict[str, bool]:
    """The account's switches, as the administrators' table shows them.

    Args:
        user: The account row.

    Returns:
        Each switch of :data:`ADMIN_USER_SWITCHES` and its stored value.
    """
    return {name: bool(getattr(user, name)) for name in ADMIN_USER_SWITCHES}
