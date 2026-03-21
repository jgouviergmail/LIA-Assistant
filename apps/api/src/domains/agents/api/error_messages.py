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

        Detects LLM provider transient errors and provides appropriate messaging.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message with recovery guidance
        """
        # Check for LLM provider transient errors first
        error_str = str(exception).lower()
        error_type = type(exception).__name__

        if (
            "overloaded" in error_str
            or "529" in error_str
            or error_type == "OverloadedError"
            or "rate_limit" in error_str
            or "429" in error_str
            or error_type == "RateLimitError"
        ):
            return SSEErrorMessages._llm_provider_busy(language)

        messages = {
            "fr": f"Une erreur s'est produite : {error_type}. Veuillez réessayer ou contacter le support si le problème persiste.",
            "en": f"An error occurred: {error_type}. Please try again or contact support if the problem persists.",
            "es": f"Se produjo un error: {error_type}. Por favor, inténtelo de nuevo o contacte con soporte si el problema persiste.",
            "de": f"Ein Fehler ist aufgetreten: {error_type}. Bitte versuchen Sie es erneut oder wenden Sie sich an den Support, wenn das Problem weiterhin besteht.",
            "it": f"Si è verificato un errore: {error_type}. Si prega di riprovare o contattare il supporto se il problema persiste.",
            "zh-CN": f"发生错误：{error_type}。请重试，如果问题仍然存在，请联系支持人员。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def stream_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Error message for SSE stream failures (router-level).

        Detects LLM provider errors (overloaded, rate limit, timeout) and returns
        a user-friendly message with retry guidance instead of raw error types.

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for stream errors
        """
        # Detect LLM provider transient errors (overloaded, rate limit, 529, 529)
        error_str = str(exception).lower()
        error_type_name = type(exception).__name__

        is_overloaded = (
            "overloaded" in error_str or "529" in error_str or error_type_name == "OverloadedError"
        )
        is_rate_limited = (
            "rate_limit" in error_str or "429" in error_str or error_type_name == "RateLimitError"
        )

        if is_overloaded or is_rate_limited:
            return SSEErrorMessages._llm_provider_busy(language)

        messages = {
            "fr": f"Erreur de streaming : {error_type_name}. Veuillez rafraîchir la page pour recommencer.",
            "en": f"Stream error: {error_type_name}. Please refresh the page to try again.",
            "es": f"Error de transmisión: {error_type_name}. Por favor, actualice la página para volver a intentarlo.",
            "de": f"Streaming-Fehler: {error_type_name}. Bitte aktualisieren Sie die Seite, um es erneut zu versuchen.",
            "it": f"Errore di streaming: {error_type_name}. Si prega di aggiornare la pagina per riprovare.",
            "zh-CN": f"流错误：{error_type_name}。请刷新页面重试。",
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
                "Le service d'intelligence artificielle est temporairement surchargé. "
                "Votre demande a bien été traitée mais la formulation de la réponse a échoué. "
                "Veuillez réessayer dans quelques instants."
            ),
            "en": (
                "The AI service is temporarily overloaded. "
                "Your request was processed but the response generation failed. "
                "Please try again in a few moments."
            ),
            "es": (
                "El servicio de inteligencia artificial está temporalmente sobrecargado. "
                "Su solicitud fue procesada pero la generación de la respuesta falló. "
                "Por favor, inténtelo de nuevo en unos momentos."
            ),
            "de": (
                "Der KI-Dienst ist vorübergehend überlastet. "
                "Ihre Anfrage wurde verarbeitet, aber die Antwortgenerierung ist fehlgeschlagen. "
                "Bitte versuchen Sie es in einigen Augenblicken erneut."
            ),
            "it": (
                "Il servizio di intelligenza artificiale è temporaneamente sovraccarico. "
                "La tua richiesta è stata elaborata ma la generazione della risposta è fallita. "
                "Per favore, riprova tra qualche istante."
            ),
            "zh-CN": ("AI服务暂时过载。" "您的请求已处理，但响应生成失败。" "请稍后重试。"),
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

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for HITL resumption
        """
        error_type = type(exception).__name__

        messages = {
            "fr": f"Erreur lors de la reprise : {error_type}. Veuillez reformuler votre demande ou recommencer.",
            "en": f"Error during resumption: {error_type}. Please rephrase your request or start over.",
            "es": f"Error durante la reanudación: {error_type}. Por favor, reformule su solicitud o comience de nuevo.",
            "de": f"Fehler bei der Wiederaufnahme: {error_type}. Bitte formulieren Sie Ihre Anfrage um oder beginnen Sie von vorne.",
            "it": f"Errore durante la ripresa: {error_type}. Si prega di riformulare la richiesta o ricominciare.",
            "zh-CN": f"恢复时出错：{error_type}。请重新表述您的请求或重新开始。",
        }

        return messages.get(language, messages["en"])

    @staticmethod
    def graph_execution_error(exception: Exception, language: SupportedLanguage = "fr") -> str:
        """
        Error message for graph execution failures (main agent flow).

        Args:
            exception: The exception that occurred
            language: Target language (fr/en/es/de/it/zh-CN)

        Returns:
            User-friendly error message for graph errors
        """
        error_type = type(exception).__name__

        messages = {
            "fr": f"Une erreur s'est produite lors du traitement : {error_type}. Veuillez réessayer avec une demande différente.",
            "en": f"An error occurred during processing: {error_type}. Please try again with a different request.",
            "es": f"Se produjo un error durante el procesamiento: {error_type}. Por favor, inténtelo de nuevo con una solicitud diferente.",
            "de": f"Bei der Verarbeitung ist ein Fehler aufgetreten: {error_type}. Bitte versuchen Sie es mit einer anderen Anfrage erneut.",
            "it": f"Si è verificato un errore durante l'elaborazione: {error_type}. Si prega di riprovare con una richiesta diversa.",
            "zh-CN": f"处理过程中发生错误：{error_type}。请使用不同的请求重试。",
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
        error_info = f"{type(error).__name__}: {error}"

        messages = {
            "fr": f"Erreur lors de la reprise: {error_info}",
            "en": f"Error during resumption: {error_info}",
            "es": f"Error durante la reanudación: {error_info}",
            "de": f"Fehler bei der Wiederaufnahme: {error_info}",
            "it": f"Errore durante la ripresa: {error_info}",
            "zh-CN": f"恢复时出错：{error_info}",
        }

        return messages.get(language, messages["en"])
