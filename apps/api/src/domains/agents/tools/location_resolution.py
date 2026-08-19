"""User-location resolution for LangChain tools and nodes.

The single place that answers "where is the user" for every location-aware
capability: the places/weather/routes tools, the skill runner's prompt
context and — by absence of a browser context — scheduled actions. Extracted
from ``runtime_helpers.py`` (2026-08-16, ADR-219) when the sources grew to
three; ``runtime_helpers`` keeps the generic runtime plumbing.

Three sources, one doctrine:

- **browser**: the live position shipped with the request
  (``__browser_context``), zero I/O;
- **last_known**: the opt-in persisted position (ADR-073, generalized by
  ADR-219) — used only while fresh, and always carrying ``as_of`` so the
  consumer can state its age instead of presenting a dated point as the
  current one;
- **home**: the configured home address, the final fallback.

Phrase-driven priorities live in :func:`resolve_location`; the pure implicit
cascade (browser > last_known > home) is :func:`resolve_implicit_location`.
"""

from datetime import datetime
from typing import Any, NamedTuple

from langchain.tools import ToolRuntime

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.runtime_helpers import parse_user_id
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ResolvedLocation(NamedTuple):
    """Resolved location data for tools (weather, places).

    ``as_of`` is set only for ``source == "last_known"``: a persisted position
    is honest ONLY when its age travels with it, so the consumer can state
    "as of <time>" instead of presenting a dated point as the current one.
    """

    lat: float
    lon: float
    source: str  # "browser", "last_known", "home", "explicit"
    address: str | None = None
    as_of: datetime | None = None


