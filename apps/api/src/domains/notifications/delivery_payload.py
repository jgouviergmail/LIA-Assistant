"""Typed Firebase payload and content-free, conservative error classification."""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from firebase_admin import exceptions, messaging

from src.core.constants import FCM_WEBPUSH_ICON_PATH


@dataclass(frozen=True, slots=True)
class TransportFailure:
    code: str
    invalid: bool = False
    retryable: bool = False
    retry_after_seconds: int = 60


def retry_after(value: str | None) -> int:
    if not value:
        return 60
    try:
        seconds = (
            int(value)
            if value.isdecimal()
            else int((parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        )
    except ValueError, TypeError, OverflowError:
        return 60
    return max(60, min(86400, seconds))


def classify_failure(error: Exception) -> TransportFailure:
    if isinstance(error, messaging.UnregisteredError | messaging.SenderIdMismatchError):
        return TransportFailure("DEVICE_INVALID", invalid=True)
    if isinstance(error, exceptions.ResourceExhaustedError):
        response = error.http_response
        delay = retry_after(response.headers.get("Retry-After") if response is not None else None)
        return TransportFailure("TRANSPORT_QUOTA", retryable=True, retry_after_seconds=delay)
    if isinstance(
        error,
        exceptions.InvalidArgumentError
        | exceptions.PermissionDeniedError
        | exceptions.UnauthenticatedError,
    ):
        return TransportFailure("TRANSPORT_REFUSED")
    # A deadline or dropped connection can hide a successful send. Retrying
    # these here would turn an unobservable acknowledgement into duplicates.
    return TransportFailure("DELIVERY_ACK_UNKNOWN")


def build_message(
    *,
    token: str,
    title: str,
    body: str,
    data: dict[str, str],
    image_url: str | None,
    occurrence: str | None,
) -> messaging.Message:
    return messaging.Message(
        notification=messaging.Notification(title=title, body=body, image=image_url),
        data=data,
        token=token,
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                click_action="OPEN_CHAT", channel_id="reminders", tag=occurrence
            ),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-collapse-id": occurrence} if occurrence else None,
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body), sound="default", badge=1
                )
            ),
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon=FCM_WEBPUSH_ICON_PATH,
                require_interaction=True,
                tag=occurrence,
            )
        ),
    )
