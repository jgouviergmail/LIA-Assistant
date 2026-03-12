"""
Planner Services Package.

This package contains the SmartPlannerService and its planning strategies.

Architecture:
- SmartPlannerService: Orchestrates planning via strategy selection (smart_planner_service.py)
- PlanningStrategy (Protocol): Interface for all strategies (strategies/base_strategy.py)
- Concrete Strategies: ReferenceBypass, CrossDomainBypass, SingleDomain, MultiDomain

This package follows modern Python conventions: imports are done explicitly
where needed rather than re-exported through __init__.py.

Main components (import directly from their modules):
- SmartPlannerService: src.domains.agents.services.smart_planner_service
- PlanningResult: src.domains.agents.services.planner.planning_result
- Strategies: src.domains.agents.services.planner.strategies
"""
