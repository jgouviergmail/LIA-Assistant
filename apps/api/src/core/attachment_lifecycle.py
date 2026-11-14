"""Attachment status vocabulary shared by storage and account lifecycle policies."""


class AttachmentStatus:
    """Lifecycle status values; an uploaded writer is not presumed stopped."""

    UPLOADED = "uploaded"
    READY = "ready"
    EXPIRED = "expired"
    DELETING = "deleting"
