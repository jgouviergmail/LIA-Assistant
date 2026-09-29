"""Reviewed read-only candidates shared by the basic and bounded selectors."""

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


def consultation_question(paths: dict[str, ReadPath]) -> ChoiceQuestion:
    question = ChoiceQuestion.model_validate_json(
        load_prompt("jev_consultation_question", version="v1")
    )
    return question.model_copy(
        update={
            "criteria": {
                key: value
                for key, value in question.criteria.items()
                if key in paths or key == "other"
            }
        }
    )
