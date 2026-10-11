"""Native application execution; permission checks also precede cached outcomes."""

import functools
from collections.abc import Callable, Coroutine
from uuid import UUID

import structlog
from pydantic import JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, UsageLimitExceededError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.asset_delete import execute_asset_deletion
from src.domains.agents.application.asset_retention import execute_asset_retention
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.bookmark_delete import execute_bookmark_deletion
from src.domains.agents.application.bookmark_keep import execute_bookmark_keep
from src.domains.agents.application.command_repository import claim_command, close_command
from src.domains.agents.application.command_service import CommandRejected, validate_execution
from src.domains.agents.application.document_delete import execute_document_deletion
from src.domains.agents.application.document_move import execute_document_move
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.email_share_send import execute_email_share
from src.domains.agents.application.habit_actions import execute_habit_action
from src.domains.agents.application.habit_forgetting import execute_habit_forgetting
from src.domains.agents.application.habit_recompute import execute_habit_recompute
from src.domains.agents.application.habit_settings import execute_habit_settings
from src.domains.agents.application.health_removal import execute_health_removal
from src.domains.agents.application.health_token_revocation import execute_health_token_revocation
from src.domains.agents.application.interest_bulk_removal import execute_interest_bulk_removal
from src.domains.agents.application.interest_creation import execute_interest_creation
from src.domains.agents.application.interest_feedback import execute_interest_feedback
from src.domains.agents.application.interest_reactivation import execute_interest_reactivation
from src.domains.agents.application.interest_removal import execute_interest_removal
from src.domains.agents.application.interest_settings import execute_interest_settings
from src.domains.agents.application.interest_update import execute_interest_update
from src.domains.agents.application.journal_consolidation import execute_journal_consolidation
from src.domains.agents.application.journal_creation import execute_journal_creation
from src.domains.agents.application.journal_feedback import execute_journal_feedback
from src.domains.agents.application.journal_removal import execute_journal_removal
from src.domains.agents.application.journal_settings import execute_journal_settings
from src.domains.agents.application.journal_update import execute_journal_update
from src.domains.agents.application.meeting_deletion import execute_meeting_deletion
from src.domains.agents.application.meeting_email_send import execute_meeting_email
from src.domains.agents.application.meeting_preferences import execute_meeting_preferences
from src.domains.agents.application.meeting_reformat import execute_meeting_reformat
from src.domains.agents.application.meeting_regeneration import execute_meeting_regeneration
from src.domains.agents.application.meeting_report_restoration import execute_report_restoration
from src.domains.agents.application.meeting_report_updating import execute_report_update
from src.domains.agents.application.meeting_retry import execute_meeting_retry
from src.domains.agents.application.meeting_template_execution import (
    execute_template_creation,
    execute_template_removal,
    execute_template_replacement,
)
from src.domains.agents.application.meeting_transcript_removal import execute_transcript_deletion
from src.domains.agents.application.memory_bulk_removal import execute_memory_bulk_removal
from src.domains.agents.application.memory_creation import execute_memory_creation
from src.domains.agents.application.memory_pin import execute_memory_pin
from src.domains.agents.application.memory_removal import execute_memory_removal
from src.domains.agents.application.memory_update import execute_memory_update
from src.domains.agents.application.open_loop_actions import execute_open_loop_action
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.peer_block import execute_peer_block
from src.domains.agents.application.peer_image import execute_peer_image
from src.domains.agents.application.peer_preferences import execute_peer_preferences
from src.domains.agents.application.peer_removal import execute_peer_removal
from src.domains.agents.application.peer_request import execute_peer_request
from src.domains.agents.application.peer_response import execute_peer_response
from src.domains.agents.application.peer_share import execute_peer_share
from src.domains.agents.application.personal_mcp_connection import execute_personal_mcp_connection
from src.domains.agents.application.personal_mcp_delete import execute_personal_mcp_delete
from src.domains.agents.application.personal_mcp_description import execute_personal_mcp_description
from src.domains.agents.application.personal_mcp_oauth_disconnect import (
    execute_personal_mcp_oauth_disconnect,
)
from src.domains.agents.application.personal_mcp_settings import execute_personal_mcp_settings
from src.domains.agents.application.personal_mcp_state import execute_personal_mcp_state
from src.domains.agents.application.plugin_delete import execute_plugin_deletion
from src.domains.agents.application.plugin_url_import import execute_plugin_url_import
from src.domains.agents.application.preference_dispatch import execute_preference_patch
from src.domains.agents.application.psyche_reset import execute_psyche_reset
from src.domains.agents.application.psyche_settings import execute_psyche_settings
from src.domains.agents.application.psyche_summary import execute_psyche_summary
from src.domains.agents.application.relation_context_refresh import execute_relation_context_refresh
from src.domains.agents.application.relation_debrief_build import execute_relation_debrief_build
from src.domains.agents.application.relation_favorite import execute_relation_favorite
from src.domains.agents.application.relation_grouping import execute_relation_grouping
from src.domains.agents.application.relation_settings import execute_relation_settings
from src.domains.agents.application.reminder_creation import execute_reminder_creation
from src.domains.agents.application.reminder_removal import execute_reminder_removal
from src.domains.agents.application.reminder_update import execute_reminder_update
from src.domains.agents.application.result_projection import public_application_values
from src.domains.agents.application.routine_creation import execute_routine_creation
from src.domains.agents.application.routine_execution import execute_routine_launch
from src.domains.agents.application.routine_operations import execute_routine_state
from src.domains.agents.application.routine_removal import execute_routine_removal
from src.domains.agents.application.routine_update import execute_routine_update
from src.domains.agents.application.secure_handoff import secure_handoff_outcome
from src.domains.agents.application.skill_delete import execute_skill_deletion
from src.domains.agents.application.skill_library_import import execute_library_import
from src.domains.agents.application.skill_update import execute_skill_update
from src.domains.agents.application.skill_url_import import execute_skill_url_import
from src.domains.agents.application.source_delete import execute_source_deletion
from src.domains.agents.application.source_link import execute_source_link
from src.domains.agents.application.source_sync import execute_source_sync
from src.domains.agents.application.source_unlink import execute_source_unlink
from src.domains.agents.application.space_create import execute_space_creation
from src.domains.agents.application.space_delete import execute_space_deletion
from src.domains.agents.application.space_update import execute_space_update
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.agents.application.workboard_comment import execute_workboard_comment
from src.domains.agents.application.workboard_create import execute_workboard_creation
from src.domains.agents.application.workboard_delete import execute_workboard_delete
from src.domains.agents.application.workboard_update import execute_workboard_update
from src.domains.auth.session_commands import SessionRevocationCompletionUnknown
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.database.session import get_db_context
from src.infrastructure.live_connector_preferences import LiveConnectorSettingsRefused

