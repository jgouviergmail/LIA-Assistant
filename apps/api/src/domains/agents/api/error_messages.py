"""
SSE Error Message Factory (PHASE 3.3.4 - Complete i18n).

Centralized error message generation with FULL i18n support.
Eliminates inconsistencies across SSE error handlers.

Supported Languages: fr, en, es, de, it, zh-CN (from core.constants.SUPPORTED_LANGUAGES)

Best Practices:
- User-friendly messages (explain what happened + recovery guidance)
- Consistent tone across all error types
- Full i18n support for all configured languages
- Error codes for programmatic handling
"""

from src.core.i18n import resolve_language
from src.core.i18n_types import SupportedLanguage


class SSEErrorMessages:
    """
    Factory for generating consistent SSE error messages with full i18n support.

    Supports: French, English, Spanish, German, Italian, Chinese (Simplified)

    Usage:
        >>> SSEErrorMessages.stream_error(ValueError("Invalid input"), language="en")
        'A problem occurred while generating the response. Please try again.'
    """

    @staticmethod
    def stream_error(exception: Exception, language: SupportedLanguage | None = None) -> str:
        """
        Error message for SSE stream failures (router-level).

        Classifies errors into user-friendly categories. Never exposes raw
        error types or technical details to end users.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly error message for stream errors
        """
        language = resolve_language(language)
        categorized = SSEErrorMessages._categorized_message(
            SSEErrorMessages._classify_error(exception), language
        )
        if categorized is not None:
            return categorized

        messages = {
            "fr": "Un problème est survenu lors de la génération de la réponse. Réessaie.",
            "en": "A problem occurred while generating the response. Please try again.",
            "es": "Ocurrió un problema al generar la respuesta. Por favor, inténtalo de nuevo.",
            "de": "Bei der Erstellung der Antwort ist ein Problem aufgetreten. Bitte versuche es erneut.",
            "it": "Si è verificato un problema durante la generazione della risposta. Riprova.",
            "zh-CN": "生成回复时出现问题。请重试。",
        }

        return messages[language]

    @staticmethod
    def run_orphaned(language: SupportedLanguage | None = None) -> str:
        """
        Error message for an orphaned background run (ADR-117 hard-kill path).

        Emitted by the SSE relay when the run's producer died without a
        terminal marker (server crash, OOM, power loss): the conversation's
        active-run lock vanished and no chunk arrived within the grace
        period. The generation is genuinely gone — the user must retry.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly error message for interrupted background runs
        """
        messages = {
            "fr": (
                "La génération a été interrompue de manière inattendue "
                "(redémarrage du serveur). Réessaie."
            ),
            "en": (
                "The response generation was unexpectedly interrupted "
                "(server restart). Please try again."
            ),
            "es": (
                "La generación de la respuesta se interrumpió de forma inesperada "
                "(reinicio del servidor). Por favor, inténtalo de nuevo."
            ),
            "de": (
                "Die Antwortgenerierung wurde unerwartet unterbrochen "
                "(Serverneustart). Bitte versuche es erneut."
            ),
            "it": (
                "La generazione della risposta è stata interrotta in modo imprevisto "
                "(riavvio del server). Riprova."
            ),
            "zh-CN": "回复生成意外中断（服务器重启）。请重试。",
        }

        return messages[resolve_language(language)]

    @staticmethod
    def _llm_provider_busy(language: SupportedLanguage | None = None) -> str:
        """
        User-friendly message when LLM provider is overloaded or rate-limited.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            Friendly message asking user to retry in a moment
        """
        messages = {
            "fr": (
                "Le fournisseur du modèle d'IA rencontre actuellement des difficultés techniques. "
                "Ce problème est indépendant de notre service et devrait se résoudre rapidement. "
                "Réessaie dans quelques instants."
            ),
            "en": (
                "The AI model provider is currently experiencing technical difficulties. "
                "This issue is independent of our service and should resolve shortly. "
                "Please try again in a few moments."
            ),
            "es": (
                "El proveedor del modelo de IA está experimentando dificultades técnicas. "
                "Este problema es independiente de nuestro servicio y debería resolverse pronto. "
                "Por favor, inténtalo de nuevo en unos momentos."
            ),
            "de": (
                "Der KI-Modellanbieter hat derzeit technische Schwierigkeiten. "
                "Dieses Problem ist unabhängig von unserem Dienst und sollte sich bald beheben. "
                "Bitte versuche es in einigen Augenblicken erneut."
            ),
            "it": (
                "Il fornitore del modello di IA sta riscontrando difficoltà tecniche. "
                "Questo problema è indipendente dal nostro servizio e dovrebbe risolversi a breve. "
                "Per favore, riprova tra qualche istante."
            ),
            "zh-CN": (
                "AI模型提供商目前遇到技术问题。"
                "此问题与我们的服务无关，应该很快会恢复。"
                "请稍后重试。"
            ),
        }

        return messages[resolve_language(language)]

    @staticmethod
    def _extract_status_code(exception: Exception) -> int | None:
        """The HTTP status the SDK already carries, when it carries one.

        Probes ``exc.status_code`` (openai-style) then
        ``exc.response.status_code`` (httpx-style). Never guesses from text.
        """
        status = getattr(exception, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(exception, "response", None)
        status = getattr(response, "status_code", None)
        return status if isinstance(status, int) else None

    @staticmethod
    def _classify_error(exception: Exception) -> str:
        """Classify an exception into a user-facing error category.

        ADR-220 (ex-F6): the HTTP status decides FIRST — the SDK exposes it on
        the exception, and text guessing misfiled real failures both ways
        ("you requested 4290 tokens" → "transient", while a bad key, a
        forbidden model and a model-name typo all fell to "unknown"). SDK
        exception type names come second (proxies of the codes when no status
        attribute survives), bounded keywords last.

        Categories:
        - "transient": overload, rate limit, 5xx — retrying can help
        - "auth": key absent/invalid (401) or model not allowed (403)
        - "quota": provider credit/billing exhausted (402)
        - "not_found": model name does not exist upstream (404), or the
          provider RETIRED the tag it once served (410)
        - "content_filter": provider safety/moderation blocks
        - "timeout": request or connection timeout (408 included)
        - "unknown": everything else

        Returns:
            Error category string.
        """
        status = SSEErrorMessages._extract_status_code(exception)
        if status is not None:
            by_status = {
                401: "auth",
                403: "auth",
                402: "quota",
                404: "not_found",
                # 410 Gone is 404's permanent sibling: the tag EXISTED and the
                # provider retired it. Measured 2026-09-10 on Ollama cloud —
                # four of eight tags answer `... was retired at 2026-06-16`.
                # Unnamed, it fell to "unknown", whose generic text ends on
                # « veuillez réessayer » about a model that will never answer
                # again. The advice a person needs is 404's: change the model.
                410: "not_found",
                408: "timeout",
            }
            if status in by_status:
                SSEErrorMessages._log_operations_failure(by_status[status], exception, status)
                return by_status[status]
            if status in (429, 500, 502, 503, 529):
                return "transient"
            # A status the ladder does not name (400, 422…) is a permanent
            # request problem: never "transient", the generic message applies.
            return "unknown"

        error_str = str(exception).lower()
        error_type = type(exception).__name__

        by_type = {
            "OverloadedError": "transient",
            "RateLimitError": "transient",
            "InternalServerError": "transient",
            "APIConnectionError": "transient",
            "ServiceUnavailableError": "transient",
            "APIStatusError": "transient",
            "AuthenticationError": "auth",
            "PermissionDeniedError": "auth",
            "NotFoundError": "not_found",
            "APITimeoutError": "timeout",
        }
        if error_type in by_type:
            category = by_type[error_type]
            if category in ("auth", "not_found", "quota"):
                SSEErrorMessages._log_operations_failure(category, exception, None)
            return category

        category = SSEErrorMessages._classify_by_keywords(error_str)
        if category in ("auth", "quota", "not_found"):
            SSEErrorMessages._log_operations_failure(category, exception, None)
        return category

    @staticmethod
    def _classify_by_keywords(error_str: str) -> str:
        """Last-resort keyword classification (no status, no SDK type).

        Numeric codes match ONLY in an HTTP-ish context (string start, or
        after error/status/code/http) — a bare substring turned "requested
        4290 tokens" and a Pydantic bound of 503 into "the service is
        saturated, retry" (measured, ex-F6).
        """
        import re as _re

        transient_keywords = (
            "overloaded",
            "rate_limit",
            "resource_exhausted",
            "service_unavailable",
            "server_error",
            "capacity",
        )
        if any(kw in error_str for kw in transient_keywords) or _re.search(
            r"(?:^|\berror\b|\bstatus\b|\bcode\b|\bhttp\b)\W{0,3}(?:429|500|502|503|529)\b",
            error_str,
        ):
            return "transient"

        auth_keywords = ("api key", "api_key", "authentication", "unauthorized", "credentials")
        if any(kw in error_str for kw in auth_keywords):
            return "auth"

        quota_keywords = ("insufficient balance", "insufficient_quota", "billing")
        if any(kw in error_str for kw in quota_keywords):
            return "quota"

        if "model_not_found" in error_str:
            return "not_found"

        # Content filter: provider safety/moderation blocks
        content_filter_keywords = (
            "datainspectionfailed",
            "content_policy_violation",
            "inappropriate content",
            "content_filter",
            "safety_block",
            "responsible_ai",
            "harm_category",
            "blocked by",
            "content management",
            "output data may contain",
        )
        if any(kw in error_str for kw in content_filter_keywords):
            return "content_filter"

        if "timeout" in error_str:
            return "timeout"

        return "unknown"

    @staticmethod
    def _log_operations_failure(category: str, exception: Exception, status: int | None) -> None:
        """Operator-facing record for CONFIGURATION failures (ADR-220).

        A bad key, a forbidden model or a model-name typo is fixed in the
        admin settings, not by retrying — before this record they were
        indistinguishable from transient noise in the logs. Type and status
        only: provider error strings can quote request fragments (PII rule).
        """
        import structlog

        structlog.get_logger(__name__).warning(
            "llm_operations_failure_classified",
            category=category,
            error_type=type(exception).__name__,
            status_code=status,
        )

    @staticmethod
    def _categorized_message(category: str, language: SupportedLanguage) -> str | None:
        """The category ladder (ADR-220), one dispatch.

        Returns the localized message for a named category, or ``None`` for
        "unknown" — the caller then falls back to its own generic text. Four
        hand-copied ladders drifted before (one had silently lost the timeout
        branch); three of their entry points had no caller and went (ADR-323).
        """
        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)
        if category == "timeout":
            return SSEErrorMessages._timeout_error(language)
        if category == "auth":
            return SSEErrorMessages._auth_error(language)
        if category == "quota":
            return SSEErrorMessages._quota_error(language)
        if category == "not_found":
            return SSEErrorMessages._model_not_found_error(language)
        return None

    @staticmethod
    def _auth_error(language: SupportedLanguage | None = None) -> str:
        """Key absent/invalid or model not allowed — fixed in settings, not by retrying."""
        messages = {
            "fr": (
                "Le fournisseur du modèle d'IA a refusé la connexion : la clé API est "
                "absente, invalide ou n'autorise pas ce modèle. Vérifie la configuration "
                "dans Paramètres → Administration → Configuration LLM."
            ),
            "en": (
                "The AI model provider refused the connection: the API key is missing, "
                "invalid, or does not allow this model. Check the configuration in "
                "Settings → Administration → LLM Configuration."
            ),
            "es": (
                "El proveedor del modelo de IA rechazó la conexión: la clave API falta, "
                "no es válida o no autoriza este modelo. Verifica la configuración en "
                "Configuración → Administración → Configuración LLM."
            ),
            "de": (
                "Der KI-Modellanbieter hat die Verbindung abgelehnt: Der API-Schlüssel "
                "fehlt, ist ungültig oder erlaubt dieses Modell nicht. Prüfe die "
                "Konfiguration unter Einstellungen → Verwaltung → LLM-Konfiguration."
            ),
            "it": (
                "Il fornitore del modello di IA ha rifiutato la connessione: la chiave "
                "API è assente, non valida o non autorizza questo modello. Verifica la "
                "configurazione in Impostazioni → Amministrazione → Configurazione LLM."
            ),
            "zh-CN": (
                "AI模型提供商拒绝了连接：API密钥缺失、无效或不允许使用此模型。"
                "请在 设置 → 管理 → LLM 配置 中检查配置。"
            ),
        }
        return messages[resolve_language(language)]

    @staticmethod
    def _quota_error(language: SupportedLanguage | None = None) -> str:
        """Provider credit or billing exhausted — retrying will not refill it."""
        messages = {
            "fr": (
                "Le crédit du fournisseur du modèle d'IA est épuisé. Recharge le compte "
                "ou vérifie la facturation chez le fournisseur, puis réessaie."
            ),
            "en": (
                "The AI model provider's credit is exhausted. Top up the account or "
                "check billing with the provider, then try again."
            ),
            "es": (
                "El crédito del proveedor del modelo de IA está agotado. Recarga la "
                "cuenta o verifica la facturación con el proveedor y vuelve a intentarlo."
            ),
            "de": (
                "Das Guthaben des KI-Modellanbieters ist aufgebraucht. Lade das "
                "Konto auf oder prüfe die Abrechnung beim Anbieter und versuche "
                "es erneut."
            ),
            "it": (
                "Il credito del fornitore del modello di IA è esaurito. Ricarica "
                "l'account o verifica la fatturazione presso il fornitore, poi riprova."
            ),
            "zh-CN": ("AI模型提供商的额度已用尽。" "请充值账户或检查提供商的账单，然后重试。"),
        }
        return messages[resolve_language(language)]

    @staticmethod
    def _model_not_found_error(language: SupportedLanguage | None = None) -> str:
        """The configured model does not exist upstream (typo after an admin edit)."""
        messages = {
            "fr": (
                "Le modèle d'IA configuré n'existe pas chez le fournisseur. Vérifie le "
                "nom du modèle dans Paramètres → Administration → Configuration LLM."
            ),
            "en": (
                "The configured AI model does not exist at the provider. Check the "
                "model name in Settings → Administration → LLM Configuration."
            ),
            "es": (
                "El modelo de IA configurado no existe en el proveedor. Verifica el "
                "nombre del modelo en Configuración → Administración → Configuración LLM."
            ),
            "de": (
                "Das konfigurierte KI-Modell existiert beim Anbieter nicht. Prüfe "
                "den Modellnamen unter Einstellungen → Verwaltung → "
                "LLM-Konfiguration."
            ),
            "it": (
                "Il modello di IA configurato non esiste presso il fornitore. Verifica "
                "il nome del modello in Impostazioni → Amministrazione → Configurazione "
                "LLM."
            ),
            "zh-CN": (
                "配置的AI模型在提供商处不存在。" "请在 设置 → 管理 → LLM 配置 中检查模型名称。"
            ),
        }
        return messages[resolve_language(language)]

    @staticmethod
    def _content_filter_error(language: SupportedLanguage | None = None) -> str:
        """User-friendly message when a provider content filter blocks the response.

        Args:
            language: User's language for localized message.

        Returns:
            Localized user-friendly message.
        """
        messages = {
            "fr": (
                "Le fournisseur du modèle d'IA n'a pas pu générer de réponse pour cette demande. "
                "Essaie de reformuler ta question."
            ),
            "en": (
                "The AI model provider could not generate a response for this request. "
                "Try rephrasing your question."
            ),
            "es": (
                "El proveedor del modelo de IA no pudo generar una respuesta para esta solicitud. "
                "Intenta reformular tu pregunta."
            ),
            "de": (
                "Der KI-Modellanbieter konnte keine Antwort auf diese Anfrage generieren. "
                "Versuche, deine Frage umzuformulieren."
            ),
            "it": (
                "Il fornitore del modello di IA non è riuscito a generare una risposta per questa richiesta. "
                "Prova a riformulare la tua domanda."
            ),
            "zh-CN": ("AI模型提供商无法为此请求生成回复。" "请尝试重新措辞你的问题。"),
        }
        return messages[resolve_language(language)]

    @staticmethod
    def _timeout_error(language: SupportedLanguage | None = None) -> str:
        """User-friendly message for request timeouts.

        Args:
            language: User's language for localized message.

        Returns:
            Localized user-friendly message.
        """
        messages = {
            "fr": (
                "La demande a pris trop de temps. "
                "Réessaie — si le problème persiste, essaie une question plus simple."
            ),
            "en": (
                "The request took too long. "
                "Please try again — if the problem persists, try a simpler question."
            ),
            "es": (
                "La solicitud tardó demasiado. "
                "Por favor, inténtalo de nuevo — si el problema persiste, prueba con una pregunta más sencilla."
            ),
            "de": (
                "Die Anfrage hat zu lange gedauert. "
                "Bitte versuche es erneut — wenn das Problem weiterhin besteht, versuche eine einfachere Frage."
            ),
            "it": (
                "La richiesta ha richiesto troppo tempo. "
                "Riprova — se il problema persiste, prova con una domanda più semplice."
            ),
            "zh-CN": ("请求耗时过长。" "请重试——如果问题仍然存在，请尝试更简单的问题。"),
        }
        return messages[resolve_language(language)]

    @staticmethod
    def validation_error(field_name: str, language: SupportedLanguage | None = None) -> str:
        """
        Error message for parameter validation failures.

        Args:
            field_name: Name of the field that failed validation
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly error message for validation errors
        """
        messages = {
            "fr": f"Paramètre invalide : {field_name}. Vérifie la valeur et réessaie.",
            "en": f"Invalid parameter: {field_name}. Check the value and try again.",
            "es": f"Parámetro inválido: {field_name}. Comprueba el valor e inténtalo de nuevo.",
            "de": f"Ungültiger Parameter: {field_name}. Überprüfe den Wert und versuche es erneut.",
            "it": f"Parametro non valido: {field_name}. Controlla il valore e riprova.",
            "zh-CN": f"无效参数：{field_name}。检查值并重试。",
        }

        return messages[resolve_language(language)]

    @staticmethod
    def confirmation_required(language: SupportedLanguage | None = None) -> str:
        """
        Generic confirmation required message.

        Used as ultimate fallback when HITL question generation fails.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly confirmation message
        """
        messages = {
            "fr": "Une confirmation est requise pour continuer.",
            "en": "Confirmation is required to proceed.",
            "es": "Se requiere confirmación para continuar.",
            "de": "Zur Fortsetzung ist eine Bestätigung erforderlich.",
            "it": "È necessaria una conferma per continuare.",
            "zh-CN": "需要确认才能继续。",
        }

        return messages[resolve_language(language)]

    @staticmethod
    def hitl_decision_stale(language: SupportedLanguage | None = None) -> str:
        """
        Error message when a one-click HITL decision no longer matches the
        pending interrupt (expired, already answered, or superseded).

        Lot 1 T1.3: the frontend card shows this and switches to its
        "expired" state — the click is never processed as a new turn.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly staleness message
        """
        messages = {
            "fr": "Cette demande de confirmation n'est plus active. Reformule ta demande si besoin.",
            "en": "This confirmation request is no longer active. Rephrase your request if needed.",
            "es": "Esta solicitud de confirmación ya no está activa. Reformula tu petición si es necesario.",
            "de": "Diese Bestätigungsanfrage ist nicht mehr aktiv. Formuliere deine Anfrage bei Bedarf neu.",
            "it": "Questa richiesta di conferma non è più attiva. Riformula la tua richiesta se necessario.",
            "zh-CN": "此确认请求已失效。如有需要，请重新表述你的请求。",
        }

        return messages[resolve_language(language)]

    @staticmethod
    def simple_fallback(language: SupportedLanguage | None = None) -> str:
        """
        Last-resort fallback when the pipeline AND the fallback LLM both fail.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN); the declared language when None

        Returns:
            User-friendly message asking the user to rephrase
        """
        messages = {
            "fr": (
                "Je n'ai pas trouvé les informations demandées. " "Peux-tu reformuler ta question ?"
            ),
            "en": (
                "I could not find the requested information. " "Could you rephrase your question?"
            ),
            "es": ("No encontré la información solicitada. " "¿Puedes reformular tu pregunta?"),
            "de": (
                "Ich konnte die angeforderten Informationen nicht finden. "
                "Kannst du deine Frage umformulieren?"
            ),
            "it": ("Non ho trovato le informazioni richieste. " "Puoi riformulare la tua domanda?"),
            "zh-CN": "我没有找到所需的信息。你能重新表述你的问题吗？",
        }

        return messages[resolve_language(language)]
