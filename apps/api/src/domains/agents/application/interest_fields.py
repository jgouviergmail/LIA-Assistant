"""Reviewed interest action vocabulary for addressed UI invalidation."""

from enum import Enum


class InterestActionField(str, Enum):
    REACTIVATE = "interest_to_reactivate"
    FEEDBACK = "interest_feedback"
    CREATE = "interest_to_create"
    UPDATE = "interest_configuration"
    DELETE = "interest_to_delete"
    DELETE_ALL = "interests_to_delete"
