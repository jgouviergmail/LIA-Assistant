"""Skill transfer is origin-bound and obeys the original gallery capability."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_download_schemas import SkillDownloadPatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_DOWNLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="skill_settings.download",
    tool_name="download_lia_skill_tool",
    sections=("skills",),
    input_model=SkillDownloadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.SKILLS,),
)
