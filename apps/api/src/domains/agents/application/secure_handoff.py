"""An exact approval awaits its declared browser interaction, without performing its effect."""

from src.core.application_interaction import PendingApplicationInteraction
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS


def secure_handoff_outcome(
    draft: ApplicationActionDraftContent,
) -> ApplicationExecutionOutcome | None:
    kind = APPLICATION_OPERATIONS.get(draft.operation_id).interaction_kind
    if kind is None:
        return None
    return ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.WAITING,
        values=(
            draft.after
            if draft.operation_id
            in {
                "knowledge_document.upload",
                "skill_file.upload",
                "plugin_file.upload",
                "personal_mcp.configuration",
                "personal_mcp.oauth_authorize",
            }
            else {}
        ),
        interaction=PendingApplicationInteraction(
            interaction_id=draft.command_id, kind=kind, expires_at=draft.expires_at
        ),
    )
