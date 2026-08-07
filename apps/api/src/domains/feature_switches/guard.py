"""Route dependency refusing a switched-off capability.

Hiding a capability's tools from the planner keeps the assistant honest;
this is what actually ENFORCES the switch. A direct HTTP call, a replayed
request, or a client that remembers an old endpoint all land here.

One factory serves every capability, so guarding a router is a single line:

    router = APIRouter(
        prefix="/attachments",
        dependencies=[Depends(require_capability(PlatformCapability.ATTACHMENTS))],
    )

The refusal carries a stable code and the capability name, never a sentence:
the frontend says WHICH feature is off, in the reader's language.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

import structlog
from fastapi import Depends, params

from src.core.constants import CAPABILITY_DISABLED_ERROR_CODE
from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled

logger = structlog.get_logger(__name__)


def require_capability(
    capability: PlatformCapability,
) -> Callable[[], Awaitable[None]]:
    """Build a FastAPI dependency that refuses when ``capability`` is off.

    Args:
        capability: The capability the guarded routes need.

    Returns:
        An async dependency raising 403 when the capability is disabled.
    """

    async def _guard() -> None:
        if await is_capability_enabled(capability):
            return
        logger.info("capability_route_refused", capability=capability.value)
        raise AuthorizationError(
            detail={
                # Technical, for logs and the admin API.
                "error": f"Capability '{capability.value}' is disabled on this instance",
                # What the client localizes on.
                "error_code": CAPABILITY_DISABLED_ERROR_CODE,
                "capability": capability.value,
            },
            capability=capability.value,
        )

    # Bound per capability (never a shared closure variable) and named after
    # it: FastAPI prints dependency names, and a row of identical "<lambda>"
    # entries makes a misconfiguration unreadable.
    _guard.__name__ = f"require_capability_{capability.value}"
    return _guard


def capability_dependencies(
    capability: PlatformCapability,
) -> Sequence[params.Depends]:
    """Router-level dependency list guarding one capability.

    Sugar over ``Depends(require_capability(...))`` so a guarded router reads
    as one line and one import:

        router = APIRouter(
            prefix="/skills",
            dependencies=capability_dependencies(PlatformCapability.SKILLS),
        )

    Args:
        capability: The capability the router needs.

    Returns:
        A dependency list ready for ``APIRouter(dependencies=...)``.
    """
    return [Depends(require_capability(capability))]