logger = structlog.get_logger(__name__)
ApplicationExecutor = Callable[
    [dict[str, object], UUID, object], Coroutine[object, object, dict[str, object]]
]


def authorized_application_executor(executor: ApplicationExecutor) -> ApplicationExecutor:
    """Reauthorize BEFORE the shared gate can serve any stored administrative result."""

    @functools.wraps(executor)
    async def run(content: dict[str, object], actor_id: UUID, deps: object) -> dict[str, object]:
        try:
            await validate_execution(content, actor_id)
        except CommandRejected as exc:
            return {"success": False, "error_code": exc.code}
        except ValidationError:
            return {"success": False, "error_code": "INVALID_INPUT"}
        except AuthorizationError as exc:
            return {"success": False, "error_code": application_access_error_code(exc)}
        except SQLAlchemyError:
            return {"success": False, "error_code": "DEPENDENCY_ERROR"}
        return await executor(content, actor_id, deps)

    return run


async def execute_application_action_draft(
    content: dict[str, object], actor_id: UUID, deps: object
) -> dict[str, object]:
    draft = await validate_execution(content, actor_id)
    async with get_db_context() as db:
        token = await claim_command(db, draft.command_id, actor_id)
    if token is None:
        return {"success": False, "error_code": "ALREADY_CLAIMED"}
    receipt = PreferenceWriteReceipt()
    outcome = await _execute_outcome(draft, actor_id, receipt)
    publish_preference_change(draft, receipt)
    try:
        async with get_db_context() as db:
            closed = await close_command(db, draft.command_id, actor_id, token, outcome)
    except SQLAlchemyError:
        closed = False
    if not closed:
        return {
            "success": False,
            "error_code": "COMPLETION_UNKNOWN",
            "committed": receipt.committed,
            "values": _committed_values(draft, receipt),
        }
    return outcome.model_dump(mode="json")


