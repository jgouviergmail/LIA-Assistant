"""A person's own skill may go back to the version it replaced, as the settings allow (lot 14)."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_restore_schemas import SkillRestorePatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_RESTORE_OPERATION = ApplicationOperationSpec(
    operation_id="skill_settings.restore_previous",
    tool_name="restore_lia_skill_previous_version_tool",
    sections=("skills",),
    input_model=SkillRestorePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS,),
)
