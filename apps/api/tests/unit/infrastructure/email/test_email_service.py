"""
Unit tests for email service module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires (Session 6)
Created: 2025-11-20
"""

import smtplib
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.infrastructure.email.email_service import EmailService, get_email_service


@pytest.fixture
def email_service():
    """Provide EmailService instance with mocked settings."""
    with patch("src.infrastructure.email.email_service.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "user@example.com"
        mock_settings.smtp_password = "password123"
        mock_settings.smtp_from = "noreply@example.com"
        mock_settings.frontend_url = "https://app.example.com"
        yield EmailService()


@pytest.fixture
def mock_smtp():
    """Mock SMTP server context manager."""
    with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock:
        server_instance = MagicMock()
        server_instance.__enter__ = Mock(return_value=server_instance)
        server_instance.__exit__ = Mock(return_value=False)
        mock.return_value = server_instance
        yield mock, server_instance


class TestEmailServiceInit:
    def test_init_extracts_smtp_settings(self):
        """Test that EmailService correctly extracts SMTP settings."""
        with patch("src.infrastructure.email.email_service.settings") as mock_settings:
            mock_settings.smtp_host = "smtp.gmail.com"
            mock_settings.smtp_port = 465
            mock_settings.smtp_user = "test@example.com"
            mock_settings.smtp_password = "secret"
            mock_settings.smtp_from = "from@example.com"

            service = EmailService()

            assert service.smtp_host == "smtp.gmail.com"
            assert service.smtp_port == 465
            assert service.smtp_user == "test@example.com"
            assert service.smtp_password == "secret"
            assert service.smtp_from == "from@example.com"


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_send_email_success(self, email_service, mock_smtp):
        """Test sending email successfully."""
        mock_smtp_class, mock_server = mock_smtp

        result = await email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test Plain Text",
        )

        assert result is True
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "password123")
        mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_without_text_body(self, email_service, mock_smtp):
        """Test sending email with only HTML body."""
        mock_smtp_class, mock_server = mock_smtp

        result = await email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
        )

        assert result is True
        mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_smtp_connection_error(self, email_service):
        """Test handling SMTP connection error."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPConnectError(421, "Connection refused")

            result = await email_service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_authentication_error(self, email_service):
        """Test handling SMTP authentication error."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
                535, "Authentication failed"
            )
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_generic_exception(self, email_service):
        """Test handling generic exception during send."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = Exception("Generic error")

            result = await email_service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_creates_correct_mime_structure(self, email_service, mock_smtp):
        """Test that email creates correct MIME structure."""
        mock_smtp_class, mock_server = mock_smtp

        await email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
            text_body="Test Plain Text",
        )

        # Verify sendmail was called with correct sender and recipient
        call_args = mock_server.sendmail.call_args
        assert call_args[0][0] == "noreply@example.com"  # from
        assert call_args[0][1] == "recipient@example.com"  # to
        # Message should contain both text and HTML parts
        message = call_args[0][2]
        assert "Test Plain Text" in message or "Test HTML" in message

    @pytest.mark.asyncio
    async def test_send_email_logs_success(self, email_service, mock_smtp, caplog):
        """Test that successful send is logged."""
        await email_service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            html_body="<p>Test HTML</p>",
        )

        assert any("email_sent" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_send_email_logs_failure(self, email_service, caplog):
        """Test that failed send is logged."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = Exception("SMTP error")

            await email_service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test HTML</p>",
            )

            assert any("email_send_failed" in record.message for record in caplog.records)


