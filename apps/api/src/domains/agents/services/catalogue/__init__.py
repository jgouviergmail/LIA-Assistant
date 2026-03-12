"""
Catalogue Services Package.

This package contains SmartCatalogueService and its filtering strategies.

Architecture:
- SmartCatalogueService: Orchestrates catalogue filtering (smart_catalogue_service.py)
- FilteringStrategy (Protocol): Interface for all strategies (strategies/base_strategy.py)
- NormalFilteringStrategy: Standard intelligent filtering (strategies/normal_filtering.py)
- PanicFilteringStrategy: Expanded catalogue for failed planning (strategies/panic_filtering.py)

This package follows modern Python conventions: imports are done explicitly
where needed rather than re-exported through __init__.py.

Main components (import directly from their modules):
- SmartCatalogueService: src.domains.agents.services.smart_catalogue_service
- Strategies: src.domains.agents.services.catalogue.strategies
"""
