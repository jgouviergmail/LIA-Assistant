"""Returned draft dispositions and batch counts, without executing or mutating context."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from prometheus_client import Counter

from src.core.application_interaction import pending_interaction_of
from src.core.field_names import FIELD_CONNECTOR_TYPE
from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_draft_refusals import get_draft_refusal_message
from src.core.tool_outcome import error_code_of, explicit_success
from src.domains.agents.services.draft_execution_result import DraftExecutionResult
from src.domains.agents.tools.common import ToolErrorCode, connector_not_activated_refusal
from src.domains.connectors.errors import ConnectorRevokedError
from src.domains.connectors.models import ConnectorType, get_connector_display_name
from src.infrastructure.email.smtp_outcome import SMTPPartialAcceptanceError


def raised_failure(error: BaseException) -> dict[str, object]:
    """The facts an executor's exception carries for its card, never its text.

    A message may quote a provider, a URL or a mailbox (ADR-303): the card
    reads a typed fact when the exception carries one and the generic sentence
    otherwise.

    Args:
        error: What the executor raised.

    Returns:
        The refusal the card reads — a partial SMTP acceptance, or the
        connector a revocation names — and ``{}`` for anything else.
    """
    if isinstance(error, SMTPPartialAcceptanceError):
        return error.to_failure()
    if isinstance(error, ConnectorRevokedError):
        return connector_not_activated_refusal(error.connector_type)
    return {}


def refusal_message(result: Mapping[str, object], language: str) -> str:
    """What the card of a confirmed draft its executor refused reads.

    On a confirmation no model writes the answer: the execution card IS the
    answer, and it shows ``DraftExecutionResult.error`` as written.

    - A connector no longer active is SAID: named as the connectors settings
      name it, with where to reactivate it.
    - Known dispositions are translated; a committed receipt stays explicit
      even when completion could not be confirmed (ADR-339).
    - Unknown codes remain in the result for diagnostics, while the card reads
      the generic sentence rather than inventing a reason.

    Args:
        result: What the executor returned.
        language: The person's language.

    Returns:
        The translated sentence, never an internal machine code.
    """
    code = error_code_of(result)
    if result.get("committed") is True or code != ToolErrorCode.CONNECTOR_NOT_ACTIVATED.value:
        return get_draft_refusal_message(code, language, committed=result.get("committed") is True)
    try:
        # The value or the member itself: ``str()`` of a ``(str, Enum)``
        # member is « ConnectorType.X », which names no connector.
        connector = ConnectorType(result.get(FIELD_CONNECTOR_TYPE))
    except ValueError:
        return get_draft_refusal_message(code, language)
    return APIMessages.connector_not_activated(
        get_connector_display_name(connector), resolve_language(language)
    )


def incomplete_draft_result(
    draft_id: str, draft_type: str, result: dict[str, object], language: str, counter: Counter
) -> DraftExecutionResult | None:
    """The disposition of an executor's result that is not a plain success.

    Args:
        draft_id: The confirmed draft.
        draft_type: Its type, the counter's label.
        result: What the executor returned.
        language: The person's language.
        counter: The executed-drafts counter, labelled by outcome.

    Returns:
        ``None`` for an explicit or legacy success; a waiting result when the
        executor handed an interaction back; otherwise a failure whose
        ``error`` is what the card reads (:func:`refusal_message`).
    """
    if pending_interaction_of(result) is not None:
        counter.labels(draft_type=draft_type, outcome="waiting").inc()
        return DraftExecutionResult(
            False,
            draft_id,
            draft_type,
            "confirm",
            result_data=result,
            user_language=language,
        )
    if explicit_success(result):
        return None
    counter.labels(draft_type=draft_type, outcome="failed").inc()
    return DraftExecutionResult(
        False,
        draft_id,
        draft_type,
        "confirm",
        result_data=result,
        error=refusal_message(result, language),
        user_language=language,
    )


@dataclass(frozen=True)
class DraftBatchCounts:
    succeeded: int
    failed: int
    waiting: int
    cancelled: int


def count_draft_results(results: Sequence[Mapping[str, object]]) -> DraftBatchCounts:
    counts = {"success": 0, "error": 0, "waiting": 0, "cancelled": 0}
    for item in results:
        status = item.get("status")
        key = status if isinstance(status, str) and status in counts else "error"
        counts[key] += 1
    return DraftBatchCounts(
        counts["success"], counts["error"], counts["waiting"], counts["cancelled"]
    )
