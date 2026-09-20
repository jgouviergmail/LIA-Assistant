"""Where each module's Google Maps Platform spend is recorded — declared, never inferred.

The family is instance-paid (``cost_bearers.py``): Places, Routes, Geocoding,
Weather, Air quality, Pollen, Static Maps, Street View and Web Risk all run on
the deployment's ``GOOGLE_API_KEY``, and the owner's rule is absolute —
whatever the modality or the path, a euro the platform pays for a person is
traced, displayed, attributed and counted for that person (2026-09-19).

Accounting is **ambient**, exactly as for the model (``infrastructure/llm/
spend_roads.py``): a client records through the ``TrackingContext`` an
ancestor published, so the file that makes the call mentions no tracker.
Reading a file proves nothing; on 2026-09-19 the dev ledger held 3 020 Google
rows and not one outside a chat turn, while the heartbeat computed departure
advice on Routes, the briefing read Google Weather, a meeting reverse-geocoded
its place and two static-map proxies served billed images — each with no
tracker in sight, each dropped by a counter that « did nothing » without one.

So every module that IMPORTS a paid Google entry (a client, a relay, the
counter itself) names its road here, and :mod:`tests.unit.domains.google_api.
test_google_spend_road_completeness` walks the import graph and refuses an
omission, a stale entry, an ``ACCOUNTED`` module that opens no tracker and a
``CALLER`` whose accountant is not itself accounted. The vocabulary is the
ledger's, shared with the model's roads:

- :attr:`SpendRoad.TURN` — inside a turn, or under a voice host that published
  a tracker (the phone call, the live session): the ambient tracker records it.
- :attr:`SpendRoad.ACCOUNTED` — out of turn, opening its own ``TrackingContext``
  against the account that benefits.
- :attr:`SpendRoad.CALLER` — reached through a caller that is itself on a road,
  which :data:`CALLER_ROAD_ACCOUNTANTS` must NAME, so the graph terminates.

There is no ``INSTANCE`` road for this family: every Maps Platform call LIA
makes serves one person, and a module that could not name one would be a
defect, not a category.
"""

from __future__ import annotations

from typing import Final

from src.infrastructure.llm.spend_roads import SpendRoad

#: Modules whose import means a paid Google call may follow: the clients, the
#: relays that build them, and the counter itself. Posix paths under ``src``,
#: without the extension. The guard walks their importers.
PAID_GOOGLE_MODULES: Final[tuple[str, ...]] = (
    "domains/connectors/clients/google_places_client",
    "domains/connectors/clients/google_routes_client",
    "domains/connectors/clients/google_geocoding_helpers",
    "domains/connectors/clients/google_environment_client",
    "domains/connectors/clients/google_weather_client",
    "domains/connectors/clients/google_api_tracker",
    "domains/connectors/street_view",
    "domains/connectors/weather_provider",
    "infrastructure/security/web_risk",
    # The billed-image door: whoever serves a Google image through it is a
    # paid call site too.
    "domains/connectors/media_proxy_router",
)

#: Every module of ``src`` that imports a paid Google entry, and the road its
#: euros take. Adding an importer without adding it here fails the build;
#: leaving one here after removing the import fails too.
GOOGLE_SPEND_ROADS: Final[dict[str, SpendRoad]] = {
    # --- Inside a turn or a voice host: the ambient tracker records these ----
    "domains/agents/tools/environment_tools.py": SpendRoad.TURN,
    "domains/agents/tools/places_environment.py": SpendRoad.TURN,
    "domains/agents/tools/places_tools.py": SpendRoad.TURN,
    "domains/agents/tools/routes_tools.py": SpendRoad.TURN,
    "domains/agents/tools/url_screening.py": SpendRoad.TURN,
    "domains/agents/tools/weather_environment_enrichment.py": SpendRoad.TURN,
    "domains/agents/tools/weather_tools.py": SpendRoad.TURN,
    # Relays used by tools only: the ambient tracker is whoever runs the tool.
    "domains/connectors/street_view.py": SpendRoad.TURN,
    "infrastructure/security/web_risk.py": SpendRoad.TURN,
    # --- Out of turn, opening their own accounting --------------------------
    # The media proxies serve BILLED images to an authenticated browser; the
    # spend is counted where Google bills it and attributed to the turn that
    # built the URL when its signed run id is presented (``media_attribution``).
    "domains/connectors/media_proxy_router.py": SpendRoad.ACCOUNTED,
    # A meeting's place name, reverse-geocoded in the processing job.
    "domains/meetings/enrichment.py": SpendRoad.ACCOUNTED,
    # The person's own address, geocoded when they save it.
    "domains/users/geocoding.py": SpendRoad.ACCOUNTED,
    # --- Reached through a caller that accounts for it ----------------------
    "domains/briefing/fetchers.py": SpendRoad.CALLER,
    "domains/connectors/router.py": SpendRoad.CALLER,
    "domains/connectors/weather_provider.py": SpendRoad.CALLER,
    "domains/heartbeat/context_aggregator.py": SpendRoad.CALLER,
    "domains/heartbeat/context_sources.py": SpendRoad.CALLER,
}

#: For each ``CALLER`` module, the module(s) that open the tracker its calls
#: land in. Named rather than implied, so the road graph terminates on a real
#: road: a caller nobody names is indistinguishable from a spend nobody records.
#: A relay read from several surfaces names every one of them.
CALLER_ROAD_ACCOUNTANTS: Final[dict[str, tuple[str, ...]]] = {
    "domains/briefing/fetchers.py": ("domains/briefing/service.py",),
    # The Places photo proxy serves its image through the media router's door.
    "domains/connectors/router.py": ("domains/connectors/media_proxy_router.py",),
    "domains/connectors/weather_provider.py": (
        "domains/briefing/service.py",
        "infrastructure/proactive/runner.py",
    ),
    "domains/heartbeat/context_aggregator.py": ("infrastructure/proactive/runner.py",),
    "domains/heartbeat/context_sources.py": ("infrastructure/proactive/runner.py",),
}

#: The calls that OPEN an accounting: an ``ACCOUNTED`` module, or the
#: accountant of a ``CALLER``, must contain one of them as an AST call.
ACCOUNTING_DOORS: Final[frozenset[str]] = frozenset(
    {"TrackingContext", "media_spend_context", "out_of_turn_spend"}
)

#: Modules that import a paid Google entry and make NO paid call. Each entry is
#: an argument, never a convenience: it must say what the module does with it.
NOT_A_PAID_CALL: Final[dict[str, str]] = {
    "domains/connectors/clients/__init__.py": (
        "Re-exports the client classes for the connector layer; builds nothing."
    ),
    "domains/connectors/clients/registry.py": (
        "Registers client CLASSES by connector type so a tool can be handed one; "
        "the tool that calls it runs under the turn's tracker."
    ),
    "infrastructure/security/__init__.py": (
        "Re-exports the Web Risk screening function for the security package; calls nothing."
    ),
    "infrastructure/startup/shutdown.py": (
        "Closes the shared geocoding client at teardown. Opening nothing is the "
        "whole point of this module."
    ),
}


__all__ = [
    "ACCOUNTING_DOORS",
    "CALLER_ROAD_ACCOUNTANTS",
    "GOOGLE_SPEND_ROADS",
    "NOT_A_PAID_CALL",
    "PAID_GOOGLE_MODULES",
    "SpendRoad",
]
