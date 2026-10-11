"""The originating browser selects and explicitly confirms the local skill file."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_file_upload_schemas import SkillFileUploadPatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_FILE_UPLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="skill_file.upload",
    tool_name="import_lia_skill_file_tool",
    sections=("skills",),
    input_model=SkillFileUploadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.SKILLS,),
)
