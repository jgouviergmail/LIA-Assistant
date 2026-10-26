"""The existing mutual live boundary, applied to a frozen public audience."""

from collections.abc import Mapping

from src.core.i18n_types import Language
from src.domains.world.collision import private_home
from src.domains.world.message_access import MessageContext
from src.domains.world.messages import MessageScope, mailbox_actor, message_pair
from src.domains.world.public_models import PublicContent, PublicRecipient
from src.domains.world.schemas import ActorState, WorldState


def public_source(state: WorldState, scope: MessageScope, now: float) -> ActorState:
    """Require a live current sender outside their private home before public correspondence."""
    own = mailbox_actor(state, scope, now)
    if private_home(own.position):
        raise ValueError("world_public_private_home")
    return own


def capture_recipients(context: MessageContext) -> dict[str, PublicRecipient]:
    """Freeze eligible unblocked people and their controllers/languages exactly once."""
    own = public_source(context.state, context.scope, context.now)
    recipients = {}
    for actor in context.state.actors.values():
        if actor.account_id == own.account_id:
            continue
        try:
            _, other = message_pair(context.state, context.scope, actor.public_id, context.now)
        except ValueError:
            continue
        language = context.policy.languages.get(other.account_id)
        if language is None:
            continue
        recipients[other.account_id] = PublicRecipient(
            public_id=other.public_id,
            controller=other.controller,
            language=language,
            delivery="authorized" if language == context.policy.language else "pending",
        )
    return recipients


def authorized_recipients(
    message: PublicContent,
    scope: MessageScope,
    state: WorldState,
    now: float,
    languages: Mapping[str, Language],
) -> set[str]:
    """Recheck the frozen audience without adding late arrivals or changed controllers/languages."""
    public_source(state, scope, now)
    result = set()
    for account, recipient in message.recipients.items():
        try:
            _, other = message_pair(state, scope, recipient.public_id, now)
        except ValueError:
            continue
        if (
            other.account_id == account
            and other.controller == recipient.controller
            and languages.get(account) == recipient.language
        ):
            result.add(account)
    return result
