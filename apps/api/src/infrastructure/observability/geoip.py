"""
GeoIP resolver utility for IP geolocation.

Uses DB-IP Lite (free MMDB format) to resolve IP addresses to geographic data.
Lazy-loaded singleton pattern — the MMDB reader is initialized on first use.
Graceful degradation: if the DB file is missing, all lookups return None.

Phase: observability — User Analytics & Geolocation
Created: 2026-03-09
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import geoip2.database

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GeoIPResult:
    """Resolved geographic information for an IP address."""

    country: str  # ISO 3166-1 alpha-2 (e.g., "FR")
    city: str | None  # City name (may be None for some IPs)
    latitude: float
    longitude: float


class GeoIPResolver:
    """
    Lazy-loaded singleton GeoIP resolver.

    The MMDB reader is opened on the first resolve() call.
    If the DB file is missing or corrupted, the resolver logs a warning
    once and returns None for all subsequent lookups.
    Thread-safe for concurrent reads after initialization (MMDB is memory-mapped).
    """

    def __init__(self) -> None:
        self._reader: geoip2.database.Reader | None = None
        self._initialized: bool = False
        self._available: bool = False

    def _init_reader(self) -> None:
        """Initialize the MMDB reader (called once on first use)."""
        if self._initialized:
            return
        self._initialized = True

        from src.core.config import settings

        geoip_enabled = getattr(settings, "geoip_enabled", True)
        if not geoip_enabled:
            logger.info("geoip_disabled", reason="GEOIP_ENABLED=false")
            return

        db_path_str = settings.geoip_db_path
        db_path = Path(db_path_str)
        if not db_path.exists():
            logger.warning(
                "geoip_db_not_found",
                path=str(db_path),
                hint="GeoIP enrichment disabled. Download DB-IP Lite MMDB.",
            )
            return

        try:
            import geoip2.database

            self._reader = geoip2.database.Reader(str(db_path))
            self._available = True
            logger.info(
                "geoip_initialized",
                path=str(db_path),
                metadata_type=self._reader.metadata().database_type,
            )
        except Exception as exc:
            logger.error("geoip_init_failed", error=str(exc), path=str(db_path))

    def resolve(self, ip: str) -> GeoIPResult | None:
        """
        Resolve an IP address to geographic data.

        Returns None for private/loopback IPs, IPs not found in the database,
        or when the MMDB file is missing.
        """
        self._init_reader()
        if not self._available or self._reader is None:
            return None

        # Skip private, loopback, and link-local addresses
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return None
        except ValueError:
            return None

        try:
            response = self._reader.city(ip)
            country = response.country.iso_code or "??"
            city = response.city.name
            lat = response.location.latitude
            lon = response.location.longitude
            if lat is None or lon is None:
                return None
            return GeoIPResult(
                country=country,
                city=city,
                latitude=lat,
                longitude=lon,
            )
        except Exception:
            # geoip2.errors.AddressNotFoundError or other lookup failures
            return None

    def close(self) -> None:
        """Close the MMDB reader (called at app shutdown)."""
        if self._reader:
            self._reader.close()
            self._reader = None
            self._available = False
            self._initialized = False


# Module-level singleton
geoip_resolver = GeoIPResolver()
