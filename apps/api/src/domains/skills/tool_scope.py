"""How a skill tool answers for a skill written elsewhere (ADR-327).

Shared by every skill tool — the script, the resource, the activation and the
command — so the refusal of a runner isolated on one skill, and the envelope
around a third-party skill's words, have ONE wording each.
"""

from __future__ import annotations

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.skills.trust import out_of_scope

__all__ = ["THIRD_PARTY_SOURCE_TYPE", "as_external", "scope_refusal"]

#: The source type of the external-content envelope around a third-party skill.
THIRD_PARTY_SOURCE_TYPE = "third_party_skill"


def scope_refusal(skill_name: str) -> UnifiedToolOutput | None:
    """A runner isolated on one skill asking for another is refused.

    Args:
        skill_name: The skill a tool was asked to serve.

    Returns:
        The refusal, or None when the skill is in scope.
    """
    if not out_of_scope(skill_name):
        return None
    return UnifiedToolOutput.failure(
        message=f"Skill '{skill_name}' is not available here: this runner serves one skill only",
        error_code="FORBIDDEN",
    )


def as_external(skill_name: str, text: str) -> str:
    """A third-party skill's words, handed to the caller as external content.

    Args:
        skill_name: The skill that produced them.
        text: What it produced.

    Returns:
        The text inside the external-content envelope.
    """
    return wrap_external_content(
        text, source_url=f"skill:{skill_name}", source_type=THIRD_PARTY_SOURCE_TYPE
    )
