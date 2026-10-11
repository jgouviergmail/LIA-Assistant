"""Resolve the existing canonical number policy before an exact human confirmation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.phone_number_schemas import (
    PhoneNumberCommandValues,
    PhoneNumberPatch,
    PhoneNumberRequest,
)
from src.domains.agents.application.preparation import _preference_content
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.phone_numbers import to_e164
from src.infrastructure.phone_number_preferences import get_phone_number_preferences


async def prepare_phone_number(
    db: AsyncSession,
    actor_id: UUID,
    request: PhoneNumberRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = PhoneNumberRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    expected = await get_phone_number_preferences().read(db, actor_id)
    number = to_e164(validated.phone_number) if validated.phone_number is not None else None
    before = PhoneNumberCommandValues(expected=expected, number=expected.values.phone_number)
    target = PhoneNumberCommandValues(expected=expected, number=number)
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    return _preference_content(
        actor_id,
        PhoneNumberPatch(phone_number=target),
        {"phone_number": before.model_dump(mode="json")},
        command_id=command_id,
    )
