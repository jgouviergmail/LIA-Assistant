"""
System Settings domain.

Provides application-wide settings controlled by administrators.
Settings are stored in the database and cached in Redis for performance.

Features:
- Voice TTS mode (standard/hd) - Global voice quality setting
- Audit trail for admin changes
- Redis caching with TTL

Usage:
    from src.domains.system_settings import get_voice_tts_mode, SystemSettingsService

    # Get current voice mode (cached)
    mode = await get_voice_tts_mode()  # "standard" or "hd"

    # Admin: Update voice mode
    service = SystemSettingsService(db)
    await service.set_voice_tts_mode("hd", admin_user_id, request)

Created: 2026-01-16
"""

from .models import SystemSetting, SystemSettingKey
from .schemas import (
    SystemSettingResponse,
    VoiceTTSModeResponse,
    VoiceTTSModeUpdate,
)
from .service import SystemSettingsService, get_voice_tts_mode, invalidate_voice_tts_mode_cache

__all__ = [
    # Models
    "SystemSetting",
    "SystemSettingKey",
    # Schemas
    "SystemSettingResponse",
    "VoiceTTSModeResponse",
    "VoiceTTSModeUpdate",
    # Service
    "SystemSettingsService",
    "get_voice_tts_mode",
    "invalidate_voice_tts_mode_cache",
]
