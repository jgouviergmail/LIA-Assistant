"""Reviewed telephony management declarations; runtime readers import no registry here."""

from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.phone_number_schemas import PhoneNumberPatch
from src.domains.agents.application.phone_preference_schemas import PhonePreferencePatch
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead
from src.infrastructure.phone_identity import PhoneIdentityProjection

PHONE_OPERATIONS = (
    ApplicationOperationSpec(
        operation_id="phone_number.update",
        tool_name="update_lia_phone_number_tool",
        sections=("telephony-identity",),
        input_model=PhoneNumberPatch,
        output_model=ApplicationExecutionOutcome,
        kind=OperationKind.ACTION,
        required_capabilities=(PlatformCapability.TELEPHONY,),
    ),
    ApplicationOperationSpec(
        operation_id="phone_preferences.update",
        tool_name="update_lia_phone_preferences_tool",
        sections=("telephony-identity",),
        input_model=PhonePreferencePatch,
        output_model=ApplicationExecutionOutcome,
        kind=OperationKind.ACTION,
        required_capabilities=(PlatformCapability.TELEPHONY,),
    ),
    ApplicationOperationSpec(
        operation_id="phone_history.read",
        tool_name="get_lia_phone_calls_tool",
        sections=("telephony-calls",),
        input_model=PhoneHistoryRead,
        output_model=PhoneHistoryProjection,
        kind=OperationKind.READ,
        required_capabilities=(PlatformCapability.TELEPHONY,),
    ),
    ApplicationOperationSpec(
        operation_id="phone_identity.read",
        tool_name="get_lia_phone_identity_tool",
        sections=("telephony-identity",),
        input_model=ApplicationEmptyRead,
        output_model=PhoneIdentityProjection,
        kind=OperationKind.READ,
        required_capabilities=(PlatformCapability.TELEPHONY,),
    ),
)
