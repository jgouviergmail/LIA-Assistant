"""Every route-enforced capability really guards its router.

The registry says a capability is ``route_enforced``; this checks the claim
against the ROUTERS THEMSELVES. A declaration nobody wired would be the worst
kind of switch: visible in the admin panel, flipped by an operator, and
enforcing nothing.

Walking the real router objects (rather than grepping source) is what makes
this survive a refactor: move a route to another file and the test follows.
"""

from __future__ import annotations

import pytest

from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability

pytestmark = pytest.mark.unit


def _guarded_capabilities(router: object) -> set[str]:
    """Capability names guarded on a router's own dependency list."""
    names = set()
    for dependency in getattr(router, "dependencies", []):
        function_name = getattr(dependency.dependency, "__name__", "")
        if function_name.startswith("require_capability_"):
            names.add(function_name.removeprefix("require_capability_"))
    return names


def _router_for(capability: PlatformCapability) -> object:
    """The router each route-enforced capability is expected to guard."""
    if capability is PlatformCapability.ATTACHMENTS:
        from src.domains.attachments.router import router
    elif capability is PlatformCapability.RAG_SPACES:
        from src.domains.rag_spaces.router import router
    elif capability is PlatformCapability.SKILLS:
        from src.domains.skills.router import router
    elif capability is PlatformCapability.MCP:
        from src.domains.user_mcp.router import router
    elif capability is PlatformCapability.TELEPHONY:
        from src.domains.telephony.router import router
    elif capability is PlatformCapability.MEETINGS:
        from src.domains.meetings.router import router
    elif capability is PlatformCapability.STT:
        from src.domains.voice.router import router
    elif capability is PlatformCapability.IMAGE_GENERATION:
        from src.domains.image_generation.options_router import router
    else:  # pragma: no cover - defensive
        raise AssertionError(f"no router mapped for {capability}")
    return router


ROUTE_ENFORCED = [
    capability for capability, spec in CAPABILITY_SPECS.items() if spec.route_enforced
]


def test_the_registry_declares_route_enforced_capabilities() -> None:
    # If this ever empties, the parametrized test below would pass vacuously.
    assert len(ROUTE_ENFORCED) >= 6


@pytest.mark.parametrize("capability", ROUTE_ENFORCED)
def test_each_route_enforced_capability_guards_its_router(
    capability: PlatformCapability,
) -> None:
    guarded = _guarded_capabilities(_router_for(capability))
    assert capability.value in guarded, (
        f"{capability.value} declares route_enforced=True but its router "
        "carries no require_capability dependency — the switch would enforce "
        "nothing."
    )


def test_speech_synthesis_is_service_enforced_not_route_enforced() -> None:
    # TTS has no route of its own — spoken answers are produced inside the
    # chat stream — so a router dependency would enforce nothing. The switch
    # lives at the single voice-synthesis chokepoint instead, and the
    # declaration says so rather than pretending.
    spec = CAPABILITY_SPECS[PlatformCapability.TTS]
    assert spec.route_enforced is False
    assert spec.service_enforced is True

    from src.domains.voice.router import router

    # The recording side (STT) does have routes, and they are guarded.
    assert "stt" in _guarded_capabilities(router)