async def get_browser_geolocation(
    runtime: ToolRuntime[LiaRuntimeContext | None, Any],
) -> ResolvedLocation | None:
    """
    Get browser geolocation from runtime config.

    The browser context is passed from frontend through ChatRequest.context
    and propagated to RunnableConfig.configurable["__browser_context"].

    Args:
        runtime: ToolRuntime containing config with browser context

    Returns:
        ResolvedLocation if geolocation available, None otherwise

    Example:
        >>> geoloc = await get_browser_geolocation(runtime)
        >>> if geoloc:
        ...     print(f"User is at {geoloc.lat}, {geoloc.lon}")
    """
    try:
        browser_context = (runtime.config.get("configurable") or {}).get("__browser_context")
        if not browser_context:
            return None

        # Handle both BrowserContext object and dict
        geolocation = None
        if hasattr(browser_context, "geolocation"):
            geolocation = browser_context.geolocation
        elif isinstance(browser_context, dict):
            geolocation = browser_context.get("geolocation")

        if not geolocation:
            return None

        # Extract coordinates (handle both object and dict)
        if hasattr(geolocation, "lat"):
            lat = geolocation.lat
            lon = geolocation.lon
        else:
            lat = geolocation.get("lat")
            lon = geolocation.get("lon")

        if lat is None or lon is None:
            return None

        return ResolvedLocation(
            lat=float(lat),
            lon=float(lon),
            source="browser",
            address=None,
        )

    except Exception as e:
        logger.warning(
            "get_browser_geolocation_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def get_user_home_location(
    runtime: ToolRuntime[LiaRuntimeContext | None, Any],
) -> ResolvedLocation | None:
    """
    Get user's configured home location from database (decrypted).

    Retrieves the encrypted home location from the User model and decrypts it
    for use in location-aware tools.

    Args:
        runtime: ToolRuntime containing user_id in config

    Returns:
        ResolvedLocation if home location configured, None otherwise

    Example:
        >>> home = await get_user_home_location(runtime)
        >>> if home:
        ...     print(f"Home is at {home.address}")
    """
    try:
        user_id_raw = (runtime.config.get("configurable") or {}).get("user_id")
        if not user_id_raw:
            logger.warning("get_user_home_location_no_user_id")
            return None

        user_id = parse_user_id(user_id_raw)

        from src.domains.users.service import UserService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            user_service = UserService(db)
            home_location = await user_service.get_home_location(user_id)

            if not home_location:
                logger.info(
                    "get_user_home_location_not_configured",
                    user_id=str(user_id),
                )
                return None

            # No PII at INFO: home address/coordinates are contents (DEBUG only)
            logger.info(
                "get_user_home_location_found",
                user_id=str(user_id),
                has_address=bool(home_location.address),
            )
            logger.debug(
                "get_user_home_location_details",
                user_id=str(user_id),
                address_preview=home_location.address[:30] if home_location.address else None,
                lat=home_location.lat,
                lon=home_location.lon,
            )
            return ResolvedLocation(
                lat=home_location.lat,
                lon=home_location.lon,
                source="home",
                address=home_location.address,
            )

    except Exception as e:
        logger.warning(
            "get_user_home_location_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def get_user_last_known_location(
    runtime: ToolRuntime[LiaRuntimeContext | None, Any],
) -> ResolvedLocation | None:
    """
    Get the user's persisted last-known location (opt-in, fresh only).

    Reads the encrypted last-known position written by the browser pushes
    (chat messages, the global sync hook) and returns it as a resolution
    source, enforcing both the per-user opt-in (``use_last_known_location``)
    and the freshness TTL (a stale position is worse than the home fallback).

    Args:
        runtime: ToolRuntime containing user_id in config.

    Returns:
        ResolvedLocation with ``source="last_known"`` and ``as_of`` set to the
        position's capture time, or None when the user opted out, nothing
        fresh is stored, or any lookup step fails (degrade, never raise).
    """
    try:
        user_id_raw = (runtime.config.get("configurable") or {}).get("user_id")
        if not user_id_raw:
            return None

        user_id = parse_user_id(user_id_raw)

        from src.domains.users.models import User
        from src.domains.users.user_location_service import UserLocationService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None or not user.use_last_known_location:
                return None

            last_known = await UserLocationService(db).get_last_known_location(user)
            if last_known is None:
                return None
            if last_known.stale:
                logger.info(
                    "get_user_last_known_location_stale",
                    user_id=str(user_id),
                )
                return None

            # No PII at INFO: coordinates are contents (source + age only).
            logger.info(
                "get_user_last_known_location_found",
                user_id=str(user_id),
            )
            return ResolvedLocation(
                lat=last_known.lat,
                lon=last_known.lon,
                source="last_known",
                address=None,
                as_of=last_known.updated_at,
            )

    except Exception as e:
        logger.warning(
            "get_user_last_known_location_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def resolve_implicit_location(
    runtime: ToolRuntime[LiaRuntimeContext | None, Any],
) -> ResolvedLocation | None:
    """
    Resolve the user's implicit location: browser > last_known > home.

    The shared cascade for callers that need *a* position without any
    location phrase to interpret (distance computation in the places tools,
    trip origins in the routes tools, the implicit branch of
    :func:`resolve_location`). Each source is only consulted when the
    previous one is absent, so a live browser position costs zero database
    reads.

    Args:
        runtime: ToolRuntime with config and user context.

    Returns:
        The first available source, or None when nothing is configured.
    """
    browser_geoloc = await get_browser_geolocation(runtime)
    if browser_geoloc:
        return browser_geoloc

    last_known = await get_user_last_known_location(runtime)
    if last_known:
        return last_known

    return await get_user_home_location(runtime)


