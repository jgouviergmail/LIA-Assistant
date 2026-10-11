"""Native URL imports retain the original personal skill capability and confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_url_import_schemas import SkillUrlImportPatch
from src.domains.feature_switches.registry import PlatformCapability

SKILL_URL_IMPORT_OPERATION = ApplicationOperationSpec(
    operation_id="skill_url.import",
    tool_name="import_lia_skill_url_tool",
    sections=("skills",),
    input_model=SkillUrlImportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS,),
)
