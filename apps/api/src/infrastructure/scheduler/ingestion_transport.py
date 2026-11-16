"""Existing FCM and SSE transports, with no chat archive or channel dispatch."""

import json

from src.core.i18n import resolve_language
from src.core.i18n_types import frontend_language_code
from src.domains.ingestion.delivery_types import (
    NTFY_DESTINATION_KEY,
    DeliveryDisposition,
    DeliveryResult,
)
from src.domains.notifications.ntfy_delivery import (
    NtfyBatch,
    NtfyTargetsUnreadable,
    push_to_ntfy,
)
from src.domains.notifications.service import FCMNotificationService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.user_channel import user_notifications_channel
from src.infrastructure.database.session import get_db_context
from src.infrastructure.external.ntfy_client import NtfyOutcome
from src.infrastructure.scheduler.ingestion_delivery import DeliveryEnvelope


def _ntfy_result(batch: NtfyBatch) -> DeliveryResult:
    """ntfy's verdict as the outbox reads it: retried only when nothing could have arrived."""
    if batch.sent:
        return DeliveryResult(DeliveryDisposition.ACCEPTED)
    if not batch.outcomes:
        # Switched off, or no subscription left since the fan-out.
        return DeliveryResult(DeliveryDisposition.CANCELLED, "NTFY_UNAVAILABLE")
    if batch.retryable and batch.retry_after_seconds:
        return DeliveryResult(
            DeliveryDisposition.RETRYABLE, "TRANSPORT_UNAVAILABLE", batch.retry_after_seconds
        )
    if batch.retryable:
        return DeliveryResult(DeliveryDisposition.RETRYABLE, "TRANSPORT_UNAVAILABLE")
    if NtfyOutcome.NO_ANSWER in batch.outcomes:
        return DeliveryResult(DeliveryDisposition.UNKNOWN, "DELIVERY_ACK_UNKNOWN")
    return DeliveryResult(DeliveryDisposition.PERMANENT, "TRANSPORT_REFUSED")


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
        if envelope.destination_key == NTFY_DESTINATION_KEY:
            try:
                batch = await push_to_ntfy(
                    envelope.user_id,
                    title=envelope.title,
                    body=envelope.body,
                    click_path=data["url"],
                )
            except NtfyTargetsUnreadable:
                # Nothing left: neither « nobody is subscribed » nor « unknown ».
                return DeliveryResult(DeliveryDisposition.RETRYABLE, "TRANSPORT_UNAVAILABLE")
            return _ntfy_result(batch)
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
