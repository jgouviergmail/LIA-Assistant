"""Only source requests enter Workboard edit prompts; private selection proofs never do."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.workboard_comment_schemas import (
    WorkboardCommentInput,
    WorkboardCommentPatch,
)
from src.domains.agents.application.workboard_create_schemas import (
    WorkboardCreateInput,
    WorkboardCreatePatch,
)
from src.domains.agents.application.workboard_delete_schemas import (
    WorkboardDeleteInput,
    WorkboardDeletePatch,
)
from src.domains.agents.application.workboard_update_schemas import (
    WorkboardUpdateInput,
    WorkboardUpdatePatch,
)

WORKBOARD_EDITOR_MODELS: tuple[type[BaseModel], ...] = (
    WorkboardCreatePatch,
    WorkboardCommentPatch,
    WorkboardDeletePatch,
    WorkboardUpdatePatch,
)


def workboard_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is WorkboardCreatePatch:
        return WorkboardCreateInput, WorkboardCreatePatch.model_validate(
            intent
        ).workboard_create.request.model_dump(mode="json")
    if model is WorkboardCommentPatch:
        return WorkboardCommentInput, WorkboardCommentPatch.model_validate(
            intent
        ).workboard_comment.request.model_dump(mode="json")
    if model is WorkboardDeletePatch:
        return WorkboardDeleteInput, WorkboardDeletePatch.model_validate(
            intent
        ).workboard_delete.request.model_dump(mode="json")
    if model is WorkboardUpdatePatch:
        return WorkboardUpdateInput, WorkboardUpdatePatch.model_validate(
            intent
        ).workboard_update.request.model_dump(mode="json", exclude_none=True)
    raise ValueError("Unknown Workboard editor")