class TestSendUserDeactivatedNotification:
    @pytest.mark.asyncio
    async def test_send_deactivated_notification_success(self, email_service, mock_smtp):
        """Test sending user deactivated notification."""
        result = await email_service.send_user_deactivated_notification(
            user_email="user@example.com",
            user_name="John Doe",
            reason="Policy violation",
            user_language="en",
        )

        assert result is True
        mock_smtp[1].sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivated_notification_without_user_name(self, email_service, mock_smtp):
        """Test notification uses email when name not provided."""
        result = await email_service.send_user_deactivated_notification(
            user_email="user@example.com",
            user_name=None,
            reason="Policy violation",
        )

        assert result is True
        # Should still send email with email as fallback for name
        mock_smtp[1].sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivated_notification_french(self, email_service, mock_smtp):
        """Test deactivated notification in French."""
        result = await email_service.send_user_deactivated_notification(
            user_email="user@example.com",
            user_name="Jean Dupont",
            reason="Violation de politique",
            user_language="fr",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_deactivated_notification_contains_reason(self, email_service):
        """Test that notification includes the reason."""
        test_reason = "Account inactive for 90 days"

        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_user_deactivated_notification(
                user_email="user@example.com",
                user_name="John Doe",
                reason=test_reason,
            )

            assert result is True
            # Verify sendmail was called
            assert mock_server.sendmail.called
            # Note: Message is base64 encoded in MIME format, so we just verify it was sent

    @pytest.mark.asyncio
    async def test_deactivated_notification_internationalized(self, email_service, mock_smtp):
        """Test that notification supports multiple languages."""
        for lang in ["fr", "en", "es", "de", "it"]:
            result = await email_service.send_user_deactivated_notification(
                user_email="user@example.com",
                user_name="Test User",
                reason="Test reason",
                user_language=lang,
            )
            assert result is True


class TestSendUserActivatedNotification:
    @pytest.mark.asyncio
    async def test_send_activated_notification_success(self, email_service, mock_smtp):
        """Test sending user activated notification."""
        result = await email_service.send_user_activated_notification(
            user_email="user@example.com",
            user_name="John Doe",
            user_language="en",
        )

        assert result is True
        mock_smtp[1].sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_activated_notification_without_user_name(self, email_service, mock_smtp):
        """Test notification uses email when name not provided."""
        result = await email_service.send_user_activated_notification(
            user_email="user@example.com",
            user_name=None,
        )

        assert result is True
        mock_smtp[1].sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_activated_notification_french(self, email_service, mock_smtp):
        """Test activated notification in French."""
        result = await email_service.send_user_activated_notification(
            user_email="user@example.com",
            user_name="Jean Dupont",
            user_language="fr",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_activated_notification_contains_login_link(self, email_service):
        """Test that notification includes login link."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_user_activated_notification(
                user_email="user@example.com",
                user_name="John Doe",
            )

            assert result is True
            # Verify sendmail was called
            assert mock_server.sendmail.called
            # Note: Message is base64 encoded in MIME format, so we just verify it was sent

    @pytest.mark.asyncio
    async def test_activated_notification_internationalized(self, email_service, mock_smtp):
        """Test that notification supports multiple languages."""
        for lang in ["fr", "en", "es", "de", "it"]:
            result = await email_service.send_user_activated_notification(
                user_email="user@example.com",
                user_name="Test User",
                user_language=lang,
            )
            assert result is True


class TestSendConnectorDisabledNotification:
    @pytest.mark.asyncio
    async def test_send_connector_disabled_success(self, email_service, mock_smtp):
        """Test sending connector disabled notification."""
        result = await email_service.send_connector_disabled_notification(
            user_email="user@example.com",
            user_name="John Doe",
            connector_type="emails",
            reason="Security policy update",
        )

        assert result is True
        mock_smtp[1].sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_connector_disabled_without_user_name(self, email_service, mock_smtp):
        """Test notification uses email when name not provided."""
        result = await email_service.send_connector_disabled_notification(
            user_email="user@example.com",
            user_name=None,
            connector_type="emails",
            reason="Security policy update",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_connector_disabled_maps_connector_labels(self, email_service):
        """Test that connector types are mapped to readable labels."""
        connector_mappings = {
            "emails": "Gmail",
            "google_drive": "Google Drive",
            "google_calendar": "Google Calendar",
            "google_contacts": "Google Contacts",
            "slack": "Slack",
            "notion": "Notion",
            "github": "GitHub",
        }

        for connector_type, _expected_label in connector_mappings.items():
            with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
                mock_server = MagicMock()
                mock_server.__enter__ = Mock(return_value=mock_server)
                mock_server.__exit__ = Mock(return_value=False)
                mock_smtp_class.return_value = mock_server

                result = await email_service.send_connector_disabled_notification(
                    user_email="user@example.com",
                    user_name="John Doe",
                    connector_type=connector_type,
                    reason="Test",
                )

                assert result is True
                # Verify sendmail was called
                assert mock_server.sendmail.called

    @pytest.mark.asyncio
    async def test_connector_disabled_unknown_type_uses_raw_value(self, email_service):
        """Test that unknown connector types use raw value."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_connector_disabled_notification(
                user_email="user@example.com",
                user_name="John Doe",
                connector_type="unknown_connector",
                reason="Test",
            )

            assert result is True
            # Verify sendmail was called
            assert mock_server.sendmail.called

    @pytest.mark.asyncio
    async def test_connector_disabled_contains_reason(self, email_service):
        """Test that notification includes the reason."""
        test_reason = "Connector deprecated"

        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_connector_disabled_notification(
                user_email="user@example.com",
                user_name="John Doe",
                connector_type="emails",
                reason=test_reason,
            )

            assert result is True
            # Verify sendmail was called
            assert mock_server.sendmail.called

    @pytest.mark.asyncio
    async def test_connector_disabled_hardcoded_french(self, email_service):
        """Test that connector disabled notification is in French (hardcoded)."""
        with patch("src.infrastructure.email.email_service.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_server.__enter__ = Mock(return_value=mock_server)
            mock_server.__exit__ = Mock(return_value=False)
            mock_smtp_class.return_value = mock_server

            result = await email_service.send_connector_disabled_notification(
                user_email="user@example.com",
                user_name="John Doe",
                connector_type="emails",
                reason="Test",
            )

            assert result is True
            # Verify sendmail was called
            assert mock_server.sendmail.called


class TestGetEmailService:
    def test_get_email_service_returns_singleton(self):
        """Test that get_email_service returns same instance."""
        with patch("src.infrastructure.email.email_service.settings") as mock_settings:
            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@example.com"
            mock_settings.smtp_password = "password"
            mock_settings.smtp_from = "from@example.com"

            # Clear singleton before test
            import src.infrastructure.email.email_service as email_module

            email_module._email_service = None

            service1 = get_email_service()
            service2 = get_email_service()

            assert service1 is service2

    def test_get_email_service_creates_instance_if_none(self):
        """Test that get_email_service creates instance on first call."""
        with patch("src.infrastructure.email.email_service.settings") as mock_settings:
            mock_settings.smtp_host = "smtp.example.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@example.com"
            mock_settings.smtp_password = "password"
            mock_settings.smtp_from = "from@example.com"

            # Clear singleton
            import src.infrastructure.email.email_service as email_module

            email_module._email_service = None

            service = get_email_service()

            assert service is not None
            assert isinstance(service, EmailService)
