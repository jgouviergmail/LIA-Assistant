"""One canonical draft envelope for reviewed application action families."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import BaseModel, JsonValue

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_drafts import get_draft_summary_label
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.digest import payload_digest


def build_action_content(
    actor_id: UUID,
    spec: ApplicationOperationSpec,
    intent: BaseModel,
    before: dict[str, JsonValue],
    after: dict[str, JsonValue],
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    if spec.kind not in {OperationKind.ACTION, OperationKind.SECURE_HANDOFF, OperationKind.DEVICE}:
        raise ValueError("Only reviewed action families may prepare an action draft")
    if spec.version != ApplicationActionDraftContent.model_fields["schema_version"].default:
        raise ValueError("An operation schema change requires an explicit draft migration")
    validated = spec.input_model.model_validate(intent)
    context = runtime_context_if_running()
    return ApplicationActionDraftContent(
        command_id=command_id or uuid4(),
        actor_id=actor_id,
        operation_id=spec.operation_id,
        schema_fingerprint=payload_digest(spec.input_model.model_json_schema()),
        expected_digest=payload_digest(before),
        intent=validated.model_dump(mode="json", exclude_unset=True),
        before=before,
        after=after,
        title=get_draft_summary_label("application_action", context.language if context else None),
        user_timezone=context.timezone if context else DEFAULT_USER_DISPLAY_TIMEZONE,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.application_command_ttl_seconds),
    )
