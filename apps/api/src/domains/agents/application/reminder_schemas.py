"""Reminder mutation keys carried by addressed invalidation hints."""

from enum import StrEnum


class ReminderField(StrEnum):
    UPDATE = "reminder_configuration"
    CREATE = "reminder_to_create"
    DELETE = "reminder_to_delete"
