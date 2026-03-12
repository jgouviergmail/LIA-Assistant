"""
Memories domain for long-term user psychological profiling.

Provides API endpoints for managing user memories with:
- Emotional profiling (weight, triggers, nuances)
- Category-based organization
- GDPR compliance (export, delete all)
"""

from src.domains.memories.router import router
from src.domains.memories.schemas import (
    MemoryCategoriesResponse,
    MemoryCategoryInfo,
    MemoryCreate,
    MemoryDeleteAllResponse,
    MemoryExportResponse,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)

__all__ = [
    "router",
    "MemoryCreate",
    "MemoryUpdate",
    "MemoryResponse",
    "MemoryListResponse",
    "MemoryExportResponse",
    "MemoryDeleteAllResponse",
    "MemoryCategoryInfo",
    "MemoryCategoriesResponse",
]