async def _apply_approved_action(
    draft: ApplicationActionDraftContent, actor_id: UUID, receipt: PreferenceWriteReceipt
) -> ApplicationExecutionOutcome:
    if handoff := secure_handoff_outcome(draft):
        # Claiming can wait on a competing transaction. It never freezes permission.
        await validate_execution(draft.model_dump(mode="json"), actor_id)
        return handoff
    async with get_db_context() as db:
        await require_application_tools(db)
        execute = {
            "knowledge_source.unlink": execute_source_unlink,
            "knowledge_source.link": execute_source_link,
            "knowledge_source.sync": execute_source_sync,
            "knowledge_source.delete": execute_source_deletion,
            "generated_assets.retention.update": execute_asset_retention,
            "generated_assets.delete": execute_asset_deletion,
            "saved_answer.keep": execute_bookmark_keep,
            "skill_settings.update": execute_skill_update,
            "personal_mcp.state.update": execute_personal_mcp_state,
            "personal_mcp.settings.update": execute_personal_mcp_settings,
            "personal_mcp.delete": execute_personal_mcp_delete,
            "personal_mcp.description.regenerate": execute_personal_mcp_description,
            "personal_mcp.connection.test": execute_personal_mcp_connection,
            "personal_mcp.oauth.disconnect": execute_personal_mcp_oauth_disconnect,
            "skill_settings.delete": execute_skill_deletion,
            "plugin.delete": execute_plugin_deletion,
            "skill_url.import": execute_skill_url_import,
            "plugin_url.import": execute_plugin_url_import,
            "skill_library.install": execute_library_import,
            "skill_library.update": execute_library_import,
            "email_share.send": execute_email_share,
            "saved_answer.delete": execute_bookmark_deletion,
            "journal_portrait.feedback": execute_journal_feedback,
            "journals.consolidate": execute_journal_consolidation,
            "journal_entries.update": execute_journal_update,
            "journal_entries.create": execute_journal_creation,
            "journal_entries.delete": execute_journal_removal,
            "journal_settings.update": execute_journal_settings,
            "psyche.reset": execute_psyche_reset,
            "health_token.revoke": execute_health_token_revocation,
            "health_samples.delete": execute_health_removal,
            "psyche.summary": execute_psyche_summary,
            "psyche_settings.update": execute_psyche_settings,
            "relation_settings.update": execute_relation_settings,
            "relation_favorite.update": execute_relation_favorite,
            "relation_grouping.update": execute_relation_grouping,
            "relation_debrief.build": execute_relation_debrief_build,
            "relation_context.refresh": execute_relation_context_refresh,
            "peer_preferences.update": execute_peer_preferences,
            "peer_connection.request": execute_peer_request,
            "peer_connection.respond": execute_peer_response,
            "peer_share.update": execute_peer_share,
            "peer_connection.remove": execute_peer_removal,
            "peer_block.update": execute_peer_block,
            "peer_image.share": execute_peer_image,
            "workboard_ticket.create": execute_workboard_creation,
            "knowledge_space.create": execute_space_creation,
            "knowledge_space.delete": execute_space_deletion,
            "knowledge_documents.delete": execute_document_deletion,
            "knowledge_documents.move": execute_document_move,
            "knowledge_space.update": execute_space_update,
            "workboard_ticket.comment": execute_workboard_comment,
            "workboard_ticket.delete": execute_workboard_delete,
            "workboard_ticket.update": execute_workboard_update,
            "meeting_template.create": execute_template_creation,
            "meeting_template.update": execute_template_replacement,
            "meeting_template.delete": execute_template_removal,
            "meeting_transcript.delete": execute_transcript_deletion,
            "meeting_report.update": execute_report_update,
            "meeting.delete": execute_meeting_deletion,
            "meeting_report.reformat": execute_meeting_reformat,
            "meeting_report.regenerate": execute_meeting_regeneration,
            "meeting.retry": execute_meeting_retry,
            "meeting_report.email": execute_meeting_email,
            "meeting_report.restore": execute_report_restoration,
            "meeting_preferences.update": execute_meeting_preferences,
            "habit_settings.update": execute_habit_settings,
            "habits.status": execute_habit_action,
            "habits.delete": execute_habit_action,
            "habits.forget": execute_habit_forgetting,
            "habits.recompute": execute_habit_recompute,
            "open_loops.update": execute_open_loop_action,
            "open_loops.close": execute_open_loop_action,
            "interests.feedback": execute_interest_feedback,
            "interests.reactivate": execute_interest_reactivation,
            "interests.create": execute_interest_creation,
            "interests.delete_all": execute_interest_bulk_removal,
            "interests.delete": execute_interest_removal,
            "interests.update": execute_interest_update,
            "interest_settings.update": execute_interest_settings,
            "memories.update": execute_memory_update,
            "memories.delete": execute_memory_removal,
            "memories.delete_all": execute_memory_bulk_removal,
            "memories.create": execute_memory_creation,
            "memories.pin": execute_memory_pin,
            "reminder.update": execute_reminder_update,
            "reminder.delete": execute_reminder_removal,
            "reminder.create": execute_reminder_creation,
            "routine_state.update": execute_routine_state,
            "routine.create": execute_routine_creation,
            "routine.delete": execute_routine_removal,
            "routine.update": execute_routine_update,
            "routine.execute": execute_routine_launch,
        }.get(draft.operation_id)
        if execute is not None:
            await execute(db, actor_id, draft, receipt)
        else:
            await execute_preference_patch(
                db,
                actor_id,
                draft.operation_id,
                draft.intent,
                draft.before,
                receipt,
                approved_until=draft.expires_at,
            )
    return ApplicationExecutionOutcome(
        success=True,
        phase=ApplicationPhase.COMMITTED,
        committed=receipt.committed,
        no_op=receipt.no_op,
        values=receipt.values if receipt.values is not None else public_application_values(draft),
    )


