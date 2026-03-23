"""
Channel service for OTP linking, CRUD operations, and binding management.

Handles:
- OTP code generation and storage in Redis
- OTP verification and binding creation (called from webhook handler)
- Binding listing, toggling, and deletion

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

import json
import secrets
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    CHANNEL_OTP_ATTEMPTS_REDIS_PREFIX,
    CHANNEL_OTP_REDIS_PREFIX,
)
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.channels.models import ChannelType, UserChannelBinding
from src.domains.channels.repository import UserChannelBindingRepository
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_active_bindings,
    channel_otp_generated_total,
    channel_otp_verified_total,
)

logger = get_logger(__name__)


class ChannelService:
    """Service for channel binding management and OTP linking flow."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserChannelBindingRepository(db)

    # ========================================================================
    # OTP Generation
    # ========================================================================

    async def generate_otp(
        self,
        user_id: UUID,
        channel_type: ChannelType,
    ) -> tuple[str, int]:
        """
        Generate an OTP code for channel linking.

        Stores the OTP in Redis with TTL. The code is single-use
        (deleted upon successful verification).

        Args:
            user_id: The LIA user requesting the link.
            channel_type: Target channel type (e.g., telegram).

        Returns:
            Tuple of (otp_code, ttl_seconds).

        Raises:
            ValidationError: If user already has an active binding for this channel type.
        """
        # Check if user already has a binding for this channel type
        existing = await self.repository.get_by_user_and_type(user_id, channel_type.value)
        if existing:
            raise ValidationError(
                f"You already have a {channel_type.value} account linked. "
                "Unlink it first to link a new one."
            )

        otp_length = settings.channel_otp_length
        otp_ttl = settings.channel_otp_ttl_seconds

        # Generate cryptographically secure numeric OTP
        code = "".join(secrets.choice("0123456789") for _ in range(otp_length))

        # Store in Redis
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()
        key = f"{CHANNEL_OTP_REDIS_PREFIX}{code}"
        data = {
            "user_id": str(user_id),
            "channel_type": channel_type.value,
        }
        await redis.setex(key, otp_ttl, json.dumps(data))

        channel_otp_generated_total.labels(channel_type=channel_type.value).inc()

        logger.info(
            "channel_otp_generated",
            user_id=str(user_id),
            channel_type=channel_type.value,
            ttl_seconds=otp_ttl,
        )

        return code, otp_ttl

    # ========================================================================
    # OTP Verification (called from webhook handler)
    # ========================================================================

    @staticmethod
    async def verify_otp(
        code: str,
        channel_type: str,
        channel_user_id: str,
        channel_username: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Verify an OTP code and return the binding data if valid.

        This is a static method because it's called from the webhook handler
        (background task) which creates its own DB session.

        Does NOT create the binding — the caller is responsible for that
        (to control the DB session lifecycle in background tasks).

        Args:
            code: The OTP code to verify.
            channel_type: Expected channel type.
            channel_user_id: Provider-specific user ID (e.g., chat_id).
            channel_username: Provider-specific username (optional).

        Returns:
            Dict with {user_id, channel_type} if valid, None if invalid/expired.
        """
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()

        # Check brute-force block
        attempts_key = f"{CHANNEL_OTP_ATTEMPTS_REDIS_PREFIX}{channel_user_id}"
        max_attempts = settings.channel_otp_max_attempts
        block_ttl = settings.channel_otp_block_ttl_seconds

        current_attempts = await redis.get(attempts_key)
        if current_attempts and int(current_attempts) >= max_attempts:
            logger.warning(
                "channel_otp_brute_force_blocked",
                channel_user_id=channel_user_id,
                attempts=int(current_attempts),
            )
            return None

        # Atomic get-and-delete (consume OTP)
        key = f"{CHANNEL_OTP_REDIS_PREFIX}{code}"
        pipe = redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()

        raw = results[0]
        if not raw:
            # Invalid or expired OTP — increment attempt counter
            pipe2 = redis.pipeline()
            pipe2.incr(attempts_key)
            pipe2.expire(attempts_key, block_ttl)
            await pipe2.execute()

            channel_otp_verified_total.labels(
                channel_type=channel_type,
                status="invalid",
            ).inc()
            logger.warning(
                "channel_otp_invalid",
                channel_user_id=channel_user_id,
                code_provided=code[:2] + "****",
            )
            return None

        try:
            data: dict = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("channel_otp_corrupt_data", key=key)
            return None

        # Verify channel type matches
        if data.get("channel_type") != channel_type:
            logger.warning(
                "channel_otp_type_mismatch",
                expected=channel_type,
                got=data.get("channel_type"),
            )
            return None

        # Clear attempt counter on success
        await redis.delete(attempts_key)

        channel_otp_verified_total.labels(
            channel_type=channel_type,
            status="success",
        ).inc()

        logger.info(
            "channel_otp_verified",
            user_id=data["user_id"],
            channel_type=channel_type,
            channel_user_id=channel_user_id,
        )

        return data

    # ========================================================================
    # Binding CRUD
    # ========================================================================

    async def create_binding(
        self,
        user_id: UUID,
        channel_type: str,
        channel_user_id: str,
        channel_username: str | None = None,
    ) -> UserChannelBinding:
        """
        Create a new channel binding after OTP verification.

        Args:
            user_id: LIA user ID.
            channel_type: Channel type (e.g., 'telegram').
            channel_user_id: Provider user ID (e.g., chat_id).
            channel_username: Provider username (optional).

        Returns:
            Created UserChannelBinding.

        Raises:
            ValidationError: If a binding already exists for this user+channel
                or for this channel_user_id.
        """
        # Check for existing binding (user + channel type)
        existing = await self.repository.get_by_user_and_type(user_id, channel_type)
        if existing:
            raise ValidationError(f"A {channel_type} binding already exists for this user")

        # Check for existing binding (channel_user_id already linked)
        existing_channel = await self.repository.get_by_channel_id(channel_type, channel_user_id)
        if existing_channel:
            raise ValidationError(f"This {channel_type} account is already linked to another user")

        binding = await self.repository.create(
            {
                "user_id": user_id,
                "channel_type": channel_type,
                "channel_user_id": channel_user_id,
                "channel_username": channel_username,
                "is_active": True,
            }
        )

        channel_active_bindings.labels(channel_type=channel_type).inc()

        logger.info(
            "channel_binding_created",
            user_id=str(user_id),
            channel_type=channel_type,
            channel_user_id=channel_user_id,
        )

        return binding

    async def list_bindings(self, user_id: UUID) -> list[UserChannelBinding]:
        """List all channel bindings for a user."""
        return await self.repository.get_all_for_user(user_id)

    async def get_binding_with_ownership_check(
        self,
        binding_id: UUID,
        user_id: UUID,
    ) -> UserChannelBinding:
        """
        Get a binding with ownership verification.

        Raises:
            ResourceNotFoundError: If binding doesn't exist or belongs to another user.
        """
        binding = await self.repository.get_by_id(binding_id, include_inactive=True)
        if not binding or binding.user_id != user_id:
            raise ResourceNotFoundError("channel_binding", str(binding_id))
        return binding

    async def toggle_binding(
        self,
        binding_id: UUID,
        user_id: UUID,
    ) -> UserChannelBinding:
        """
        Toggle a channel binding's active state.

        Raises:
            ResourceNotFoundError: If binding doesn't exist or belongs to another user.
        """
        binding = await self.get_binding_with_ownership_check(binding_id, user_id)
        binding = await self.repository.update(binding, {"is_active": not binding.is_active})

        logger.info(
            "channel_binding_toggled",
            binding_id=str(binding_id),
            user_id=str(user_id),
            is_active=binding.is_active,
        )

        return binding

    async def delete_binding(
        self,
        binding_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Delete a channel binding (unlink).

        Raises:
            ResourceNotFoundError: If binding doesn't exist or belongs to another user.
        """
        binding = await self.get_binding_with_ownership_check(binding_id, user_id)
        await self.repository.delete(binding)

        channel_active_bindings.labels(channel_type=binding.channel_type).dec()

        logger.info(
            "channel_binding_deleted",
            binding_id=str(binding_id),
            user_id=str(user_id),
            channel_type=binding.channel_type,
        )
