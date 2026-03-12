"""
Golden Plan Patterns - Deterministic pattern seeding.

This module provides predefined "golden" patterns that represent
valid and tested tool sequences. These patterns are used to:
1. Initialize new environments (DEV, STAGING, PROD)
2. Reset corrupted pattern data
3. Ensure consistency across environments

DESIGN PRINCIPLE: Only include patterns that represent REAL user scenarios.
Avoid artificial combinations that would never occur in practice.

Confidence calculation with Beta(2,1) prior:
  s=20, f=0 → (2+20)/(2+1+20) = 22/23 = 95.7%  (bypass eligible)
  s=15, f=0 → (2+15)/(2+1+15) = 17/18 = 94.4%  (bypass eligible)
  s=10, f=0 → (2+10)/(2+1+10) = 12/13 = 92.3%  (bypass eligible)

Created: 2026-01-14
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.constants import (
    PLAN_PATTERN_INTENT_MUTATION,
    PLAN_PATTERN_INTENT_READ,
)

if TYPE_CHECKING:
    from src.domains.agents.services.plan_pattern_learner import PlanPatternLearner

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GoldenPattern:
    """A predefined valid pattern."""

    key: str
    domains: str  # Sorted, comma-separated
    intent: str  # PLAN_PATTERN_INTENT_READ or PLAN_PATTERN_INTENT_MUTATION
    successes: int = 20
    failures: int = 0
    description: str = ""


# =============================================================================
# GOLDEN PATTERNS - REAL USER SCENARIOS ONLY
# =============================================================================

GOLDEN_PATTERNS: list[GoldenPattern] = [
    # =========================================================================
    # 1 DOMAIN - READ (basic queries)
    # =========================================================================
    # "Search for Marie in my contacts"
    GoldenPattern("get_contacts", "contact", PLAN_PATTERN_INTENT_READ, 20, 0, "Search contacts"),
    # "Show my latest emails"
    GoldenPattern("get_emails", "email", PLAN_PATTERN_INTENT_READ, 20, 0, "Search emails"),
    # "My appointments for tomorrow"
    GoldenPattern("get_events", "event", PLAN_PATTERN_INTENT_READ, 20, 0, "Search events"),
    # "My recent files"
    GoldenPattern("get_files", "file", PLAN_PATTERN_INTENT_READ, 20, 0, "Search Drive files"),
    # "My current tasks"
    GoldenPattern("get_tasks", "task", PLAN_PATTERN_INTENT_READ, 20, 0, "Search tasks"),
    # "What's the weather like?"
    GoldenPattern(
        "get_weather_forecast", "weather", PLAN_PATTERN_INTENT_READ, 20, 0, "Weather forecast"
    ),
    GoldenPattern(
        "get_current_weather", "weather", PLAN_PATTERN_INTENT_READ, 20, 0, "Current weather"
    ),
    # "Restaurant nearby"
    GoldenPattern("get_places", "place", PLAN_PATTERN_INTENT_READ, 20, 0, "Search places"),
    GoldenPattern(
        "get_current_location", "place", PLAN_PATTERN_INTENT_READ, 20, 0, "Current location"
    ),
    # "How to get to Paris?"
    GoldenPattern("get_route", "route", PLAN_PATTERN_INTENT_READ, 20, 0, "Get directions"),
    # "What is machine learning?"
    GoldenPattern(
        "get_wikipedia_summary", "wikipedia", PLAN_PATTERN_INTENT_READ, 20, 0, "Wikipedia summary"
    ),
    GoldenPattern("search_perplexity", "perplexity", PLAN_PATTERN_INTENT_READ, 20, 0, "Web search"),
    # "My reminders"
    GoldenPattern("list_reminders", "reminder", PLAN_PATTERN_INTENT_READ, 20, 0, "List reminders"),
    # =========================================================================
    # 1 DOMAIN - MUTATION (basic actions)
    # =========================================================================
    # "Send an email to test@example.com"
    GoldenPattern(
        "send_email", "email", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Send email directly"
    ),
    # "Create an appointment tomorrow at 2pm"
    GoldenPattern("create_event", "event", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Create event"),
    # "Add Pierre as a contact"
    GoldenPattern(
        "create_contact", "contact", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Create contact"
    ),
    # "Create a task for..."
    GoldenPattern("create_task", "task", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Create task"),
    # "Remind me to..."
    GoldenPattern(
        "create_reminder", "reminder", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Create reminder"
    ),
    # Update/delete single domain
    GoldenPattern("update_event", "event", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Update event"),
    GoldenPattern("delete_event", "event", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Delete event"),
    GoldenPattern(
        "update_contact", "contact", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Update contact"
    ),
    GoldenPattern(
        "delete_contact", "contact", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Delete contact"
    ),
    GoldenPattern("update_task", "task", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Update task"),
    GoldenPattern("delete_task", "task", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Delete task"),
    GoldenPattern("delete_email", "email", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Delete email"),
    GoldenPattern(
        "cancel_reminder", "reminder", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Cancel reminder"
    ),
    # =========================================================================
    # 2 DOMAINS - READ (cross-domain queries)
    # =========================================================================
    # "Marie's emails" -> search contact then filter emails
    GoldenPattern(
        "get_contacts→get_emails",
        "contact,email",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Emails from a contact",
    ),
    GoldenPattern(
        "get_emails→get_contacts",
        "contact,email",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Contact info from email sender",
    ),
    # "How to get to Jean's?" -> search address then route
    GoldenPattern(
        "get_contacts→get_route",
        "contact,route",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Directions to contact address",
    ),
    # "Restaurant near Marie's place"
    GoldenPattern(
        "get_contacts→get_places",
        "contact,place",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Places near contact",
    ),
    # "My appointments with Pierre"
    GoldenPattern(
        "get_contacts→get_events",
        "contact,event",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Events with a contact",
    ),
    GoldenPattern(
        "get_events→get_contacts",
        "contact,event",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Contact info of attendees",
    ),
    # "How to get to my appointment?" / "Directions to my appointment"
    # IMPORTANT: Uses arrival_time = event.start_datetime (NOT departure_time)
    # The user needs to ARRIVE at the event time, not LEAVE at that time
    GoldenPattern(
        "get_events→get_route",
        "event,route",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Directions to event (arrival-based: event.start_datetime → route.arrival_time)",
    ),
    # "Weather for my appointment tomorrow"
    GoldenPattern(
        "get_events→get_weather_forecast",
        "event,weather",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Weather for event",
    ),
    # "Restaurant for my appointment"
    GoldenPattern(
        "get_events→get_places", "event,place", PLAN_PATTERN_INTENT_READ, 20, 0, "Places near event"
    ),
    # "How to get to the restaurant?"
    GoldenPattern(
        "get_places→get_route",
        "place,route",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Directions to a place",
    ),
    # "Weather in Lyon"
    GoldenPattern(
        "get_places→get_weather_forecast",
        "place,weather",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Weather at a place",
    ),
    # "Restaurant nearby" (with geolocation)
    GoldenPattern(
        "get_current_location→get_places",
        "place",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Places near current location",
    ),
    GoldenPattern(
        "get_current_location→get_route",
        "place,route",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Directions from here",
    ),
    # "My tasks for this appointment"
    GoldenPattern(
        "get_events→get_tasks", "event,task", PLAN_PATTERN_INTENT_READ, 20, 0, "Tasks for an event"
    ),
    GoldenPattern(
        "get_tasks→get_events",
        "event,task",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Events related to task",
    ),
    # =========================================================================
    # 2 DOMAINS - MUTATION (cross-domain actions)
    # =========================================================================
    # "Send an email to Marie" -> THE classic pattern
    GoldenPattern(
        "get_contacts→send_email",
        "contact,email",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Send email to contact",
    ),
    # "Create an appointment with Pierre"
    GoldenPattern(
        "get_contacts→create_event",
        "contact,event",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Create event with contact",
    ),
    # "Create a task for Pierre"
    GoldenPattern(
        "get_contacts→create_task",
        "contact,task",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Create task for contact",
    ),
    # "Remind me to call Marie"
    GoldenPattern(
        "get_contacts→create_reminder",
        "contact,reminder",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Reminder about contact",
    ),
    # "Edit contact Marie"
    GoldenPattern(
        "get_contacts→update_contact",
        "contact",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then update contact",
    ),
    GoldenPattern(
        "get_contacts→delete_contact",
        "contact",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then delete contact",
    ),
    # "Reply to this email"
    GoldenPattern(
        "get_emails→send_email", "email", PLAN_PATTERN_INTENT_MUTATION, 20, 0, "Reply/forward email"
    ),
    GoldenPattern(
        "get_emails→delete_email",
        "email",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then delete emails",
    ),
    # "Create an appointment from this email"
    GoldenPattern(
        "get_emails→create_event",
        "email,event",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Create event from email",
    ),
    GoldenPattern(
        "get_emails→create_task",
        "email,task",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Create task from email",
    ),
    # "Edit my appointment tomorrow"
    GoldenPattern(
        "get_events→update_event",
        "event",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then update event",
    ),
    GoldenPattern(
        "get_events→delete_event",
        "event",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then delete events",
    ),
    # "Send an email to appointment attendees"
    GoldenPattern(
        "get_events→send_email",
        "email,event",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Email about event",
    ),
    # "Create an appointment at the restaurant"
    GoldenPattern(
        "get_places→create_event",
        "event,place",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Create event at place",
    ),
    # "Remind me when I get there"
    GoldenPattern(
        "get_places→create_reminder",
        "place,reminder",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Reminder about place",
    ),
    # "Edit my task"
    GoldenPattern(
        "get_tasks→update_task",
        "task",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then update task",
    ),
    GoldenPattern(
        "get_tasks→delete_task",
        "task",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Search then delete tasks",
    ),
    # "Share this file with Pierre"
    GoldenPattern(
        "get_files→send_email",
        "email,file",
        PLAN_PATTERN_INTENT_MUTATION,
        20,
        0,
        "Share file via email",
    ),
    # =========================================================================
    # 3 DOMAINS - READ (complex queries)
    # =========================================================================
    # "How to get to the restaurant near Marie's?"
    GoldenPattern(
        "get_contacts→get_places→get_route",
        "contact,place,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Route to place near contact",
    ),
    # "Weather and restaurant to go to Jean's"
    GoldenPattern(
        "get_contacts→get_places→get_weather_forecast",
        "contact,place,weather",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Weather at places near contact",
    ),
    # "How to get to my appointment's restaurant?"
    # For event-related routing: use arrival_time = event.start_datetime
    GoldenPattern(
        "get_events→get_places→get_route",
        "event,place,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Route to place near event (arrival-based)",
    ),
    # "Weather for my appointment location"
    GoldenPattern(
        "get_events→get_places→get_weather_forecast",
        "event,place,weather",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Weather at event location",
    ),
    # "How to get to the appointment attendee's?"
    # For event-related routing: use arrival_time = event.start_datetime
    GoldenPattern(
        "get_events→get_contacts→get_route",
        "contact,event,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Route to event attendee (arrival-based)",
    ),
    # "Restaurant nearby with directions"
    GoldenPattern(
        "get_current_location→get_places→get_route",
        "place,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Nearby places with directions",
    ),
    # "Weather along route to restaurant"
    GoldenPattern(
        "get_places→get_route→get_weather_forecast",
        "place,route,weather",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Weather along route to place",
    ),
    # =========================================================================
    # 3 DOMAINS - MUTATION (complex actions)
    # =========================================================================
    # "Send Pierre the restaurant info"
    GoldenPattern(
        "get_places→get_contacts→send_email",
        "contact,email,place",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Email contact about place",
    ),
    # "Create an appointment at restaurant with Pierre"
    GoldenPattern(
        "get_places→get_contacts→create_event",
        "contact,event,place",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Create event at place with contact",
    ),
    GoldenPattern(
        "get_contacts→get_places→create_event",
        "contact,event,place",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Create event with contact at nearby place",
    ),
    # "Send an email to my appointment attendees"
    GoldenPattern(
        "get_events→get_contacts→send_email",
        "contact,email,event",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Email event attendees",
    ),
    # "Forward this email to Pierre"
    GoldenPattern(
        "get_emails→get_contacts→send_email",
        "contact,email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Forward email to contact",
    ),
    # "Create an appointment with this email's sender"
    GoldenPattern(
        "get_emails→get_contacts→create_event",
        "contact,email,event",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Create event with email sender",
    ),
    # "Share this file with Pierre"
    GoldenPattern(
        "get_files→get_contacts→send_email",
        "contact,email,file",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Share file with contact",
    ),
    # =========================================================================
    # MULTI-CONTACT PATTERNS (multiple recipients/attendees)
    # =========================================================================
    # "Send an email to Pierre and Marie"
    GoldenPattern(
        "get_contacts→get_contacts→send_email",
        "contact,email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Email to 2 contacts",
    ),
    # "Create an appointment with my wife and son"
    GoldenPattern(
        "get_contacts→get_contacts→create_event",
        "contact,event",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Event with 2 contacts",
    ),
    # "Send an email to Pierre, Marie and Jean"
    GoldenPattern(
        "get_contacts→get_contacts→get_contacts→send_email",
        "contact,email",
        PLAN_PATTERN_INTENT_MUTATION,
        12,
        0,
        "Email to 3 contacts",
    ),
    # "Create an appointment with my wife, son and brother"
    GoldenPattern(
        "get_contacts→get_contacts→get_contacts→create_event",
        "contact,event",
        PLAN_PATTERN_INTENT_MUTATION,
        12,
        0,
        "Event with 3 contacts",
    ),
    # =========================================================================
    # 4 DOMAINS - READ (rare but valid complex scenarios)
    # =========================================================================
    # "Weather to go to restaurant near my appointment"
    # For event-related routing: use arrival_time = event.start_datetime
    GoldenPattern(
        "get_events→get_places→get_route→get_weather_forecast",
        "event,place,route,weather",
        PLAN_PATTERN_INTENT_READ,
        10,
        0,
        "Weather for route to place near event (arrival-based)",
    ),
    # "How to get to Pierre's appointment location?"
    # For event-related routing: use arrival_time = event.start_datetime
    GoldenPattern(
        "get_contacts→get_events→get_places→get_route",
        "contact,event,place,route",
        PLAN_PATTERN_INTENT_READ,
        10,
        0,
        "Route to contact's event location (arrival-based)",
    ),
    # =========================================================================
    # 4 DOMAINS - MUTATION (rare but valid)
    # =========================================================================
    # "Send Pierre the restaurant near my appointment"
    GoldenPattern(
        "get_events→get_places→get_contacts→send_email",
        "contact,email,event,place",
        PLAN_PATTERN_INTENT_MUTATION,
        10,
        0,
        "Email contact about place near event",
    ),
    # =========================================================================
    # FOR_EACH PATTERNS (plan_planner.md Section 14)
    # =========================================================================
    # Patterns where step N iterates over results of step N-1
    # Key format: "provider→consumer[for_each]"
    # =========================================================================
    # "Send an email to each group contact"
    GoldenPattern(
        "get_contacts→send_email[for_each]",
        "contact,email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Email each contact (for_each iteration)",
    ),
    # "Get weather for each city"
    GoldenPattern(
        "get_places→get_weather_forecast[for_each]",
        "place,weather",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Weather for each place (for_each iteration)",
    ),
    # "Create a reminder for each tomorrow's appointment"
    GoldenPattern(
        "get_events→create_reminder[for_each]",
        "event,reminder",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Reminder for each event (for_each iteration)",
    ),
    # "Find the route for each location"
    GoldenPattern(
        "get_places→get_route[for_each]",
        "place,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Route to each place (for_each iteration)",
    ),
    # "Send weather info for each city to contacts"
    GoldenPattern(
        "get_places→get_weather_forecast[for_each]→send_email",
        "email,place,weather",
        PLAN_PATTERN_INTENT_MUTATION,
        12,
        0,
        "Weather for each place then email (for_each + send)",
    ),
    # "Send an email to each attendee of my appointment"
    GoldenPattern(
        "get_events→get_contacts→send_email[for_each]",
        "contact,email,event",
        PLAN_PATTERN_INTENT_MUTATION,
        12,
        0,
        "Get event → get attendees → email each (for_each)",
    ),
    # =========================================================================
    # FOR_EACH PATTERNS - Additional (2026-01-30)
    # =========================================================================
    # "Weather for my next two appointments" - THE missing pattern causing double planner
    GoldenPattern(
        "get_events→get_weather_forecast[for_each]",
        "event,weather",
        PLAN_PATTERN_INTENT_READ,
        20,
        0,
        "Weather for each event (for_each iteration)",
    ),
    # "Directions for each of my appointments"
    GoldenPattern(
        "get_events→get_route[for_each]",
        "event,route",
        PLAN_PATTERN_INTENT_READ,
        15,
        0,
        "Route to each event (for_each iteration)",
    ),
    # "Delete all promotional emails"
    GoldenPattern(
        "get_emails→delete_email[for_each]",
        "email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Delete each matching email (for_each iteration)",
    ),
    # "Create an appointment for each group contact"
    GoldenPattern(
        "get_contacts→create_event[for_each]",
        "contact,event",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Create event for each contact (for_each iteration)",
    ),
    # "Create a task for each unread email"
    GoldenPattern(
        "get_emails→create_task[for_each]",
        "email,task",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Create task for each email (for_each iteration)",
    ),
    # "Delete all cancelled appointments"
    GoldenPattern(
        "get_events→delete_event[for_each]",
        "event",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Delete each matching event (for_each iteration)",
    ),
    # "Delete all completed tasks"
    GoldenPattern(
        "get_tasks→delete_task[for_each]",
        "task",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Delete each matching task (for_each iteration)",
    ),
    # "Archive all emails in this thread"
    GoldenPattern(
        "get_emails→archive_email[for_each]",
        "email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Archive each matching email (for_each iteration)",
    ),
    # "Mark all newsletter emails as read"
    GoldenPattern(
        "get_emails→mark_email_read[for_each]",
        "email",
        PLAN_PATTERN_INTENT_MUTATION,
        15,
        0,
        "Mark each email as read (for_each iteration)",
    ),
    # "Search Wikipedia info for each location"
    GoldenPattern(
        "get_places→get_wikipedia_summary[for_each]",
        "place,wikipedia",
        PLAN_PATTERN_INTENT_READ,
        12,
        0,
        "Wikipedia info for each place (for_each iteration)",
    ),
    # "Weather for each contact (at their address)"
    GoldenPattern(
        "get_contacts→get_weather_forecast[for_each]",
        "contact,weather",
        PLAN_PATTERN_INTENT_READ,
        12,
        0,
        "Weather at each contact's location (for_each iteration)",
    ),
    # "Directions to each contact"
    GoldenPattern(
        "get_contacts→get_route[for_each]",
        "contact,route",
        PLAN_PATTERN_INTENT_READ,
        12,
        0,
        "Route to each contact (for_each iteration)",
    ),
]


def get_golden_patterns(
    domains: list[str] | None = None,
    intent: str | None = None,
) -> list[GoldenPattern]:
    """Get golden patterns, optionally filtered."""
    patterns = GOLDEN_PATTERNS
    if domains is not None:
        target = ",".join(sorted(domains))
        patterns = [p for p in patterns if p.domains == target]
    if intent is not None:
        patterns = [p for p in patterns if p.intent == intent]
    return patterns


async def seed_golden_patterns(
    learner: PlanPatternLearner | None = None,
    replace_existing: bool = False,
) -> dict[str, int]:
    """Seed all golden patterns into Redis."""
    if learner is None:
        from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

        learner = get_pattern_learner()

    stats = {"seeded": 0, "skipped": 0, "errors": 0}

    for pattern in GOLDEN_PATTERNS:
        try:
            existing = await learner.get_pattern(pattern.key)
            if existing and not replace_existing:
                stats["skipped"] += 1
                continue

            success = await learner.seed_pattern(
                pattern_key=pattern.key,
                domains=pattern.domains.split(","),
                intent=pattern.intent,
                successes=pattern.successes,
                failures=pattern.failures,
            )
            if success:
                stats["seeded"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            logger.error("golden_pattern_seed_error", pattern=pattern.key, error=str(e))
            stats["errors"] += 1

    logger.info("golden_patterns_seed_complete", **stats, total=len(GOLDEN_PATTERNS))
    return stats


async def reset_to_golden_patterns() -> dict[str, int]:
    """Delete all existing patterns and seed golden patterns."""
    from src.domains.agents.services.plan_pattern_learner import get_pattern_learner

    learner = get_pattern_learner()
    deleted = await learner.delete_all_patterns()
    logger.warning("golden_patterns_reset_deleted", deleted_count=deleted)
    return await seed_golden_patterns(learner, replace_existing=True)


__all__ = [
    "GoldenPattern",
    "GOLDEN_PATTERNS",
    "get_golden_patterns",
    "seed_golden_patterns",
    "reset_to_golden_patterns",
]
