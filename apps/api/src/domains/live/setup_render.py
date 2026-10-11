"""The provider setup of a live session, rendered at the instant it is asked (ADR-299, ADR-329).

The start renders it, and so does every wake: the clock the voice speaks, LIA's
inner state, the person's personality and domain switches are those of the
instant the connection opens — never the start's, kept from hours before. One
function serves both, so the two renderings cannot drift. Extracted from
``service.py``, which is size-capped.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from src.domains.journals.portrait_builder import build_journal_user_model_block
from src.domains.live.direct_mandate import build_direct_setup_inputs

if TYPE_CHECKING:
    from src.domains.live.connector_service import LiveConnectorService
    from src.domains.live.providers import LiveProvider, LiveSetupInputs
    from src.domains.live.schemas import LiveConnectorSettings, LiveSessionMode
    from src.domains.users.models import User


async def render_setup_inputs(
    connectors: LiveConnectorService,
    provider: LiveProvider,
    user: User,
    chosen: LiveConnectorSettings,
    *,
    mode: LiveSessionMode,
    language: str,
    timezone: str,
    display_name: str,
    now: datetime,
    personality: str,
    psyche_block: str,
) -> LiveSetupInputs:
    """What the provider setup of a connection is rendered from.

    A DIRECT session renders the direct mandate — the phone's context block and
    LIA's read-only tools declared on the setup, no delegation (ADR-300 wave 4);
    a delegated one, the delegation mandate.

    Args:
        connectors: The account's live connectors.
        provider: The session's provider.
        user: The person.
        chosen: The settings of the session's model on its connector.
        mode: How the session runs.
        language: The person's language.
        timezone: The person's display timezone.
        display_name: How the voice calls the person.
        now: The instant of the connection — the clock the voice speaks.
        personality: The personality the person chose for LIA.
        psyche_block: LIA's inner state, or "".

    Returns:
        The setup inputs, kept on the record for the connection's renewals.
    """
    preferences = connectors.preferences(user)
    if mode == "direct":
        inputs = await build_direct_setup_inputs(
            user_id=user.id,
            model=chosen.model,
            voice=chosen.voice,
            thinking_level=chosen.thinking_level,
            preferences=preferences,
            disabled_domains=frozenset(user.phone_disabled_domains or ()),
            language=language,
            timezone=timezone,
            display_name=display_name,
            now=now,
            personality=personality,
            psyche_block=psyche_block,
        )
    else:
        inputs = connectors.setup_inputs(
            provider,
            user,
            chosen,
            language=language,
            timezone=timezone,
            display_name=display_name,
            now=now,
            personality=personality,
            psyche_block=psyche_block,
        )
    # One composition for start and wake, shared by every provider and mode.
    # A native domain refusal also refuses its ambient portrait.
    if "journal" not in (user.phone_disabled_domains or ()):
        portrait = await build_journal_user_model_block(
            user.id,
            format="brief",
            flow="live",
            max_tokens=inputs.target_tokens,
            budget_prefix=inputs.system_instruction,
        )
        instruction = f"{inputs.system_instruction}\n\n{portrait}" if portrait else ""
        if instruction:
            inputs = replace(inputs, system_instruction=instruction)
    return inputs


__all__ = ["render_setup_inputs"]
