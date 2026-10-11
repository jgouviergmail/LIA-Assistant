"""An owned skill may be removed without altering system skills or plugin components."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_delete_schemas import SkillDeletePatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="skill_settings.delete",
    tool_name="delete_lia_skill_tool",
    sections=("skills",),
    input_model=SkillDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS,),
)
