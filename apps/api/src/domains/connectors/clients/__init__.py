"""
API clients for external connectors.

LOT 5.4: Added GoogleCalendarClient for calendar operations.
LOT 9: Added GoogleDriveClient, GoogleTasksClient for document and task management.
LOT 10: Added OpenWeatherMapClient and WikipediaClient for weather and knowledge.
LOT 11: Added PerplexityClient for internet search and GooglePlacesClient for location services.
LOT 12: Added GoogleRoutesClient for directions and route calculations.
Sprint 14: Added BaseOAuthClient super-abstraction.
Sprint 15: Added ClientRegistry for auto-discovery.
"""

from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.google_calendar_client import (
    GoogleCalendarClient,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.google_places_client import GooglePlacesClient
from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.clients.registry import (
    ClientRegistry,
    get_client_for_connector,
)
from src.domains.connectors.clients.wikipedia_client import WikipediaClient

__all__ = [
    # Base classes
    "BaseOAuthClient",
    # Registry
    "ClientRegistry",
    "get_client_for_connector",
    # Google OAuth clients
    "GooglePeopleClient",
    "GoogleGmailClient",
    "GoogleCalendarClient",
    "GoogleDriveClient",
    "GoogleTasksClient",
    # Google API Key clients (global key, not per-user)
    "GooglePlacesClient",
    "GoogleRoutesClient",
    # External API Key clients
    "BraveSearchClient",
    "OpenWeatherMapClient",
    "PerplexityClient",
    "WikipediaClient",
]
