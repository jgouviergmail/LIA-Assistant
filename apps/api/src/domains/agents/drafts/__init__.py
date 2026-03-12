"""
Drafts Package.

Provides infrastructure for deferred commands (drafts) that require user confirmation
before execution. Implements the HITL (Human-in-the-Loop) draft critique pattern.

Architecture:
- DraftType: Types of drafts (EMAIL, EVENT, CONTACT, etc.)
- DraftStatus: Lifecycle states (PENDING → CONFIRMED → EXECUTED)
- Draft: Full draft object with lifecycle methods
- DraftService: Service for creating drafts from tool inputs

HITL Flow:
    1. Tool creates draft via DraftService.create_*_draft()
    2. Draft returned as StandardToolOutput with requires_confirmation=True
    3. task_orchestrator detects draft, sets pending_draft_critique
    4. draft_critique_node presents draft to user via interrupt()
    5. User: CONFIRM → execute_draft() | EDIT → update | CANCEL → discard

Usage:
    from src.domains.agents.drafts import (
        DraftType,
        DraftStatus,
        DraftAction,
        Draft,
        EmailDraftInput,
        EventDraftInput,
        DraftService,
        create_email_draft,
        create_event_draft,
    )

    # Create email draft
    draft_output = await create_email_draft(
        EmailDraftInput(to="john@example.com", subject="Hi", body="Hello!"),
        registry={}
    )

Created: 2025-11-27
"""

from src.domains.agents.drafts.models import (
    BaseDraftInput,
    ContactDeleteDraftInput,
    ContactDraftInput,
    ContactUpdateDraftInput,
    Draft,
    DraftAction,
    DraftActionRequest,
    DraftActionResult,
    DraftInput,
    DraftStatus,
    DraftType,
    EmailDeleteDraftInput,
    EmailDraftInput,
    EmailForwardDraftInput,
    EmailReplyDraftInput,
    EventDeleteDraftInput,
    EventDraftInput,
    EventUpdateDraftInput,
    FileDeleteDraftInput,
    LabelDeleteDraftInput,
    TaskDeleteDraftInput,
    TaskDraftInput,
    TaskUpdateDraftInput,
)
from src.domains.agents.drafts.service import (
    DraftService,
    create_contact_delete_draft,
    create_contact_draft,
    create_contact_update_draft,
    create_delete_event_draft,
    create_email_delete_draft,
    create_email_draft,
    create_email_forward_draft,
    create_email_reply_draft,
    create_event_draft,
    create_file_delete_draft,
    create_label_delete_draft,
    create_task_delete_draft,
    create_task_draft,
    create_task_update_draft,
    create_update_event_draft,
)

__all__ = [
    # Models - Types & Status
    "DraftType",
    "DraftStatus",
    "DraftAction",
    # Models - Draft object
    "Draft",
    "DraftInput",
    "BaseDraftInput",
    # Models - Input types
    "EmailDraftInput",
    "EmailReplyDraftInput",
    "EmailForwardDraftInput",
    "EmailDeleteDraftInput",
    "EventDraftInput",
    "EventUpdateDraftInput",
    "EventDeleteDraftInput",
    "ContactDraftInput",
    "ContactUpdateDraftInput",
    "ContactDeleteDraftInput",
    "TaskDraftInput",
    "TaskUpdateDraftInput",
    "TaskDeleteDraftInput",
    "FileDeleteDraftInput",
    "LabelDeleteDraftInput",
    # Models - Request/Result
    "DraftActionRequest",
    "DraftActionResult",
    # Service
    "DraftService",
    # Convenience functions
    "create_email_draft",
    "create_email_reply_draft",
    "create_email_forward_draft",
    "create_email_delete_draft",
    "create_event_draft",
    "create_update_event_draft",
    "create_delete_event_draft",
    "create_contact_draft",
    "create_contact_update_draft",
    "create_contact_delete_draft",
    "create_task_draft",
    "create_task_update_draft",
    "create_task_delete_draft",
    "create_file_delete_draft",
    "create_label_delete_draft",
]
