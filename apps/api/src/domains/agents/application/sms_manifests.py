"""Finite native management catalogue; no secret is ever an agent result."""

from pydantic import BaseModel

from src.domains.agents.application.sms_action_schemas import (
    SmsTokenCreateRequest,
    SmsTokenRevokeRequest,
)
from src.domains.agents.application.sms_action_spec import SMS_NATIVE_OPERATIONS
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.sender_commands import SmsSenderBlockRequest

SMS_REQUEST_MODELS: dict[str, type[BaseModel]] = {
    "sms_token.create": SmsTokenCreateRequest,
    "sms_token.revoke": SmsTokenRevokeRequest,
    "sms_preferences.update": SmsPreferences,
    "sms_sender_block.update": SmsSenderBlockRequest,
    "sms_messages.delete": SmsEraseRequest,
}
_DESCRIPTIONS = {
    "sms_token.create": "Prepare exact approval to create an iPhone SMS ingestion token. Authenticated originating browser required. Approval only hands off; the browser continues once and alone receives the secret. Never ask for or expose a secret in chat. Lost acknowledgement cannot replay secret delivery; inspect public token metadata and revoke before a separate creation.",
    "sms_token.revoke": "Prepare exact approval to revoke one owned SMS ingestion token identified by its public UUID. Stops that credential and cancels pending deliveries if no active source credential remains. Existing SMS remain in LIA.",
    "sms_preferences.update": "Prepare exact approval for the three independent SMS preferences: ingestion, assistant access, immediate push at any hour. Assistant access defaults off. Disabling assistant access fences future reads and invalidates derived contexts; existing chat and explicit memories have their own retention.",
    "sms_sender_block.update": "Prepare exact approval to block or unblock one literal SMS sender. Blocks future ingestion before content retention. Existing SMS remain in LIA. Never infer an identifier from a display name; use the raw sender.",
    "sms_messages.delete": "Prepare exact approval to erase an explicit SMS scope: all, sender UUID, aware date interval or up to 100 message UUIDs. No free-text erasure. Preview fixes count and immutable source snapshot. Removes content/index, cancels pending deliveries, invalidates hosted exports and derived contexts. Downloaded exports and previous chat copies cannot be recalled.",
}

SMS_ACTION_MANIFESTS = tuple(
    ToolManifest(
        name=spec.tool_name,
        agent="setting_agent",
        description=_DESCRIPTIONS[spec.operation_id],
        parameters=[
            ParameterSchema(
                name="request",
                type="object",
                required=True,
                description="Exact requested scope, never authority or approval.",
                schema=SMS_REQUEST_MODELS[spec.operation_id].model_json_schema(),
            )
        ],
        outputs=[
            OutputFieldSchema(
                path="draft", type="object", description="Non-secret exact human confirmation"
            )
        ],
        cost=CostProfile(),
        permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
        mutation_policy="draft",
        tool_category="system",
        binding_unit="lia_sms",
        initiative_eligible=False,
        semantic_keywords=[_DESCRIPTIONS[spec.operation_id].split(".")[0]],
        display=DisplayMetadata(
            emoji="💬", i18n_key=spec.tool_name.removesuffix("_tool"), category="tool"
        ),
    )
    for spec in SMS_NATIVE_OPERATIONS
)
