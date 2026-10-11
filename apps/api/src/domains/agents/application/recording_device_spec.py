"""Microphone and potentially paid processing keep exact human confirmation."""

from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.recording_device_schemas import (
    RecordingDevicePatch,
    RecordingDeviceRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

RECORDING_DEVICE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_device.control",
    tool_name="control_lia_meeting_recording_tool",
    sections=("meetings",),
    input_model=RecordingDevicePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    addressed_device=True,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
RECORDING_DEVICE_MANIFEST = ToolManifest(
    name=RECORDING_DEVICE_OPERATION.tool_name,
    agent="setting_agent",
    description="Propose an exact confirmed action in the originating browser's original meeting recorder: start or resume microphone capture; stop uploads and queue potentially billed transcription/minutes; explicitly finalize despite missing segments; irreversibly discard captured meeting/audio. A fresh browser observation is required. Never controls another tab, invents microphone permission, audio or completed minutes. Device completion is device-reported; server facts and processing remain separate. No automatic replay after an unknown claim or completion. Start/resume still need the browser's own permission and gesture. Current configured quotas, costs and recording preferences apply; no fixed final price is promised.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Finite original recorder action",
            schema=RecordingDeviceRequest.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="control_lia_meeting_recording", category="tool"),
)

RECORDING_DEVICE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_device.read",
    tool_name="get_lia_meeting_recorder_tool",
    sections=("meetings",),
    input_model=ApplicationEmptyRead,
    output_model=RecordingDeviceSnapshot,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
RECORDING_DEVICE_READ_MANIFEST = ToolManifest(
    name=RECORDING_DEVICE_READ_OPERATION.tool_name,
    agent="setting_agent",
    description="Read this originating browser's short-lived device-reported meeting recorder phase, microphone support and meeting identifier. The observation timestamp is explicit; it is neither server proof nor current processing completion. No microphone permission request, action, spending or secrets. Unavailable without an authenticated addressed browser. Use get_lia_meetings_tool for actual server metadata and processing status.",
    parameters=[],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="read",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="get_lia_meeting_recorder", category="tool"),
)
