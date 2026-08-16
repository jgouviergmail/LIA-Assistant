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

from typing import Literal

# Type alias for supported languages (from core.constants.SUPPORTED_LANGUAGES)
SupportedLanguage = Literal["fr", "en", "es", "de", "it", "zh-CN"]


class SSEErrorMessages:
    """
    Factory for generating consistent SSE error messages with full i18n support.

    Supports: French, English, Spanish, German, Italian, Chinese (Simplified)

    Usage:
        >>> msg = SSEErrorMessages.generic_error(ValueError("Invalid input"), language="fr")
        >>> msg
        "Une erreur s'est produite : ValueError. Veuillez réessayer."
    """

    @staticmethod
    def generic_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Generic error message for unexpected exceptions.

        Classifies errors into user-friendly categories and never exposes
        raw error types or technical details to end users.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message with recovery guidance
        """
        categorized = SSEErrorMessages._categorized_message(
            SSEErrorMessages._classify_error(exception), language
        )
        if categorized is not None:
            return categorized

        messages = {
            "fr": "Une erreur inattendue s'est produite. Veuillez réessayer ou contacter le support si le problème persiste.",
            "en": "An unexpected error occurred. Please try again or contact support if the problem persists.",
            "es": "Se produjo un error inesperado. Por favor, inténtelo de nuevo o contacte con soporte si el problema persiste.",
            "de": "Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder wenden Sie sich an den Support.",
            "it": "Si è verificato un errore imprevisto. Si prega di riprovare o contattare il supporto se il problema persiste.",
            "zh-CN": "发生意外错误。请重试，如果问题仍然存在，请联系支持人员。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def stream_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Error message for SSE stream failures (router-level).

        Classifies errors into user-friendly categories. Never exposes raw
        error types or technical details to end users.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for stream errors
        """
        categorized = SSEErrorMessages._categorized_message(
            SSEErrorMessages._classify_error(exception), language
        )
        if categorized is not None:
            return categorized

        messages = {
            "fr": "Un problème est survenu lors de la génération de la réponse. Veuillez réessayer.",
            "en": "A problem occurred while generating the response. Please try again.",
            "es": "Ocurrió un problema al generar la respuesta. Por favor, inténtelo de nuevo.",
            "de": "Bei der Erstellung der Antwort ist ein Problem aufgetreten. Bitte versuchen Sie es erneut.",
            "it": "Si è verificato un problema durante la generazione della risposta. Si prega di riprovare.",
            "zh-CN": "生成回复时出现问题。请重试。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def run_orphaned(language: SupportedLanguage = "fr") -> str:
        """
        Error message for an orphaned background run (ADR-117 hard-kill path).

        Emitted by the SSE relay when the run's producer died without a
        terminal marker (server crash, OOM, power loss): the conversation's
        active-run lock vanished and no chunk arrived within the grace
        period. The generation is genuinely gone — the user must retry.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for interrupted background runs
        """
        messages = {
            "fr": (
                "La génération a été interrompue de manière inattendue "
                "(redémarrage du serveur). Veuillez réessayer."
            ),
            "en": (
                "The response generation was unexpectedly interrupted "
                "(server restart). Please try again."
            ),
            "es": (
                "La generación de la respuesta se interrumpió de forma inesperada "
                "(reinicio del servidor). Por favor, inténtelo de nuevo."
            ),
            "de": (
                "Die Antwortgenerierung wurde unerwartet unterbrochen "
                "(Serverneustart). Bitte versuchen Sie es erneut."
            ),
            "it": (
                "La generazione della risposta è stata interrotta in modo imprevisto "
                "(riavvio del server). Si prega di riprovare."
            ),
            "zh-CN": "回复生成意外中断（服务器重启）。请重试。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def _llm_provider_busy(language: SupportedLanguage = "fr") -> str:
        """
        User-friendly message when LLM provider is overloaded or rate-limited.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            Friendly message asking user to retry in a moment
        """
        messages = {
            "fr": (
                "Le fournisseur du modèle d'IA rencontre actuellement des difficultés techniques. "
                "Ce problème est indépendant de notre service et devrait se résoudre rapidement. "
                "Veuillez réessayer dans quelques instants."
            ),
            "en": (
                "The AI model provider is currently experiencing technical difficulties. "
                "This issue is independent of our service and should resolve shortly. "
                "Please try again in a few moments."
            ),
            "es": (
                "El proveedor del modelo de IA está experimentando dificultades técnicas. "
                "Este problema es independiente de nuestro servicio y debería resolverse pronto. "
                "Por favor, inténtelo de nuevo en unos momentos."
            ),
            "de": (
                "Der KI-Modellanbieter hat derzeit technische Schwierigkeiten. "
                "Dieses Problem ist unabhängig von unserem Dienst und sollte sich bald beheben. "
                "Bitte versuchen Sie es in einigen Augenblicken erneut."
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

        return messages.get(language, messages["en"])

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
        - "not_found": model name does not exist upstream (404)
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
        """The shared category ladder (ADR-220): one dispatch, four callers.

        Returns the localized message for a named category, or ``None`` for
        "unknown" — each public method then falls back to its own generic
        text. Four hand-copied ladders drifted before (hitl_resumption_error
        had silently lost the timeout branch).
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
    def _auth_error(language: SupportedLanguage = "fr") -> str:
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
                "no es válida o no autoriza este modelo. Verifique la configuración en "
                "Configuración → Administración → Configuración LLM."
            ),
            "de": (
                "Der KI-Modellanbieter hat die Verbindung abgelehnt: Der API-Schlüssel "
                "fehlt, ist ungültig oder erlaubt dieses Modell nicht. Prüfen Sie die "
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
        return messages.get(language, messages["en"])

    @staticmethod
    def _quota_error(language: SupportedLanguage = "fr") -> str:
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
                "El crédito del proveedor del modelo de IA está agotado. Recargue la "
                "cuenta o verifique la facturación con el proveedor y vuelva a intentarlo."
            ),
            "de": (
                "Das Guthaben des KI-Modellanbieters ist aufgebraucht. Laden Sie das "
                "Konto auf oder prüfen Sie die Abrechnung beim Anbieter und versuchen "
                "Sie es erneut."
            ),
            "it": (
                "Il credito del fornitore del modello di IA è esaurito. Ricarica "
                "l'account o verifica la fatturazione presso il fornitore, poi riprova."
            ),
            "zh-CN": ("AI模型提供商的额度已用尽。" "请充值账户或检查提供商的账单，然后重试。"),
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def _model_not_found_error(language: SupportedLanguage = "fr") -> str:
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
                "El modelo de IA configurado no existe en el proveedor. Verifique el "
                "nombre del modelo en Configuración → Administración → Configuración LLM."
            ),
            "de": (
                "Das konfigurierte KI-Modell existiert beim Anbieter nicht. Prüfen Sie "
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
        return messages.get(language, messages["en"])

    @staticmethod
    def _content_filter_error(language: SupportedLanguage = "fr") -> str:
        """User-friendly message when a provider content filter blocks the response.

        Args:
            language: User's language for localized message.

        Returns:
            Localized user-friendly message.
        """
        messages = {
            "fr": (
                "Le fournisseur du modèle d'IA n'a pas pu générer de réponse pour cette demande. "
                "Essayez de reformuler votre question."
            ),
            "en": (
                "The AI model provider could not generate a response for this request. "
                "Try rephrasing your question."
            ),
            "es": (
                "El proveedor del modelo de IA no pudo generar una respuesta para esta solicitud. "
                "Intente reformular su pregunta."
            ),
            "de": (
                "Der KI-Modellanbieter konnte keine Antwort auf diese Anfrage generieren. "
                "Versuchen Sie, Ihre Frage umzuformulieren."
            ),
            "it": (
                "Il fornitore del modello di IA non è riuscito a generare una risposta per questa richiesta. "
                "Prova a riformulare la tua domanda."
            ),
            "zh-CN": ("AI模型提供商无法为此请求生成回复。" "请尝试重新措辞您的问题。"),
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def _timeout_error(language: SupportedLanguage = "fr") -> str:
        """User-friendly message for request timeouts.

        Args:
            language: User's language for localized message.

        Returns:
            Localized user-friendly message.
        """
        messages = {
            "fr": (
                "La demande a pris trop de temps. "
                "Veuillez réessayer — si le problème persiste, essayez une question plus simple."
            ),
            "en": (
                "The request took too long. "
                "Please try again — if the problem persists, try a simpler question."
            ),
            "es": (
                "La solicitud tardó demasiado. "
                "Por favor, inténtelo de nuevo — si el problema persiste, pruebe con una pregunta más sencilla."
            ),
            "de": (
                "Die Anfrage hat zu lange gedauert. "
                "Bitte versuchen Sie es erneut — wenn das Problem weiterhin besteht, versuchen Sie eine einfachere Frage."
            ),
            "it": (
                "La richiesta ha richiesto troppo tempo. "
                "Si prega di riprovare — se il problema persiste, provare con una domanda più semplice."
            ),
            "zh-CN": ("请求耗时过长。" "请重试——如果问题仍然存在，请尝试更简单的问题。"),
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def hitl_security_error(
        action_count: int,
        max_allowed: int,
        language: SupportedLanguage = "fr",
    ) -> str:
        """
        Security error for HITL max actions exceeded (DoS protection).

        Args:
            action_count: Number of actions requested
            max_allowed: Maximum allowed actions
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            Detailed error message with security context
        """
        messages = {
            "fr": (
                f"Trop d'actions à approuver ({action_count} actions). "
                f"Maximum autorisé : {max_allowed}. "
                "Cette limite protège le système contre les surcharges. "
                "Si tu penses avoir besoin de plus d'actions simultanées, "
                "contacte le support technique."
            ),
            "en": (
                f"Too many actions to approve ({action_count} actions). "
                f"Maximum allowed: {max_allowed}. "
                "This limit protects the system from overload. "
                "If you need more simultaneous actions, contact technical support."
            ),
            "es": (
                f"Demasiadas acciones para aprobar ({action_count} acciones). "
                f"Máximo permitido: {max_allowed}. "
                "Este límite protege el sistema contra sobrecarga. "
                "Si necesita más acciones simultáneas, contacte con soporte técnico."
            ),
            "de": (
                f"Zu viele Aktionen zum Genehmigen ({action_count} Aktionen). "
                f"Maximal erlaubt: {max_allowed}. "
                "Diese Grenze schützt das System vor Überlastung. "
                "Wenn Sie mehr gleichzeitige Aktionen benötigen, wenden Sie sich an den technischen Support."
            ),
            "it": (
                f"Troppe azioni da approvare ({action_count} azioni). "
                f"Massimo consentito: {max_allowed}. "
                "Questo limite protegge il sistema dal sovraccarico. "
                "Se hai bisogno di più azioni simultanee, contatta il supporto tecnico."
            ),
            "zh-CN": (
                f"要批准的操作过多（{action_count} 个操作）。"
                f"最大允许：{max_allowed}。"
                "此限制保护系统免受过载。"
                "如果您需要更多同时操作，请联系技术支持。"
            ),
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def hitl_resumption_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Error message for HITL resumption failures.

        Uses _classify_error to provide category-specific messages.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for HITL resumption
        """
        categorized = SSEErrorMessages._categorized_message(
            SSEErrorMessages._classify_error(exception), language
        )
        if categorized is not None:
            return categorized

        messages = {
            "fr": "Un problème est survenu lors de la reprise. Veuillez reformuler votre demande ou recommencer.",
            "en": "A problem occurred during resumption. Please rephrase your request or start over.",
            "es": "Ocurrió un problema durante la reanudación. Por favor, reformule su solicitud o comience de nuevo.",
            "de": "Bei der Wiederaufnahme ist ein Problem aufgetreten. Bitte formulieren Sie Ihre Anfrage um oder beginnen Sie von vorne.",
            "it": "Si è verificato un problema durante la ripresa. Si prega di riformulare la richiesta o ricominciare.",
            "zh-CN": "恢复时出现问题。请重新表述您的请求或重新开始。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def graph_execution_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Error message for graph execution failures (main agent flow).

        Uses _classify_error to provide category-specific messages.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for graph errors
        """
        categorized = SSEErrorMessages._categorized_message(
            SSEErrorMessages._classify_error(exception), language
        )
        if categorized is not None:
            return categorized

        messages = {
            "fr": "Un problème est survenu lors du traitement. Veuillez réessayer avec une demande différente.",
            "en": "A problem occurred during processing. Please try again with a different request.",
            "es": "Ocurrió un problema durante el procesamiento. Por favor, inténtelo de nuevo con una solicitud diferente.",
            "de": "Bei der Verarbeitung ist ein Problem aufgetreten. Bitte versuchen Sie es mit einer anderen Anfrage erneut.",
            "it": "Si è verificato un problema durante l'elaborazione. Si prega di riprovare con una richiesta diversa.",
            "zh-CN": "处理过程中出现问题。请使用不同的请求重试。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def classification_error(language: SupportedLanguage = "fr") -> str:
        """
        Error message for HITL classification failures.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for classification errors
        """
        messages = {
            "fr": "Je n'ai pas bien compris ta réponse. Peux-tu reformuler plus clairement ? (Exemple: 'oui', 'non', 'modifie le nom', etc.)",
            "en": "I didn't understand your response. Can you rephrase more clearly? (Example: 'yes', 'no', 'change the name', etc.)",
            "es": "No entendí tu respuesta. ¿Puedes reformular más claramente? (Ejemplo: 'sí', 'no', 'cambiar el nombre', etc.)",
            "de": "Ich habe Ihre Antwort nicht verstanden. Können Sie es klarer formulieren? (Beispiel: 'ja', 'nein', 'Namen ändern', usw.)",
            "it": "Non ho capito la tua risposta. Puoi riformulare più chiaramente? (Esempio: 'sì', 'no', 'cambia il nome', ecc.)",
            "zh-CN": "我没有理解你的回答。你能更清楚地重新表述吗？（例如：'是'、'否'、'更改名称'等）",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def validation_error(field_name: str, language: SupportedLanguage = "fr") -> str:
        """
        Error message for parameter validation failures.

        Args:
            field_name: Name of the field that failed validation
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for validation errors
        """
        messages = {
            "fr": f"Paramètre invalide : {field_name}. Vérifie la valeur et réessaie.",
            "en": f"Invalid parameter: {field_name}. Check the value and try again.",
            "es": f"Parámetro inválido: {field_name}. Compruebe el valor e inténtelo de nuevo.",
            "de": f"Ungültiger Parameter: {field_name}. Überprüfen Sie den Wert und versuchen Sie es erneut.",
            "it": f"Parametro non valido: {field_name}. Controlla il valore e riprova.",
            "zh-CN": f"无效参数：{field_name}。检查值并重试。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def hitl_rejection_message(reasoning: str, language: SupportedLanguage = "fr") -> str:
        """
        HITL rejection message with user reasoning (PHASE 3.2.2 - i18n gap fix).

        Replaces hardcoded French in:
        - hitl_management.py:258
        - resumption_strategies.py:462-468

        Args:
            reasoning: User's rejection reasoning
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            Formatted rejection message with reasoning

        Example:
            >>> msg = SSEErrorMessages.hitl_rejection_message("Mauvais contact", language="fr")
            >>> assert "Action refusée" in msg
        """
        messages = {
            "fr": f"Action refusée par l'utilisateur : {reasoning}",
            "en": f"Action rejected by user: {reasoning}",
            "es": f"Acción rechazada por el usuario: {reasoning}",
            "de": f"Aktion vom Benutzer abgelehnt: {reasoning}",
            "it": f"Azione rifiutata dall'utente: {reasoning}",
            "zh-CN": f"用户拒绝操作：{reasoning}",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def plan_approval_fallback(step_count: int, language: SupportedLanguage = "fr") -> str:
        """
        Fallback message for plan approval when LLM question generation fails.

        Args:
            step_count: Number of steps requiring approval
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly plan approval message
        """
        # Step word pluralization
        step_words = {
            "fr": ("étape", "étapes"),
            "en": ("step", "steps"),
            "es": ("paso", "pasos"),
            "de": ("Schritt", "Schritte"),
            "it": ("passaggio", "passaggi"),
            "zh-CN": ("步骤", "步骤"),  # Chinese doesn't have plural
        }

        words = step_words.get(language, step_words["en"])
        step_word = words[0] if step_count == 1 else words[1]

        messages = {
            "fr": (
                f"Ce plan contient {step_count} {step_word} nécessitant ton approbation. "
                f"Merci de valider pour continuer."
            ),
            "en": (
                f"This plan contains {step_count} {step_word} that require your approval. "
                f"Please review and approve to proceed."
            ),
            "es": (
                f"Este plan contiene {step_count} {step_word} que requieren tu aprobación. "
                f"Por favor revisa y aprueba para continuar."
            ),
            "de": (
                f"Dieser Plan enthält {step_count} {step_word}, die Ihre Genehmigung erfordern. "
                f"Bitte überprüfen und genehmigen Sie, um fortzufahren."
            ),
            "it": (
                f"Questo piano contiene {step_count} {step_word} che richiedono la tua approvazione. "
                f"Per favore rivedi e approva per continuare."
            ),
            "zh-CN": (f"此计划包含 {step_count} 个{step_word}需要您的批准。请审核并批准以继续。"),
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def confirmation_required(language: SupportedLanguage = "fr") -> str:
        """
        Generic confirmation required message.

        Used as ultimate fallback when HITL question generation fails.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

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

        return messages.get(language, messages["en"])

    @staticmethod
    def hitl_decision_stale(language: SupportedLanguage = "fr") -> str:
        """
        Error message when a one-click HITL decision no longer matches the
        pending interrupt (expired, already answered, or superseded).

        Lot 1 T1.3: the frontend card shows this and switches to its
        "expired" state — the click is never processed as a new turn.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

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

        return messages.get(language, messages["en"])

    @staticmethod
    def hitl_resumption_error_simple(error: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Simple error message for HITL resumption failures (used in prompts.py).

        Args:
            error: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            Formatted error message for resumption errors
        """
        category = SSEErrorMessages._classify_error(error)

        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)

        messages = {
            "fr": "Un problème est survenu lors de la reprise. Veuillez reformuler votre demande.",
            "en": "A problem occurred during resumption. Please rephrase your request.",
            "es": "Ocurrió un problema durante la reanudación. Por favor, reformule su solicitud.",
            "de": "Bei der Wiederaufnahme ist ein Problem aufgetreten. Bitte formulieren Sie Ihre Anfrage um.",
            "it": "Si è verificato un problema durante la ripresa. Si prega di riformulare la richiesta.",
            "zh-CN": "恢复时出现问题。请重新表述您的请求。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def simple_fallback(language: SupportedLanguage = "fr") -> str:
        """
        Last-resort fallback when the pipeline AND the fallback LLM both fail.

        Args:
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly message asking the user to rephrase
        """
        messages = {
            "fr": (
                "Je n'ai pas trouvé les informations demandées. "
                "Pouvez-vous reformuler votre question ?"
            ),
            "en": (
                "I could not find the requested information. " "Could you rephrase your question?"
            ),
            "es": ("No encontré la información solicitada. " "¿Puede reformular su pregunta?"),
            "de": (
                "Ich konnte die angeforderten Informationen nicht finden. "
                "Können Sie Ihre Frage umformulieren?"
            ),
            "it": ("Non ho trovato le informazioni richieste. " "Puoi riformulare la tua domanda?"),
            "zh-CN": "我没有找到所需的信息。您能重新表述您的问题吗？",
        }

        return messages.get(language, messages["en"])
