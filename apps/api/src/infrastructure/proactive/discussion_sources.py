"""Composition of all native source ports; readers do no work until the gateway admits them."""

from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType

from src.domains.connectors.discussion_sources import (
    CalendarDiscussionSource,
    ContactDiscussionSource,
    EmailDiscussionSource,
    TaskDiscussionSource,
)
from src.domains.connectors.discussion_weather import WeatherDiscussionSource
from src.domains.habits.discussion_source import HabitDiscussionSource
from src.domains.health_metrics.discussion_source import HealthDiscussionSource
from src.domains.interests.discussion_source import InterestDiscussionSource
from src.domains.journals.discussion_source import JournalDiscussionSource, PortraitDiscussionSource
from src.domains.meetings.discussion_source import MeetingDiscussionSource
from src.domains.memories.discussion_source import MemoryDiscussionSource
from src.domains.open_loops.discussion_source import OpenLoopDiscussionSource
from src.domains.peers.discussion_source import PeerDiscussionSource, PeerMessageDiscussionSource
from src.domains.relations.discussion_source import RelationDiscussionSource
from src.domains.reminders.discussion_source import ReminderDiscussionSource
from src.domains.scheduled_actions.discussion_source import ScheduledActionDiscussionSource
from src.domains.shared.discussion_sources import DiscussionSource, SourceKey
from src.domains.sms.discussion_source import SmsDiscussionSource
from src.domains.users.discussion_location import LocationDiscussionSource
from src.domains.workboard.discussion_source import WorkboardDiscussionSource
from src.infrastructure.proactive.conversation_source import ConversationDiscussionSource


def discussion_readers(
    *, authorize_weather: Callable[[], Awaitable[None]] | None = None
) -> Mapping[SourceKey, DiscussionSource]:
    """Build every native source port, one per source key.

    Args:
        authorize_weather: Admits the billed weather call against the run's
            permit, or None.

    Returns:
        A read-only mapping from source key to its reader.
    """
    return MappingProxyType(
        {
            SourceKey.CALENDAR: CalendarDiscussionSource(),
            SourceKey.EMAILS: EmailDiscussionSource(),
            SourceKey.CONTACTS: ContactDiscussionSource(),
            SourceKey.TASKS: TaskDiscussionSource(),
            SourceKey.WEATHER: WeatherDiscussionSource(authorize_paid=authorize_weather),
            SourceKey.LOCATION: LocationDiscussionSource(),
            SourceKey.MEMORIES: MemoryDiscussionSource(),
            SourceKey.JOURNALS: JournalDiscussionSource(),
            SourceKey.PORTRAIT: PortraitDiscussionSource(),
            SourceKey.OPEN_LOOPS: OpenLoopDiscussionSource(),
            SourceKey.HABITS: HabitDiscussionSource(),
            SourceKey.RELATIONS: RelationDiscussionSource(),
            SourceKey.HEALTH: HealthDiscussionSource(),
            SourceKey.CONVERSATIONS: ConversationDiscussionSource(),
            SourceKey.MEETINGS: MeetingDiscussionSource(),
            SourceKey.PEERS: PeerDiscussionSource(),
            SourceKey.PEER_MESSAGES: PeerMessageDiscussionSource(),
            SourceKey.INTERESTS: InterestDiscussionSource(),
            SourceKey.REMINDERS: ReminderDiscussionSource(),
            SourceKey.SCHEDULED_ACTIONS: ScheduledActionDiscussionSource(),
            SourceKey.WORKBOARD: WorkboardDiscussionSource(),
            SourceKey.SMS: SmsDiscussionSource(),
        }
    )
