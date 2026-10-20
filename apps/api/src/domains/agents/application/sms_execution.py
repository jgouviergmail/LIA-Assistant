"""One exact-approval gate and the existing fenced SMS source writers."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.sms_action_schemas import (
    SmsErasePatch,
    SmsPreferencePatch,
    SmsSenderBlockPatch,
    SmsTokenCreatePatch,
    SmsTokenRevokePatch,
)
from src.domains.agents.application.sms_action_spec import SMS_ACTION_SPECS
from src.domains.agents.application.sms_actions import (
    SmsManagementAudience,
    authorize_sms_management,
    canonical_sms_action,
)
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.draft_approval import valid_draft_approval
from src.domains.agents.effects.scope import current_scope
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.registry import IngestionResource
from src.domains.ingestion.schemas import IngestionTokenSecret
from src.domains.ingestion.token_commands import (
    IngestionTokenCompletionUnknown,
    create_managed_token,
    revoke_managed_token,
)
from src.domains.sms.management_commands import (
    SmsCompletionUnknown,
    erase_sms,
    update_sms_preferences,
)
from src.domains.sms.sender_commands import update_sender_block
from src.domains.users.preference_cas import PreferenceWriteReceipt


def require_exact_sms_approval(owner: UUID, draft: ApplicationActionDraftContent) -> None:
    if draft.actor_id != owner:
        raise CommandRejected("FORBIDDEN")
    if not valid_draft_approval(current_scope(), draft.model_dump(mode="json")):
        raise CommandRejected("CONFIRMATION_MISSING")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    spec = SMS_ACTION_SPECS.get(draft.operation_id)
    if spec is None or draft.schema_fingerprint != payload_digest(
        spec.input_model.model_json_schema()
    ):
        raise CommandRejected("SCHEMA_CHANGED")
    if draft.schema_version != spec.version or draft.expected_digest != payload_digest(
        draft.before
    ):
        raise CommandRejected("INVALID_DRAFT")
    if not canonical_sms_action(draft):
        raise CommandRejected("INVALID_DRAFT")


def require_settings_execution(
    draft: ApplicationActionDraftContent, audience: SmsManagementAudience
) -> None:
    if audience is not SmsManagementAudience.SETTINGS:
        return
    scope = current_scope()
    if (
        scope is None
        or scope.source != "user"
        or scope.run_id != str(draft.command_id)
        or not scope.approval_ref
        or not scope.approval_ref.startswith("ui:sms:")
    ):
        raise CommandRejected("BROWSER_APPROVAL_REQUIRED")


async def execute_sms_action(
    db: AsyncSession,
    owner: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    *,
    origin: ApplicationOrigin | None = None,
    audience: SmsManagementAudience = SmsManagementAudience.ASSISTANT,
) -> IngestionTokenSecret | None:
    async def check() -> None:
        require_exact_sms_approval(owner, draft)
        require_settings_execution(draft, audience)
        await authorize_sms_management(
            db, owner, origin, browser=draft.operation_id == "sms_token.create", audience=audience
        )

    require_exact_sms_approval(owner, draft)
    require_settings_execution(draft, audience)
    await lock_active_owner(db, owner)
    await check()
    spec = SMS_ACTION_SPECS[draft.operation_id]
    patch = spec.input_model.model_validate(draft.intent)
    secret = None
    try:
        if isinstance(patch, SmsTokenCreatePatch):
            request = patch.ingestion_token_to_create
            secret = await create_managed_token(
                db,
                owner,
                draft.command_id,
                request.label,
                request.source_id,
                receipt,
                check,
                resource=IngestionResource.SMS,
            )
        elif isinstance(patch, SmsTokenRevokePatch):
            if patch.ingestion_token_to_revoke.token.resource != IngestionResource.SMS:
                raise CommandRejected("FORBIDDEN")
            await revoke_managed_token(db, owner, patch.ingestion_token_to_revoke, receipt, check)
        elif isinstance(patch, SmsPreferencePatch):
            before = SmsPreferencePatch.model_validate(draft.before)
            await update_sms_preferences(
                db,
                owner,
                expected=before.sms_preferences,
                selected=patch.sms_preferences,
                receipt=receipt,
                check=check,
            )
        elif isinstance(patch, SmsSenderBlockPatch):
            await update_sender_block(db, owner, patch.sms_sender_block, receipt, check)
        elif isinstance(patch, SmsErasePatch):
            await erase_sms(db, owner, patch.sms_messages_to_delete, receipt, check)
        else:
            raise CommandRejected("INVALID_DRAFT")
    except IngestionTokenCompletionUnknown, SmsCompletionUnknown:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
    await check()
    return secret


async def execute_sms_native_action(
    db: AsyncSession,
    owner: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    """The agent executor can never issue or receive a browser-only secret."""
    if draft.operation_id == "sms_token.create":
        raise CommandRejected("BROWSER_REQUIRED")
    await execute_sms_action(db, owner, draft, receipt)
