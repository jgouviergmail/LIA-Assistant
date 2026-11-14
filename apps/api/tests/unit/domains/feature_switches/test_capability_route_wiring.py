"""Every route-enforced capability really guards its router.

The registry says a capability is ``route_enforced``; this checks the claim
against the ROUTERS THEMSELVES. A declaration nobody wired would be the worst
kind of switch: visible in the admin panel, flipped by an operator, and
enforcing nothing.

Walking the real router objects (rather than grepping source) is what makes
this survive a refactor: move a route to another file and the test follows.
"""

from __future__ import annotations

import importlib

import pytest

from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability
from tests._routes import served_routes

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
    for route in served_routes(router):
        names |= _names_in(getattr(route, "dependencies", []))
    return names


# The module holding the router each route-enforced capability is expected to
# guard — a table, so the next capability is one line rather than one more
# branch of a dispatch that had reached a strict complexity of 19.
_ROUTER_MODULES: dict[PlatformCapability, str] = {
    PlatformCapability.ATTACHMENTS: "src.domains.attachments.router",
    PlatformCapability.RAG_SPACES: "src.domains.rag_spaces.router",
    PlatformCapability.SKILLS: "src.domains.skills.router",
    PlatformCapability.MCP: "src.domains.user_mcp.router",
    PlatformCapability.TELEPHONY: "src.domains.telephony.router",
    PlatformCapability.MEETINGS: "src.domains.meetings.router",
    PlatformCapability.SMS: "src.domains.sms.router",
    PlatformCapability.STT: "src.domains.voice.router",
    PlatformCapability.IMAGE_GENERATION: "src.domains.image_generation.options_router",
    # B7 — the features whose router IS the ability (habits and the heartbeat
    # moved to the act with the ADR-280 amendment of 2026-09-11).
    PlatformCapability.WORKBOARD: "src.domains.workboard.router",
    PlatformCapability.JOURNALS: "src.domains.journals.router",
    PlatformCapability.PEERS: "src.domains.peers.router",
    PlatformCapability.PSYCHE: "src.domains.psyche.router",
    PlatformCapability.CHANNELS: "src.domains.channels.router",
    PlatformCapability.OPEN_LOOPS: "src.domains.open_loops.router",
    # ADR-282 — guarded at the ROUTE like uploads: keeping is the act, the
    # kept answers are the record.
    PlatformCapability.BOOKMARKS: "src.domains.bookmarks.router",
    # ADR-299 — the live voice mode: the routes ARE the ability (credential
    # minting, the session record); a delegated turn goes through the chat's door.
    PlatformCapability.LIVE: "src.domains.live.router",
    # ADR-321 — sending by e-mail: the router IS the ability, and it keeps no
    # record (the file stays in the gallery, the answer in the chat).
    PlatformCapability.EMAIL_SHARE: "src.domains.email_share.router",
    PlatformCapability.SKILL_LIBRARY: "src.domains.skill_library.router",
    # ADR-324 — the radio's routes ARE the listening and its settings.
    PlatformCapability.RADIO: "src.domains.radio.router",
    PlatformCapability.AVATAR: "src.domains.avatars.router",
    PlatformCapability.WORLD: "src.domains.world.router",
    # ADR-369 — the workbench's routes ARE the ability; the connectors and
    # what they hold stay untouched when it is off.
    PlatformCapability.WORKBENCH: "src.domains.workbench.router",
    # ADR-372 — a click asks a model from those screens: the routes are that ability.
    PlatformCapability.TOOL_ASSISTS: "src.domains.tool_assists.router",
    # ADR-386 — the public address IS the ability; the routines and the calls
    # already accepted stay readable (the secret's route carries it too).
    PlatformCapability.ROUTINE_WEBHOOKS: "src.domains.scheduled_actions.webhook_router",
    # Guarded at the ACT and on the routes that are acts (recompute, presence).
    PlatformCapability.HABITS: "src.domains.habits.router",
    # Guarded at the synthesis chokepoint and on the routes that speak a sample.
    PlatformCapability.TTS: "src.domains.voice.lia_voices_router",
}


