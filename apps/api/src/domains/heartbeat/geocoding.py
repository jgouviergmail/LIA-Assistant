"""Compatibility shim — geocoding moved to ``connectors.geocoding`` (Lot 6).

The function lived here historically; briefing imports this path. Moving the
implementation to the neutral connectors home broke the
heartbeat<->interests runtime cycle (F009) introduced by the interests
locality resolution. One-way re-export only.
"""

from src.domains.connectors.geocoding import resolve_city_name as resolve_city_name
