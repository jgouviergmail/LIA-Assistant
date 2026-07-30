"""Draft-executor registry population (extracted from ``draft_executor``).

One function, one job: import every per-domain executor and bind it to its
``DraftType``. It lives apart from the execution engine because it is the only
part that must import the whole tool surface — keeping it here is what lets
``draft_executor`` stay a small engine as draft types keep being added.

The imports are deliberately LAZY (inside the function): the tool modules
import the drafts package back, so importing them at module load would close a
cycle.
"""

from __future__ import annotations

import structlog

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.services.draft_executor_types import (
    EXECUTOR_REGISTRY,
    register_executor,
)

logger = structlog.get_logger(__name__)


def ensure_executors_registered() -> None:
    """
    Lazy-load executor functions to avoid circular imports.

    Called on first use of DraftExecutor.
    Registers all draft type executors for the HITL confirmation flow.
    """
    if EXECUTOR_REGISTRY:
        return  # Already registered

    # Import and register all executor functions
    try:
        # Calendar executors
        from src.domains.agents.tools.calendar_tools import (
            execute_event_delete_draft,
            execute_event_draft,
            execute_event_update_draft,
        )

        # Drive executors
        from src.domains.agents.tools.drive_tools import execute_file_delete_draft

        # Email executors
        from src.domains.agents.tools.emails_tools import (
            execute_email_delete_draft,
            execute_email_draft,
            execute_email_forward_draft,
            execute_email_reply_draft,
        )

        # Contact executors
        from src.domains.agents.tools.google_contacts_tools import (
            execute_contact_delete_draft,
            execute_contact_draft,
            execute_contact_update_draft,
        )

        # Label executors
        from src.domains.agents.tools.labels_tools import execute_label_delete_draft

        # Reminder executors
        from src.domains.agents.tools.reminder_tools import execute_reminder_delete_draft

        # Task executors
        from src.domains.agents.tools.tasks_tools import (
            execute_task_delete_draft,
            execute_task_draft,
            execute_task_update_draft,
        )

        # Telephony executor (per-user connector; import is flag-independent — a
        # confirmed phone_call draft must always resolve to an executor)
        from src.domains.agents.tools.telephony_tools import execute_phone_call_draft

        # Register all executors
        # Email
        register_executor(DraftType.EMAIL.value, execute_email_draft)
        register_executor(DraftType.EMAIL_REPLY.value, execute_email_reply_draft)
        register_executor(DraftType.EMAIL_FORWARD.value, execute_email_forward_draft)
        register_executor(DraftType.EMAIL_DELETE.value, execute_email_delete_draft)

        # Calendar events
        register_executor(DraftType.EVENT.value, execute_event_draft)
        register_executor(DraftType.EVENT_UPDATE.value, execute_event_update_draft)
        register_executor(DraftType.EVENT_DELETE.value, execute_event_delete_draft)

        # Contacts
        register_executor(DraftType.CONTACT.value, execute_contact_draft)
        register_executor(DraftType.CONTACT_UPDATE.value, execute_contact_update_draft)
        register_executor(DraftType.CONTACT_DELETE.value, execute_contact_delete_draft)

        # Tasks
        register_executor(DraftType.TASK.value, execute_task_draft)
        register_executor(DraftType.TASK_UPDATE.value, execute_task_update_draft)
        register_executor(DraftType.TASK_DELETE.value, execute_task_delete_draft)

        # Drive files
        register_executor(DraftType.FILE_DELETE.value, execute_file_delete_draft)

        # Labels
        register_executor(DraftType.LABEL_DELETE.value, execute_label_delete_draft)

        # Reminders
        register_executor(DraftType.REMINDER_DELETE.value, execute_reminder_delete_draft)

        # Telephony
        register_executor(DraftType.PHONE_CALL.value, execute_phone_call_draft)

        # Automations (chat-created scheduled actions, ADR-140)
        from src.domains.agents.tools.automation_tools import execute_scheduled_action_draft

        register_executor(DraftType.SCHEDULED_ACTION.value, execute_scheduled_action_draft)

        # DevOps remote tasks (FN-1): the draft IS the confirmation gate
        from src.domains.agents.tools.devops_tools import execute_devops_task_draft

        register_executor(DraftType.DEVOPS_TASK.value, execute_devops_task_draft)

        # Peers relayed messages (A3): the draft IS the confirmation gate
        from src.domains.agents.tools.peers_tools import execute_peer_message_draft

        register_executor(DraftType.PEER_MESSAGE.value, execute_peer_message_draft)

        logger.info(
            "draft_executors_initialized",
            registered_types=list(EXECUTOR_REGISTRY.keys()),
            total_count=len(EXECUTOR_REGISTRY),
        )
    except ImportError as e:
        logger.error(
            "draft_executor_import_error",
            error=str(e),
        )
