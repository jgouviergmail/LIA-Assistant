"""Read original email UI options and deterministic contacts without sending or retaining secrets."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.email_share_read_schemas import (
    EmailShareReadInput,
    EmailShareReadProjection,
)
from src.domains.email_share.rate_limits import rate_limit_recipient_suggestions as limit_recipients
from src.domains.email_share.recipients import suggest_recipients, suggestions_available
from src.domains.email_share.schemas import RecipientSuggestionItem, RecipientSuggestionsResponse
from src.domains.email_share.service import options_for, resolve_route
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User


async def _access(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.EMAIL_SHARE)
    return await load_actor(db, actor_id)


async def read_email_share_options(
    db: AsyncSession, actor_id: UUID, query: EmailShareReadInput
) -> EmailShareReadProjection:
    selected = EmailShareReadInput.model_validate(query.model_dump())
    user = await _access(db, actor_id)
    await db.commit()
    route = await resolve_route(user)
    contacts = await suggestions_available(actor_id)
    options = options_for(route, contacts_connected=contacts)
    recipients = None
    if selected.recipient_query is not None and options.recipient_suggestions:
        await limit_recipients(user)
        found = await suggest_recipients(actor_id, selected.recipient_query)
        recipients = RecipientSuggestionsResponse(
            query=found.query,
            suggestions=[
                RecipientSuggestionItem(name=item.name, email=item.email)
                for item in found.suggestions
            ],
            truncated=found.truncated,
        )
    await _access(db, actor_id)
    result = EmailShareReadProjection(
        observed_at=datetime.now(UTC), options=options, recipients=recipients
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Recipient projection too large")
    return result
