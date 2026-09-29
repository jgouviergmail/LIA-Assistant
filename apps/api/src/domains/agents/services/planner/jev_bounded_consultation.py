"""Code owns candidate parameters; Jev matches the WHOLE request or abstains."""

import json
import re
from dataclasses import replace
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.config import settings
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.planner.consultation_paths import (
    READ_PATHS,
    ReadPath,
    consultation_question,
)
from src.infrastructure.llm.typesafe_client import ChoiceQuestion

# This is candidate extraction, never semantic routing. Written/ambiguous numbers
# stay with the planner; the classifier still verifies every other constraint.
_COUNT = re.compile(
    r"\b(?:first|last|latest|recent|next|list|show(?: me)?|get(?: me)?)\s+(\d+)\b", re.I
)
_NUMBERS = re.compile(r"[-+]?\d+(?:[.,]\d+)*")
_CAPS = {
    "email": "emails_tool_default_max_results",
    "contact": "contacts_tool_default_max_results",
    "file": "drive_tool_default_max_results",
    "task": "tasks_tool_default_max_results",
    "event": "calendar_tool_default_max_results",
}

# Independently calibrated for these candidates; not a probability of correctness.
BOUNDED_MIN_CONFIDENCE = 0.97


def wants_bounded_path(qi: QueryIntelligence) -> bool:
    """Dispatch to one switch, never two sequential native attempts."""
    return qi.primary_domain == "event" or bool(_NUMBERS.search(qi.english_query))


def _count(qi: QueryIntelligence) -> int | None:
    match = _COUNT.search(qi.english_query)
    if match is None or _NUMBERS.findall(qi.english_query) != [match.group(1)]:
        return None
    if len(match.group(1)) > 4:
        return None
    count = int(match.group(1))
    setting = _CAPS.get(qi.primary_domain)
    if setting is None or not 1 <= count <= getattr(settings, setting):
        return None
    return count


def _calendar_paths(timezone: str, anchor: datetime) -> dict[str, ReadPath]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError, ValueError:
        return {}
    if anchor.tzinfo is None:
        return {}
    today = anchor.astimezone(zone).date()
    paths = {}
    for offset, name in enumerate(("today", "tomorrow")):
        day = today + timedelta(days=offset)
        start = datetime.combine(day, time.min, zone)
        end = datetime.combine(day + timedelta(days=1), time.min, zone)
        paths[f"event_{name}"] = ReadPath(
            "event",
            "get_events_tool",
            (("time_min", start.isoformat()), ("time_max", end.isoformat())),
            f"List appointments {name}, the local calendar day {day.isoformat()} in {timezone}, "
            "in the primary calendar. No other search or filter. Application page limit applies; "
            "not an exhaustive retrieval across pages or calendars.",
        )
    return paths


def bounded_paths(qi: QueryIntelligence, timezone: str, anchor: datetime) -> dict[str, ReadPath]:
    """Offer only parameters the executable tool accepts, without clamping."""
    count = _count(qi)
    if _NUMBERS.search(qi.english_query) and count is None:
        return {}
    if qi.primary_domain == "event":
        paths = _calendar_paths(timezone, anchor)
    elif count is not None and not qi.has_temporal_reference:
        labels = consultation_question(READ_PATHS).criteria
        paths = {
            key: replace(path, description=str(labels[key]))
            for key, path in READ_PATHS.items()
            if path.domain == qi.primary_domain and path.domain in _CAPS
        }
    else:
        return {}
    if count is None:
        return paths
    return {
        key: replace(
            path,
            parameters=(*path.parameters, ("max_results", count)),
            description=f"{path.description} Return at most {count} items as explicitly requested. "
            "This is a retrieval limit, not an item ordinal or a date.",
        )
        for key, path in paths.items()
    }


def bounded_question(paths: dict[str, ReadPath]) -> ChoiceQuestion:
    template = json.loads(load_prompt("jev_bounded_consultation_question", version="v1"))
    return ChoiceQuestion(
        instructions=template["instructions"],
        criteria={
            **{key: path.description for key, path in paths.items()},
            "other": template["criteria"]["other"],
        },
    )
