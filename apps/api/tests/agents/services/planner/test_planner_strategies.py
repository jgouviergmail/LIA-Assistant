"""
Tests for Phase 2.2 - SmartPlannerService Strategy Pattern.

These tests verify that planning strategies are correctly implemented
and can be instantiated without errors.
"""

from src.domains.agents.services.planner.strategies import (
    CrossDomainBypassStrategy,
    MultiDomainStrategy,
    ReferenceBypassStrategy,
    SingleDomainStrategy,
)


class TestPlannerStrategiesInstantiation:
    """Test that all planning strategies can be instantiated."""

    def test_reference_bypass_strategy_instantiation(self):
        """Test ReferenceBypassStrategy can be instantiated."""
        strategy = ReferenceBypassStrategy()
        assert strategy is not None

    def test_cross_domain_bypass_strategy_instantiation(self):
        """Test CrossDomainBypassStrategy can be instantiated."""
        strategy = CrossDomainBypassStrategy()
        assert strategy is not None

    def test_single_domain_strategy_instantiation(self):
        """Test SingleDomainStrategy can be instantiated."""
        strategy = SingleDomainStrategy(service=None)
        assert strategy is not None

    def test_multi_domain_strategy_instantiation(self):
        """Test MultiDomainStrategy can be instantiated."""
        strategy = MultiDomainStrategy(service=None)
        assert strategy is not None


class TestSmartPlannerServiceIntegration:
    """Test SmartPlannerService integrates with strategies correctly."""

    def test_smart_planner_service_has_strategies(self):
        """Test that SmartPlannerService has strategies list."""
        from src.domains.agents.services.smart_planner_service import (
            get_smart_planner_service,
        )

        service = get_smart_planner_service()
        assert hasattr(service, "strategies")
        assert len(service.strategies) == 4
        assert isinstance(service.strategies[0], ReferenceBypassStrategy)
        assert isinstance(service.strategies[1], CrossDomainBypassStrategy)
        assert isinstance(service.strategies[2], SingleDomainStrategy)
        assert isinstance(service.strategies[3], MultiDomainStrategy)

    def test_strategies_have_service_reference(self):
        """Test that LLM strategies have service reference for delegation."""
        from src.domains.agents.services.smart_planner_service import (
            get_smart_planner_service,
        )

        service = get_smart_planner_service()
        # SingleDomain and MultiDomain strategies should have service reference
        single_domain = service.strategies[2]
        multi_domain = service.strategies[3]

        assert single_domain.service is service
        assert multi_domain.service is service
