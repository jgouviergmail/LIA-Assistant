"""Execution reports share public data only; private comparison snapshots stay in commands."""

from pydantic import JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_action_schemas import canonical_habit, habit_command
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch
from src.domains.agents.application.habit_forgetting import canonical_habit_forgetting
from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeletePatch
from src.domains.agents.application.interest_create_schemas import InterestCreatePatch
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackPatch
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivationPatch
from src.domains.agents.application.interest_removal_schemas import InterestDeletePatch
from src.domains.agents.application.interest_update_schemas import InterestUpdatePatch
from src.domains.agents.application.live_connector_schemas import LiveConnectorPreferencePatch
from src.domains.agents.application.live_schemas import LivePreferencePatch
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeletePatch
from src.domains.agents.application.memory_create_schemas import MemoryCreatePatch
from src.domains.agents.application.memory_pin_schemas import MemoryPinPatch
from src.domains.agents.application.memory_removal_schemas import MemoryDeletePatch
from src.domains.agents.application.memory_update_schemas import MemoryUpdatePatch
from src.domains.agents.application.open_loop_action_schemas import canonical_open_loop
from src.domains.agents.application.phone_number_schemas import PhoneNumberPatch
from src.domains.agents.application.phone_preference_schemas import PhonePreferencePatch
from src.domains.agents.application.reminder_create_schemas import ReminderCreatePatch
from src.domains.agents.application.reminder_removal_schemas import ReminderDeletePatch
from src.domains.agents.application.reminder_update_schemas import ReminderUpdatePatch
from src.domains.agents.application.routine_create_schemas import RoutineCreatePatch
from src.domains.agents.application.routine_removal_schemas import RoutineDeletePatch
from src.domains.agents.application.routine_run_schemas import RoutineRunPatch
from src.domains.agents.application.routine_schemas import RoutineStatePatch
from src.domains.agents.application.routine_update_schemas import RoutineUpdatePatch
from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferencePatch


def _reminder_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    if draft.operation_id == "reminder.update":
        edited_reminder = ReminderUpdatePatch.model_validate(draft.intent).reminder_configuration
        return {
            "reminder_id": str(edited_reminder.expected.id),
            **edited_reminder.configuration.model_dump(mode="json"),
        }
    if draft.operation_id == "reminder.delete":
        removed_reminder = ReminderDeletePatch.model_validate(draft.intent).reminder_to_delete
        return {
            "reminder_id": str(removed_reminder.id),
            "content": removed_reminder.content,
            "deleted": True,
        }
    if draft.operation_id == "reminder.create":
        reminder = ReminderCreatePatch.model_validate(draft.intent).reminder_to_create
        return {
            "reminder_id": str(reminder.id),
            "content": reminder.configuration.content,
            "trigger_at": reminder.trigger_at.isoformat(),
            "user_timezone": reminder.user_timezone,
            "recurrence": reminder.recurrence.model_dump(mode="json"),
        }
    raise ValueError("Unsupported reminder result")


def _memory_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    if draft.operation_id == "memories.delete_all":
        erased_memories = MemoryBulkDeletePatch.model_validate(draft.intent).memories_to_delete
        return {
            "deleted_count": erased_memories.selected_count,
            "preserved_count": erased_memories.preserved_count,
            "preserve_pinned": erased_memories.preserve_pinned,
        }
    if draft.operation_id == "memories.delete":
        removed_memory = MemoryDeletePatch.model_validate(draft.intent).memory_to_delete
        return {"memory_id": str(removed_memory.id), "deleted": True}
    if draft.operation_id == "memories.update":
        edited_memory = MemoryUpdatePatch.model_validate(draft.intent).memory_configuration
        return {
            "memory_id": str(edited_memory.expected.id),
            "pinned": edited_memory.expected.pinned,
            **edited_memory.configuration.model_dump(mode="json"),
        }
    if draft.operation_id == "memories.create":
        created_memory = MemoryCreatePatch.model_validate(draft.intent).memory_to_create
        return {
            "memory_id": str(created_memory.id),
            "created": True,
            "pinned": created_memory.pinned,
            **created_memory.configuration.model_dump(mode="json"),
        }
    if draft.operation_id == "memories.pin":
        pinned_memory = MemoryPinPatch.model_validate(draft.intent).memory_pin
        return {"memory_id": str(pinned_memory.expected.id), "pinned": pinned_memory.pinned}
    raise ValueError("Unsupported memory result")


