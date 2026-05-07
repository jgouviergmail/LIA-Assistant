"""
System Settings domain.

Provides application-wide settings controlled by administrators.
Settings are stored in the database and cached in Redis for performance.

Features:
- Debug panel toggle (admin-only visibility) and user-access flag
- Audit trail for admin changes
- Redis caching with TTL

The legacy ``voice_tts_mode`` setting was retired in v1.20.x — TTS provider
and voice selection now live on ``llm_config_overrides`` (LLM type
``voice_tts``).

Created: 2026-01-16
"""

from .models import SystemSetting, SystemSettingKey
from .schemas import SystemSettingResponse
from .service import SystemSettingsService

__all__ = [
    # Models
    "SystemSetting",
    "SystemSettingKey",
    # Schemas
    "SystemSettingResponse",
    # Service
    "SystemSettingsService",
]
