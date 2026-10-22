"""Recover bounded native recurrence declarations lost when a provider expands occurrences."""

from pydantic import Field

from src.core.exceptions import ConnectorAPIError, ResourceNotFoundError
from src.core.read_budget import ReadCallLimit
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.connectors.discussion_projections import ProviderValue, provider_reference
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    GraphRecurrence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    semantic_version,
)


class SeriesDeclaration(ProviderValue):
    """A recurring series' own declaration: its rule or pattern, and its status."""

    id: str = Field(min_length=1, max_length=256)
    recurrence: tuple[str, ...] = Field(default=(), max_length=32)
    recurrence_pattern: GraphRecurrence | None = None
    status: str = "confirmed"


def _enrich(item: DiscussionEvidence, declaration: SeriesDeclaration) -> DiscussionEvidence:
    if declaration.status == "cancelled":
        return item
    rule = next((rule for rule in declaration.recurrence if rule.startswith("RRULE:")), None)
    if rule is None and declaration.recurrence_pattern is None:
        return item
    scope = (
        declaration.recurrence_pattern.model_dump_json() if declaration.recurrence_pattern else ""
    )
    support = provider_reference(SourceKey.CALENDAR, item.source_account, declaration.id)
    return item.model_copy(
        update={
            "recurrence_rule": rule,
            "native_recurrence": declaration.recurrence_pattern,
            "supports": tuple(dict.fromkeys((*item.supports, support))),
            "version": semantic_version((item.version, rule or "", scope)),
        }
    )


async def enrich_calendar_series(
    request: SourceReadRequest, opened: CalendarAccess, snapshot: SourceSnapshot
) -> SourceSnapshot:
    """Restore the recurrence of expanded occurrences from their series, at most two.

    A provider listing occurrences drops the series rule; the series is read for
    it and becomes a support of each occurrence. A series that cannot be read or
    validated adds nothing and marks the page truncated, never complete.

    Args:
        request: The read.
        opened: The opened calendar.
        snapshot: The page of occurrences.

    Returns:
        The page, occurrences enriched where their series could be read.
    """
    parents = tuple(
        dict.fromkeys(
            item.series_id
            for item in snapshot.items
            if item.series_id
            and item.series_id != item.object_id
            and item.recurrence_rule is None
            and item.native_recurrence is None
        )
    )
    declarations: dict[str, SeriesDeclaration] = {}
    for identifier in parents[:2]:
        try:
            raw: object = await opened.client.get_event(
                identifier,
                calendar_id=opened.calendar_id,
                fields=["id", "recurrence", "status", "updated"],
            )
            declaration = SeriesDeclaration.model_validate(raw)
            if declaration.id != identifier:
                raise ValueError("calendar returned another series declaration")
            declarations[identifier] = declaration
        except ReadCallLimit:
            break
        except ResourceNotFoundError, ConnectorAPIError, ValueError:
            # The occurrence is still known. No rule, outcome or absence is
            # inferred from a parent the account cannot read or validate.
            continue
    items = tuple(
        _enrich(item, declarations[item.series_id]) if item.series_id in declarations else item
        for item in snapshot.items
    )
    missing = set(parents) - declarations.keys()
    return snapshot.model_copy(
        update={"items": items, "status": "truncated" if missing else snapshot.status}
    )
