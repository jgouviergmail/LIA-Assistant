"""Source capabilities shared by discussion readers and the consultation vocabulary."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.domains.shared.discussion_sources import ReadOperation, SourceKey


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """What a source offers: registry domain, reads, dependencies and shape.

    ``indivisible`` marks a source used as one whole; ``current_object`` one read
    around now rather than around a past instant; ``connector_category`` the
    connector category that serves the source (``CONNECTOR_FUNCTIONAL_CATEGORIES``),
    so a connector's removal forgets what it served and an opening's delivery
    checks the connector still selected — None for a source no connector serves.
    """

    domain: str
    operations: tuple[ReadOperation, ...] = ("recent", "search", "detail", "history", "future")
    dependencies: tuple[SourceKey, ...] = ()
    indivisible: bool = False
    current_object: bool = False
    connector_category: str | None = None


SOURCE_REGISTRY: Mapping[SourceKey, SourceDefinition] = MappingProxyType(
    {
        SourceKey.CALENDAR: SourceDefinition("event", connector_category="calendar"),
        SourceKey.EMAILS: SourceDefinition(
            "email",
            operations=("recent", "search", "detail", "history"),
            connector_category="email",
        ),
        SourceKey.CONTACTS: SourceDefinition(
            "contact",
            operations=("search", "detail"),
            current_object=True,
            connector_category="contacts",
        ),
        SourceKey.TASKS: SourceDefinition("task", connector_category="tasks"),
        SourceKey.WEATHER: SourceDefinition(
            "weather",
            operations=("recent", "future"),
            dependencies=(SourceKey.LOCATION,),
            connector_category="weather",
        ),
        SourceKey.LOCATION: SourceDefinition("place", operations=("recent",)),
        SourceKey.MEMORIES: SourceDefinition(
            "context", operations=("recent", "search", "detail", "history"), current_object=True
        ),
        SourceKey.JOURNALS: SourceDefinition(
            "journal", operations=("recent", "search", "detail", "history")
        ),
        SourceKey.PORTRAIT: SourceDefinition(
            "journal", operations=("recent",), indivisible=True, current_object=True
        ),
        SourceKey.OPEN_LOOPS: SourceDefinition("peer", current_object=True),
        SourceKey.HABITS: SourceDefinition(
            "automation", operations=("recent", "detail"), current_object=True
        ),
        SourceKey.RELATIONS: SourceDefinition("contact", operations=("search", "detail")),
        SourceKey.HEALTH: SourceDefinition("health", operations=("recent", "history")),
        SourceKey.CONVERSATIONS: SourceDefinition(
            "context", operations=("recent", "search", "history")
        ),
        SourceKey.MEETINGS: SourceDefinition(
            "document", operations=("recent", "search", "detail", "history")
        ),
        SourceKey.PEERS: SourceDefinition("peer", operations=("recent", "detail")),
        SourceKey.PEER_MESSAGES: SourceDefinition(
            "peer", operations=("recent", "search", "detail", "history")
        ),
        SourceKey.INTERESTS: SourceDefinition(
            "interest", operations=("recent", "search", "detail"), current_object=True
        ),
        SourceKey.REMINDERS: SourceDefinition(
            "reminder", operations=("recent", "search", "detail", "future")
        ),
        SourceKey.SCHEDULED_ACTIONS: SourceDefinition("automation"),
        SourceKey.WORKBOARD: SourceDefinition("ticket"),
        SourceKey.SMS: SourceDefinition(
            "sms", operations=("recent", "search", "detail", "history")
        ),
    }
)


def reread_operation(source: SourceKey, *, planned: bool, around_instant: bool) -> ReadOperation:
    """Return the read that finds one known fact of a source again.

    A calendar fact is read in an expanded history (a native detail read returns a
    recurring series' master, never the moved occurrence). A source that names its
    objects reads one by ``detail``. A planned fact of a source without one is read
    in its future, where it was found (a forecast is in no recent page). Otherwise a
    fact is read in its history around its own instant when ``around_instant``, else
    in the source's recent page.

    Args:
        source: The fact's source.
        planned: Whether the fact is planned (asserted for later).
        around_instant: Whether the read is centred on the fact's own instant
            rather than on the page that read it.

    Returns:
        The read operation.
    """
    operations = SOURCE_REGISTRY[source].operations
    if source == SourceKey.CALENDAR:
        return "history"
    if "detail" in operations:
        return "detail"
    if planned and "future" in operations:
        return "future"
    preferred: tuple[ReadOperation, ...] = (
        ("history", "recent") if around_instant else ("recent", "history")
    )
    return next(operation for operation in preferred if operation in operations)
