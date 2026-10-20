"""Existing FCM and SSE transports, with no chat archive or channel dispatch."""

import json

from src.core.i18n import resolve_language
from src.core.i18n_types import frontend_language_code
from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult
from src.domains.notifications.service import FCMNotificationService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.user_channel import user_notifications_channel
from src.infrastructure.database.session import get_db_context
from src.infrastructure.scheduler.ingestion_delivery import DeliveryEnvelope


class IngestionTransport:
    async def send(self, envelope: DeliveryEnvelope) -> DeliveryResult:
        language = frontend_language_code(resolve_language(envelope.language))
        data = {
            "type": "sms_received",
            "message_id": str(envelope.message_id),
            "occurrence_id": str(envelope.occurrence),
            "user_id": str(envelope.user_id),
            "url": f"/{language}/dashboard/sms?message={envelope.message_id}",
        }
        if envelope.destination_key == "sse":
            redis = await get_redis_cache()
            await redis.publish(user_notifications_channel(envelope.user_id), json.dumps(data))
            # Accepted by Redis is distinct from an FCM acceptance or a read.
            return DeliveryResult(DeliveryDisposition.ACCEPTED)
        if envelope.token is None:
            return DeliveryResult(DeliveryDisposition.CANCELLED, "DEVICE_INVALID")
        # The service's public single-device seam performs no SQL. Close the
        # unused session before network I/O rather than hold a transaction.
        async with get_db_context() as db:
            service = FCMNotificationService(db)
        result = await service.send_to_device(
            token=envelope.token,
            title=envelope.title,
            body=envelope.body,
            data=data,
            occurrence_key=str(envelope.occurrence),
        )
        if result.success:
            return DeliveryResult(DeliveryDisposition.ACCEPTED)
        if result.retryable:
            return DeliveryResult(
                DeliveryDisposition.RETRYABLE,
                result.error_code or "TRANSPORT_UNAVAILABLE",
                result.retry_after_seconds,
            )
        if result.token_invalid or result.error_code == "TRANSPORT_REFUSED":
            return DeliveryResult(
                DeliveryDisposition.PERMANENT, result.error_code or "DEVICE_INVALID"
            )
        return DeliveryResult(DeliveryDisposition.UNKNOWN, "DELIVERY_ACK_UNKNOWN")
