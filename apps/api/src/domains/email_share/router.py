"""Routes of sending a generated file or an answer by e-mail (ADR-321).

Three routes, all under the capability guard — the router IS the ability:

- ``GET /email-share/options`` — what the dialog may offer this account right
  now: the road, its one recipient when it is the relay, the largest file it
  carries and every bound the send will meet (ADR-184: what is enforced is
  published).
- ``GET /email-share/recipients`` — the contacts to offer for what is being
  typed in the recipient field (ADR-321 amendment), from the account's
  contacts connector; nothing without one.
- ``POST /email-share`` — the send. The dialog's button is the confirmation.
  The request session is committed BEFORE anything leaves (ADR-304): the
  authentication and the file check read on it, the send holds nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.email_share.recipients import suggest_recipients, suggestions_available
from src.domains.email_share.schemas import (
    EmailShareOptions,
    EmailShareRequest,
    EmailShareResult,
    RecipientSuggestionItem,
    RecipientSuggestionsResponse,
)
from src.domains.email_share.service import (
    deliver_share,
    options_for,
    prepare_share,
    resolve_route,
)
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User

router = APIRouter(
    prefix="/email-share",
    tags=["Email share"],
    dependencies=capability_dependencies(PlatformCapability.EMAIL_SHARE),
)

# Read once at import, like every settings-driven module constant: the limiter
# counts one account's sends, whatever road they take.
rate_limit_email_share = create_user_rate_limiter(
    "email_share",
    max_calls=settings.email_share_rate_limit_calls,
    window_seconds=settings.email_share_rate_limit_window_seconds,
)
# One request per pause in typing: its own, wider window, never the send's.
rate_limit_recipient_suggestions = create_user_rate_limiter(
    "email_share_recipients",
    max_calls=settings.email_share_suggest_rate_limit_calls,
    window_seconds=settings.email_share_suggest_rate_limit_window_seconds,
)


@router.get(
    "/options",
    response_model=EmailShareOptions,
    summary="What « Send by e-mail » may offer this account",
    description=(
        "The road a send would take (the connected mailbox, or LIA's relay to the "
        "account's own verified address), the largest file it carries and the "
        "published bounds of the dialog (ADR-321)."
    ),
)
async def get_email_share_options(
    user: User = Depends(get_current_active_session),
) -> EmailShareOptions:
    """Resolve the account's road and publish what it accepts."""
    return options_for(
        await resolve_route(user), contacts_connected=await suggestions_available(user.id)
    )


@router.get(
    "/recipients",
    response_model=RecipientSuggestionsResponse,
    summary="Contacts to suggest for the recipient being typed",
    description=(
        "Matches the account's contacts connector by name or first name (accents and "
        "punctuation ignored), address or phone number, and answers their addresses — "
        "nothing without a contacts connector. The bounds are published by /options."
    ),
    dependencies=[Depends(rate_limit_recipient_suggestions)],
)
async def get_recipient_suggestions(
    q: str = Query(
        ...,
        max_length=EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS,
        description="One recipient being typed.",
    ),
    user: User = Depends(get_current_active_session),
) -> RecipientSuggestionsResponse:
    """Suggest the contacts matching one recipient query."""
    found = await suggest_recipients(user.id, q)
    return RecipientSuggestionsResponse(
        query=found.query,
        suggestions=[
            RecipientSuggestionItem(name=item.name, email=item.email) for item in found.suggestions
        ],
        truncated=found.truncated,
    )


@router.post(
    "",
    response_model=EmailShareResult,
    summary="Send a generated file or an answer by e-mail",
    description=(
        "Sends one of the caller's generated files, or an answer as its Markdown "
        "export, with a subject and optional words — the click is the confirmation "
        "(ADR-321). Refusals carry a stable code in `detail.code`."
    ),
    dependencies=[Depends(rate_limit_email_share)],
)
async def send_by_email(
    payload: EmailShareRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> EmailShareResult:
    """Check, commit, then send — nothing is held across the network call."""
    route = await resolve_route(user)
    prepared = await prepare_share(db, user, payload, route)
    # ADR-304: the pooled connection goes back BEFORE the provider is called.
    await db.commit()
    return await deliver_share(user.id, prepared)
