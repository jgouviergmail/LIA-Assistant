"""
Sub-Agents domain.

Persistent, specialized sub-agents that the principal assistant can delegate
tasks to. Provides CRUD, execution, skills resolution, and token guard.
"""

from src.domains.sub_agents.models import SubAgent, SubAgentCreatedBy, SubAgentStatus
from src.domains.sub_agents.repository import SubAgentRepository
from src.domains.sub_agents.service import SubAgentService

__all__ = [
    "SubAgent",
    "SubAgentCreatedBy",
    "SubAgentRepository",
    "SubAgentService",
    "SubAgentStatus",
]