def _interest_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    if draft.operation_id == "interests.reactivate":
        dormant = InterestReactivationPatch.model_validate(draft.intent).interest_to_reactivate
        return {
            "interest_id": str(dormant.expected.id),
            "status": dormant.result.status,
            "positive_signals": dormant.result.positive_signals,
            "negative_signals": dormant.result.negative_signals,
            "last_mentioned_at_refreshed": True,
            "last_notified_at": None,
            "dormant_since": None,
        }
    if draft.operation_id == "interests.feedback":
        verdict = InterestFeedbackPatch.model_validate(draft.intent).interest_feedback
        return {
            "interest_id": str(verdict.expected.id),
            "feedback": verdict.feedback,
            "notification_id": str(verdict.notification.id) if verdict.notification else None,
            "status": verdict.expected.status.value,
            **verdict.configuration.model_dump(mode="json"),
        }
    if draft.operation_id == "interests.delete_all":
        removed_interests = InterestBulkDeletePatch.model_validate(draft.intent).interests_to_delete
        return {"deleted_count": removed_interests.selected_count}
    if draft.operation_id == "interests.delete":
        removed_interest = InterestDeletePatch.model_validate(draft.intent).interest_to_delete
        return {"interest_id": str(removed_interest.expected.id), "deleted": True}
    if draft.operation_id == "interests.update":
        edited_interest = InterestUpdatePatch.model_validate(draft.intent).interest_configuration
        return {
            "interest_id": str(edited_interest.expected.id),
            **edited_interest.configuration.model_dump(mode="json"),
        }
    if draft.operation_id == "interests.create":
        interest = InterestCreatePatch.model_validate(draft.intent).interest_to_create
        return {
            "interest_id": str(interest.id),
            "created": True,
            **interest.configuration.model_dump(mode="json"),
        }
    raise ValueError("Unsupported interest result")


def _open_loop_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    if not canonical_open_loop(draft):
        raise ValueError("Invalid commitment result")
    return {"open_loop": draft.after["open_loop"]}


def _habit_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    if draft.operation_id == "habits.recompute":
        # The source receipt supplies the observed result; there is no forecast.
        return {"recompute_result_unavailable": True}
    if draft.operation_id == "habits.forget":
        if not canonical_habit_forgetting(draft):
            raise ValueError("Invalid full habit erasure scope")
        selected = HabitForgetPatch.model_validate(draft.intent).habit_data
        return {
            "deleted_habits": selected.habits,
            "profile_deleted": True,
            "deleted_activity_days": selected.activity_days,
            "advisory_cleanup_confirmed": False,
        }
    if not canonical_habit(draft):
        raise ValueError("Invalid habit result")
    expected, change = habit_command(draft)
    return {
        "habit_id": str(expected.id),
        "status": change.status if change else None,
        "deleted": change is None,
    }


def public_application_values(draft: ApplicationActionDraftContent) -> dict[str, JsonValue]:
    projection = {
        "open_loops": _open_loop_values,
        "habits": _habit_values,
        "interests": _interest_values,
        "memories": _memory_values,
        "reminder": _reminder_values,
    }.get(draft.operation_id.partition(".")[0])
    if projection is not None:
        return projection(draft)
    if draft.operation_id == "routine.execute":
        launched = RoutineRunPatch.model_validate(draft.intent).routine_to_run
        return {
            "routine_id": str(launched.expected.id),
            "title": launched.configuration.title,
            "launch_reserved": True,
            "execution_completed": False,
        }
    if draft.operation_id == "routine.update":
        edited = RoutineUpdatePatch.model_validate(draft.intent).routine_configuration
        return {
            "routine_id": str(edited.expected.id),
            "title": edited.configuration.title,
            "is_enabled": edited.enabled,
        }
    if draft.operation_id == "routine.delete":
        removed = RoutineDeletePatch.model_validate(draft.intent).routine_to_delete
        return {"routine_id": str(removed.id), "title": removed.title, "deleted": True}
    if draft.operation_id == "routine.create":
        created = RoutineCreatePatch.model_validate(draft.intent).routine_to_create
        return {
            "routine_id": str(created.id),
            "title": created.configuration.title,
            "is_enabled": True,
        }
    if draft.operation_id == "routine_state.update":
        routine_state = RoutineStatePatch.model_validate(draft.intent).routine_state
        return {
            "routine_id": str(routine_state.expected.id),
            "title": routine_state.expected.title,
            "is_enabled": routine_state.enabled,
        }
    if draft.operation_id == "phone_number.update":
        current_number = PhoneNumberPatch.model_validate(draft.intent).phone_number
        return {"phone_number": current_number.public_values().model_dump(mode="json")}
    if draft.operation_id == "phone_preferences.update":
        current_phone = PhonePreferencePatch.model_validate(draft.intent).phone_preferences
        return {"phone_preferences": current_phone.values.model_dump(mode="json")}
    if draft.operation_id == "live_connector_preferences.update":
        current = LiveConnectorPreferencePatch.model_validate(draft.intent).live_connector_settings
        return {
            "live_connector_settings": {
                "provider": current.expected.provider,
                "settings": current.settings.model_dump(mode="json"),
            }
        }
    if draft.operation_id == "live_preferences.update":
        current_live = LivePreferencePatch.model_validate(draft.intent).live_reflexes
        return {"live_reflexes": current_live.values.model_dump(mode="json")}
    if draft.operation_id == "shared_mcp_preferences.update":
        current_mcp = SharedMCPPreferencePatch.model_validate(draft.intent).shared_mcp_server
        return {
            "shared_mcp_server": current_mcp.model_dump(mode="json", exclude={"catalogue_digest"})
        }
    return draft.after
