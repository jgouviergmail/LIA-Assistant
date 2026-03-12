"""
Planning Strategies Package.

This package contains concrete planning strategy implementations.

Strategies (ordered by priority):
0. SkillBypassStrategy - Bypass LLM for deterministic skill plan templates (optional)
1. ReferenceBypassStrategy - Bypass LLM for pure reference resolution queries
2. CrossDomainBypassStrategy - Bypass LLM for cross-domain reference queries
3. SingleDomainStrategy - LLM planning for single domain queries
4. MultiDomainStrategy - LLM planning for multi-domain queries
"""

from src.domains.agents.services.planner.strategies.base_strategy import (
    PlanningStrategy,
)
from src.domains.agents.services.planner.strategies.cross_domain_bypass import (
    CrossDomainBypassStrategy,
)
from src.domains.agents.services.planner.strategies.multi_domain import (
    MultiDomainStrategy,
)
from src.domains.agents.services.planner.strategies.reference_bypass import (
    ReferenceBypassStrategy,
)
from src.domains.agents.services.planner.strategies.single_domain import (
    SingleDomainStrategy,
)
from src.domains.agents.services.planner.strategies.skill_bypass import (
    SkillBypassStrategy,
)

__all__ = [
    "PlanningStrategy",
    "SkillBypassStrategy",
    "ReferenceBypassStrategy",
    "CrossDomainBypassStrategy",
    "SingleDomainStrategy",
    "MultiDomainStrategy",
]
