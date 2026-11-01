"""Whether a call is confirmed before it runs — the effect gate's own rule (spec 2026-10-29 D8).

The effect gate refuses a ``confirm`` call nobody approved (ADR-263) and turns it
into a draft; in the ReAct loop that draft ENDS the loop (ADR-298 measured it).
The loop asks the person BEFORE a call its ``react_hitl_map`` marks. Read from
two rules, the loop bound unasked what the gate would refuse: a tool its server
declares destructive, the server's confirmation off. One predicate, read for
every tool the loop binds — an iterative server's individual on its OWN manifest.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domains.agents.registry.catalogue import ToolManifest


def requires_confirmation(manifest: ToolManifest) -> bool:
    """Whether the person confirms this tool's call before it runs.

    Args:
        manifest: The tool's manifest.

    Returns:
        True when the owner asked for it (``hitl_required``) or the tool owes it
        (``mutation_policy == "confirm"``, the gate's refusal case) — unless the
        person approved it in advance (their « never ask », spec 2026-10-30 D6),
        which the gate files under its own approval.
    """
    if manifest.approved_in_advance:
        return False
    permissions = manifest.permissions
    return bool(permissions and permissions.hitl_required) or manifest.mutation_policy == "confirm"


def task_requires_confirmation(individuals: Iterable[ToolManifest]) -> bool:
    """Whether a dedicated agent is asked before the task it is given.

    Owner decision 2026-10-31: once before the task whenever one of the agent's own
    tools would ask — that answer covers its calls (the task's approved scope reaches
    every inner call) and the task runs to completion. Read by every registration of
    a task, the person's servers and the administrator's, and by the synthesis.

    Args:
        individuals: The manifests of the tools the agent may call.

    Returns:
        True when one of them requires confirmation; a « never ask » tool does not.
    """
    return any(requires_confirmation(manifest) for manifest in individuals)
