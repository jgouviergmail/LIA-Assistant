"""Exact confirmation required by application command execution."""

from collections.abc import Mapping

from src.domains.agents.effects.digest import draft_digest
from src.domains.agents.effects.scope import EffectScope


def valid_draft_approval(scope: EffectScope | None, content: Mapping[str, object]) -> bool:
    return bool(
        scope is not None
        and scope.approved
        and scope.approval_kind == "draft_critique"
        and scope.approval_ref
        and scope.idempotency_key == f"draft:{scope.approval_ref}"
        and scope.draft_digest == draft_digest(content)
    )
