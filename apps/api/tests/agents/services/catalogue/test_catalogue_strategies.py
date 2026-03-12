"""
Tests for Phase 2.3 - SmartCatalogueService Strategy Pattern.

These tests verify that filtering strategies are correctly implemented
and can be instantiated without errors.
"""

from src.domains.agents.services.catalogue.strategies import (
    NormalFilteringStrategy,
    PanicFilteringStrategy,
)


class TestCatalogueStrategiesInstantiation:
    """Test that all filtering strategies can be instantiated."""

    def test_normal_filtering_strategy_instantiation(self):
        """Test NormalFilteringStrategy can be instantiated."""
        strategy = NormalFilteringStrategy(service=None)  # type: ignore
        assert strategy is not None
        assert strategy.service is None

    def test_panic_filtering_strategy_instantiation(self):
        """Test PanicFilteringStrategy can be instantiated."""
        normal_strategy = NormalFilteringStrategy(service=None)  # type: ignore
        strategy = PanicFilteringStrategy(
            service=None,  # type: ignore
            normal_strategy=normal_strategy,
        )
        assert strategy is not None
        assert strategy.service is None
        assert strategy.normal_strategy is normal_strategy


class TestSmartCatalogueServiceIntegration:
    """Test SmartCatalogueService integrates with strategies correctly."""

    def test_smart_catalogue_service_has_strategies(self):
        """Test that SmartCatalogueService has normal and panic strategies."""
        from src.domains.agents.services.smart_catalogue_service import (
            get_smart_catalogue_service,
        )

        service = get_smart_catalogue_service()
        assert hasattr(service, "normal_strategy")
        assert hasattr(service, "panic_strategy")
        assert isinstance(service.normal_strategy, NormalFilteringStrategy)
        assert isinstance(service.panic_strategy, PanicFilteringStrategy)

    def test_strategies_have_service_reference(self):
        """Test that strategies have service reference for helper methods."""
        from src.domains.agents.services.smart_catalogue_service import (
            get_smart_catalogue_service,
        )

        service = get_smart_catalogue_service()
        assert service.normal_strategy.service is service
        assert service.panic_strategy.service is service

    def test_panic_strategy_has_normal_strategy_reference(self):
        """Test that panic strategy has reference to normal strategy."""
        from src.domains.agents.services.smart_catalogue_service import (
            get_smart_catalogue_service,
        )

        service = get_smart_catalogue_service()
        assert service.panic_strategy.normal_strategy is service.normal_strategy
