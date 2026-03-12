"""
Notifications domain.

Provides Firebase Cloud Messaging (FCM) push notification support
and real-time SSE notifications.
"""

from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.repository import FCMTokenRepository
from src.domains.notifications.schemas import (
    TokenInfo,
    TokenRegisterRequest,
    TokenRegisterResponse,
    TokenUnregisterRequest,
    TokenUnregisterResponse,
    UserTokensResponse,
)
from src.domains.notifications.service import (
    FCMBatchResult,
    FCMNotificationService,
    FCMSendResult,
)

__all__ = [
    # Models
    "UserFCMToken",
    # Repository
    "FCMTokenRepository",
    # Service
    "FCMNotificationService",
    "FCMSendResult",
    "FCMBatchResult",
    # Schemas
    "TokenRegisterRequest",
    "TokenRegisterResponse",
    "TokenUnregisterRequest",
    "TokenUnregisterResponse",
    "UserTokensResponse",
    "TokenInfo",
]

# Note: router is imported directly in api/v1/routes.py to avoid circular imports
