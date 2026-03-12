"""
Catalogue Filtering Strategies Package.

This package contains concrete filtering strategy implementations for
SmartCatalogueService.

Strategies:
1. NormalFilteringStrategy - Standard intelligent filtering (96% token reduction)
2. PanicFilteringStrategy - Expanded catalogue when planning fails (anti-false-negative)
"""

from src.domains.agents.services.catalogue.strategies.base_strategy import (
    FilteringStrategy,
)
from src.domains.agents.services.catalogue.strategies.normal_filtering import (
    NormalFilteringStrategy,
)
from src.domains.agents.services.catalogue.strategies.panic_filtering import (
    PanicFilteringStrategy,
)

__all__ = [
    "FilteringStrategy",
    "NormalFilteringStrategy",
    "PanicFilteringStrategy",
]
