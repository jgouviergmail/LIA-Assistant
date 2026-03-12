"""
Google API Domain.

Handles tracking and pricing for Google Maps Platform APIs:
- Places API (search, details, autocomplete, photos)
- Routes API (directions, distance matrix)
- Geocoding API
- Static Maps API

Components:
- models.py: SQLAlchemy models (GoogleApiPricing, GoogleApiUsageLog)
- schemas.py: Pydantic schemas for API
- repository.py: Database access layer
- pricing_service.py: Pricing cache and cost calculation
- service.py: Usage tracking service for non-chat contexts

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from src.domains.google_api.models import GoogleApiPricing, GoogleApiUsageLog

__all__ = [
    "GoogleApiPricing",
    "GoogleApiUsageLog",
]
