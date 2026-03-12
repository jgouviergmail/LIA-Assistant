"""
Partial Error Handler - Centralized handling of partial domain failures.

This module provides the core logic for handling situations where some domains
succeed while others fail, enabling graceful degradation of multi-domain results.

Architecture:
- PartialErrorHandler: Main handler for partial failures
- ErrorRecoveryStrategy: Defines how to handle each error type
- DomainErrorContext: Contextual information about failures

Benefits:
- Graceful degradation instead of complete failure
- User-friendly error messages
- Retry suggestions based on error type
- Metrics tracking for observability

Usage:
    from src.core.partial_error_handler import PartialErrorHandler

    handler = PartialErrorHandler()

    # When a domain fails
    error_context = handler.handle_error(
        domain="emails",
        error=exception,
        partial_data={"contacts": contacts_result}
    )

    # Get user-friendly message
    message = handler.format_error_message(error_context)

Phase: Multi-Domain Architecture v1.0
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS AND SCHEMAS
# =============================================================================


class ErrorSeverity(str, Enum):
    """Severity levels for domain errors."""

    LOW = "low"  # Non-critical, informational
    MEDIUM = "medium"  # Degraded experience but usable
    HIGH = "high"  # Significant impact on results
    CRITICAL = "critical"  # Cannot provide meaningful results


class ErrorCategory(str, Enum):
    """Categories of domain errors."""

    AUTHENTICATION = "authentication"  # OAuth token expired, etc.
    RATE_LIMIT = "rate_limit"  # API quota exceeded
    NETWORK = "network"  # Connection timeout, DNS failure
    VALIDATION = "validation"  # Invalid parameters
    NOT_FOUND = "not_found"  # Resource doesn't exist
    PERMISSION = "permission"  # Access denied
    INTERNAL = "internal"  # Unexpected internal error
    TIMEOUT = "timeout"  # Operation timeout
    UNKNOWN = "unknown"  # Unclassified error


class RecoveryAction(str, Enum):
    """Suggested recovery actions for errors."""

    RETRY = "retry"  # Retry the operation
    REAUTHENTICATE = "reauthenticate"  # Re-authenticate connector
    WAIT = "wait"  # Wait before retrying
    MODIFY_QUERY = "modify_query"  # Change search parameters
    CONTACT_ADMIN = "contact_admin"  # Escalate to administrator
    NONE = "none"  # No action possible


class DomainErrorContext(BaseModel):
    """Context information about a domain error."""

    domain: str = Field(..., description="Failed domain name")
    error_type: str = Field(..., description="Exception type name")
    error_message: str = Field(..., description="Error message")
    category: ErrorCategory = Field(default=ErrorCategory.UNKNOWN)
    severity: ErrorSeverity = Field(default=ErrorSeverity.MEDIUM)
    recovery_action: RecoveryAction = Field(default=RecoveryAction.NONE)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    retry_after_seconds: int | None = Field(default=None)
    partial_data_available: bool = Field(default=False)
    user_message: str = Field(default="")
    technical_details: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}


# =============================================================================
# PARTIAL ERROR HANDLER
# =============================================================================


class PartialErrorHandler:
    """
    Handler for partial domain failures in multi-domain operations.

    Provides:
    - Error classification and categorization
    - User-friendly message generation
    - Recovery suggestions
    - Metrics tracking

    Example:
        handler = PartialErrorHandler()

        try:
            emails = fetch_emails(query)
        except Exception as e:
            context = handler.handle_error(
                domain="emails",
                error=e,
                partial_data={"contacts": contacts}
            )
            # Continue with partial results
    """

    def __init__(self) -> None:
        """Initialize handler with error pattern matchers."""
        # Error patterns for classification
        self._error_patterns: dict[str, tuple[ErrorCategory, ErrorSeverity, RecoveryAction]] = {
            # Authentication errors
            "token expired": (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.HIGH,
                RecoveryAction.REAUTHENTICATE,
            ),
            "invalid credentials": (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.HIGH,
                RecoveryAction.REAUTHENTICATE,
            ),
            "unauthorized": (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.HIGH,
                RecoveryAction.REAUTHENTICATE,
            ),
            "401": (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.HIGH,
                RecoveryAction.REAUTHENTICATE,
            ),
            # Rate limiting
            "rate limit": (
                ErrorCategory.RATE_LIMIT,
                ErrorSeverity.MEDIUM,
                RecoveryAction.WAIT,
            ),
            "quota exceeded": (
                ErrorCategory.RATE_LIMIT,
                ErrorSeverity.MEDIUM,
                RecoveryAction.WAIT,
            ),
            "429": (
                ErrorCategory.RATE_LIMIT,
                ErrorSeverity.MEDIUM,
                RecoveryAction.WAIT,
            ),
            # Network errors
            "timeout": (
                ErrorCategory.TIMEOUT,
                ErrorSeverity.MEDIUM,
                RecoveryAction.RETRY,
            ),
            "connection": (
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                RecoveryAction.RETRY,
            ),
            "dns": (
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                RecoveryAction.RETRY,
            ),
            "ssl": (
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                RecoveryAction.RETRY,
            ),
            "certificate": (
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                RecoveryAction.CONTACT_ADMIN,
            ),
            "proxy": (
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                RecoveryAction.CONTACT_ADMIN,
            ),
            # Permission errors
            "forbidden": (
                ErrorCategory.PERMISSION,
                ErrorSeverity.HIGH,
                RecoveryAction.CONTACT_ADMIN,
            ),
            "403": (
                ErrorCategory.PERMISSION,
                ErrorSeverity.HIGH,
                RecoveryAction.CONTACT_ADMIN,
            ),
            "access denied": (
                ErrorCategory.PERMISSION,
                ErrorSeverity.HIGH,
                RecoveryAction.CONTACT_ADMIN,
            ),
            # Not found errors
            "not found": (
                ErrorCategory.NOT_FOUND,
                ErrorSeverity.LOW,
                RecoveryAction.MODIFY_QUERY,
            ),
            "404": (
                ErrorCategory.NOT_FOUND,
                ErrorSeverity.LOW,
                RecoveryAction.MODIFY_QUERY,
            ),
            # Validation errors
            "invalid": (
                ErrorCategory.VALIDATION,
                ErrorSeverity.LOW,
                RecoveryAction.MODIFY_QUERY,
            ),
            "validation": (
                ErrorCategory.VALIDATION,
                ErrorSeverity.LOW,
                RecoveryAction.MODIFY_QUERY,
            ),
        }

        # User-friendly messages by category (i18n - 6 languages)
        self._user_messages: dict[str, dict[ErrorCategory, str]] = {
            "fr": {
                ErrorCategory.AUTHENTICATION: (
                    "La connexion au service {domain} a expiré. "
                    "Veuillez vous reconnecter dans les paramètres."
                ),
                ErrorCategory.RATE_LIMIT: (
                    "Le service {domain} a atteint sa limite de requêtes. "
                    "Veuillez réessayer dans quelques minutes."
                ),
                ErrorCategory.NETWORK: (
                    "Impossible de contacter le service {domain}. Vérifiez votre connexion internet."
                ),
                ErrorCategory.TIMEOUT: (
                    "Le service {domain} n'a pas répondu à temps. Veuillez réessayer."
                ),
                ErrorCategory.PERMISSION: (
                    "Accès refusé au service {domain}. Vérifiez les permissions de votre compte."
                ),
                ErrorCategory.NOT_FOUND: (
                    "Aucun résultat trouvé dans {domain}. Essayez avec d'autres critères."
                ),
                ErrorCategory.VALIDATION: (
                    "Les paramètres de recherche pour {domain} sont incorrects. "
                    "Veuillez reformuler votre demande."
                ),
                ErrorCategory.INTERNAL: (
                    "Une erreur inattendue s'est produite avec {domain}. Veuillez réessayer."
                ),
                ErrorCategory.UNKNOWN: (
                    "Une erreur s'est produite avec {domain}. Veuillez réessayer plus tard."
                ),
            },
            "en": {
                ErrorCategory.AUTHENTICATION: (
                    "The connection to {domain} service has expired. "
                    "Please reconnect in settings."
                ),
                ErrorCategory.RATE_LIMIT: (
                    "The {domain} service has reached its request limit. "
                    "Please try again in a few minutes."
                ),
                ErrorCategory.NETWORK: (
                    "Unable to contact {domain} service. Check your internet connection."
                ),
                ErrorCategory.TIMEOUT: (
                    "The {domain} service did not respond in time. Please try again."
                ),
                ErrorCategory.PERMISSION: (
                    "Access denied to {domain} service. Check your account permissions."
                ),
                ErrorCategory.NOT_FOUND: (
                    "No results found in {domain}. Try with different criteria."
                ),
                ErrorCategory.VALIDATION: (
                    "The search parameters for {domain} are incorrect. "
                    "Please rephrase your request."
                ),
                ErrorCategory.INTERNAL: (
                    "An unexpected error occurred with {domain}. Please try again."
                ),
                ErrorCategory.UNKNOWN: ("An error occurred with {domain}. Please try again later."),
            },
            "es": {
                ErrorCategory.AUTHENTICATION: (
                    "La conexión con el servicio {domain} ha expirado. "
                    "Por favor, reconéctese en la configuración."
                ),
                ErrorCategory.RATE_LIMIT: (
                    "El servicio {domain} ha alcanzado su límite de solicitudes. "
                    "Por favor, inténtelo de nuevo en unos minutos."
                ),
                ErrorCategory.NETWORK: (
                    "No se puede contactar con el servicio {domain}. Compruebe su conexión a internet."
                ),
                ErrorCategory.TIMEOUT: (
                    "El servicio {domain} no respondió a tiempo. Por favor, inténtelo de nuevo."
                ),
                ErrorCategory.PERMISSION: (
                    "Acceso denegado al servicio {domain}. Compruebe los permisos de su cuenta."
                ),
                ErrorCategory.NOT_FOUND: (
                    "No se encontraron resultados en {domain}. Intente con otros criterios."
                ),
                ErrorCategory.VALIDATION: (
                    "Los parámetros de búsqueda para {domain} son incorrectos. "
                    "Por favor, reformule su solicitud."
                ),
                ErrorCategory.INTERNAL: (
                    "Se produjo un error inesperado con {domain}. Por favor, inténtelo de nuevo."
                ),
                ErrorCategory.UNKNOWN: (
                    "Se produjo un error con {domain}. Por favor, inténtelo más tarde."
                ),
            },
            "de": {
                ErrorCategory.AUTHENTICATION: (
                    "Die Verbindung zum {domain}-Dienst ist abgelaufen. "
                    "Bitte erneut in den Einstellungen verbinden."
                ),
                ErrorCategory.RATE_LIMIT: (
                    "Der {domain}-Dienst hat sein Anfragelimit erreicht. "
                    "Bitte versuchen Sie es in ein paar Minuten erneut."
                ),
                ErrorCategory.NETWORK: (
                    "Der {domain}-Dienst ist nicht erreichbar. Prüfen Sie Ihre Internetverbindung."
                ),
                ErrorCategory.TIMEOUT: (
                    "Der {domain}-Dienst hat nicht rechtzeitig geantwortet. Bitte erneut versuchen."
                ),
                ErrorCategory.PERMISSION: (
                    "Zugriff auf den {domain}-Dienst verweigert. Prüfen Sie Ihre Kontoberechtigungen."
                ),
                ErrorCategory.NOT_FOUND: (
                    "Keine Ergebnisse in {domain} gefunden. Versuchen Sie es mit anderen Kriterien."
                ),
                ErrorCategory.VALIDATION: (
                    "Die Suchparameter für {domain} sind falsch. "
                    "Bitte formulieren Sie Ihre Anfrage um."
                ),
                ErrorCategory.INTERNAL: (
                    "Ein unerwarteter Fehler ist mit {domain} aufgetreten. Bitte erneut versuchen."
                ),
                ErrorCategory.UNKNOWN: (
                    "Ein Fehler ist mit {domain} aufgetreten. Bitte versuchen Sie es später erneut."
                ),
            },
            "it": {
                ErrorCategory.AUTHENTICATION: (
                    "La connessione al servizio {domain} è scaduta. "
                    "Si prega di riconnettersi nelle impostazioni."
                ),
                ErrorCategory.RATE_LIMIT: (
                    "Il servizio {domain} ha raggiunto il limite di richieste. "
                    "Si prega di riprovare tra qualche minuto."
                ),
                ErrorCategory.NETWORK: (
                    "Impossibile contattare il servizio {domain}. Controlla la tua connessione internet."
                ),
                ErrorCategory.TIMEOUT: (
                    "Il servizio {domain} non ha risposto in tempo. Si prega di riprovare."
                ),
                ErrorCategory.PERMISSION: (
                    "Accesso negato al servizio {domain}. Controlla i permessi del tuo account."
                ),
                ErrorCategory.NOT_FOUND: (
                    "Nessun risultato trovato in {domain}. Prova con altri criteri."
                ),
                ErrorCategory.VALIDATION: (
                    "I parametri di ricerca per {domain} non sono corretti. "
                    "Si prega di riformulare la richiesta."
                ),
                ErrorCategory.INTERNAL: (
                    "Si è verificato un errore imprevisto con {domain}. Si prega di riprovare."
                ),
                ErrorCategory.UNKNOWN: (
                    "Si è verificato un errore con {domain}. Si prega di riprovare più tardi."
                ),
            },
            "zh-CN": {
                ErrorCategory.AUTHENTICATION: ("{domain}服务的连接已过期。请在设置中重新连接。"),
                ErrorCategory.RATE_LIMIT: ("{domain}服务已达到请求限制。请稍后几分钟再试。"),
                ErrorCategory.NETWORK: ("无法联系{domain}服务。请检查您的网络连接。"),
                ErrorCategory.TIMEOUT: ("{domain}服务未能及时响应。请重试。"),
                ErrorCategory.PERMISSION: ("访问{domain}服务被拒绝。请检查您的账户权限。"),
                ErrorCategory.NOT_FOUND: ("在{domain}中未找到结果。请尝试其他条件。"),
                ErrorCategory.VALIDATION: ("{domain}的搜索参数不正确。请重新表述您的请求。"),
                ErrorCategory.INTERNAL: ("{domain}发生意外错误。请重试。"),
                ErrorCategory.UNKNOWN: ("{domain}发生错误。请稍后重试。"),
            },
        }

    def handle_error(
        self,
        domain: str,
        error: Exception,
        partial_data: dict[str, Any] | None = None,
        language: str = "fr",
    ) -> DomainErrorContext:
        """
        Handle a domain error and create context.

        Args:
            domain: Name of the failed domain
            error: The exception that occurred
            partial_data: Data from other successful domains
            language: Language code for error messages (fr, en, es, de, it, zh-CN)

        Returns:
            DomainErrorContext with classification and suggestions
        """
        # Normalize language code
        lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
        if lang not in self._user_messages:
            lang = "fr"

        # Truncate error message to prevent log bloat
        raw_error_message = str(error)
        error_message = raw_error_message.lower()
        truncated_error_message = (
            raw_error_message[:500] + "..." if len(raw_error_message) > 500 else raw_error_message
        )
        error_type = type(error).__name__

        # Classify the error
        category, severity, recovery = self._classify_error(error_message)

        # Generate user message (i18n)
        lang_messages = self._user_messages.get(lang, self._user_messages["fr"])
        user_message = lang_messages.get(category, lang_messages[ErrorCategory.UNKNOWN]).format(
            domain=domain.capitalize()
        )

        # Determine retry timing for rate limits
        retry_after = None
        if category == ErrorCategory.RATE_LIMIT:
            retry_after = self._extract_retry_after(error)

        # Check for partial data
        has_partial = bool(partial_data and any(partial_data.values()))

        # Build context
        context = DomainErrorContext(
            domain=domain,
            error_type=error_type,
            error_message=truncated_error_message,
            category=category,
            severity=severity,
            recovery_action=recovery,
            retry_after_seconds=retry_after,
            partial_data_available=has_partial,
            user_message=user_message,
            technical_details={
                "exception_class": error_type,
                "traceback": getattr(error, "__traceback__", None) is not None,
            },
        )

        # Log the error
        logger.warning(
            "partial_error_handled",
            domain=domain,
            category=category.value,
            severity=severity.value,
            recovery_action=recovery.value,
            error_type=error_type,
            has_partial_data=has_partial,
        )

        return context

    def format_error_message(
        self,
        context: DomainErrorContext,
        include_recovery: bool = True,
        language: str = "fr",
    ) -> str:
        """
        Format error context into user-friendly message.

        Args:
            context: Error context to format
            include_recovery: Whether to include recovery suggestions
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Formatted message string
        """
        # Normalize language code
        lang = language[:2] if len(language) > 2 and language != "zh-CN" else language
        if lang not in self._user_messages:
            lang = "fr"

        parts = [context.user_message]

        if include_recovery and context.recovery_action != RecoveryAction.NONE:
            recovery_msg = self._get_recovery_message(context, lang)
            if recovery_msg:
                parts.append(recovery_msg)

        if context.partial_data_available:
            partial_notes = {
                "fr": "Note : Des résultats partiels sont disponibles pour les autres domaines.",
                "en": "Note: Partial results are available for other domains.",
                "es": "Nota: Hay resultados parciales disponibles para otros dominios.",
                "de": "Hinweis: Teilergebnisse sind für andere Domänen verfügbar.",
                "it": "Nota: Sono disponibili risultati parziali per altri domini.",
                "zh-CN": "注意：其他领域有部分结果可用。",
            }
            parts.append(partial_notes.get(lang, partial_notes["fr"]))

        return " ".join(parts)

    def format_partial_results_header(
        self,
        successful_domains: list[str],
        failed_domains: list[str],
        language: str = "fr",
    ) -> str:
        """
        Format a header for partial results.

        Args:
            successful_domains: List of domains that succeeded
            failed_domains: List of domains that failed
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Formatted header string
        """
        if not failed_domains:
            return ""

        # Normalize language code
        lang = language[:2] if len(language) > 2 and language != "zh-CN" else language

        successful_str = ", ".join(d.capitalize() for d in successful_domains)
        failed_str = ", ".join(d.capitalize() for d in failed_domains)

        headers = {
            "fr": (
                f"## ⚠️ Résultats partiels\n\n"
                f"**Réussi** : {successful_str}\n"
                f"**Échoué** : {failed_str}\n\n"
                f"---\n"
            ),
            "en": (
                f"## ⚠️ Partial Results\n\n"
                f"**Succeeded** : {successful_str}\n"
                f"**Failed** : {failed_str}\n\n"
                f"---\n"
            ),
            "es": (
                f"## ⚠️ Resultados parciales\n\n"
                f"**Exitoso** : {successful_str}\n"
                f"**Fallido** : {failed_str}\n\n"
                f"---\n"
            ),
            "de": (
                f"## ⚠️ Teilergebnisse\n\n"
                f"**Erfolgreich** : {successful_str}\n"
                f"**Fehlgeschlagen** : {failed_str}\n\n"
                f"---\n"
            ),
            "it": (
                f"## ⚠️ Risultati parziali\n\n"
                f"**Riuscito** : {successful_str}\n"
                f"**Fallito** : {failed_str}\n\n"
                f"---\n"
            ),
            "zh-CN": (
                f"## ⚠️ 部分结果\n\n"
                f"**成功** : {successful_str}\n"
                f"**失败** : {failed_str}\n\n"
                f"---\n"
            ),
        }

        return headers.get(lang, headers["fr"])

    def should_retry(self, context: DomainErrorContext) -> bool:
        """
        Determine if the operation should be retried.

        Args:
            context: Error context

        Returns:
            True if retry is recommended
        """
        retryable_actions = {
            RecoveryAction.RETRY,
            RecoveryAction.WAIT,
        }
        return context.recovery_action in retryable_actions

    def _classify_error(
        self,
        error_message: str,
    ) -> tuple[ErrorCategory, ErrorSeverity, RecoveryAction]:
        """
        Classify error based on message patterns.

        Args:
            error_message: Lowercase error message

        Returns:
            Tuple of (category, severity, recovery_action)
        """
        for pattern, classification in self._error_patterns.items():
            if pattern in error_message:
                return classification

        # Default classification
        return (
            ErrorCategory.INTERNAL,
            ErrorSeverity.MEDIUM,
            RecoveryAction.RETRY,
        )

    def _extract_retry_after(self, error: Exception) -> int | None:
        """
        Extract retry-after timing from error if available.

        Args:
            error: The exception

        Returns:
            Retry delay in seconds or None
        """
        # Try to get from response headers if available
        if hasattr(error, "response"):
            response = error.response
            if hasattr(response, "headers"):
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        return int(retry_after)
                    except (ValueError, TypeError):
                        pass

        # Default retry timing based on patterns
        error_str = str(error).lower()
        if "rate limit" in error_str or "quota" in error_str:
            return 60  # Default 60 seconds for rate limits

        return None

    def _get_recovery_message(self, context: DomainErrorContext, language: str = "fr") -> str:
        """
        Get recovery suggestion message (i18n).

        Args:
            context: Error context
            language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Recovery suggestion string
        """
        retry_seconds = context.retry_after_seconds or 60

        messages_by_lang = {
            "fr": {
                RecoveryAction.RETRY: "Vous pouvez réessayer immédiatement.",
                RecoveryAction.REAUTHENTICATE: (
                    "Reconnectez le service dans Paramètres > Connecteurs."
                ),
                RecoveryAction.WAIT: (
                    f"Réessayez dans {retry_seconds} secondes."
                    if context.retry_after_seconds
                    else "Réessayez dans quelques minutes."
                ),
                RecoveryAction.MODIFY_QUERY: "Essayez avec des termes de recherche différents.",
                RecoveryAction.CONTACT_ADMIN: (
                    "Contactez votre administrateur pour vérifier les permissions."
                ),
            },
            "en": {
                RecoveryAction.RETRY: "You can try again immediately.",
                RecoveryAction.REAUTHENTICATE: ("Reconnect the service in Settings > Connectors."),
                RecoveryAction.WAIT: (
                    f"Try again in {retry_seconds} seconds."
                    if context.retry_after_seconds
                    else "Try again in a few minutes."
                ),
                RecoveryAction.MODIFY_QUERY: "Try with different search terms.",
                RecoveryAction.CONTACT_ADMIN: ("Contact your administrator to verify permissions."),
            },
            "es": {
                RecoveryAction.RETRY: "Puede volver a intentarlo inmediatamente.",
                RecoveryAction.REAUTHENTICATE: (
                    "Reconecte el servicio en Configuración > Conectores."
                ),
                RecoveryAction.WAIT: (
                    f"Vuelva a intentarlo en {retry_seconds} segundos."
                    if context.retry_after_seconds
                    else "Vuelva a intentarlo en unos minutos."
                ),
                RecoveryAction.MODIFY_QUERY: "Intente con términos de búsqueda diferentes.",
                RecoveryAction.CONTACT_ADMIN: (
                    "Contacte con su administrador para verificar los permisos."
                ),
            },
            "de": {
                RecoveryAction.RETRY: "Sie können es sofort erneut versuchen.",
                RecoveryAction.REAUTHENTICATE: (
                    "Verbinden Sie den Dienst unter Einstellungen > Konnektoren erneut."
                ),
                RecoveryAction.WAIT: (
                    f"Versuchen Sie es in {retry_seconds} Sekunden erneut."
                    if context.retry_after_seconds
                    else "Versuchen Sie es in einigen Minuten erneut."
                ),
                RecoveryAction.MODIFY_QUERY: "Versuchen Sie es mit anderen Suchbegriffen.",
                RecoveryAction.CONTACT_ADMIN: (
                    "Wenden Sie sich an Ihren Administrator, um die Berechtigungen zu prüfen."
                ),
            },
            "it": {
                RecoveryAction.RETRY: "Puoi riprovare immediatamente.",
                RecoveryAction.REAUTHENTICATE: (
                    "Riconnetti il servizio in Impostazioni > Connettori."
                ),
                RecoveryAction.WAIT: (
                    f"Riprova tra {retry_seconds} secondi."
                    if context.retry_after_seconds
                    else "Riprova tra qualche minuto."
                ),
                RecoveryAction.MODIFY_QUERY: "Prova con termini di ricerca diversi.",
                RecoveryAction.CONTACT_ADMIN: (
                    "Contatta il tuo amministratore per verificare i permessi."
                ),
            },
            "zh-CN": {
                RecoveryAction.RETRY: "您可以立即重试。",
                RecoveryAction.REAUTHENTICATE: "请在设置 > 连接器中重新连接服务。",
                RecoveryAction.WAIT: (
                    f"请在{retry_seconds}秒后重试。"
                    if context.retry_after_seconds
                    else "请稍后几分钟重试。"
                ),
                RecoveryAction.MODIFY_QUERY: "请尝试使用不同的搜索词。",
                RecoveryAction.CONTACT_ADMIN: "请联系管理员验证权限。",
            },
        }

        lang_messages = messages_by_lang.get(language, messages_by_lang["fr"])
        return lang_messages.get(context.recovery_action, "")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_default_error_handler() -> PartialErrorHandler:
    """
    Create a PartialErrorHandler with default configuration.

    Returns:
        Configured PartialErrorHandler instance
    """
    return PartialErrorHandler()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "PartialErrorHandler",
    "DomainErrorContext",
    "ErrorCategory",
    "ErrorSeverity",
    "RecoveryAction",
    "create_default_error_handler",
]
