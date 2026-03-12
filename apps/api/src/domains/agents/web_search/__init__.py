"""
Web Search agent - Unified Triple Source Search.

Orchestrates Perplexity AI (synthesis), Brave Search (URLs), and Wikipedia (encyclopedia)
in parallel to provide comprehensive web search results.
"""

from src.domains.agents.web_search.catalogue_manifests import (
    unified_web_search_catalogue_manifest,
)

__all__ = ["unified_web_search_catalogue_manifest"]
