"""
Email service for sending notifications.
Uses SMTP with template-based emails.
"""

import asyncio
import html
import smtplib
from collections.abc import Sequence
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from src.core.config import settings
from src.core.i18n import _, normalize_language
from src.core.i18n_drafts import label_separator
from src.infrastructure.email.outgoing import OutgoingAttachment, with_attachments

logger = structlog.get_logger(__name__)


def _reason_lines(reason: str | None, language: str) -> tuple[str, str]:
    """The reason line of a notification, as HTML and as plain text.

    A reason nobody gave is no line at all. The placeholders it replaced were
    French for everyone: « Reason: Non spécifiée » in the deactivation e-mail
    (the label translated, the value not), « Raison : Raison non spécifiée » in
    the connector one.

    Args:
        reason: The administrator's words, or None.
        language: The reader's language.

    Returns:
        ``(html, text)`` — both empty when there is no reason. The text is a
        whole paragraph of the plain-text body, its blank line included, so a
        body without one keeps a single blank line between its paragraphs.
    """
    if not reason:
        return "", ""
    label = _("Reason", language)
    separator = label_separator(language)
    return (
        f"<p><strong>{label}{separator}</strong>{html.escape(reason)}</p>",
        f"\n        {label}{separator}{reason}\n",
    )


class EmailService:
    """
    Service for sending email notifications.

    Uses unified SMTP configuration (ALERTMANAGER_SMTP_*) for all emails.
    Settings properties automatically extract host/port from smarthost format.
    """

    def __init__(self) -> None:
        # Note: These are @property accessors in Settings that extract from ALERTMANAGER_SMTP_* vars
        self.smtp_host = settings.smtp_host  # Extracted from alertmanager_smtp_smarthost
        self.smtp_port = settings.smtp_port  # Extracted from alertmanager_smtp_smarthost
        self.smtp_user = settings.smtp_user  # Alias for alertmanager_smtp_auth_username
        self.smtp_password = settings.smtp_password  # Alias for alertmanager_smtp_auth_password
        self.smtp_from = settings.smtp_from  # Alias for application_smtp_from

    def _deliver(self, to_email: str, payload: str) -> None:
        """Hand ``payload`` to the relay — blocking, call it from a worker thread.

        TLS and authentication only when there are credentials to present. A
        relay reached over a private network has neither, and demanding them
        there is how the demonstrator's verification email — the one that
        ACTIVATES the account — failed on every registration (measured
        2026-08-06). Where credentials exist, the exchange is unchanged:
        encrypted then authenticated, never one without the other.
        """
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.smtp_user and self.smtp_password:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_from, to_email, payload)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional, falls back to HTML)
            attachments: Files following the body (ADR-321); none keeps the
                message the plain ``alternative`` it always was.

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # The typed words: plain text (fallback) then HTML.
            alternative = MIMEMultipart("alternative")
            if text_body:
                alternative.attach(MIMEText(text_body, "plain"))
            alternative.attach(MIMEText(html_body, "html"))

            msg = with_attachments(alternative, attachments)
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = to_email

            # The SMTP exchange is synchronous (smtplib): it runs in a worker
            # thread so the event loop keeps serving SSE while the relay answers.
            await asyncio.to_thread(self._deliver, to_email, msg.as_string())

            # No PII at INFO: the address and the subject (user content) stay at DEBUG.
            logger.info("email_sent", subject_length=len(subject))
            logger.debug("email_sent_detail", to_email=to_email, subject=subject)
            return True

        except Exception as e:
            logger.error("email_send_failed", error=str(e), error_type=e.__class__.__name__)
            logger.debug("email_send_failed_detail", to_email=to_email, subject=subject)
            return False

    async def send_user_deactivated_notification(
        self,
        user_email: str,
        user_name: str | None,
        reason: str | None,
        user_language: str,
    ) -> bool:
        """
        Send notification when user account is deactivated by admin.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            reason: The administrator's reason; no line when none was given
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)

        # Internationalized subject
        subject = _("Your LIA account has been deactivated", lang)

        display_name = user_name or user_email

        # Internationalized content
        greeting = _("Hello {name},", lang).format(name=display_name)
        body_text = _(
            "We inform you that your LIA account has been deactivated by an administrator.",
            lang,
        )
        reason_html, reason_text = _reason_lines(reason, lang)
        no_access_text = _("You can no longer access the application.", lang)
        error_text = _("If you think this is an error, please contact the administrator.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #d32f2f;">{_("Account deactivated", lang)}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{body_text}</p>
            {reason_html}
            <p>{no_access_text}</p>
            <p>{error_text}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {_("Account deactivated", lang)}

        {greeting}

        {body_text}
{reason_text}
        {no_access_text}

        {error_text}

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_user_activated_notification(
        self,
        user_email: str,
        user_name: str | None,
        user_language: str,
    ) -> bool:
        """
        Send notification when user account is reactivated by admin.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)

        # Internationalized subject
        subject = _("Your LIA account has been reactivated", lang)

        display_name = user_name or user_email

        # Internationalized content
        greeting = _("Hello {name},", lang).format(name=display_name)
        body_text = _("We inform you that your LIA account has been reactivated.", lang)
        access_text = _("You can now access the application again.", lang)
        login_button_text = _("Log in", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        login_link_text = _("Login link", lang)
        separator = label_separator(lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2e7d32;">{_("Account reactivated", lang)}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{body_text}</p>
            <p>{access_text}</p>
            <p><a href="{settings.frontend_url}/login" style="display: inline-block; padding: 10px 20px; background-color: #1976d2; color: #fff; text-decoration: none; border-radius: 4px;">{login_button_text}</a></p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {_("Account reactivated", lang)}

        {greeting}

        {body_text}

        {access_text}

        {login_link_text}{separator}{settings.frontend_url}/login

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_connector_disabled_notification(
        self,
        user_email: str,
        user_name: str | None,
        connector_label: str,
        reason: str | None,
        user_language: str,
    ) -> bool:
        """
        Send notification when a connector type is disabled globally.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            connector_label: The connector's display name, as the registry names it
                (``get_connector_display_name``) — written verbatim, escaped in HTML
            reason: The administrator's reason; no line when none was given
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)
        display_name = user_name or user_email

        subject = _("Connector {connector} disabled", lang).format(connector=connector_label)
        heading = _("Connector disabled", lang)
        greeting = _("Hello {name},", lang).format(name=display_name)
        disabled = _(
            "We inform you that the connector {connector} has been disabled by an administrator.",
            lang,
        )
        reason_html, reason_text = _reason_lines(reason, lang)
        revoked_text = _(
            "Your existing connection has been revoked and you can no longer use this connector.",
            lang,
        )
        questions_text = _("If you have any questions, please contact the administrator.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        disabled_html = disabled.format(
            connector=f"<strong>{html.escape(connector_label)}</strong>"
        )

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">{heading}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{disabled_html}</p>
            {reason_html}
            <p>{revoked_text}</p>
            <p>{questions_text}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {heading}

        {greeting}

        {disabled.format(connector=connector_label)}
{reason_text}
        {revoked_text}

        {questions_text}

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_email_verification(
        self,
        user_email: str,
        user_name: str | None,
        verification_url: str,
        user_language: str,
    ) -> bool:
        """
        Send email verification link to new user.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            verification_url: Full URL for email verification
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)

        subject = _("Verify your LIA account email", lang)
        display_name = user_name or user_email

        greeting = _("Hello {name},", lang).format(name=display_name)
        welcome_text = _(
            "Welcome to LIA! Please verify your email address to activate your account.", lang
        )
        verify_button_text = _("Verify my email", lang)
        link_expires_text = _("This link expires in 24 hours.", lang)
        ignore_text = _("If you did not create an account, you can ignore this email.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        verify_link_text = _("Verification link", lang)
        separator = label_separator(lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #1976d2;">{_("Email verification", lang)}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{welcome_text}</p>
            <p>
                <a href="{verification_url}" style="display: inline-block; padding: 12px 24px; background-color: #1976d2; color: #fff; text-decoration: none; border-radius: 4px; font-weight: bold;">
                    {verify_button_text}
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">{link_expires_text}</p>
            <p style="color: #666; font-size: 14px;">{ignore_text}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {_("Email verification", lang)}

        {greeting}

        {welcome_text}

        {verify_link_text}{separator}{verification_url}

        {link_expires_text}

        {ignore_text}

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_password_reset(
        self,
        user_email: str,
        user_name: str | None,
        reset_url: str,
        user_language: str,
    ) -> bool:
        """
        Send password reset link to user.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            reset_url: Full URL for password reset
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)

        subject = _("Reset your LIA password", lang)
        display_name = user_name or user_email

        greeting = _("Hello {name},", lang).format(name=display_name)
        request_text = _("We received a request to reset your password.", lang)
        reset_button_text = _("Reset my password", lang)
        link_expires_text = _("This link expires in 1 hour for security reasons.", lang)
        ignore_text = _("If you did not request a password reset, you can ignore this email.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        reset_link_text = _("Reset link", lang)
        separator = label_separator(lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">{_("Password reset", lang)}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{request_text}</p>
            <p>
                <a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: #f57c00; color: #fff; text-decoration: none; border-radius: 4px; font-weight: bold;">
                    {reset_button_text}
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">{link_expires_text}</p>
            <p style="color: #666; font-size: 14px;">{ignore_text}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {_("Password reset", lang)}

        {greeting}

        {request_text}

        {reset_link_text}{separator}{reset_url}

        {link_expires_text}

        {ignore_text}

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_pending_activation_notification(
        self,
        user_email: str,
        user_name: str | None,
        user_language: str,
    ) -> bool:
        """
        Send notification to user that their account is pending admin activation.

        Sent when a new user account is created but requires admin approval:
        - After OAuth registration (Google)
        - After email verification (standard registration)

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            user_language: The language of the person the e-mail reaches —
                required: a known person's e-mail never falls back to the
                declared language, which may be someone else's (ADR-323).

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(user_language)

        subject = _("Your LIA account is pending activation", lang)
        display_name = user_name or user_email

        greeting = _("Hello {name},", lang).format(name=display_name)
        welcome_text = _("Welcome to LIA! Your account has been created successfully.", lang)
        pending_text = _("Your account is currently pending activation by an administrator.", lang)
        notify_text = _("You will receive an email once your account has been activated.", lang)
        patience_text = _("Thank you for your patience.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">{_("Account pending activation", lang)}</h2>
            <p>{html.escape(greeting)}</p>
            <p>{welcome_text}</p>
            <p>{pending_text}</p>
            <p>{notify_text}</p>
            <p>{patience_text}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {_("Account pending activation", lang)}

        {greeting}

        {welcome_text}

        {pending_text}

        {notify_text}

        {patience_text}

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_new_registration_admin_notification(
        self,
        admin_email: str,
        new_user_email: str,
        new_user_name: str | None,
        registration_method: str = "email",
        *,
        admin_language: str,
    ) -> bool:
        """
        Send notification to admin when a new user registers.

        Args:
            admin_email: Admin's email address
            new_user_email: New user's email address
            new_user_name: New user's full name (optional)
            registration_method: Method of registration (email, google, etc.)
            admin_language: The administrator's own language — required, like
                every language of an e-mail addressed to a known person.

        Returns:
            True if email sent successfully
        """
        lang = normalize_language(admin_language)
        display_name = new_user_name or new_user_email
        admin_url = f"{settings.frontend_url}/dashboard/admin/users"

        subject = _("[LIA] New user awaiting activation: {email}", lang).format(
            email=new_user_email
        )
        heading = _("New user registered", lang)
        intro = _("A new user has registered on LIA and is waiting for your activation:", lang)
        email_label = _("Email", lang)
        name_label = _("Name", lang)
        method_label = _("Method", lang)
        manage_label = _("Manage users", lang)
        admin_link_label = _("Administration link", lang)
        separator = label_separator(lang)
        auto_email_text = _("This is an automated email from LIA.", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #1976d2;">{heading}</h2>
            <p>{intro}</p>
            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">{email_label}{separator}</td>
                    <td style="padding: 8px;">{html.escape(new_user_email)}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">{name_label}{separator}</td>
                    <td style="padding: 8px;">{html.escape(display_name)}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">{method_label}{separator}</td>
                    <td style="padding: 8px;">{html.escape(registration_method)}</td>
                </tr>
            </table>
            <p>
                <a href="{admin_url}" style="display: inline-block; padding: 10px 20px; background-color: #1976d2; color: #fff; text-decoration: none; border-radius: 4px;">
                    {manage_label}
                </a>
            </p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                {auto_email_text}
            </p>
        </body>
        </html>
        """

        text_body = f"""
        {heading}

        {intro}

        {email_label}{separator}{new_user_email}
        {name_label}{separator}{display_name}
        {method_label}{separator}{registration_method}

        {admin_link_label}{separator}{admin_url}

        ---
        {auto_email_text}
        """

        return await self.send_email(admin_email, subject, html_body, text_body)


# Singleton instance
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get singleton EmailService instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
