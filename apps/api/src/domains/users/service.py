"""
Users service containing business logic for user management.
"""

from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from src.domains.chat.models import UserStatistics

from fastapi import Request
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    raise_admin_required,
    raise_user_not_found,
)
from src.core.field_names import FIELD_IS_ACTIVE, FIELD_USER_ID
from src.core.i18n import _
from src.domains.auth.models import User
from src.domains.users.repository import UserRepository
from src.domains.users.schemas import (
    HomeLocationData,
    HomeLocationResponse,
    HomeLocationUpdate,
    UserActivationResponse,
    UserActivationUpdate,
    UserAutocompleteItem,
    UserAutocompleteResponse,
    UserListResponse,
    UserListWithStatsResponse,
    UserProfile,
    UserProfileWithStats,
    UserSearchParams,
    UserUpdate,
)
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.email import get_email_service

logger = structlog.get_logger(__name__)


class UserService:
    """Service for user management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserRepository(db)

    async def get_user_by_id(self, user_id: UUID) -> UserProfile:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            UserProfile

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        return self._build_user_profile(user)

    def _build_user_profile(self, user: User) -> UserProfile:
        """
        Build UserProfile from User model, including decrypted home_address.

        Args:
            user: User model instance

        Returns:
            UserProfile with all fields populated
        """
        # Extract home_address from encrypted field
        home_address = None
        if user.home_location_encrypted:
            try:
                from src.core.security.utils import decrypt_data

                decrypted_json = decrypt_data(user.home_location_encrypted)
                location_data = HomeLocationData.model_validate_json(decrypted_json)
                home_address = location_data.address
            except Exception:
                # If decryption fails, leave home_address as None
                pass

        return UserProfile(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            timezone=user.timezone,
            language=user.language,
            personality_id=user.personality_id,
            home_address=home_address,
            is_active=user.is_active,
            is_verified=user.is_verified,
            is_superuser=user.is_superuser,
            oauth_provider=user.oauth_provider,
            picture_url=user.picture_url,
            memory_enabled=user.memory_enabled,
            voice_enabled=user.voice_enabled,
            tokens_display_enabled=user.tokens_display_enabled,
            theme=user.theme,
            color_theme=user.color_theme,
            font_family=user.font_family,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def get_all_users(
        self,
        page: int = 1,
        page_size: int = 50,
        is_active: bool | None = None,
    ) -> UserListResponse:
        """
        Get all users with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            is_active: Filter by active status (optional)

        Returns:
            UserListResponse with paginated users
        """
        # Validate pagination parameters
        from src.core.pagination_helpers import (
            calculate_skip,
            calculate_total_pages,
            validate_pagination,
        )

        page, page_size = validate_pagination(page, page_size)
        skip = calculate_skip(page, page_size)

        # Fetch users
        users, total = await self.repository.get_all_with_count(
            skip=skip,
            limit=page_size,
            is_active=is_active,
        )

        # Calculate total pages
        total_pages = calculate_total_pages(total, page_size)

        logger.info(
            "users_listed",
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )

        return UserListResponse(
            users=[self._build_user_profile(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_user(self, user_id: UUID, data: UserUpdate) -> UserProfile:
        """
        Update user profile.

        Args:
            user_id: User UUID
            data: Update data

        Returns:
            Updated UserProfile

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        # Type narrowing: user is User (not None) after exception check
        assert user is not None

        # Track timezone and language changes for special logging
        timezone_changed = False
        language_changed = False
        old_timezone = user.timezone
        old_language = user.language

        # Only update fields that are provided
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            # No fields to update
            return UserProfile.model_validate(user)

        # Check if timezone is being changed
        if "timezone" in update_data and update_data["timezone"] != old_timezone:
            timezone_changed = True

        # Check if language is being changed
        if "language" in update_data and update_data["language"] != old_language:
            language_changed = True

        # Update user
        user = await self.repository.update(user, update_data)
        await self.db.commit()

        # Recalculate scheduled actions if timezone changed
        if timezone_changed and user.timezone:
            try:
                from src.domains.scheduled_actions.service import ScheduledActionService

                sa_service = ScheduledActionService(self.db)
                recalc_count = await sa_service.recalculate_all_for_user(user_id, user.timezone)
                if recalc_count > 0:
                    await self.db.commit()
                    logger.info(
                        "scheduled_actions_recalculated_on_timezone_change",
                        user_id=str(user_id),
                        new_timezone=user.timezone,
                        recalculated_count=recalc_count,
                    )
            except Exception as e:
                logger.warning(
                    "scheduled_actions_recalculation_failed",
                    user_id=str(user_id),
                    error=str(e),
                )

        # Log with timezone and language change details
        log_data = {
            FIELD_USER_ID: str(user_id),
            "fields": list(update_data.keys()),
        }
        if timezone_changed:
            log_data["timezone_changed"] = "true"
            log_data["old_timezone"] = old_timezone
            log_data["new_timezone"] = user.timezone

        if language_changed:
            log_data["language_changed"] = "true"
            log_data["old_language"] = old_language
            log_data["new_language"] = user.language

        logger.info("user_profile_updated", **log_data)

        return self._build_user_profile(user)

    async def delete_user(self, user_id: UUID, hard_delete: bool = False) -> None:
        """
        Delete user (soft delete by default).

        Args:
            user_id: User UUID
            hard_delete: If True, permanently delete from database

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        # Type narrowing: user is User (not None) after exception check
        assert user is not None

        if hard_delete:
            await self.repository.hard_delete(user)
            logger.info("user_hard_deleted", user_id=str(user_id))
        else:
            await self.repository.delete(user)
            logger.info("user_soft_deleted", user_id=str(user_id))

        await self.db.commit()

    async def search_users_by_email(self, email_pattern: str) -> list[UserProfile]:
        """
        Search users by email pattern.

        Args:
            email_pattern: Email pattern to search for

        Returns:
            List of matching UserProfile objects
        """
        users = await self.repository.search_by_email(email_pattern)

        logger.info("users_searched", pattern=email_pattern, count=len(users))

        return [self._build_user_profile(user) for user in users]

    async def autocomplete_users(self, query: str, limit: int = 10) -> UserAutocompleteResponse:
        """
        Autocomplete users by email or full name (admin only).

        Searches both email and full_name fields (case-insensitive).
        Returns simplified user info for autocomplete dropdowns.

        Args:
            query: Search query (min 2 chars)
            limit: Maximum number of results (default 10)

        Returns:
            UserAutocompleteResponse with matching users
        """
        users = await self.repository.search_for_autocomplete(query, limit)

        logger.info(
            "users_autocomplete",
            query=query[:20],
            results=len(users),
        )

        return UserAutocompleteResponse(
            users=[
                UserAutocompleteItem(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    is_active=user.is_active,
                )
                for user in users
            ],
            total=len(users),
        )

    # ========== HOME LOCATION METHODS ==========

    async def get_home_location(self, user_id: UUID) -> HomeLocationResponse | None:
        """
        Get user's home location (decrypted).

        Args:
            user_id: User UUID

        Returns:
            HomeLocationResponse or None if not set
        """
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        if not user.home_location_encrypted:
            return None

        # Decrypt location data
        from src.core.security.utils import decrypt_data

        try:
            decrypted_json = decrypt_data(user.home_location_encrypted)
            location_data = HomeLocationData.model_validate_json(decrypted_json)
            return HomeLocationResponse(
                address=location_data.address,
                lat=location_data.lat,
                lon=location_data.lon,
                place_id=location_data.place_id,
            )
        except Exception as e:
            logger.error(
                "home_location_decrypt_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return None

    async def set_home_location(
        self,
        user_id: UUID,
        location: HomeLocationUpdate,
    ) -> HomeLocationResponse:
        """
        Set user's home location (encrypted).

        Requires Google Places connector to be active for the user.
        If coordinates are invalid (0,0), will geocode the address using Google Places.

        Args:
            user_id: User UUID
            location: Location data to set

        Returns:
            HomeLocationResponse with saved location

        Raises:
            HTTPException: If user not found, Google Places not active, or geocoding fails
        """
        from src.core.exceptions import raise_invalid_input, raise_permission_denied
        from src.core.security.utils import encrypt_data
        from src.domains.connectors.service import ConnectorService

        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        # Verify Google Places connector is enabled for this user
        connector_service = ConnectorService(self.db)
        if not await connector_service.is_places_enabled(user_id):
            raise_permission_denied(
                action="set home location",
                resource_type="home_location",
                details="Google Places connector must be enabled to set home location",
            )

        # Geocode if coordinates are invalid (0,0 or very close)
        final_lat = location.lat
        final_lon = location.lon
        final_place_id = location.place_id

        if abs(location.lat) < 0.0001 and abs(location.lon) < 0.0001:
            # Coordinates are essentially (0,0) - need geocoding
            logger.info(
                "home_location_geocoding_required",
                user_id=str(user_id),
                address=location.address[:50] if location.address else None,
            )

            try:
                from src.domains.connectors.clients.google_places_client import (
                    GooglePlacesClient,
                )

                places_client = GooglePlacesClient(
                    user_id=user_id,
                    language=user.language or "fr",
                )

                # Use search_text to geocode the address
                result = await places_client.search_text(
                    query=location.address,
                    max_results=1,
                    use_cache=False,  # Don't cache geocoding results
                )

                places = result.get("places", [])
                if not places:
                    raise_invalid_input(
                        f"Could not find location for address: {location.address[:50]}",
                        address=location.address,
                        error="no_results",
                    )

                # Extract coordinates from first result
                first_place = places[0]
                place_location = first_place.get("location", {})

                if not place_location.get("latitude") or not place_location.get("longitude"):
                    raise_invalid_input(
                        f"Could not geocode address: {location.address[:50]}",
                        address=location.address,
                        error="no_coordinates",
                    )

                final_lat = place_location["latitude"]
                final_lon = place_location["longitude"]
                final_place_id = first_place.get("id")

                # Track the API call (outside chat context, direct logging)
                # Note: search_text tracking via ContextVar is skipped when no tracker active
                from src.domains.google_api.service import GoogleApiUsageService

                await GoogleApiUsageService.record_api_call(
                    db=self.db,
                    user_id=user_id,
                    api_name="places",
                    endpoint="/places:searchText",
                )

                logger.info(
                    "home_location_geocoded",
                    user_id=str(user_id),
                    lat=final_lat,
                    lon=final_lon,
                    place_id=final_place_id,
                )

            except Exception as e:
                from fastapi import HTTPException

                if isinstance(e, HTTPException):
                    raise  # Re-raise HTTP exceptions (invalid_input, etc.)

                logger.error(
                    "home_location_geocoding_failed",
                    user_id=str(user_id),
                    address=location.address[:50] if location.address else None,
                    error=str(e),
                )
                raise_invalid_input(
                    f"Failed to geocode address: {str(e)[:100]}",
                    address=location.address,
                    error=str(e),
                )

        # Encrypt location data with geocoded coordinates
        location_data = HomeLocationData(
            address=location.address,
            lat=final_lat,
            lon=final_lon,
            place_id=final_place_id,
        )
        encrypted = encrypt_data(location_data.model_dump_json())

        # Update user
        await self.repository.update(user, {"home_location_encrypted": encrypted})
        await self.db.commit()

        logger.info(
            "home_location_set",
            user_id=str(user_id),
            address_preview=location.address[:50] if location.address else None,
            lat=final_lat,
            lon=final_lon,
        )

        return HomeLocationResponse(
            address=location.address,
            lat=final_lat,
            lon=final_lon,
            place_id=final_place_id,
        )

    async def clear_home_location(self, user_id: UUID) -> bool:
        """
        Clear user's home location.

        Args:
            user_id: User UUID

        Returns:
            True if cleared, False if was already empty

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(user_id)

        if not user:
            raise_user_not_found(user_id)

        if not user.home_location_encrypted:
            return False

        # Clear location
        await self.repository.update(user, {"home_location_encrypted": None})
        await self.db.commit()

        logger.info("home_location_cleared", user_id=str(user_id))

        return True

    # ========== ADMIN METHODS ==========

    async def search_users(
        self, params: UserSearchParams, admin_user_id: UUID
    ) -> UserListWithStatsResponse:
        """
        Search and list users with pagination and statistics (admin only).

        Args:
            params: Search parameters (query, filters, pagination)
            admin_user_id: ID of admin performing search

        Returns:
            UserListWithStatsResponse with paginated results including stats
        """
        # Build filters
        filters = []

        if params.q:
            # Search in email and full_name (case and accent insensitive)
            search_pattern = f"%{params.q}%"
            filters.append(
                or_(
                    func.unaccent(User.email).ilike(func.unaccent(search_pattern)),
                    func.unaccent(User.full_name).ilike(func.unaccent(search_pattern)),
                )
            )

        if params.is_active is not None:
            filters.append(User.is_active == params.is_active)

        if params.is_verified is not None:
            filters.append(User.is_verified == params.is_verified)

        if params.is_superuser is not None:
            filters.append(User.is_superuser == params.is_superuser)

        # Get paginated users with statistics (LEFT JOIN)
        users_with_stats = await self.repository.get_users_with_stats_paginated(
            filters=filters,
            page=params.page,
            page_size=params.page_size,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
        )

        # Get total count
        total = await self.repository.count_users(filters)

        from src.core.pagination_helpers import calculate_total_pages

        total_pages = calculate_total_pages(total, params.page_size)

        logger.info(
            "users_searched_admin",
            admin_user_id=str(admin_user_id),
            query=params.q,
            total_results=total,
            page=params.page,
        )

        # Fetch memory counts for all users in batch (from LangGraph store)
        user_ids = [user.id for user, _, _, _ in users_with_stats]
        memory_counts = await self._get_memory_counts_batch(user_ids)

        # Fetch interests counts for all users in batch (from DB)
        interests_counts = await self._get_interests_counts_batch(user_ids)

        # Build user profiles with stats
        users_profiles = []
        for user, stats, active_connectors_count, last_message_at in users_with_stats:
            users_profiles.append(
                self._build_user_profile_with_stats(
                    user,
                    stats,
                    active_connectors_count,
                    last_message_at,
                    memories_count=memory_counts.get(user.id, 0),
                    interests_count=interests_counts.get(user.id, 0),
                )
            )

        return UserListWithStatsResponse(
            users=users_profiles,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
        )

    async def _get_memory_counts_batch(self, user_ids: list[UUID]) -> dict[UUID, int]:
        """
        Get memory counts for multiple users from LangGraph store.

        Queries the semantic store to count memories per user.
        Uses a single store connection with multiple namespace queries.

        Args:
            user_ids: List of user UUIDs to count memories for

        Returns:
            Dict mapping user_id to memory count
        """
        from src.domains.agents.context.store import get_tool_context_store
        from src.infrastructure.store.semantic_store import MemoryNamespace

        counts: dict[UUID, int] = {}

        try:
            store = await get_tool_context_store()

            # Query each user's namespace (optimized: minimal data retrieval)
            for user_id in user_ids:
                try:
                    namespace = MemoryNamespace(str(user_id))
                    # Search with empty query to count all memories
                    results = await store.asearch(
                        namespace.to_tuple(),
                        query="",
                        limit=1000,  # Max memories to count
                    )
                    counts[user_id] = len(results)
                except Exception as e:
                    logger.warning(
                        "memory_count_failed_for_user",
                        user_id=str(user_id),
                        error=str(e),
                    )
                    counts[user_id] = 0

        except Exception as e:
            logger.warning(
                "memory_store_unavailable",
                error=str(e),
            )
            # Return empty counts if store unavailable
            for user_id in user_ids:
                counts[user_id] = 0

        return counts

    async def _get_interests_counts_batch(self, user_ids: list[UUID]) -> dict[UUID, int]:
        """
        Get interests counts for multiple users from database.

        Args:
            user_ids: List of user UUIDs to count interests for

        Returns:
            Dict mapping user_id to interests count
        """
        from src.domains.interests.repository import InterestRepository

        try:
            interest_repo = InterestRepository(self.db)
            return await interest_repo.count_by_user_ids(user_ids)
        except Exception as e:
            logger.warning(
                "interests_count_failed",
                error=str(e),
            )
            # Return zeros if query fails
            return {user_id: 0 for user_id in user_ids}

    def _build_user_profile_with_stats(
        self,
        user: User,
        stats: "UserStatistics | None",
        active_connectors_count: int = 0,
        last_message_at: datetime | None = None,
        memories_count: int = 0,
        interests_count: int = 0,
    ) -> UserProfileWithStats:
        """
        Build UserProfileWithStats from User and UserStatistics models.

        Args:
            user: User model instance
            stats: UserStatistics model instance (can be None)
            active_connectors_count: Number of active connectors for this user
            last_message_at: Timestamp of last message sent
            memories_count: Number of memories stored for this user
            interests_count: Number of interests for this user

        Returns:
            UserProfileWithStats with all fields populated
        """
        # Get base profile data
        base_profile = self._build_user_profile(user)

        # Calculate statistics - Lifetime totals
        tokens_in = stats.total_prompt_tokens if stats else 0
        tokens_out = stats.total_completion_tokens if stats else 0
        tokens_cache = stats.total_cached_tokens if stats else 0
        total_tokens = tokens_in + tokens_out + tokens_cache
        total_messages = stats.total_messages if stats else 0
        total_cost_eur = float(stats.total_cost_eur) if stats else 0.0
        total_google_api_requests = stats.total_google_api_requests if stats else 0

        # Calculate statistics - Current billing cycle
        cycle_prompt = stats.cycle_prompt_tokens if stats else 0
        cycle_completion = stats.cycle_completion_tokens if stats else 0
        cycle_cache = stats.cycle_cached_tokens if stats else 0
        cycle_tokens = cycle_prompt + cycle_completion + cycle_cache
        cycle_messages = stats.cycle_messages if stats else 0
        cycle_google_api_requests = stats.cycle_google_api_requests if stats else 0
        cycle_cost_eur = float(stats.cycle_cost_eur) if stats else 0.0

        return UserProfileWithStats(
            # Base profile fields
            id=base_profile.id,
            email=base_profile.email,
            full_name=base_profile.full_name,
            timezone=base_profile.timezone,
            language=base_profile.language,
            personality_id=base_profile.personality_id,
            home_address=base_profile.home_address,
            is_active=base_profile.is_active,
            is_verified=base_profile.is_verified,
            is_superuser=base_profile.is_superuser,
            oauth_provider=base_profile.oauth_provider,
            picture_url=base_profile.picture_url,
            memory_enabled=base_profile.memory_enabled,
            voice_enabled=base_profile.voice_enabled,
            tokens_display_enabled=base_profile.tokens_display_enabled,
            theme=base_profile.theme,
            color_theme=base_profile.color_theme,
            font_family=base_profile.font_family,
            created_at=base_profile.created_at,
            updated_at=base_profile.updated_at,
            # Statistics fields - Lifetime totals
            last_login=user.last_login,
            last_message_at=last_message_at,
            total_messages=total_messages,
            total_tokens=total_tokens,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            total_cost_eur=total_cost_eur,
            total_google_api_requests=total_google_api_requests,
            # Statistics fields - Current billing cycle
            cycle_messages=cycle_messages,
            cycle_tokens=cycle_tokens,
            cycle_google_api_requests=cycle_google_api_requests,
            cycle_cost_eur=cycle_cost_eur,
            # Other stats
            active_connectors_count=active_connectors_count,
            memories_count=memories_count,
            interests_count=interests_count,
        )

    async def update_user_activation(
        self,
        user_id: UUID,
        update_data: UserActivationUpdate,
        admin_user_id: UUID,
        request: Request | None = None,
    ) -> UserActivationResponse:
        """
        Activate or deactivate user account (admin only).

        When deactivating:
        - User cannot login
        - Existing sessions are invalidated
        - Reason is logged
        - Email notification sent

        Args:
            user_id: User ID to update
            update_data: Activation status and reason
            admin_user_id: ID of admin performing action
            request: FastAPI Request object (for IP/user agent)

        Returns:
            UserActivationResponse with user profile and email notification status

        Raises:
            HTTPException: If user not found
        """
        user = await self.repository.get_by_id(user_id, include_inactive=True)
        if not user:
            raise_user_not_found(user_id)

        # Type narrowing: user is User (not None) after exception check
        assert user is not None

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        # Update activation status
        user.is_active = update_data.is_active
        await self.repository.update(user, {FIELD_IS_ACTIVE: update_data.is_active})
        await self.db.commit()
        await self.db.refresh(user)

        # Create audit log
        await self.repository.create_audit_log(
            admin_user_id=admin_user_id,
            action="user_deactivated" if not update_data.is_active else "user_activated",
            resource_type="user",
            resource_id=user_id,
            details={
                "reason": update_data.reason,
                "user_email": user.email,
                "previous_status": not update_data.is_active,
                "new_status": update_data.is_active,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Initialize email notification tracking
        email_sent = False
        email_error = None

        # If deactivating, invalidate all sessions
        if not update_data.is_active:
            await self._invalidate_all_user_sessions(user_id)

            logger.warning(
                "user_deactivated",
                user_id=str(user_id),
                email=user.email,
                reason=update_data.reason,
                admin_user_id=str(admin_user_id),
            )

            # Send email notification
            email_service = get_email_service()
            email_sent = await email_service.send_user_deactivated_notification(
                user_email=user.email,
                user_name=user.full_name,
                reason=update_data.reason or "Non spécifiée",
                user_language=user.language,
            )

            if not email_sent:
                # Get user's language for error message
                from src.core.i18n import Language

                user_lang = cast(Language, user.language)
                email_error = _("Failed to send deactivation email notification", user_lang)
                logger.error(
                    "user_deactivation_email_failed",
                    user_id=str(user_id),
                    email=user.email,
                    admin_user_id=str(admin_user_id),
                )
        else:
            logger.info(
                "user_activated",
                user_id=str(user_id),
                email=user.email,
                admin_user_id=str(admin_user_id),
            )

            # Send email notification
            email_service = get_email_service()
            email_sent = await email_service.send_user_activated_notification(
                user_email=user.email,
                user_name=user.full_name,
                user_language=user.language,
            )

            if not email_sent:
                # Get user's language for error message
                from src.core.i18n import Language

                user_lang = cast(Language, user.language)
                email_error = _("Failed to send activation email notification", user_lang)
                logger.error(
                    "user_activation_email_failed",
                    user_id=str(user_id),
                    email=user.email,
                    admin_user_id=str(admin_user_id),
                )

        return UserActivationResponse(
            user=self._build_user_profile(user),
            email_notification_sent=email_sent,
            email_notification_error=email_error,
        )

    async def delete_user_gdpr(
        self,
        user_id: UUID,
        admin_user_id: UUID,
        request: Request | None = None,
    ) -> None:
        """
        Delete user and all associated data (RGPD compliance).

        Cascade deletes:
        - User record
        - All connectors (via SQLAlchemy cascade)
        - All sessions (Redis)
        - Future: conversations, documents, etc.

        Args:
            user_id: User ID to delete
            admin_user_id: ID of admin performing action
            request: FastAPI Request object (for IP/user agent)

        Raises:
            HTTPException: If user not found or is superuser
        """
        user = await self.repository.get_by_id(user_id, include_inactive=True)
        if not user:
            raise_user_not_found(user_id)

        # Type narrowing: user is User (not None) after exception check
        assert user is not None

        # Prevent deletion of superusers (safety check)
        if user.is_superuser:
            raise_admin_required(user_id)

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        # Count connectors before deletion for audit (using efficient COUNT query)
        connector_count = await self.repository.count_user_connectors(user_id)

        # Create audit log BEFORE deletion
        await self.repository.create_audit_log(
            admin_user_id=admin_user_id,
            action="user_deleted_gdpr",
            resource_type="user",
            resource_id=user_id,
            details={
                "user_email": user.email,
                "user_name": user.full_name,
                "had_connectors": connector_count,
                "was_verified": user.is_verified,
                "was_active": user.is_active,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Invalidate all sessions
        await self._invalidate_all_user_sessions(user_id)

        # Delete user (cascades to connectors via SQLAlchemy relationship)
        await self.repository.hard_delete(user)
        await self.db.commit()

        logger.warning(
            "user_deleted_gdpr",
            user_id=str(user_id),
            email=user.email,
            had_connectors=connector_count,
            admin_user_id=str(admin_user_id),
        )

    async def _invalidate_all_user_sessions(self, user_id: UUID) -> None:
        """
        Invalidate all Redis sessions for user using batched pipeline deletion.

        Optimized Implementation (Phase 3.2.9):
        - Scans all session:* keys in Redis using SCAN (O(N) complexity)
        - Parses each session JSON to check user_id match
        - Batch deletes using Redis pipeline (reduces network round-trips)
        - Performance: 3-5x faster than sequential delete() calls

        Architecture:
        - Phase 3.2.9: Batched deletion with pipeline
        - Future Phase: Maintain user_sessions:<user_id> SET for O(M) invalidation
          (Only implement if session invalidation becomes bottleneck at >10k sessions)
        """
        redis = await get_redis_session()

        try:
            # Get all session keys
            cursor = 0
            keys_to_delete = []

            # Phase 1: Scan and collect matching keys
            while True:
                cursor, keys = await redis.scan(cursor, match="session:*", count=100)
                for key in keys:
                    # Check key type to avoid WRONGTYPE error on SET keys (user tokens)
                    key_type = await redis.type(key)
                    if key_type != "string":
                        continue  # Skip non-string keys (like session:<user_id> SETs)

                    session_data = await redis.get(key)
                    if session_data:
                        # Check if this session belongs to the user
                        import json

                        try:
                            data = json.loads(session_data)
                            if data.get(FIELD_USER_ID) == str(user_id):
                                keys_to_delete.append(key)
                        except json.JSONDecodeError:
                            pass

                if cursor == 0:
                    break

            # Phase 2: Batch delete using pipeline (optimization)
            session_count = 0
            if keys_to_delete:
                pipeline = redis.pipeline()
                for key in keys_to_delete:
                    pipeline.delete(key)

                # Execute pipeline atomically
                results = await pipeline.execute()
                session_count = sum(1 for result in results if result > 0)

            logger.info(
                "user_sessions_invalidated",
                user_id=str(user_id),
                sessions_deleted=session_count,
            )
        except Exception as e:
            logger.error(
                "user_sessions_invalidation_failed",
                user_id=str(user_id),
                error=str(e),
            )
