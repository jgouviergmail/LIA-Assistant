"""A returned SMTP refusal map means some recipients already accepted the mail."""


class SMTPPartialAcceptanceError(Exception):
    """Known partial acceptance, without retaining recipient addresses or server text."""

    def __init__(self, accepted: int, refused: int) -> None:
        self.accepted = accepted
        self.refused = refused
        super().__init__(
            f"SMTP accepted {accepted} recipient(s) and refused {refused}. "
            "Do not resend to everyone; check recipient status before any new attempt."
        )

    def to_failure(self) -> dict[str, object]:
        """The truthful finite facts shared by tools and confirmation cards."""
        return {
            "success": False,
            "error_code": "PARTIAL_SEND",
            "accepted_recipients_count": self.accepted,
            "refused_recipients_count": self.refused,
            "message": str(self),
        }
