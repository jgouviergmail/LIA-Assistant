"""
Email service for sending notifications.
Uses SMTP with template-based emails.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import cast

import structlog

from src.core.config import settings
from src.core.i18n import Language, _

logger = structlog.get_logger(__name__)


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

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body (optional, falls back to HTML)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = to_email

            # Attach plain text (fallback)
            if text_body:
                part1 = MIMEText(text_body, "plain")
                msg.attach(part1)

            # Attach HTML
            part2 = MIMEText(html_body, "html")
            msg.attach(part2)

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to_email, msg.as_string())

            logger.info(
                "email_sent",
                to_email=to_email,
                subject=subject,
            )
            return True

        except Exception as e:
            logger.error(
                "email_send_failed",
                to_email=to_email,
                subject=subject,
                error=str(e),
            )
            return False

    async def send_user_deactivated_notification(
        self,
        user_email: str,
        user_name: str | None,
        reason: str,
        user_language: str = "fr",
    ) -> bool:
        """
        Send notification when user account is deactivated by admin.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            reason: Reason for deactivation
            user_language: User's preferred language (fr, en, es, de, it)

        Returns:
            True if email sent successfully
        """
        # Cast user_language to Language type for type safety
        lang = cast(Language, user_language)

        # Internationalized subject
        subject = _("Your LIA account has been deactivated", lang)

        display_name = user_name or user_email

        # Internationalized content
        greeting = _("Hello", lang)
        body_text = _(
            "We inform you that your LIA account has been deactivated by an administrator.",
            lang,
        )
        reason_label = _("Reason", lang)
        no_access_text = _("You can no longer access the application.", lang)
        error_text = _("If you think this is an error, please contact the administrator.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #d32f2f;">{_("Account deactivated", lang)}</h2>
            <p>{greeting} {display_name},</p>
            <p>{body_text}</p>
            <p><strong>{reason_label}:</strong> {reason}</p>
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

        {greeting} {display_name},

        {body_text}

        {reason_label}: {reason}

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
        user_language: str = "fr",
    ) -> bool:
        """
        Send notification when user account is reactivated by admin.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            user_language: User's preferred language (fr, en, es, de, it)

        Returns:
            True if email sent successfully
        """
        # Cast user_language to Language type for type safety
        lang = cast(Language, user_language)

        # Internationalized subject
        subject = _("Your LIA account has been reactivated", lang)

        display_name = user_name or user_email

        # Internationalized content
        greeting = _("Hello", lang)
        body_text = _("We inform you that your LIA account has been reactivated.", lang)
        access_text = _("You can now access the application again.", lang)
        login_button_text = _("Log in", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        login_link_text = _("Login link", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2e7d32;">{_("Account reactivated", lang)}</h2>
            <p>{greeting} {display_name},</p>
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

        {greeting} {display_name},

        {body_text}

        {access_text}

        {login_link_text}: {settings.frontend_url}/login

        ---
        {auto_email_text}
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_connector_disabled_notification(
        self,
        user_email: str,
        user_name: str | None,
        connector_type: str,
        reason: str,
    ) -> bool:
        """
        Send notification when a connector type is disabled globally.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            connector_type: Type of connector (e.g., "google_contacts")
            reason: Reason for disabling

        Returns:
            True if email sent successfully
        """
        subject = f"Connecteur {connector_type} désactivé"

        display_name = user_name or user_email

        connector_labels = {
            "gmail": "Gmail",
            "google_drive": "Google Drive",
            "google_calendar": "Google Calendar",
            "google_contacts": "Google Contacts",
            "slack": "Slack",
            "notion": "Notion",
            "github": "GitHub",
        }
        connector_label = connector_labels.get(connector_type, connector_type)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">Connecteur désactivé</h2>
            <p>Bonjour {display_name},</p>
            <p>Nous vous informons que le connecteur <strong>{connector_label}</strong> a été désactivé par un administrateur.</p>
            <p><strong>Raison :</strong> {reason}</p>
            <p>Votre connexion existante a été révoquée et vous ne pouvez plus utiliser ce connecteur.</p>
            <p>Si vous avez des questions, veuillez contacter l'administrateur.</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                Ceci est un email automatique, merci de ne pas y répondre.
            </p>
        </body>
        </html>
        """

        text_body = f"""
        Connecteur désactivé

        Bonjour {display_name},

        Nous vous informons que le connecteur {connector_label} a été désactivé par un administrateur.

        Raison : {reason}

        Votre connexion existante a été révoquée et vous ne pouvez plus utiliser ce connecteur.

        Si vous avez des questions, veuillez contacter l'administrateur.

        ---
        Ceci est un email automatique, merci de ne pas y répondre.
        """

        return await self.send_email(user_email, subject, html_body, text_body)

    async def send_email_verification(
        self,
        user_email: str,
        user_name: str | None,
        verification_url: str,
        user_language: str = "fr",
    ) -> bool:
        """
        Send email verification link to new user.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            verification_url: Full URL for email verification
            user_language: User's preferred language (fr, en, es, de, it)

        Returns:
            True if email sent successfully
        """
        lang = cast(Language, user_language)

        subject = _("Verify your LIA account email", lang)
        display_name = user_name or user_email

        greeting = _("Hello", lang)
        welcome_text = _(
            "Welcome to LIA! Please verify your email address to activate your account.", lang
        )
        verify_button_text = _("Verify my email", lang)
        link_expires_text = _("This link expires in 24 hours.", lang)
        ignore_text = _("If you did not create an account, you can ignore this email.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        verify_link_text = _("Verification link", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #1976d2;">{_("Email verification", lang)}</h2>
            <p>{greeting} {display_name},</p>
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

        {greeting} {display_name},

        {welcome_text}

        {verify_link_text}: {verification_url}

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
        user_language: str = "fr",
    ) -> bool:
        """
        Send password reset link to user.

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            reset_url: Full URL for password reset
            user_language: User's preferred language (fr, en, es, de, it)

        Returns:
            True if email sent successfully
        """
        lang = cast(Language, user_language)

        subject = _("Reset your LIA password", lang)
        display_name = user_name or user_email

        greeting = _("Hello", lang)
        request_text = _("We received a request to reset your password.", lang)
        reset_button_text = _("Reset my password", lang)
        link_expires_text = _("This link expires in 1 hour for security reasons.", lang)
        ignore_text = _("If you did not request a password reset, you can ignore this email.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)
        reset_link_text = _("Reset link", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">{_("Password reset", lang)}</h2>
            <p>{greeting} {display_name},</p>
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

        {greeting} {display_name},

        {request_text}

        {reset_link_text}: {reset_url}

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
        user_language: str = "fr",
    ) -> bool:
        """
        Send notification to user that their account is pending admin activation.

        Sent when a new user account is created but requires admin approval:
        - After OAuth registration (Google)
        - After email verification (standard registration)

        Args:
            user_email: User's email address
            user_name: User's full name (optional)
            user_language: User's preferred language (fr, en, es, de, it, zh-CN)

        Returns:
            True if email sent successfully
        """
        lang = cast(Language, user_language)

        subject = _("Your LIA account is pending activation", lang)
        display_name = user_name or user_email

        greeting = _("Hello", lang)
        welcome_text = _("Welcome to LIA! Your account has been created successfully.", lang)
        pending_text = _("Your account is currently pending activation by an administrator.", lang)
        notify_text = _("You will receive an email once your account has been activated.", lang)
        patience_text = _("Thank you for your patience.", lang)
        auto_email_text = _("This is an automated email, please do not reply.", lang)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #f57c00;">{_("Account pending activation", lang)}</h2>
            <p>{greeting} {display_name},</p>
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

        {greeting} {display_name},

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
    ) -> bool:
        """
        Send notification to admin when a new user registers.

        Args:
            admin_email: Admin's email address
            new_user_email: New user's email address
            new_user_name: New user's full name (optional)
            registration_method: Method of registration (email, google, etc.)

        Returns:
            True if email sent successfully
        """
        subject = f"[LIA] Nouvel utilisateur en attente d'activation: {new_user_email}"
        display_name = new_user_name or new_user_email

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #1976d2;">Nouvel utilisateur inscrit</h2>
            <p>Un nouvel utilisateur s'est inscrit sur LIA et attend votre activation :</p>
            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">Email :</td>
                    <td style="padding: 8px;">{new_user_email}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">Nom :</td>
                    <td style="padding: 8px;">{display_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #666;">Méthode :</td>
                    <td style="padding: 8px;">{registration_method}</td>
                </tr>
            </table>
            <p>
                <a href="{settings.frontend_url}/dashboard/admin/users" style="display: inline-block; padding: 10px 20px; background-color: #1976d2; color: #fff; text-decoration: none; border-radius: 4px;">
                    Gérer les utilisateurs
                </a>
            </p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="font-size: 12px; color: #666;">
                Ceci est un email automatique de LIA.
            </p>
        </body>
        </html>
        """

        text_body = f"""
        Nouvel utilisateur inscrit

        Un nouvel utilisateur s'est inscrit sur LIA et attend votre activation :

        Email : {new_user_email}
        Nom : {display_name}
        Méthode : {registration_method}

        Lien administration : {settings.frontend_url}/dashboard/admin/users

        ---
        Ceci est un email automatique de LIA.
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
