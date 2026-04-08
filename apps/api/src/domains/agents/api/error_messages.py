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
        category = SSEErrorMessages._classify_error(exception)

        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)
        if category == "timeout":
            return SSEErrorMessages._timeout_error(language)

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
        category = SSEErrorMessages._classify_error(exception)

        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)
        if category == "timeout":
            return SSEErrorMessages._timeout_error(language)

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
    def _classify_error(exception: Exception) -> str:
        """Classify an exception into a user-facing error category.

        Categories:
        - "transient": Provider overload, rate limit, temporary unavailability
        - "content_filter": Provider content moderation/safety filter triggered
        - "timeout": Request or connection timeout
        - "unknown": Everything else

        Returns:
            Error category string.
        """
        error_str = str(exception).lower()
        error_type = type(exception).__name__

        # Transient: overload, rate limit, capacity, server errors
        transient_keywords = (
            "overloaded",
            "rate_limit",
            "resource_exhausted",
            "service_unavailable",
            "server_error",
            "capacity",
        )
        transient_codes = ("429", "500", "502", "503", "529")
        transient_types = {
            "OverloadedError",
            "RateLimitError",
            "InternalServerError",
            "APIConnectionError",
            "ServiceUnavailableError",
            "APIStatusError",
        }

        if (
            any(kw in error_str for kw in transient_keywords)
            or any(code in error_str for code in transient_codes)
            or error_type in transient_types
        ):
            return "transient"

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

        # Timeout
        if error_type == "APITimeoutError" or "timeout" in error_str:
            return "timeout"

        return "unknown"

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
        category = SSEErrorMessages._classify_error(exception)

        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)

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
        category = SSEErrorMessages._classify_error(exception)

        if category == "transient":
            return SSEErrorMessages._llm_provider_busy(language)
        if category == "content_filter":
            return SSEErrorMessages._content_filter_error(language)
        if category == "timeout":
            return SSEErrorMessages._timeout_error(language)

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
