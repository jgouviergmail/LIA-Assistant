"""Reviewed read-only candidates shared by the basic and bounded selectors.

Both selectors ask ONE question (``jev_consultation_question``): structured rules,
the conservative ``other`` offered FIRST (Choice favours its first option), each
candidate a ``{"what": ...}`` criterion. Measured against the previous wording on
the gate and bounded corpora (2026-10-11): no wrong selection either way, and the
holdout coverage rose from 73.5 % to 88.2 %
(``docs/technical/JEV_SEMANTIC_QUALIFICATION.md``).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm.typesafe_client import ChoiceQuestion


@dataclass(frozen=True)
class ReadPath:
    domain: str
    tool: str
    parameters: tuple[tuple[str, str | bool | int], ...] = ()
    description: str = ""


READ_PATHS = {
    "email_recent": ReadPath("email", "get_emails_tool"),
    "email_unread": ReadPath("email", "get_emails_tool", (("query", "is:unread"),)),
    "email_inbox": ReadPath("email", "get_emails_tool", (("query", "in:inbox"),)),
    "contact_list": ReadPath("contact", "get_contacts_tool"),
    "file_list": ReadPath("file", "get_files_tool"),
    "folder_list": ReadPath("file", "get_files_tool", (("content_type", "folders_only"),)),
    "task_pending": ReadPath("task", "get_tasks_tool"),
    "task_completed": ReadPath(
        "task", "get_tasks_tool", (("show_completed", True), ("only_completed", True))
    ),
    "reminder_pending": ReadPath("reminder", "list_reminders_tool"),
}


def _template() -> ChoiceQuestion:
    return ChoiceQuestion.model_validate_json(
        load_prompt("jev_consultation_question", version="v1")
    )


def path_label(key: str) -> str:
    """The reviewed wording of one fixed listing (its criterion's ``what``)."""
    criterion = _template().criteria[key]
    assert isinstance(criterion, dict) and isinstance(criterion.get("what"), str)
    return str(criterion["what"])


def candidate_question(descriptions: Mapping[str, str]) -> ChoiceQuestion:
    """The same question over listings the code built (``other`` stays first)."""
    template = _template()
    return template.model_copy(
        update={
            "criteria": {
                "other": template.criteria["other"],
                **{key: {"what": text} for key, text in descriptions.items()},
            }
        }
    )


def consultation_question(paths: dict[str, ReadPath]) -> ChoiceQuestion:
    question = _template()
    return question.model_copy(
        update={
            "criteria": {
                key: value
                for key, value in question.criteria.items()
                if key in paths or key == "other"
            }
        }
    )
