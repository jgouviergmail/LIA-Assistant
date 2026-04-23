"""Briefing domain — Today dashboard orchestration.

Public surface: only the router is exposed for FastAPI wiring.
Internal modules (service, fetchers, llm, formatters) stay private.
"""

from src.domains.briefing.router import router as briefing_router

__all__ = ["briefing_router"]