async def resolve_location(
    runtime: ToolRuntime[LiaRuntimeContext | None, Any],
    user_message: str,
    language: str = "fr",
) -> tuple[ResolvedLocation | None, str | None]:
    """
    Resolve location for tools based on user message and available sources.

    Main location resolution function that combines phrase detection with
    location source lookup. Priority depends on detected location type:

    - HOME: Home location > Browser geolocation > Fallback message
      (last_known never answers a "home" reference: a position captured on
      the road says nothing about home)
    - CURRENT / QUERY: Browser geolocation > Last-known (fresh, opt-in,
      ``as_of`` carried so the answer can state its age) > Fallback message
    - EXPLICIT: Return None (let tool geocode the explicit location)
    - NONE: Browser > Last-known (fresh, opt-in) > Home > None (silent)

    Args:
        runtime: ToolRuntime with config and user context
        user_message: User's message to analyze for location references
        language: Language code for phrase detection (default: "fr")

    Returns:
        Tuple of (ResolvedLocation | None, fallback_message | None)
        - If location found: (location, None)
        - If location needed but not found: (None, fallback_message)
        - If explicit location: (None, None) - let tool handle geocoding

    Example:
        >>> location, fallback = await resolve_location(runtime, "météo chez moi", "fr")
        >>> if location:
        ...     weather = await get_weather(location.lat, location.lon)
        >>> elif fallback:
        ...     return fallback  # Ask user for location
    """
    from src.domains.agents.utils.i18n_location import (
        LocationType,
        detect_location_type,
        get_fallback_message,
    )

    location_type = detect_location_type(user_message, language)

    logger.debug(
        "resolve_location_type_detected",
        location_type=location_type.value,
        user_message_preview=user_message[:50] if user_message else "",
        language=language,
    )

    # Each branch loads only the sources it can actually use — a live browser
    # position (no I/O) short-circuits every database read.
    browser_geoloc = await get_browser_geolocation(runtime)

    match location_type:
        case LocationType.HOME:
            # User explicitly references home ("chez moi", "at home")
            # Priority: home > browser > fallback. last_known stays out: a
            # position captured on the road says nothing about home.
            home_location = await get_user_home_location(runtime)
            if home_location:
                logger.info(
                    "resolve_location_using_home",
                    has_home=True,
                )
                return (home_location, None)

            if browser_geoloc:
                logger.info(
                    "resolve_location_home_fallback_to_browser",
                    reason="No home configured, using browser geolocation",
                )
                return (browser_geoloc, None)

            # No location available for HOME reference
            logger.warning(
                "resolve_location_home_no_source",
                has_browser=False,
                has_home=False,
            )
            return (None, get_fallback_message(language))

        case LocationType.CURRENT | LocationType.QUERY:
            # User references or asks about their current position ("nearby",
            # "around me", "where am I"). Priority: browser > fresh last_known
            # (its ``as_of`` lets the answer state the position's age — a
            # dated point presented as current would be a lie) > fallback.
            if browser_geoloc:
                logger.info("resolve_location_using_browser")
                return (browser_geoloc, None)

            last_known = await get_user_last_known_location(runtime)
            if last_known:
                logger.info("resolve_location_using_last_known")
                return (last_known, None)

            # No live nor persisted position for CURRENT/QUERY reference
            logger.warning("resolve_location_current_no_source")
            return (None, get_fallback_message(language))

        # Note: LocationType.EXPLICIT was removed in 2026-01 cleanup.
        # Explicit location extraction is now handled by the planner via the
        # 'location' parameter in tool manifests. When planner provides location,
        # resolve_location() is not called at all.

        case LocationType.NONE:
            # No location reference detected - use the shared implicit cascade
            # (browser > last_known > home), silent when nothing is available.
            implicit = await resolve_implicit_location(runtime)
            if implicit:
                logger.debug(
                    "resolve_location_implicit",
                    source=implicit.source,
                )
                return (implicit, None)

            # No implicit location available - silent (tools may have their own fallback)
            logger.debug("resolve_location_implicit_none")
            return (None, None)

    # All LocationType members are matched above; kept for type completeness.
    return (None, None)


__all__ = [
    "ResolvedLocation",
    "get_browser_geolocation",
    "get_user_home_location",
    "get_user_last_known_location",
    "resolve_implicit_location",
    "resolve_location",
]
