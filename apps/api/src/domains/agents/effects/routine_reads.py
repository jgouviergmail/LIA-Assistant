"""What routine runs READ, offered to the habits domain (ADR-375).

A routine run names the turn it executed (``scheduled_action_runs.run_id``);
the treatments register holds that turn's consultations. Habits needs the
DOMAINS a routine reads to tell whether a recurring need is already served,
and cannot import this package (agents imports habits): the reader below is
installed into ``habits.usage_ports`` at import and again by the boot.

Every treatment row is a consultation by construction (actions live in
``agent_effects``), so no filter on the policy is needed; the domain is the
register's own reading of the capability, and only registered domains leave.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import AgentTreatment, EffectSource
from src.domains.agents.effects.treatment_labels import treatment_domain
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.habits.usage_ports import install_routine_reads_reader


async def read_routine_run_domains(
    db: AsyncSession, user_id: UUID, run_ids: Sequence[str]
) -> Mapping[str, frozenset[str]]:
    """The registered domains each routine run consulted.

    Args:
        db: The caller's session.
        user_id: The owner of the runs.
        run_ids: The runs asked about.

    Returns:
        ``{run_id: domains}`` — a run that consulted nothing registered is absent.
    """
    if not run_ids:
        return {}
    rows = await db.execute(
        select(AgentTreatment.run_id, AgentTreatment.tool_name)
        .where(
            AgentTreatment.user_id == user_id,
            AgentTreatment.source == EffectSource.SCHEDULED,
            AgentTreatment.run_id.in_(list(run_ids)),
        )
        .distinct()
    )
    read: dict[str, set[str]] = defaultdict(set)
    for run_id, tool_name in rows.all():
        domain = treatment_domain(tool_name)
        if domain in DOMAIN_REGISTRY:
            read[run_id].add(domain)
    return {run_id: frozenset(domains) for run_id, domains in read.items()}


install_routine_reads_reader(read_routine_run_domains)
