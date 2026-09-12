"""The public link to the demonstrator, readable without credentials.

The landing page is anonymous, so whether it advertises a demonstrator must
be readable anonymously. And it must be switchable AT RUNTIME: "take the demo
offline" is the most urgent action an operator can need, and it cannot wait
for a rebuild of a ``NEXT_PUBLIC_*`` value.

Two values, two homes, on purpose:

- the **URL** is a deployment fact (environment): it changes when the domain
  changes, which is to say almost never;
- the **switch** is an operator fact (settings store): it changes in a hurry.

When the switch is off the URL is not disclosed at all. Hiding a link whose
address is still served would only hide it from people who do not look.

Created: 2026-08-06 (live-demonstrator programme, lot 5)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.core.config import settings
from src.domains.feature_switches.public_state import PublicCapabilityState
from src.domains.product.demo_capabilities import fetch_demo_capabilities
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import read_setting

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/product", tags=["product"])


@dataclass(frozen=True)
class PublicDemoLink:
    """Whether the landing shows a demonstrator link, and where it points."""

    enabled: bool = False
    url: str | None = None


class PublicCapabilityEntry(BaseModel):
    """One capability of the demonstrator, as it publishes it itself."""

    enabled: bool = Field(description="Effectively available on the demonstrator right now")
    family: str = Field(description="The registry family the capability belongs to")


class PublicDemoLinkResponse(BaseModel):
    """Anonymous read of the demonstrator link."""

    enabled: bool = Field(description="Whether a demonstrator link should be shown")
    url: str | None = Field(
        default=None,
        description="Where it points. Absent when the link is off — the address is not disclosed.",
    )
    capabilities: dict[str, PublicCapabilityEntry] | None = Field(
        default=None,
        description=(
            "What the demonstrator offers, keyed like the frontend's "
            "`capabilities.items.*` labels — read from the demonstrator's own "
            "public configuration and relayed here. None when the link is off "
            "or the demonstrator could not be read: the page then says so "
            "rather than showing an empty list."
        ),
    )


def configured_public_demo_url() -> str:
    """Read the demonstrator URL this deployment declares.

    Single reader of the environment fact: the anonymous route and the admin
    view must never disagree on whether a demonstrator exists.

    Returns:
        The URL, stripped; empty when this deployment serves no demonstrator.
    """
    return (getattr(settings, "demo_instance_public_url", "") or "").strip()


async def resolve_public_demo_link() -> PublicDemoLink:
    """Resolve the link an anonymous visitor may be shown.

    Never raises: a failing store resolves to OFF, which is the safe direction
    — a link nobody can take down is worse than a missing one.

    Returns:
        The link state; ``url`` is None whenever the link is off.
    """
    url = configured_public_demo_url()
    if not url:
        # Advertising a link to nowhere is worse than advertising nothing.
        return PublicDemoLink()
    try:
        enabled: bool = await read_setting(SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED)
    except Exception as exc:  # noqa: BLE001 — the landing never 500s for this
        logger.error("public_demo_link_read_failed", error_type=type(exc).__name__)
        return PublicDemoLink()
    if not enabled:
        return PublicDemoLink()
    return PublicDemoLink(enabled=True, url=url)


@router.get(
    "/public-demo-link",
    response_model=PublicDemoLinkResponse,
    summary="Whether the landing advertises a public demonstrator",
    description=(
        "Anonymous read: the landing page has no session. Returns the link "
        "only when an operator switched it on."
    ),
)
async def get_public_demo_link() -> PublicDemoLinkResponse:
    """Read the demonstrator link state (no credentials required)."""
    link = await resolve_public_demo_link()
    capabilities: dict[str, PublicCapabilityState] | None = None
    if link.enabled and link.url:
        # Relayed rather than read from the visitor's browser: the document's
        # CSP allows connect-src to this API alone (see demo_capabilities.py).
        capabilities = await fetch_demo_capabilities(link.url)
    return PublicDemoLinkResponse(
        enabled=link.enabled,
        url=link.url,
        capabilities=(
            {key: PublicCapabilityEntry(**entry) for key, entry in capabilities.items()}
            if capabilities
            else None
        ),
    )
