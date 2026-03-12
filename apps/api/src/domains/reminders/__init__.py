"""
Reminders domain - Reminder management.

Provides:
- Reminder model with status tracking
- Repository with anti-concurrence locking
- Service with business logic
- Pydantic schemas for API

Phase: Reminders with FCM notifications
Created: 2025-12-28
"""

from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.repository import ReminderRepository
from src.domains.reminders.schemas import (
    ReminderCreate,
    ReminderListResponse,
    ReminderResponse,
    ReminderStatusUpdate,
)
from src.domains.reminders.service import ReminderService

__all__ = [
    # Models
    "Reminder",
    "ReminderStatus",
    # Repository
    "ReminderRepository",
    # Service
    "ReminderService",
    # Schemas
    "ReminderCreate",
    "ReminderResponse",
    "ReminderListResponse",
    "ReminderStatusUpdate",
]
