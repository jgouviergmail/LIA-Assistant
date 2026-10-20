"""Finite continuation failures preserve observed commits and never expose input."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown


def application_continuation_failure(
    error: BaseException, receipt: PreferenceWriteReceipt
) -> ApplicationExecutionOutcome:
    code, phase = "EXECUTION_FAILED", ApplicationPhase.FAILED
    if isinstance(error, AuthorizationError):
        code = application_access_error_code(error)
    elif isinstance(error, ResourceConflictError | ResourceNotFoundError):
        code, phase = "STALE_STATE", ApplicationPhase.CONFLICT
    elif isinstance(error, ExportDownloadCompletionUnknown | asyncio.CancelledError):
        code = "COMPLETION_UNKNOWN"
    elif isinstance(error, CommandRejected):
        code = error.code
    elif isinstance(error, SQLAlchemyError | OSError):
        code = "DEPENDENCY_ERROR"
    elif isinstance(error, ValueError):
        code = "INVALID_INPUT"
    return ApplicationExecutionOutcome(
        success=False,
        phase=phase,
        committed=receipt.committed,
        error_code="POST_COMMIT_FAILURE" if receipt.committed else code,
    )
