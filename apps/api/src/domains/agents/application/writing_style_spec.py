"""The writing style, from the conversation as from the settings (ADR-383 amendment 2026-11-16).

The record stays readable and forgettable whatever the person's switch says (ADR-280: a
switch removes the capability, never the record); learning needs it on, since nothing is
read while it is off.
"""

from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleForgetPatch,
    WritingStyleLearnPatch,
)
from src.domains.writing_style.schemas import WritingStyleResponse

#: The settings section every writing-style operation mirrors.
WRITING_STYLE_SECTION = "writing-style"

WRITING_STYLE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="writing_style.read",
    tool_name="get_lia_writing_style_tool",
    sections=(WRITING_STYLE_SECTION,),
    input_model=ApplicationEmptyRead,
    output_model=WritingStyleResponse,
    kind=OperationKind.READ,
)

WRITING_STYLE_LEARN_OPERATION = ApplicationOperationSpec(
    operation_id="writing_style.learn",
    tool_name="learn_lia_writing_style_tool",
    sections=(WRITING_STYLE_SECTION,),
    input_model=WritingStyleLearnPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

WRITING_STYLE_FORGET_OPERATION = ApplicationOperationSpec(
    operation_id="writing_style.forget",
    tool_name="forget_lia_writing_style_tool",
    sections=(WRITING_STYLE_SECTION,),
    input_model=WritingStyleForgetPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
