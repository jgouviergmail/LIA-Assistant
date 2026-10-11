"""Execute reviewed reversible settings through the original CAS and effect ledger."""

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.confirmation_policy import requires_confirmation
from src.domains.agents.application.draft_execution import _execute_outcome
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.setting_choices import describe_setting_values
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.scope import current_scope
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.database.session import get_db_context


async def execute_reversible_change(
    content: ApplicationActionDraftContent,
) -> UnifiedToolOutput:
    context = runtime_context_if_running()
    scope = current_scope()
    if context is None or context.user_id != content.actor_id or scope is None:
        raise CommandRejected("FORBIDDEN")
    spec = APPLICATION_OPERATIONS.get(content.operation_id)
    if spec.administrative or requires_confirmation(content.operation_id, content.intent):
        raise CommandRejected("CONFIRMATION_MISSING")
    async with get_db_context() as db:
        await require_application_tools(db)
        await load_actor(db, content.actor_id)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)
    receipt = PreferenceWriteReceipt()
    outcome = await _execute_outcome(content, content.actor_id, receipt)
    publish_preference_change(content, receipt)
    if not outcome.success:
        return UnifiedToolOutput(
            success=False,
            message="Application setting change did not complete. Inspect committed state before retrying.",
            error_message="Application setting change did not complete.",
            error_code=outcome.error_code or "EXECUTION_FAILED",
            structured_data={"application_result": outcome.model_dump(mode="json")},
        )
    return UnifiedToolOutput.data_success(
        message="Application settings saved.",
        structured_data={
            "application_result": outcome.model_dump(mode="json"),
            "setting_choices": describe_setting_values(outcome.values, context.language),
        },
    )
