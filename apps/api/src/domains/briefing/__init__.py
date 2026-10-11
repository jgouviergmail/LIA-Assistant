"""Briefing domain — Today dashboard orchestration.

Public surface: only the router is exposed for FastAPI wiring.
The public router is loaded on demand so importing schemas, constants or
preferences does not initialize routes and tool integrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

    from src.domains.briefing.router import router as briefing_router

__all__ = ["briefing_router"]


def __getattr__(name: str) -> APIRouter:
    if name != "briefing_router":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from src.domains.briefing.router import router

    return router
