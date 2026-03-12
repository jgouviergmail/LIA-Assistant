"""Brave Search agent - Web and News search via Brave Search API."""

from src.domains.agents.brave.catalogue_manifests import (
    brave_news_catalogue_manifest,
    brave_search_catalogue_manifest,
)

__all__ = [
    "brave_search_catalogue_manifest",
    "brave_news_catalogue_manifest",
]
