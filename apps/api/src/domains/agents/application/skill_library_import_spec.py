"""Both personal library writes use the original mandatory confirmation boundary."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.skill_library_import_schemas import LibraryImportPatch
from src.domains.feature_switches.registry import PlatformCapability

LIBRARY_INSTALL_OPERATION = ApplicationOperationSpec(
    operation_id="skill_library.install",
    tool_name="install_lia_library_skill_tool",
    sections=("skills",),
    input_model=LibraryImportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS, PlatformCapability.SKILL_LIBRARY),
)
LIBRARY_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="skill_library.update",
    tool_name="update_lia_library_skill_tool",
    sections=("skills",),
    input_model=LibraryImportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.SKILLS, PlatformCapability.SKILL_LIBRARY),
)