def _router_for(capability: PlatformCapability) -> object:
    """The router each route-enforced capability is expected to guard (imported lazily)."""
    module = _ROUTER_MODULES.get(capability)
    assert module is not None, f"no router mapped for {capability}"
    return importlib.import_module(module).router


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
        for route in served_routes(router)
        if "attachments" in _names_in(getattr(route, "dependencies", []))
    }
    # The doors that put a file IN — an upload, a copy of a knowledge document,
    # of a kept answer, of a generated file — and nothing else: reading and
    # deleting stay open.
    assert guarded == {
        "/attachments/upload",
        "/attachments/from-knowledge-document",
        "/attachments/from-bookmark",
        "/attachments/from-generated",
    }, guarded


def test_habits_are_guarded_at_the_two_ACT_routes_only() -> None:
    """ADR-280 amendment (2026-09-11): the habits capability is an act —
    learning at night, consuming at every tick — guarded where it acts.
    On the router only the two routes that ACT carry it; reading,
    correcting and deleting what was learned stay open, like the memories."""
    from src.domains.habits.router import router

    assert _names_in(router.dependencies) == set()
    guarded = {
        route.path
        for route in served_routes(router)
        if "habits" in _names_in(getattr(route, "dependencies", []))
    }
    assert guarded == {"/habits/recompute", "/habits/presence"}, guarded
    # Guarded at the act AND on those routes: the declaration says both.
    spec = CAPABILITY_SPECS[PlatformCapability.HABITS]
    assert spec.route_enforced is True and spec.service_enforced is True


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


def test_speech_synthesis_is_enforced_at_its_chokepoint_and_on_the_routes_that_speak() -> None:
    # A spoken answer is produced inside the chat stream, so the switch lives
    # at the single voice-synthesis chokepoint. Two routes speak too — a voice
    # sample, a text read aloud — and carry the guard: the declaration says
    # both, since the panel prints it.
    spec = CAPABILITY_SPECS[PlatformCapability.TTS]
    assert spec.route_enforced is True
    assert spec.service_enforced is True

    from src.domains.voice.lia_voices_router import router as voices
    from src.domains.voice.router import router

    assert "tts" in _guarded_capabilities(voices)
    # The recording side (STT) does have routes, and they are guarded.
    assert "stt" in _guarded_capabilities(router)


def test_a_telephony_key_is_removed_whatever_the_switch_says() -> None:
    """ADR-280 amendment (2026-11-12): a switch removes the capability, never
    the record. The key a person stored is theirs: removing it — the agent LIA
    created at the vendor, then the connector — goes through a door the switch
    does not close, as a Live key goes through the connectors' own route.
    Everything else on ``/telephony`` IS the ability and stays guarded."""
    from src.domains.telephony import router as telephony

    record_door = {
        (method, route.path)
        for route in served_routes(telephony.record_router)
        for method in route.methods or ()
    }
    # What the person already HAS — a key, a number, a history — is read and
    # taken back whatever the switch says; and a call placed before it was
    # flipped still reports its end, or its account would be lost.
    assert record_door == {
        ("DELETE", "/telephony/connector"),
        ("GET", "/telephony/calls"),
        ("GET", "/telephony/calls/{call_id}"),
        ("GET", "/telephony/identity"),
        ("DELETE", "/telephony/identity/number"),
        ("POST", "/telephony/webhook"),
    }, record_door
    assert _guarded_capabilities(telephony.record_router) == set()

    assert "telephony" in _names_in(telephony.router.dependencies)
    guarded = {
        (method, route.path)
        for route in served_routes(telephony.router)
        for method in route.methods or ()
    }
    assert guarded.isdisjoint(record_door)
    # Whatever places a call, creates something at the vendor or sets up the
    # next call is the capability: declaring a number, verifying it by a call,
    # the preferences of owner calls, activating a key.
    assert guarded == {
        ("POST", "/telephony/connector/validate-key"),
        ("POST", "/telephony/connector/activate"),
        ("PUT", "/telephony/identity/number"),
        ("POST", "/telephony/identity/verify"),
        ("POST", "/telephony/identity/confirm"),
        ("PATCH", "/telephony/identity"),
    }, guarded
