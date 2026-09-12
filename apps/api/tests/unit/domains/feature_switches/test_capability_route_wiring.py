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


def _names_in(dependencies: object) -> set[str]:
    """Capability names carried by one dependency list."""
    names = set()
    for dependency in dependencies or []:
        function_name = getattr(getattr(dependency, "dependency", None), "__name__", "")
        if function_name.startswith("require_capability_"):
            names.add(function_name.removeprefix("require_capability_"))
    return names


def _guarded_capabilities(router: object) -> set[str]:
    """Capability names guarded on a router — on the router itself or on a route.

    A router-wide dependency is the usual shape, but not always the right one:
    ATTACHMENTS guards the UPLOAD alone since ADR-279, because switching uploads
    off must not also close reading and deleting the files LIA already produced.
    A guard is a guard wherever it is declared; what this test refuses is a
    capability that declares ``route_enforced`` and enforces nothing anywhere.
    """
    names = _names_in(getattr(router, "dependencies", []))
    for route in getattr(router, "routes", []):
        names |= _names_in(getattr(route, "dependencies", []))
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
    # B7 — the features whose router IS the ability (habits and the heartbeat
    # moved to the act with the ADR-280 amendment of 2026-09-11).
    elif capability is PlatformCapability.WORKBOARD:
        from src.domains.workboard.router import router
    elif capability is PlatformCapability.JOURNALS:
        from src.domains.journals.router import router
    elif capability is PlatformCapability.PEERS:
        from src.domains.peers.router import router
    elif capability is PlatformCapability.PSYCHE:
        from src.domains.psyche.router import router
    elif capability is PlatformCapability.CHANNELS:
        from src.domains.channels.router import router
    elif capability is PlatformCapability.OPEN_LOOPS:
        from src.domains.open_loops.router import router
    # ADR-282 — guarded at the ROUTE like uploads: keeping is the act, the
    # kept answers are the record.
    elif capability is PlatformCapability.BOOKMARKS:
        from src.domains.bookmarks.router import router
    else:  # pragma: no cover - defensive
        raise AssertionError(f"no router mapped for {capability}")
    return router


ROUTE_ENFORCED = [
    capability for capability, spec in CAPABILITY_SPECS.items() if spec.route_enforced
]


def test_the_registry_declares_route_enforced_capabilities() -> None:
    # If this ever empties, the parametrized test below would pass vacuously.
    assert len(ROUTE_ENFORCED) >= 14


@pytest.mark.parametrize("capability", ROUTE_ENFORCED)
def test_each_route_enforced_capability_guards_its_router(
    capability: PlatformCapability,
) -> None:
    guarded = _guarded_capabilities(_router_for(capability))
    assert capability.value in guarded, (
        f"{capability.value} declares route_enforced=True but neither its "
        "router nor any of its routes carries a require_capability dependency "
        "— the switch would enforce nothing."
    )


def test_uploads_are_guarded_at_the_ROUTE_not_at_the_router() -> None:
    """ADR-279: a switch that removes an ability must not remove access to what
    that ability already produced.

    The guard used to sit on the attachments router, so switching uploads off
    also closed reading and deleting — including the images and documents LIA
    produced, which the person can no longer create but can still legitimately
    keep, open and remove.
    """
    from src.domains.attachments.router import router

    assert _names_in(router.dependencies) == set()
    guarded = {
        route.path
        for route in router.routes
        if "attachments" in _names_in(getattr(route, "dependencies", []))
    }
    assert guarded == {"/attachments/upload"}, guarded


def test_habits_are_guarded_at_the_two_ACT_routes_only() -> None:
    """ADR-280 amendment (2026-09-11): the habits capability is an act —
    learning at night, consuming at every tick — guarded where it acts.
    On the router only the two routes that ACT carry it; reading,
    correcting and deleting what was learned stay open, like the memories."""
    from src.domains.habits.router import router

    assert _names_in(router.dependencies) == set()
    guarded = {
        route.path
        for route in router.routes
        if "habits" in _names_in(getattr(route, "dependencies", []))
    }
    assert guarded == {"/habits/recompute", "/habits/presence"}, guarded


def test_the_heartbeat_record_is_never_gated_on_the_switch() -> None:
    """Same amendment: the heartbeat acts in its sweeps, never through a
    route — settings, history, offers and feedback are what the person
    reads and changes, capability on or off. Measured on docker dev
    (2026-09-11): the router still carried the guard and answered 403."""
    from src.domains.heartbeat.router import router

    assert _guarded_capabilities(router) == set()


def test_the_generated_gallery_is_not_gated_on_uploads() -> None:
    """It lists what LIA PRODUCED: an instance that offers neither image nor
    document generation simply lists nothing."""
    from src.domains.attachments.gallery_router import router

    assert _guarded_capabilities(router) == set()


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
