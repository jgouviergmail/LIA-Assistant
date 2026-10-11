"""Personal skill activation is separate from administrative system activation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_update_schemas import SkillUpdatePatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="skill_settings.update",
    tool_name="update_lia_skill_settings_tool",
    sections=("skills",),
    input_model=SkillUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS,),
)
