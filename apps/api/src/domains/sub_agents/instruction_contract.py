"""What a sub-agent's ``instruction`` is told, in both modes (point 38, ADR-083).

The planner reads the delegation tool's manifest; the ReAct loop binds its
``@tool`` schema and never the manifest (ADR-310). The two had drifted apart:
the manifest said the expert has no user-data tools, the schema told the loop
that it « fetches what it needs » — so a ReAct turn delegated « analyse my last
e-mails » to an expert that could not read a single one.

The FACTS are therefore written once, here — which tools the expert has, and
that the person's data reaches it only inside the instruction — and read by
both. How the data is handed over is the mode's own: a plan references earlier
steps, a loop writes the facts in. So is where the cap is published: the
planner's delegation section states it (the manifest points at it, one
authority — prompt audit 2026-09-12), while the loop has no such section and
reads it here. The tool checks the cap itself, so it holds in both modes.
"""

from src.core.config import get_settings
from src.core.constants import SUBAGENT_RESEARCH_TOOLS_WHITELIST_DEFAULT

_TASK = "The task for the expert: what to analyse, what to produce, in which form."

#: The tools the « cannot read the user's data » claim may vouch for: the
#: public research tools LIA ships as the whitelist. An operator who names
#: another tool gets the list stated without the claim — a prompt states what
#: the code holds, nothing more (ADR-284).
_PUBLIC_RESEARCH_TOOLS = frozenset(
    name.strip() for name in SUBAGENT_RESEARCH_TOOLS_WHITELIST_DEFAULT.split(",") if name.strip()
)


def expert_reach() -> str:
    """What the expert can read on its own — the fact both modes must agree on.

    Returns:
        One sentence, from the deployment's whitelist.
    """
    tools = get_settings().subagent_research_tools_whitelist_parsed
    if not tools:
        # Empty whitelist = legacy blocklist mode (discouraged by its validator).
        return "The expert has every read-only tool of the catalogue."
    listed = ", ".join(tools)
    if set(tools) <= _PUBLIC_RESEARCH_TOOLS:
        return (
            f"The expert's only tools are {listed}: it cannot read the user's data "
            "(mail, calendar, contacts, files, memories)."
        )
    return (
        f"The expert's only tools are {listed}; whatever of the user's data they "
        "cannot read must be in the instruction."
    )


def instruction_description(*, in_plan: bool) -> str:
    """The description of ``instruction`` for the plan's manifest or the loop's schema.

    Args:
        in_plan: True for the planner's manifest, False for the ``@tool`` schema
            the ReAct loop binds.

    Returns:
        The parameter's description, from the deployment's settings.
    """
    if in_plan:
        return (
            f"{_TASK} {expert_reach()} Hand it the user data it needs through "
            "`$steps.step_N.<field>` references to earlier steps (never paste data by hand), "
            "and chain experts through `$steps.step_N.analysis`. Once references are "
            "resolved the instruction is capped at the token budget stated in the SUB-AGENT "
            "DELEGATION section: reference the fields the expert needs, not whole payloads."
        )
    cap = get_settings().subagent_instruction_max_tokens_resolved
    return (
        f"{_TASK} {expert_reach()} Put the facts it needs from the user's data INTO the "
        f"instruction — the relevant fields, never whole payloads. Above {cap} tokens the "
        "instruction is refused."
    )
