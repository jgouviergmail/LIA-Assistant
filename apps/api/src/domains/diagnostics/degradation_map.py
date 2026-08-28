"""Declared capability degradations per circuit-breaker service.

Alternatives are NEVER invented: an entry exists only where a real substitute
capability exists in the platform (both web-search providers, both weather
providers). An open breaker with no entry is still reported — capability =
the service name, alternative None. Whether the user can actually use the
alternative (connector configured, capability enabled) stays the existing
catalogue's authority; the advisor only suggests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakerDegradation:
    """How one open circuit breaker translates into a capability degradation."""

    capability: str
    alternative: str | None


#: Breaker service name → declared degradation. Keys are the REAL names used
#: at get_circuit_breaker call sites (connector clients use ConnectorType
#: values as service names).
BREAKER_DEGRADATIONS: dict[str, BreakerDegradation] = {
    "brave_search": BreakerDegradation(capability="web_search", alternative="perplexity"),
    "perplexity": BreakerDegradation(capability="web_search", alternative="brave_search"),
    "openweathermap": BreakerDegradation(capability="weather", alternative="google_weather"),
    "google_weather": BreakerDegradation(capability="weather", alternative="openweathermap"),
    "browser_cdp": BreakerDegradation(capability="browser", alternative=None),
}


def assert_degradation_map_completeness() -> None:
    """Refuse a map whose alternatives name unknown connector services.

    Raises:
        AssertionError: An alternative references no ConnectorType value.
    """
    from src.domains.connectors.models import ConnectorType

    known_services = {member.value for member in ConnectorType}
    for service, entry in BREAKER_DEGRADATIONS.items():
        assert entry.capability, f"{service}: empty capability"
        if entry.alternative is not None:
            assert (
                entry.alternative in known_services
            ), f"{service}: alternative '{entry.alternative}' is not a ConnectorType value"