async def _execute_outcome(
    draft: ApplicationActionDraftContent, actor_id: UUID, receipt: PreferenceWriteReceipt
) -> ApplicationExecutionOutcome:
    try:
        return await _apply_approved_action(draft, actor_id, receipt)
    except ResourceConflictError:
        return ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.CONFLICT,
            error_code="STALE_STATE",
            committed=receipt.committed,
            values=_committed_values(draft, receipt),
        )
    except DomainValidationError:
        return _failed_outcome(draft, receipt, "CONSTRAINT_VIOLATION")
    except UsageLimitExceededError as exc:
        return _failed_outcome(draft, receipt, exc.error_code or "USAGE_LIMIT_EXCEEDED")
    except SessionRevocationCompletionUnknown:
        return _failed_outcome(draft, receipt, "COMPLETION_UNKNOWN")
    except CommandRejected as exc:
        return _failed_outcome(draft, receipt, exc.code)
    except AuthorizationError as exc:
        return _failed_outcome(draft, receipt, application_access_error_code(exc))
    except LiveConnectorSettingsRefused as exc:
        return _failed_outcome(draft, receipt, exc.code)
    except Exception as exc:
        # The receipt distinguishes a failed propagation from a failed write.
        logger.warning(
            "application_command_failed",
            operation=draft.operation_id,
            exception_type=type(exc).__name__,
            committed=receipt.committed,
        )
        return _failed_outcome(draft, receipt, "EXECUTION_FAILED")


def _failed_outcome(
    draft: ApplicationActionDraftContent, receipt: PreferenceWriteReceipt, code: str
) -> ApplicationExecutionOutcome:
    return ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.FAILED,
        committed=receipt.committed,
        values=_committed_values(draft, receipt),
        error_code="POST_COMMIT_FAILURE" if receipt.committed else code,
    )


def _committed_values(
    draft: ApplicationActionDraftContent, receipt: PreferenceWriteReceipt
) -> dict[str, JsonValue]:
    if not receipt.committed:
        return {}
    return receipt.values if receipt.values is not None else public_application_values(draft)
