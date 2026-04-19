"""
Centralized API Messages Factory with full i18n support (PHASE i18n-consolidation).

Provides internationalized messages for:
- HTTP exceptions (400, 401, 403, 404, 409, 500, 503)
- Success responses (registration, login, logout, etc.)
- Validation errors
- Domain-specific messages (memories, conversations, connectors)

Supported Languages: fr, en, es, de, it, zh-CN

Usage:
    from src.core.i18n_api_messages import APIMessages

    # In router
    raise HTTPException(
        status_code=404,
        detail=APIMessages.resource_not_found("connector", language=user_language)
    )

    # In success response
    return MessageResponse(
        message=APIMessages.login_successful(language=user_language)
    )

Design Principles:
- Same pattern as agents/api/error_messages.py (SSEErrorMessages)
- Dictionary-based translations (no gettext dependency at call time)
- Type-safe language parameter (SupportedLanguage)
- Fallback to English if language not found
"""

from src.core.i18n_types import SupportedLanguage


class APIMessages:
    """
    Factory for generating consistent API messages with full i18n support.

    Supports: French, English, Spanish, German, Italian, Chinese (Simplified)

    Organized by category:
    - Authentication & Authorization
    - Resource operations (CRUD)
    - Validation errors
    - External services
    - Domain-specific (memories, conversations, connectors)
    """

    # =========================================================================
    # AUTHENTICATION & AUTHORIZATION
    # =========================================================================

    @staticmethod
    def invalid_credentials(language: SupportedLanguage = "fr") -> str:
        """Authentication error - invalid email/password."""
        messages = {
            "fr": "Identifiants invalides",
            "en": "Invalid credentials",
            "es": "Credenciales inválidas",
            "de": "Ungültige Anmeldedaten",
            "it": "Credenziali non valide",
            "zh-CN": "凭据无效",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def token_invalid_or_expired(token_type: str, language: SupportedLanguage = "fr") -> str:
        """Authentication error - invalid or expired token."""
        messages = {
            "fr": f"{token_type} invalide ou expiré",
            "en": f"Invalid or expired {token_type}",
            "es": f"{token_type} inválido o expirado",
            "de": f"Ungültiges oder abgelaufenes {token_type}",
            "it": f"{token_type} non valido o scaduto",
            "zh-CN": f"{token_type} 无效或已过期",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def token_already_used(language: SupportedLanguage = "fr") -> str:
        """Authentication error - token already used (single-use tokens)."""
        messages = {
            "fr": "Ce lien a déjà été utilisé. Veuillez en demander un nouveau.",
            "en": "This link has already been used. Please request a new one.",
            "es": "Este enlace ya ha sido utilizado. Por favor, solicite uno nuevo.",
            "de": "Dieser Link wurde bereits verwendet. Bitte fordern Sie einen neuen an.",
            "it": "Questo link è già stato utilizzato. Si prega di richiederne uno nuovo.",
            "zh-CN": "此链接已被使用。请重新申请。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def session_invalid_or_expired(language: SupportedLanguage = "fr") -> str:
        """Authentication error - session invalid or expired."""
        messages = {
            "fr": "Session invalide ou expirée",
            "en": "Session invalid or expired",
            "es": "Sesión inválida o expirada",
            "de": "Sitzung ungültig oder abgelaufen",
            "it": "Sessione non valida o scaduta",
            "zh-CN": "会话无效或已过期",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def authentication_required(language: SupportedLanguage = "fr") -> str:
        """Authentication error - user not authenticated."""
        messages = {
            "fr": "Authentification requise",
            "en": "Authentication required",
            "es": "Autenticación requerida",
            "de": "Authentifizierung erforderlich",
            "it": "Autenticazione richiesta",
            "zh-CN": "需要身份验证",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def not_authorized(language: SupportedLanguage = "fr") -> str:
        """Authorization error - not authorized to access resource."""
        messages = {
            "fr": "Non autorisé à accéder à cette ressource",
            "en": "Not authorized to access this resource",
            "es": "No autorizado para acceder a este recurso",
            "de": "Nicht berechtigt, auf diese Ressource zuzugreifen",
            "it": "Non autorizzato ad accedere a questa risorsa",
            "zh-CN": "无权访问此资源",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def not_authorized_action(
        action: str, resource_type: str, language: SupportedLanguage = "fr"
    ) -> str:
        """Authorization error - not authorized to perform action on resource."""
        messages = {
            "fr": f"Non autorisé à {action} {resource_type}",
            "en": f"Not authorized to {action} {resource_type}",
            "es": f"No autorizado para {action} {resource_type}",
            "de": f"Nicht berechtigt, {resource_type} zu {action}",
            "it": f"Non autorizzato a {action} {resource_type}",
            "zh-CN": f"无权对 {resource_type} 执行 {action}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def admin_required(language: SupportedLanguage = "fr") -> str:
        """Authorization error - admin privileges required."""
        messages = {
            "fr": "Privilèges administrateur requis",
            "en": "Admin privileges required",
            "es": "Se requieren privilegios de administrador",
            "de": "Administratorrechte erforderlich",
            "it": "Privilegi di amministratore richiesti",
            "zh-CN": "需要管理员权限",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def user_inactive(language: SupportedLanguage = "fr") -> str:
        """Authorization error - user account is inactive."""
        messages = {
            "fr": "Le compte utilisateur est inactif",
            "en": "User account is inactive",
            "es": "La cuenta de usuario está inactiva",
            "de": "Benutzerkonto ist inaktiv",
            "it": "L'account utente è inattivo",
            "zh-CN": "用户帐户处于非活动状态",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_verification_required(language: SupportedLanguage = "fr") -> str:
        """Authorization error - email verification required."""
        messages = {
            "fr": "Vérification de l'email requise",
            "en": "Email verification required",
            "es": "Se requiere verificación del correo electrónico",
            "de": "E-Mail-Verifizierung erforderlich",
            "it": "Verifica email richiesta",
            "zh-CN": "需要电子邮件验证",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def user_id_mismatch(language: SupportedLanguage = "fr") -> str:
        """Authorization error - user_id mismatch."""
        messages = {
            "fr": "Identifiant utilisateur non concordant",
            "en": "User ID mismatch",
            "es": "Discrepancia en el ID de usuario",
            "de": "Benutzer-ID stimmt nicht überein",
            "it": "ID utente non corrispondente",
            "zh-CN": "用户ID不匹配",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # RESOURCE OPERATIONS (CRUD)
    # =========================================================================

    @staticmethod
    def resource_not_found(resource_type: str, language: SupportedLanguage = "fr") -> str:
        """Resource not found (404)."""
        # Capitalize first letter for display
        resource_display = resource_type.capitalize()
        messages = {
            "fr": f"{resource_display} introuvable",
            "en": f"{resource_display} not found",
            "es": f"{resource_display} no encontrado",
            "de": f"{resource_display} nicht gefunden",
            "it": f"{resource_display} non trovato",
            "zh-CN": f"未找到{resource_display}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def resource_already_exists(resource_type: str, language: SupportedLanguage = "fr") -> str:
        """Resource conflict - already exists (409)."""
        resource_display = resource_type.capitalize()
        messages = {
            "fr": f"{resource_display} existe déjà",
            "en": f"{resource_display} already exists",
            "es": f"{resource_display} ya existe",
            "de": f"{resource_display} existiert bereits",
            "it": f"{resource_display} esiste già",
            "zh-CN": f"{resource_display}已存在",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_already_registered(language: SupportedLanguage = "fr") -> str:
        """Resource conflict - email already registered."""
        messages = {
            "fr": "Cet email est déjà enregistré",
            "en": "Email already registered",
            "es": "El correo electrónico ya está registrado",
            "de": "E-Mail bereits registriert",
            "it": "Email già registrata",
            "zh-CN": "电子邮件已注册",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # SUCCESS MESSAGES - AUTH
    # =========================================================================

    @staticmethod
    def registration_successful(language: SupportedLanguage = "fr") -> str:
        """Success - registration completed."""
        messages = {
            "fr": "Inscription réussie",
            "en": "Registration successful",
            "es": "Registro exitoso",
            "de": "Registrierung erfolgreich",
            "it": "Registrazione completata",
            "zh-CN": "注册成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def login_successful(language: SupportedLanguage = "fr") -> str:
        """Success - login completed."""
        messages = {
            "fr": "Connexion réussie",
            "en": "Login successful",
            "es": "Inicio de sesión exitoso",
            "de": "Anmeldung erfolgreich",
            "it": "Accesso riuscito",
            "zh-CN": "登录成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def logout_successful(language: SupportedLanguage = "fr") -> str:
        """Success - logout completed."""
        messages = {
            "fr": "Déconnexion réussie",
            "en": "Successfully logged out",
            "es": "Sesión cerrada exitosamente",
            "de": "Erfolgreich abgemeldet",
            "it": "Disconnessione riuscita",
            "zh-CN": "成功退出",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def logout_all_successful(language: SupportedLanguage = "fr") -> str:
        """Success - logout from all devices completed."""
        messages = {
            "fr": "Déconnexion de tous les appareils réussie",
            "en": "Successfully logged out from all devices",
            "es": "Sesión cerrada exitosamente en todos los dispositivos",
            "de": "Erfolgreich von allen Geräten abgemeldet",
            "it": "Disconnessione da tutti i dispositivi riuscita",
            "zh-CN": "已成功从所有设备退出",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def password_reset_sent(language: SupportedLanguage = "fr") -> str:
        """Success - password reset email sent (generic for security)."""
        messages = {
            "fr": "Si l'email existe, un lien de réinitialisation a été envoyé",
            "en": "If the email exists, a password reset link has been sent",
            "es": "Si el correo existe, se ha enviado un enlace de restablecimiento",
            "de": "Falls die E-Mail existiert, wurde ein Link zum Zurücksetzen gesendet",
            "it": "Se l'email esiste, è stato inviato un link per reimpostare la password",
            "zh-CN": "如果该电子邮件存在，已发送密码重置链接",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # SUCCESS MESSAGES - PREFERENCES
    # =========================================================================

    @staticmethod
    def memory_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - memory preference updated."""
        if enabled:
            messages = {
                "fr": "Préférence mémoire mise à jour",
                "en": "Memory preference updated",
                "es": "Preferencia de memoria actualizada",
                "de": "Speichereinstellung aktualisiert",
                "it": "Preferenza memoria aggiornata",
                "zh-CN": "记忆偏好已更新",
            }
        else:
            messages = {
                "fr": "Mémoire désactivée",
                "en": "Memory disabled",
                "es": "Memoria desactivada",
                "de": "Speicher deaktiviert",
                "it": "Memoria disattivata",
                "zh-CN": "记忆已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def voice_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - voice preference updated."""
        if enabled:
            messages = {
                "fr": "Préférence vocale mise à jour",
                "en": "Voice preference updated",
                "es": "Preferencia de voz actualizada",
                "de": "Spracheinstellung aktualisiert",
                "it": "Preferenza vocale aggiornata",
                "zh-CN": "语音偏好已更新",
            }
        else:
            messages = {
                "fr": "Voix désactivée",
                "en": "Voice disabled",
                "es": "Voz desactivada",
                "de": "Sprache deaktiviert",
                "it": "Voce disattivata",
                "zh-CN": "语音已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def voice_mode_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - voice mode preference updated."""
        if enabled:
            messages = {
                "fr": "Mode vocal activé",
                "en": "Voice mode enabled",
                "es": "Modo de voz activado",
                "de": "Sprachmodus aktiviert",
                "it": "Modalità vocale attivata",
                "zh-CN": "语音模式已启用",
            }
        else:
            messages = {
                "fr": "Mode vocal désactivé",
                "en": "Voice mode disabled",
                "es": "Modo de voz desactivado",
                "de": "Sprachmodus deaktiviert",
                "it": "Modalità vocale disattivata",
                "zh-CN": "语音模式已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def tokens_display_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - tokens display preference updated."""
        if enabled:
            messages = {
                "fr": "Affichage des tokens activé",
                "en": "Tokens display enabled",
                "es": "Visualización de tokens activada",
                "de": "Token-Anzeige aktiviert",
                "it": "Visualizzazione token attivata",
                "zh-CN": "令牌显示已启用",
            }
        else:
            messages = {
                "fr": "Affichage des tokens désactivé",
                "en": "Tokens display disabled",
                "es": "Visualización de tokens desactivada",
                "de": "Token-Anzeige deaktiviert",
                "it": "Visualizzazione token disattivata",
                "zh-CN": "令牌显示已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def debug_panel_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - debug panel preference updated."""
        if enabled:
            messages = {
                "fr": "Panneau de debug activé",
                "en": "Debug panel enabled",
                "es": "Panel de depuración activado",
                "de": "Debug-Panel aktiviert",
                "it": "Pannello di debug attivato",
                "zh-CN": "调试面板已启用",
            }
        else:
            messages = {
                "fr": "Panneau de debug désactivé",
                "en": "Debug panel disabled",
                "es": "Panel de depuración desactivado",
                "de": "Debug-Panel deaktiviert",
                "it": "Pannello di debug disattivato",
                "zh-CN": "调试面板已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def sub_agents_preference_updated(enabled: bool, language: SupportedLanguage = "fr") -> str:
        """Success - sub-agents delegation preference updated."""
        if enabled:
            messages = {
                "fr": "Délégation aux sous-agents activée",
                "en": "Sub-agents delegation enabled",
                "es": "Delegación a sub-agentes activada",
                "de": "Sub-Agenten-Delegierung aktiviert",
                "it": "Delegazione ai sub-agenti attivata",
                "zh-CN": "子代理委派已启用",
            }
        else:
            messages = {
                "fr": "Délégation aux sous-agents désactivée",
                "en": "Sub-agents delegation disabled",
                "es": "Delegación a sub-agentes desactivada",
                "de": "Sub-Agenten-Delegierung deaktiviert",
                "it": "Delegazione ai sub-agenti disattivata",
                "zh-CN": "子代理委派已禁用",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def display_mode_preference_updated(mode: str, language: SupportedLanguage = "fr") -> str:
        """Success - response display mode preference updated."""
        mode_labels = {
            "cards": {
                "fr": "Mode d'affichage : Cartes HTML",
                "en": "Display mode: HTML Cards",
                "es": "Modo de visualización: Tarjetas HTML",
                "de": "Anzeigemodus: HTML-Karten",
                "it": "Modalità di visualizzazione: Schede HTML",
                "zh-CN": "显示模式：HTML卡片",
            },
            "html": {
                "fr": "Mode d'affichage : HTML enrichi",
                "en": "Display mode: Rich HTML",
                "es": "Modo de visualización: HTML enriquecido",
                "de": "Anzeigemodus: Rich-HTML",
                "it": "Modalità di visualizzazione: HTML arricchito",
                "zh-CN": "显示模式：富HTML",
            },
            "markdown": {
                "fr": "Mode d'affichage : Markdown",
                "en": "Display mode: Markdown",
                "es": "Modo de visualización: Markdown",
                "de": "Anzeigemodus: Markdown",
                "it": "Modalità di visualizzazione: Markdown",
                "zh-CN": "显示模式：Markdown",
            },
        }
        messages = mode_labels.get(mode, mode_labels["cards"])
        return messages.get(language, messages["en"])

    @staticmethod
    def onboarding_preference_updated(language: SupportedLanguage = "fr") -> str:
        """Success - onboarding preference updated."""
        messages = {
            "fr": "Tutoriel d'accueil marqué comme terminé",
            "en": "Onboarding tutorial marked as completed",
            "es": "Tutorial de bienvenida marcado como completado",
            "de": "Einführungs-Tutorial als abgeschlossen markiert",
            "it": "Tutorial di benvenuto contrassegnato come completato",
            "zh-CN": "入门教程已标记为完成",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def preferences_updated(language: SupportedLanguage = "fr") -> str:
        """Success - preferences updated."""
        messages = {
            "fr": "Préférences mises à jour avec succès",
            "en": "Preferences updated successfully",
            "es": "Preferencias actualizadas exitosamente",
            "de": "Einstellungen erfolgreich aktualisiert",
            "it": "Preferenze aggiornate con successo",
            "zh-CN": "首选项更新成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def weather_location_preference_updated(
        enabled: bool, language: SupportedLanguage = "fr"
    ) -> str:
        """Success - weather location preference updated."""
        if enabled:
            messages = {
                "fr": "Localisation actuelle activée pour les alertes météo",
                "en": "Current location enabled for weather alerts",
                "es": "Ubicación actual habilitada para alertas meteorológicas",
                "de": "Aktueller Standort für Wetterwarnungen aktiviert",
                "it": "Posizione attuale abilitata per gli avvisi meteo",
                "zh-CN": "已启用当前位置用于天气提醒",
            }
        else:
            messages = {
                "fr": "Localisation actuelle désactivée, position effacée",
                "en": "Current location disabled, stored position cleared",
                "es": "Ubicación actual deshabilitada, posición borrada",
                "de": "Aktueller Standort deaktiviert, gespeicherte Position gelöscht",
                "it": "Posizione attuale disattivata, posizione memorizzata cancellata",
                "zh-CN": "当前位置已禁用,已清除存储的位置",
            }
        return messages.get(language, messages["en"])

    # =========================================================================
    # CONVERSATIONS
    # =========================================================================

    @staticmethod
    def no_active_conversation(language: SupportedLanguage = "fr") -> str:
        """Error - no active conversation found."""
        messages = {
            "fr": "Aucune conversation active trouvée",
            "en": "No active conversation found",
            "es": "No se encontró ninguna conversación activa",
            "de": "Keine aktive Konversation gefunden",
            "it": "Nessuna conversazione attiva trovata",
            "zh-CN": "未找到活动对话",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_active_conversation_start_chatting(language: SupportedLanguage = "fr") -> str:
        """Error - no active conversation, invite to start chatting."""
        messages = {
            "fr": "Aucune conversation active trouvée. Commencez à discuter pour en créer une.",
            "en": "No active conversation found. Start chatting to create one.",
            "es": "No se encontró ninguna conversación activa. Empieza a chatear para crear una.",
            "de": "Keine aktive Konversation gefunden. Starten Sie einen Chat, um eine zu erstellen.",
            "it": "Nessuna conversazione attiva trovata. Inizia a chattare per crearne una.",
            "zh-CN": "未找到活动对话。开始聊天以创建一个。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_active_conversation_to_reset(language: SupportedLanguage = "fr") -> str:
        """Error - no active conversation to reset."""
        messages = {
            "fr": "Aucune conversation active à réinitialiser",
            "en": "No active conversation to reset",
            "es": "No hay conversación activa para restablecer",
            "de": "Keine aktive Konversation zum Zurücksetzen",
            "it": "Nessuna conversazione attiva da reimpostare",
            "zh-CN": "没有可重置的活动对话",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def conversation_reset_successful(language: SupportedLanguage = "fr") -> str:
        """Success - conversation reset."""
        messages = {
            "fr": "Conversation réinitialisée avec succès",
            "en": "Conversation reset successfully",
            "es": "Conversación restablecida exitosamente",
            "de": "Konversation erfolgreich zurückgesetzt",
            "it": "Conversazione reimpostata con successo",
            "zh-CN": "对话重置成功",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # MEMORIES
    # =========================================================================

    @staticmethod
    def memory_not_found(memory_id: str, language: SupportedLanguage = "fr") -> str:
        """Error - memory not found."""
        messages = {
            "fr": f"Mémoire '{memory_id}' introuvable",
            "en": f"Memory '{memory_id}' not found",
            "es": f"Memoria '{memory_id}' no encontrada",
            "de": f"Erinnerung '{memory_id}' nicht gefunden",
            "it": f"Memoria '{memory_id}' non trovata",
            "zh-CN": f"未找到记忆 '{memory_id}'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_retrieve_memories(language: SupportedLanguage = "fr") -> str:
        """Error - failed to retrieve memories."""
        messages = {
            "fr": "Échec de la récupération des mémoires",
            "en": "Failed to retrieve memories",
            "es": "Error al recuperar memorias",
            "de": "Erinnerungen konnten nicht abgerufen werden",
            "it": "Impossibile recuperare le memorie",
            "zh-CN": "检索记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_retrieve_memory(language: SupportedLanguage = "fr") -> str:
        """Error - failed to retrieve memory."""
        messages = {
            "fr": "Échec de la récupération de la mémoire",
            "en": "Failed to retrieve memory",
            "es": "Error al recuperar la memoria",
            "de": "Erinnerung konnte nicht abgerufen werden",
            "it": "Impossibile recuperare la memoria",
            "zh-CN": "检索记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_create_memory(language: SupportedLanguage = "fr") -> str:
        """Error - failed to create memory."""
        messages = {
            "fr": "Échec de la création de la mémoire",
            "en": "Failed to create memory",
            "es": "Error al crear la memoria",
            "de": "Erinnerung konnte nicht erstellt werden",
            "it": "Impossibile creare la memoria",
            "zh-CN": "创建记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_update_memory(language: SupportedLanguage = "fr") -> str:
        """Error - failed to update memory."""
        messages = {
            "fr": "Échec de la mise à jour de la mémoire",
            "en": "Failed to update memory",
            "es": "Error al actualizar la memoria",
            "de": "Erinnerung konnte nicht aktualisiert werden",
            "it": "Impossibile aggiornare la memoria",
            "zh-CN": "更新记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_toggle_pin(language: SupportedLanguage = "fr") -> str:
        """Error - failed to toggle memory pin state."""
        messages = {
            "fr": "Échec du changement d'état d'épinglage de la mémoire",
            "en": "Failed to toggle memory pin state",
            "es": "Error al cambiar el estado de anclaje de la memoria",
            "de": "Anheftstatus der Erinnerung konnte nicht geändert werden",
            "it": "Impossibile cambiare lo stato di blocco della memoria",
            "zh-CN": "切换记忆固定状态失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_delete_memory(language: SupportedLanguage = "fr") -> str:
        """Error - failed to delete memory."""
        messages = {
            "fr": "Échec de la suppression de la mémoire",
            "en": "Failed to delete memory",
            "es": "Error al eliminar la memoria",
            "de": "Erinnerung konnte nicht gelöscht werden",
            "it": "Impossibile eliminare la memoria",
            "zh-CN": "删除记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_delete_all_memories(language: SupportedLanguage = "fr") -> str:
        """Error - failed to delete all memories."""
        messages = {
            "fr": "Échec de la suppression de toutes les mémoires",
            "en": "Failed to delete all memories",
            "es": "Error al eliminar todas las memorias",
            "de": "Alle Erinnerungen konnten nicht gelöscht werden",
            "it": "Impossibile eliminare tutte le memorie",
            "zh-CN": "删除所有记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_export_memories(language: SupportedLanguage = "fr") -> str:
        """Error - failed to export memories."""
        messages = {
            "fr": "Échec de l'exportation des mémoires",
            "en": "Failed to export memories",
            "es": "Error al exportar memorias",
            "de": "Erinnerungen konnten nicht exportiert werden",
            "it": "Impossibile esportare le memorie",
            "zh-CN": "导出记忆失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def memories_deleted_successfully(
        deleted_count: int,
        preserved_count: int = 0,
        language: SupportedLanguage = "fr",
    ) -> str:
        """Success - memories deleted."""
        base_messages = {
            "fr": f"{deleted_count} mémoire(s) supprimée(s) avec succès",
            "en": f"Successfully deleted {deleted_count} memories",
            "es": f"{deleted_count} memoria(s) eliminada(s) exitosamente",
            "de": f"{deleted_count} Erinnerung(en) erfolgreich gelöscht",
            "it": f"{deleted_count} memoria/e eliminata/e con successo",
            "zh-CN": f"成功删除 {deleted_count} 条记忆",
        }

        message = base_messages.get(language, base_messages["en"])

        if preserved_count > 0:
            preserved_suffix = {
                "fr": f" ({preserved_count} mémoire(s) épinglée(s) conservée(s))",
                "en": f" ({preserved_count} pinned memories preserved)",
                "es": f" ({preserved_count} memoria(s) anclada(s) conservada(s))",
                "de": f" ({preserved_count} angeheftete Erinnerung(en) erhalten)",
                "it": f" ({preserved_count} memoria/e bloccata/e conservata/e)",
                "zh-CN": f"（{preserved_count} 条已固定的记忆已保留）",
            }
            message += preserved_suffix.get(language, preserved_suffix["en"])

        return message

    # =========================================================================
    # INTERESTS
    # =========================================================================

    @staticmethod
    def interest_not_found(interest_id: str, language: SupportedLanguage = "fr") -> str:
        """Error - interest not found."""
        messages = {
            "fr": f"Centre d'intérêt '{interest_id}' introuvable",
            "en": f"Interest '{interest_id}' not found",
            "es": f"Interés '{interest_id}' no encontrado",
            "de": f"Interesse '{interest_id}' nicht gefunden",
            "it": f"Interesse '{interest_id}' non trovato",
            "zh-CN": f"未找到兴趣 '{interest_id}'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def interest_already_exists(language: SupportedLanguage = "fr") -> str:
        """Error - interest already exists for user."""
        messages = {
            "fr": "Un centre d'intérêt avec ce sujet existe déjà",
            "en": "Interest with this topic already exists",
            "es": "Ya existe un interés con este tema",
            "de": "Ein Interesse mit diesem Thema existiert bereits",
            "it": "Esiste già un interesse con questo argomento",
            "zh-CN": "具有此主题的兴趣已存在",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_retrieve_interests(language: SupportedLanguage = "fr") -> str:
        """Error - failed to retrieve interests."""
        messages = {
            "fr": "Échec de la récupération des centres d'intérêt",
            "en": "Failed to retrieve interests",
            "es": "Error al recuperar los intereses",
            "de": "Interessen konnten nicht abgerufen werden",
            "it": "Impossibile recuperare gli interessi",
            "zh-CN": "检索兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_create_interest(language: SupportedLanguage = "fr") -> str:
        """Error - failed to create interest."""
        messages = {
            "fr": "Échec de la création du centre d'intérêt",
            "en": "Failed to create interest",
            "es": "Error al crear el interés",
            "de": "Interesse konnte nicht erstellt werden",
            "it": "Impossibile creare l'interesse",
            "zh-CN": "创建兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_delete_interest(language: SupportedLanguage = "fr") -> str:
        """Error - failed to delete interest."""
        messages = {
            "fr": "Échec de la suppression du centre d'intérêt",
            "en": "Failed to delete interest",
            "es": "Error al eliminar el interés",
            "de": "Interesse konnte nicht gelöscht werden",
            "it": "Impossibile eliminare l'interesse",
            "zh-CN": "删除兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_update_interest(language: SupportedLanguage = "fr") -> str:
        """Error - failed to update interest."""
        messages = {
            "fr": "Échec de la mise à jour du centre d'intérêt",
            "en": "Failed to update interest",
            "es": "Error al actualizar el interés",
            "de": "Interesse konnte nicht aktualisiert werden",
            "it": "Impossibile aggiornare l'interesse",
            "zh-CN": "更新兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_delete_all_interests(language: SupportedLanguage = "fr") -> str:
        """Error - failed to delete all interests."""
        messages = {
            "fr": "Échec de la suppression de tous les centres d'intérêt",
            "en": "Failed to delete all interests",
            "es": "Error al eliminar todos los intereses",
            "de": "Alle Interessen konnten nicht gelöscht werden",
            "it": "Impossibile eliminare tutti gli interessi",
            "zh-CN": "删除所有兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_export_interests(language: SupportedLanguage = "fr") -> str:
        """Error - failed to export interests."""
        messages = {
            "fr": "Échec de l'exportation des centres d'intérêt",
            "en": "Failed to export interests",
            "es": "Error al exportar los intereses",
            "de": "Interessen konnten nicht exportiert werden",
            "it": "Impossibile esportare gli interessi",
            "zh-CN": "导出兴趣失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def interest_already_exists_in_category(language: SupportedLanguage = "fr") -> str:
        """Error - interest already exists in this category."""
        messages = {
            "fr": "Un centre d'intérêt avec ce sujet existe déjà dans cette catégorie",
            "en": "An interest with this topic already exists in this category",
            "es": "Ya existe un interés con este tema en esta categoría",
            "de": "Ein Interesse mit diesem Thema existiert bereits in dieser Kategorie",
            "it": "Esiste già un interesse con questo argomento in questa categoria",
            "zh-CN": "此类别中已存在具有此主题的兴趣",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_submit_feedback(language: SupportedLanguage = "fr") -> str:
        """Error - failed to submit feedback."""
        messages = {
            "fr": "Échec de l'envoi du feedback",
            "en": "Failed to submit feedback",
            "es": "Error al enviar el feedback",
            "de": "Feedback konnte nicht gesendet werden",
            "it": "Impossibile inviare il feedback",
            "zh-CN": "提交反馈失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_update_settings(language: SupportedLanguage = "fr") -> str:
        """Error - failed to update interest settings."""
        messages = {
            "fr": "Échec de la mise à jour des paramètres",
            "en": "Failed to update settings",
            "es": "Error al actualizar la configuración",
            "de": "Einstellungen konnten nicht aktualisiert werden",
            "it": "Impossibile aggiornare le impostazioni",
            "zh-CN": "更新设置失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def interest_deleted_successfully(language: SupportedLanguage = "fr") -> str:
        """Success - interest deleted."""
        messages = {
            "fr": "Centre d'intérêt supprimé avec succès",
            "en": "Interest deleted successfully",
            "es": "Interés eliminado exitosamente",
            "de": "Interesse erfolgreich gelöscht",
            "it": "Interesse eliminato con successo",
            "zh-CN": "兴趣删除成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def feedback_submitted_successfully(language: SupportedLanguage = "fr") -> str:
        """Success - feedback submitted."""
        messages = {
            "fr": "Feedback enregistré avec succès",
            "en": "Feedback submitted successfully",
            "es": "Feedback enviado exitosamente",
            "de": "Feedback erfolgreich gesendet",
            "it": "Feedback inviato con successo",
            "zh-CN": "反馈提交成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def settings_updated_successfully(language: SupportedLanguage = "fr") -> str:
        """Success - settings updated."""
        messages = {
            "fr": "Paramètres mis à jour avec succès",
            "en": "Settings updated successfully",
            "es": "Configuración actualizada exitosamente",
            "de": "Einstellungen erfolgreich aktualisiert",
            "it": "Impostazioni aggiornate con successo",
            "zh-CN": "设置更新成功",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # CONNECTORS
    # =========================================================================

    @staticmethod
    def connector_not_found(language: SupportedLanguage = "fr") -> str:
        """Error - connector not found."""
        messages = {
            "fr": "Connecteur introuvable",
            "en": "Connector not found",
            "es": "Conector no encontrado",
            "de": "Connector nicht gefunden",
            "it": "Connettore non trovato",
            "zh-CN": "未找到连接器",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def connector_type_no_preferences(
        connector_type: str, language: SupportedLanguage = "fr"
    ) -> str:
        """Error - connector type does not support preferences."""
        messages = {
            "fr": f"Le type de connecteur '{connector_type}' ne supporte pas les préférences",
            "en": f"Connector type '{connector_type}' does not support preferences",
            "es": f"El tipo de conector '{connector_type}' no soporta preferencias",
            "de": f"Connector-Typ '{connector_type}' unterstützt keine Einstellungen",
            "it": f"Il tipo di connettore '{connector_type}' non supporta le preferenze",
            "zh-CN": f"连接器类型 '{connector_type}' 不支持首选项",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def connector_already_exists(connector_type: str, language: SupportedLanguage = "fr") -> str:
        """Error - connector already exists for user."""
        messages = {
            "fr": f"Le connecteur {connector_type} existe déjà",
            "en": f"{connector_type.capitalize()} connector already exists",
            "es": f"El conector {connector_type} ya existe",
            "de": f"{connector_type.capitalize()}-Connector existiert bereits",
            "it": f"Il connettore {connector_type} esiste già",
            "zh-CN": f"{connector_type} 连接器已存在",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # EXTERNAL SERVICES
    # =========================================================================

    @staticmethod
    def service_unavailable(service_name: str, language: SupportedLanguage = "fr") -> str:
        """Error - external service unavailable."""
        messages = {
            "fr": f"Service {service_name} indisponible",
            "en": f"{service_name} service unavailable",
            "es": f"Servicio {service_name} no disponible",
            "de": f"{service_name}-Service nicht verfügbar",
            "it": f"Servizio {service_name} non disponibile",
            "zh-CN": f"{service_name} 服务不可用",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def google_api_key_not_configured(language: SupportedLanguage = "fr") -> str:
        """Error - Google API key not configured."""
        messages = {
            "fr": "Clé API Google non configurée",
            "en": "Google API key not configured",
            "es": "Clave de API de Google no configurada",
            "de": "Google API-Schlüssel nicht konfiguriert",
            "it": "Chiave API Google non configurata",
            "zh-CN": "未配置 Google API 密钥",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def google_places_not_configured(language: SupportedLanguage = "fr") -> str:
        """Error - Google Places connector not configured."""
        messages = {
            "fr": "Connecteur Google Places non configuré",
            "en": "Google Places connector not configured",
            "es": "Conector de Google Places no configurado",
            "de": "Google Places Connector nicht konfiguriert",
            "it": "Connettore Google Places non configurato",
            "zh-CN": "Google Places 连接器未配置",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def google_places_token_not_available(language: SupportedLanguage = "fr") -> str:
        """Error - Google Places OAuth token not available."""
        messages = {
            "fr": "Token OAuth Google Places non disponible",
            "en": "Google Places OAuth token not available",
            "es": "Token OAuth de Google Places no disponible",
            "de": "Google Places OAuth-Token nicht verfügbar",
            "it": "Token OAuth Google Places non disponibile",
            "zh-CN": "Google Places OAuth 令牌不可用",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_fetch_thumbnail(language: SupportedLanguage = "fr") -> str:
        """Error - failed to fetch thumbnail."""
        messages = {
            "fr": "Échec de la récupération de la miniature",
            "en": "Failed to fetch thumbnail",
            "es": "Error al obtener la miniatura",
            "de": "Miniaturansicht konnte nicht abgerufen werden",
            "it": "Impossibile recuperare la miniatura",
            "zh-CN": "获取缩略图失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_fetch_photo(language: SupportedLanguage = "fr") -> str:
        """Error - failed to fetch photo."""
        messages = {
            "fr": "Échec de la récupération de la photo",
            "en": "Failed to fetch photo",
            "es": "Error al obtener la foto",
            "de": "Foto konnte nicht abgerufen werden",
            "it": "Impossibile recuperare la foto",
            "zh-CN": "获取照片失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_connect_google_drive(language: SupportedLanguage = "fr") -> str:
        """Error - failed to connect to Google Drive."""
        messages = {
            "fr": "Échec de la connexion à Google Drive",
            "en": "Failed to connect to Google Drive",
            "es": "Error al conectar con Google Drive",
            "de": "Verbindung zu Google Drive fehlgeschlagen",
            "it": "Impossibile connettersi a Google Drive",
            "zh-CN": "连接 Google Drive 失败",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def failed_to_connect_google_places(language: SupportedLanguage = "fr") -> str:
        """Error - failed to connect to Google Places API."""
        messages = {
            "fr": "Échec de la connexion à l'API Google Places",
            "en": "Failed to connect to Google Places API",
            "es": "Error al conectar con la API de Google Places",
            "de": "Verbindung zur Google Places API fehlgeschlagen",
            "it": "Impossibile connettersi all'API Google Places",
            "zh-CN": "连接 Google Places API 失败",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # OAUTH
    # =========================================================================

    @staticmethod
    def oauth_state_mismatch(language: SupportedLanguage = "fr") -> str:
        """Validation error - OAuth state mismatch (CSRF protection)."""
        messages = {
            "fr": "État OAuth non concordant",
            "en": "OAuth state mismatch",
            "es": "Discrepancia en el estado OAuth",
            "de": "OAuth-Status stimmt nicht überein",
            "it": "Stato OAuth non corrispondente",
            "zh-CN": "OAuth 状态不匹配",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def oauth_flow_failed(error: str, language: SupportedLanguage = "fr") -> str:
        """Validation error - OAuth flow failed."""
        messages = {
            "fr": f"Échec du flux OAuth : {error}",
            "en": f"OAuth flow failed: {error}",
            "es": f"Flujo OAuth fallido: {error}",
            "de": f"OAuth-Ablauf fehlgeschlagen: {error}",
            "it": f"Flusso OAuth fallito: {error}",
            "zh-CN": f"OAuth 流程失败：{error}",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # LLM SERVICE
    # =========================================================================

    @staticmethod
    def llm_service_error(error: str, language: SupportedLanguage = "fr") -> str:
        """External service error - LLM service failure."""
        messages = {
            "fr": f"Erreur du service LLM : {error}",
            "en": f"LLM service error: {error}",
            "es": f"Error del servicio LLM: {error}",
            "de": f"LLM-Service-Fehler: {error}",
            "it": f"Errore servizio LLM: {error}",
            "zh-CN": f"LLM 服务错误：{error}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def invalid_sort_parameter(
        allowed_values: list[str], language: SupportedLanguage = "fr"
    ) -> str:
        """Validation error - invalid sort parameter."""
        allowed_str = ", ".join(sorted(allowed_values))
        messages = {
            "fr": f"Paramètre de tri invalide. Valeurs autorisées : {allowed_str}",
            "en": f"Invalid sort_by parameter. Allowed values: {allowed_str}",
            "es": f"Parámetro de ordenación inválido. Valores permitidos: {allowed_str}",
            "de": f"Ungültiger Sortierparameter. Erlaubte Werte: {allowed_str}",
            "it": f"Parametro di ordinamento non valido. Valori consentiti: {allowed_str}",
            "zh-CN": f"排序参数无效。允许的值：{allowed_str}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_already_exists(model_name: str, language: SupportedLanguage = "fr") -> str:
        """Conflict error - active pricing already exists for model."""
        messages = {
            "fr": f"Une tarification active existe déjà pour le modèle '{model_name}'. Utilisez PUT pour mettre à jour.",
            "en": f"Active pricing already exists for model '{model_name}'. Use PUT to update.",
            "es": f"Ya existe un precio activo para el modelo '{model_name}'. Use PUT para actualizar.",
            "de": f"Für Modell '{model_name}' existiert bereits eine aktive Preisgestaltung. Verwenden Sie PUT zum Aktualisieren.",
            "it": f"Esiste già un prezzo attivo per il modello '{model_name}'. Usa PUT per aggiornare.",
            "zh-CN": f"模型 '{model_name}' 已存在活动定价。使用 PUT 进行更新。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_not_found(model_name: str, language: SupportedLanguage = "fr") -> str:
        """Not found error - no active pricing for model."""
        messages = {
            "fr": f"Aucune tarification active trouvée pour le modèle '{model_name}'",
            "en": f"No active pricing found for model '{model_name}'",
            "es": f"No se encontró precio activo para el modelo '{model_name}'",
            "de": f"Keine aktive Preisgestaltung für Modell '{model_name}' gefunden",
            "it": f"Nessun prezzo attivo trovato per il modello '{model_name}'",
            "zh-CN": f"未找到模型 '{model_name}' 的活动定价",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_entry_not_found(pricing_id: str, language: SupportedLanguage = "fr") -> str:
        """Not found error - pricing entry not found."""
        messages = {
            "fr": f"Entrée de tarification introuvable : {pricing_id}",
            "en": f"Pricing entry not found: {pricing_id}",
            "es": f"Entrada de precio no encontrada: {pricing_id}",
            "de": f"Preiseintrag nicht gefunden: {pricing_id}",
            "it": f"Voce di prezzo non trovata: {pricing_id}",
            "zh-CN": f"未找到定价条目：{pricing_id}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_cache_not_initialized(language: SupportedLanguage = "fr") -> str:
        """Warning - pricing cache not initialized, cost estimation unavailable."""
        messages = {
            "fr": "Cache de tarification non initialisé. Estimation des coûts indisponible.",
            "en": "Pricing cache not initialized. Cost estimation unavailable.",
            "es": "Caché de precios no inicializado. Estimación de costos no disponible.",
            "de": "Preiscache nicht initialisiert. Kostenschätzung nicht verfügbar.",
            "it": "Cache prezzi non inizializzata. Stima costi non disponibile.",
            "zh-CN": "定价缓存未初始化。成本估算不可用。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_cache_model_not_found(model: str, language: SupportedLanguage = "fr") -> str:
        """Warning - model not found in pricing cache."""
        messages = {
            "fr": f"Modèle '{model}' non trouvé dans le cache de tarification.",
            "en": f"Model '{model}' not found in pricing cache.",
            "es": f"Modelo '{model}' no encontrado en el caché de precios.",
            "de": f"Modell '{model}' nicht im Preiscache gefunden.",
            "it": f"Modello '{model}' non trovato nella cache prezzi.",
            "zh-CN": f"在定价缓存中未找到模型 '{model}'。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def pricing_cache_refresh_failed(error: str, language: SupportedLanguage = "fr") -> str:
        """Error - pricing cache refresh failed."""
        messages = {
            "fr": f"Échec de l'actualisation du cache de tarification : {error}",
            "en": f"Pricing cache refresh failed: {error}",
            "es": f"Error al actualizar el caché de precios: {error}",
            "de": f"Aktualisierung des Preiscaches fehlgeschlagen: {error}",
            "it": f"Aggiornamento cache prezzi fallito: {error}",
            "zh-CN": f"定价缓存刷新失败：{error}",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    @staticmethod
    def hitl_rate_limit_exceeded(language: SupportedLanguage = "fr") -> str:
        """Rate limit error - too many HITL responses."""
        messages = {
            "fr": "Trop de réponses en peu de temps. Réessayez dans quelques secondes.",
            "en": "Too many responses in a short time. Please try again in a few seconds.",
            "es": "Demasiadas respuestas en poco tiempo. Inténtelo de nuevo en unos segundos.",
            "de": "Zu viele Antworten in kurzer Zeit. Bitte versuchen Sie es in einigen Sekunden erneut.",
            "it": "Troppe risposte in poco tempo. Riprova tra qualche secondo.",
            "zh-CN": "短时间内响应过多。请稍后再试。",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # GENERIC ERRORS
    # =========================================================================

    @staticmethod
    def internal_error(error_type: str, language: SupportedLanguage = "fr") -> str:
        """Generic internal error with type info."""
        messages = {
            "fr": f"Erreur interne : {error_type}",
            "en": f"Internal error: {error_type}",
            "es": f"Error interno: {error_type}",
            "de": f"Interner Fehler: {error_type}",
            "it": f"Errore interno: {error_type}",
            "zh-CN": f"内部错误：{error_type}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def google_api_error(language: SupportedLanguage = "fr") -> str:
        """Generic Google API error."""
        messages = {
            "fr": "Erreur de l'API Google",
            "en": "Google API error",
            "es": "Error de la API de Google",
            "de": "Google API-Fehler",
            "it": "Errore API Google",
            "zh-CN": "Google API 错误",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # EMAIL TOOL VALIDATION
    # =========================================================================

    @staticmethod
    def email_field_required(field: str, language: SupportedLanguage = "fr") -> str:
        """Email validation - required field missing."""
        messages = {
            "fr": f"Le champ '{field}' est obligatoire",
            "en": f"Field '{field}' is required",
            "es": f"El campo '{field}' es obligatorio",
            "de": f"Das Feld '{field}' ist erforderlich",
            "it": f"Il campo '{field}' è obbligatorio",
            "zh-CN": f"字段 '{field}' 是必填项",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_fields_required(fields: list[str], language: SupportedLanguage = "fr") -> str:
        """Email validation - multiple required fields missing."""
        fields_str = ", ".join(f"'{f}'" for f in fields)
        messages = {
            "fr": f"Les champs {fields_str} sont obligatoires",
            "en": f"Fields {fields_str} are required",
            "es": f"Los campos {fields_str} son obligatorios",
            "de": f"Die Felder {fields_str} sind erforderlich",
            "it": f"I campi {fields_str} sono obbligatori",
            "zh-CN": f"字段 {fields_str} 是必填项",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_invalid_format(email: str, language: SupportedLanguage = "fr") -> str:
        """Email validation - invalid email format."""
        messages = {
            "fr": f"Format d'adresse email invalide: '{email}'. L'adresse doit contenir un domaine complet (ex: user@example.com)",
            "en": f"Invalid email format: '{email}'. Address must include a complete domain (e.g., user@example.com)",
            "es": f"Formato de correo electrónico inválido: '{email}'. La dirección debe incluir un dominio completo (ej: user@example.com)",
            "de": f"Ungültiges E-Mail-Format: '{email}'. Die Adresse muss eine vollständige Domain enthalten (z.B. user@example.com)",
            "it": f"Formato email non valido: '{email}'. L'indirizzo deve includere un dominio completo (es: user@example.com)",
            "zh-CN": f"无效的邮件格式: '{email}'。地址必须包含完整域名（例如：user@example.com）",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def content_generation_failed(
        error: str | None = None, language: SupportedLanguage = "fr"
    ) -> str:
        """Email tool - LLM content generation failed."""
        if error:
            messages = {
                "fr": f"Échec de la génération du contenu: {error}",
                "en": f"Content generation failed: {error}",
                "es": f"Error al generar el contenido: {error}",
                "de": f"Inhaltsgenerierung fehlgeschlagen: {error}",
                "it": f"Generazione contenuto fallita: {error}",
                "zh-CN": f"内容生成失败: {error}",
            }
        else:
            messages = {
                "fr": "Échec de la génération du contenu",
                "en": "Content generation failed",
                "es": "Error al generar el contenido",
                "de": "Inhaltsgenerierung fehlgeschlagen",
                "it": "Generazione contenuto fallita",
                "zh-CN": "内容生成失败",
            }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_content_missing(language: SupportedLanguage = "fr") -> str:
        """Email tool - subject and body required."""
        messages = {
            "fr": "Subject et body requis (directement ou via content_instruction)",
            "en": "Subject and body required (directly or via content_instruction)",
            "es": "Se requieren asunto y cuerpo (directamente o mediante content_instruction)",
            "de": "Betreff und Text erforderlich (direkt oder über content_instruction)",
            "it": "Oggetto e corpo richiesti (direttamente o tramite content_instruction)",
            "zh-CN": "需要主题和正文（直接提供或通过 content_instruction）",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # DRAFT ACTIONS (HITL confirmation/cancellation)
    # =========================================================================

    @staticmethod
    def draft_action_completed(language: SupportedLanguage = "fr") -> str:
        """Draft action - generic completion message."""
        messages = {
            "fr": "Action effectuée.",
            "en": "Action completed.",
            "es": "Acción completada.",
            "de": "Aktion abgeschlossen.",
            "it": "Azione completata.",
            "zh-CN": "操作已完成。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def draft_cancelled(language: SupportedLanguage = "fr") -> str:
        """Draft action - cancelled by user."""
        messages = {
            "fr": "OK, c'est annulé.",
            "en": "OK, cancelled.",
            "es": "OK, cancelado.",
            "de": "OK, abgebrochen.",
            "it": "OK, annullato.",
            "zh-CN": "好的，已取消。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_sent_successfully(to: str, language: SupportedLanguage = "fr") -> str:
        """Success - email sent."""
        messages = {
            "fr": f"Email envoyé avec succès à {to}",
            "en": f"Email successfully sent to {to}",
            "es": f"Email enviado exitosamente a {to}",
            "de": f"E-Mail erfolgreich an {to} gesendet",
            "it": f"Email inviata con successo a {to}",
            "zh-CN": f"邮件已成功发送至 {to}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reply_sent_successfully(language: SupportedLanguage = "fr") -> str:
        """Success - reply sent."""
        messages = {
            "fr": "Réponse envoyée avec succès",
            "en": "Reply sent successfully",
            "es": "Respuesta enviada exitosamente",
            "de": "Antwort erfolgreich gesendet",
            "it": "Risposta inviata con successo",
            "zh-CN": "回复已成功发送",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_forwarded_successfully(to: str, language: SupportedLanguage = "fr") -> str:
        """Success - email forwarded."""
        messages = {
            "fr": f"Email transféré avec succès à {to}",
            "en": f"Email successfully forwarded to {to}",
            "es": f"Email reenviado exitosamente a {to}",
            "de": f"E-Mail erfolgreich an {to} weitergeleitet",
            "it": f"Email inoltrata con successo a {to}",
            "zh-CN": f"邮件已成功转发至 {to}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_moved_to_trash(subject: str | None = None, language: SupportedLanguage = "fr") -> str:
        """Success - email moved to trash."""
        if subject:
            messages = {
                "fr": f"Email '{subject}' déplacé vers la corbeille",
                "en": f"Email '{subject}' moved to trash",
                "es": f"Email '{subject}' movido a la papelera",
                "de": f"E-Mail '{subject}' in den Papierkorb verschoben",
                "it": f"Email '{subject}' spostata nel cestino",
                "zh-CN": f"邮件 '{subject}' 已移至垃圾箱",
            }
        else:
            messages = {
                "fr": "Email déplacé vers la corbeille",
                "en": "Email moved to trash",
                "es": "Email movido a la papelera",
                "de": "E-Mail in den Papierkorb verschoben",
                "it": "Email spostata nel cestino",
                "zh-CN": "邮件已移至垃圾箱",
            }
        return messages.get(language, messages["en"])

    # =========================================================================
    # CALENDAR TOOL MESSAGES
    # =========================================================================

    @staticmethod
    def event_created_successfully(summary: str, language: SupportedLanguage = "fr") -> str:
        """Success - calendar event created."""
        messages = {
            "fr": f"Événement '{summary}' créé avec succès",
            "en": f"Event '{summary}' created successfully",
            "es": f"Evento '{summary}' creado exitosamente",
            "de": f"Termin '{summary}' erfolgreich erstellt",
            "it": f"Evento '{summary}' creato con successo",
            "zh-CN": f"活动 '{summary}' 创建成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def event_updated_successfully(summary: str, language: SupportedLanguage = "fr") -> str:
        """Success - calendar event updated."""
        messages = {
            "fr": f"Événement '{summary}' mis à jour avec succès",
            "en": f"Event '{summary}' updated successfully",
            "es": f"Evento '{summary}' actualizado exitosamente",
            "de": f"Termin '{summary}' erfolgreich aktualisiert",
            "it": f"Evento '{summary}' aggiornato con successo",
            "zh-CN": f"活动 '{summary}' 更新成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def event_deleted_successfully(event_id: str, language: SupportedLanguage = "fr") -> str:
        """Success - calendar event deleted."""
        messages = {
            "fr": f"Événement '{event_id}' supprimé avec succès",
            "en": f"Event '{event_id}' deleted successfully",
            "es": f"Evento '{event_id}' eliminado exitosamente",
            "de": f"Termin '{event_id}' erfolgreich gelöscht",
            "it": f"Evento '{event_id}' eliminato con successo",
            "zh-CN": f"活动 '{event_id}' 删除成功",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # CONTACT TOOL MESSAGES
    # =========================================================================

    @staticmethod
    def contact_created_successfully(name: str, language: SupportedLanguage = "fr") -> str:
        """Success - contact created."""
        messages = {
            "fr": f"Contact '{name}' créé avec succès",
            "en": f"Contact '{name}' created successfully",
            "es": f"Contacto '{name}' creado exitosamente",
            "de": f"Kontakt '{name}' erfolgreich erstellt",
            "it": f"Contatto '{name}' creato con successo",
            "zh-CN": f"联系人 '{name}' 创建成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def contact_updated_successfully(name: str, language: SupportedLanguage = "fr") -> str:
        """Success - contact updated."""
        messages = {
            "fr": f"Contact '{name}' mis à jour avec succès",
            "en": f"Contact '{name}' updated successfully",
            "es": f"Contacto '{name}' actualizado exitosamente",
            "de": f"Kontakt '{name}' erfolgreich aktualisiert",
            "it": f"Contatto '{name}' aggiornato con successo",
            "zh-CN": f"联系人 '{name}' 更新成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def contact_deleted_successfully(
        name: str | None = None, language: SupportedLanguage = "fr"
    ) -> str:
        """Success - contact deleted."""
        if name:
            messages = {
                "fr": f"Contact '{name}' supprimé avec succès",
                "en": f"Contact '{name}' deleted successfully",
                "es": f"Contacto '{name}' eliminado exitosamente",
                "de": f"Kontakt '{name}' erfolgreich gelöscht",
                "it": f"Contatto '{name}' eliminato con successo",
                "zh-CN": f"联系人 '{name}' 删除成功",
            }
        else:
            messages = {
                "fr": "Contact supprimé avec succès",
                "en": "Contact deleted successfully",
                "es": "Contacto eliminado exitosamente",
                "de": "Kontakt erfolgreich gelöscht",
                "it": "Contatto eliminato con successo",
                "zh-CN": "联系人删除成功",
            }
        return messages.get(language, messages["en"])

    # =========================================================================
    # TASK TOOL MESSAGES
    # =========================================================================

    @staticmethod
    def task_created_successfully(title: str, language: SupportedLanguage = "fr") -> str:
        """Success - task created."""
        messages = {
            "fr": f"Tâche '{title}' créée avec succès",
            "en": f"Task '{title}' created successfully",
            "es": f"Tarea '{title}' creada exitosamente",
            "de": f"Aufgabe '{title}' erfolgreich erstellt",
            "it": f"Attività '{title}' creata con successo",
            "zh-CN": f"任务 '{title}' 创建成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def task_updated_successfully(title: str, language: SupportedLanguage = "fr") -> str:
        """Success - task updated."""
        messages = {
            "fr": f"Tâche '{title}' mise à jour avec succès",
            "en": f"Task '{title}' updated successfully",
            "es": f"Tarea '{title}' actualizada exitosamente",
            "de": f"Aufgabe '{title}' erfolgreich aktualisiert",
            "it": f"Attività '{title}' aggiornata con successo",
            "zh-CN": f"任务 '{title}' 更新成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def task_deleted_successfully(
        title: str | None = None, language: SupportedLanguage = "fr"
    ) -> str:
        """Success - task deleted."""
        if title:
            messages = {
                "fr": f"Tâche '{title}' supprimée avec succès",
                "en": f"Task '{title}' deleted successfully",
                "es": f"Tarea '{title}' eliminada exitosamente",
                "de": f"Aufgabe '{title}' erfolgreich gelöscht",
                "it": f"Attività '{title}' eliminata con successo",
                "zh-CN": f"任务 '{title}' 删除成功",
            }
        else:
            messages = {
                "fr": "Tâche supprimée avec succès",
                "en": "Task deleted successfully",
                "es": "Tarea eliminada exitosamente",
                "de": "Aufgabe erfolgreich gelöscht",
                "it": "Attività eliminata con successo",
                "zh-CN": "任务删除成功",
            }
        return messages.get(language, messages["en"])

    # =========================================================================
    # DRIVE TOOL MESSAGES
    # =========================================================================

    @staticmethod
    def file_deleted_successfully(
        name: str | None = None, language: SupportedLanguage = "fr"
    ) -> str:
        """Success - file deleted."""
        if name:
            messages = {
                "fr": f"Fichier '{name}' supprimé avec succès",
                "en": f"File '{name}' deleted successfully",
                "es": f"Archivo '{name}' eliminado exitosamente",
                "de": f"Datei '{name}' erfolgreich gelöscht",
                "it": f"File '{name}' eliminato con successo",
                "zh-CN": f"文件 '{name}' 删除成功",
            }
        else:
            messages = {
                "fr": "Fichier supprimé avec succès",
                "en": "File deleted successfully",
                "es": "Archivo eliminado exitosamente",
                "de": "Datei erfolgreich gelöscht",
                "it": "File eliminato con successo",
                "zh-CN": "文件删除成功",
            }
        return messages.get(language, messages["en"])

    # =========================================================================
    # REMINDER MESSAGES
    # =========================================================================

    @staticmethod
    def reminder_created(formatted_time: str, language: SupportedLanguage = "fr") -> str:
        """Success - reminder created."""
        messages = {
            "fr": f"🔔 Rappel créé pour {formatted_time}",
            "en": f"🔔 Reminder set for {formatted_time}",
            "es": f"🔔 Recordatorio creado para {formatted_time}",
            "de": f"🔔 Erinnerung erstellt für {formatted_time}",
            "it": f"🔔 Promemoria creato per {formatted_time}",
            "zh-CN": f"🔔 提醒已设置为 {formatted_time}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_cancelled(content: str, language: SupportedLanguage = "fr") -> str:
        """Success - reminder cancelled."""
        messages = {
            "fr": f"🔔 Rappel annulé : {content}",
            "en": f"🔔 Reminder cancelled: {content}",
            "es": f"🔔 Recordatorio cancelado: {content}",
            "de": f"🔔 Erinnerung abgebrochen: {content}",
            "it": f"🔔 Promemoria annullato: {content}",
            "zh-CN": f"🔔 提醒已取消：{content}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_not_found(identifier: str, language: SupportedLanguage = "fr") -> str:
        """Error - reminder not found."""
        messages = {
            "fr": f"Rappel non trouvé : {identifier}",
            "en": f"Reminder not found: {identifier}",
            "es": f"Recordatorio no encontrado: {identifier}",
            "de": f"Erinnerung nicht gefunden: {identifier}",
            "it": f"Promemoria non trovato: {identifier}",
            "zh-CN": f"未找到提醒：{identifier}",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # GENERIC TOOL VALIDATION MESSAGES
    # =========================================================================

    @staticmethod
    def field_required(field: str, language: SupportedLanguage = "fr") -> str:
        """Validation - single required field missing (generic, DRY replacement for domain-specific variants)."""
        messages = {
            "fr": f"Le champ '{field}' est obligatoire",
            "en": f"Field '{field}' is required",
            "es": f"El campo '{field}' es obligatorio",
            "de": f"Das Feld '{field}' ist erforderlich",
            "it": f"Il campo '{field}' è obbligatorio",
            "zh-CN": f"字段 '{field}' 是必填项",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def fields_required(fields: list[str], language: SupportedLanguage = "fr") -> str:
        """Validation - multiple fields required."""
        fields_str = ", ".join(f"'{f}'" for f in fields)
        messages = {
            "fr": f"Les champs {fields_str} sont obligatoires",
            "en": f"Fields {fields_str} are required",
            "es": f"Los campos {fields_str} son obligatorios",
            "de": f"Die Felder {fields_str} sind erforderlich",
            "it": f"I campi {fields_str} sono obbligatori",
            "zh-CN": f"字段 {fields_str} 是必填项",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def invalid_date(language: SupportedLanguage = "fr") -> str:
        """Validation - invalid date format."""
        messages = {
            "fr": "Date invalide",
            "en": "Invalid date",
            "es": "Fecha inválida",
            "de": "Ungültiges Datum",
            "it": "Data non valida",
            "zh-CN": "日期无效",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def invalid_rating_range(
        min_val: float, max_val: float, language: SupportedLanguage = "fr"
    ) -> str:
        """Validation - rating outside valid range."""
        messages = {
            "fr": f"La note doit être comprise entre {min_val} et {max_val}",
            "en": f"Rating must be between {min_val} and {max_val}",
            "es": f"La calificación debe estar entre {min_val} y {max_val}",
            "de": f"Bewertung muss zwischen {min_val} und {max_val} liegen",
            "it": f"La valutazione deve essere tra {min_val} e {max_val}",
            "zh-CN": f"评分必须在 {min_val} 到 {max_val} 之间",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def invalid_price_level(
        invalid_values: list[str], valid_values: list[str], language: SupportedLanguage = "fr"
    ) -> str:
        """Validation - invalid price level values."""
        invalid_str = ", ".join(invalid_values)
        valid_str = ", ".join(valid_values)
        messages = {
            "fr": f"Niveau de prix invalide : {invalid_str}. Valeurs autorisées : {valid_str}",
            "en": f"Invalid price level: {invalid_str}. Allowed values: {valid_str}",
            "es": f"Nivel de precio inválido: {invalid_str}. Valores permitidos: {valid_str}",
            "de": f"Ungültige Preisstufe: {invalid_str}. Erlaubte Werte: {valid_str}",
            "it": f"Livello di prezzo non valido: {invalid_str}. Valori consentiti: {valid_str}",
            "zh-CN": f"无效的价格等级: {invalid_str}。允许的值: {valid_str}",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # CONNECTOR ERROR MESSAGES
    # =========================================================================

    @staticmethod
    def connector_auth_invalid(connector_name: str, language: SupportedLanguage = "fr") -> str:
        """Connector authentication invalid."""
        messages = {
            "fr": f"Authentification {connector_name} invalide. Veuillez réactiver le connecteur dans les paramètres.",
            "en": f"{connector_name} authentication invalid. Please reactivate the connector in settings.",
            "es": f"Autenticación de {connector_name} inválida. Por favor, reactive el conector en la configuración.",
            "de": f"{connector_name}-Authentifizierung ungültig. Bitte aktivieren Sie den Connector in den Einstellungen erneut.",
            "it": f"Autenticazione {connector_name} non valida. Riattivare il connettore nelle impostazioni.",
            "zh-CN": f"{connector_name} 身份验证无效。请在设置中重新激活连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def connector_reauthorize_permissions(language: SupportedLanguage = "fr") -> str:
        """Connector needs reauthorization with permissions."""
        messages = {
            "fr": "Veuillez réautoriser le connecteur avec les permissions nécessaires.",
            "en": "Please reauthorize the connector with the necessary permissions.",
            "es": "Por favor, reautoriza el conector con los permisos necesarios.",
            "de": "Bitte autorisieren Sie den Connector mit den erforderlichen Berechtigungen erneut.",
            "it": "Si prega di riautorizzare il connettore con i permessi necessari.",
            "zh-CN": "请使用必要的权限重新授权连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def connector_not_enabled(connector_name: str, language: SupportedLanguage = "fr") -> str:
        """Connector not enabled for user - used in draft execution."""
        messages = {
            "fr": f"Le connecteur {connector_name} n'est pas activé. Veuillez l'activer dans les paramètres.",
            "en": f"{connector_name} connector is not enabled. Please enable it in settings.",
            "es": f"El conector {connector_name} no está habilitado. Por favor, actívelo en la configuración.",
            "de": f"Der {connector_name}-Connector ist nicht aktiviert. Bitte aktivieren Sie ihn in den Einstellungen.",
            "it": f"Il connettore {connector_name} non è abilitato. Attivarlo nelle impostazioni.",
            "zh-CN": f"{connector_name} 连接器未启用。请在设置中启用它。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def insufficient_permissions(
        connector_name: str,
        scope_names: list[str],
        operation: str | None = None,
        language: SupportedLanguage = "fr",
    ) -> str:
        """Insufficient OAuth permissions for connector."""
        scopes_str = ", ".join(scope_names)
        operation_part = {
            "fr": f" pour {operation}" if operation else "",
            "en": f" for {operation}" if operation else "",
            "es": f" para {operation}" if operation else "",
            "de": f" für {operation}" if operation else "",
            "it": f" per {operation}" if operation else "",
            "zh-CN": f" 用于 {operation}" if operation else "",
        }
        messages = {
            "fr": f"Permissions insuffisantes pour {connector_name}{operation_part['fr']}. Permissions manquantes : {scopes_str}. Veuillez réautoriser le connecteur avec les permissions nécessaires.",
            "en": f"Insufficient permissions for {connector_name}{operation_part['en']}. Missing permissions: {scopes_str}. Please reauthorize the connector with the necessary permissions.",
            "es": f"Permisos insuficientes para {connector_name}{operation_part['es']}. Permisos faltantes: {scopes_str}. Por favor, reautoriza el conector con los permisos necesarios.",
            "de": f"Unzureichende Berechtigungen für {connector_name}{operation_part['de']}. Fehlende Berechtigungen: {scopes_str}. Bitte autorisieren Sie den Connector mit den erforderlichen Berechtigungen erneut.",
            "it": f"Permessi insufficienti per {connector_name}{operation_part['it']}. Permessi mancanti: {scopes_str}. Si prega di riautorizzare il connettore con i permessi necessari.",
            "zh-CN": f"{connector_name}{operation_part['zh-CN']} 权限不足。缺少权限：{scopes_str}。请使用必要的权限重新授权连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def rate_limit_exceeded(
        connector_name: str,
        retry_after_seconds: int | None = None,
        language: SupportedLanguage = "fr",
    ) -> str:
        """Rate limit exceeded for connector."""
        if retry_after_seconds:
            wait_msg = {
                "fr": f"Veuillez réessayer dans {retry_after_seconds} secondes.",
                "en": f"Please retry in {retry_after_seconds} seconds.",
                "es": f"Por favor, inténtelo de nuevo en {retry_after_seconds} segundos.",
                "de": f"Bitte versuchen Sie es in {retry_after_seconds} Sekunden erneut.",
                "it": f"Riprova tra {retry_after_seconds} secondi.",
                "zh-CN": f"请在 {retry_after_seconds} 秒后重试。",
            }
        else:
            wait_msg = {
                "fr": "Veuillez réessayer dans quelques instants.",
                "en": "Please retry in a few moments.",
                "es": "Por favor, inténtelo de nuevo en unos momentos.",
                "de": "Bitte versuchen Sie es in einigen Augenblicken erneut.",
                "it": "Riprova tra qualche istante.",
                "zh-CN": "请稍后重试。",
            }

        base_msg = {
            "fr": f"Limite de débit {connector_name} atteinte.",
            "en": f"{connector_name} rate limit reached.",
            "es": f"Límite de velocidad de {connector_name} alcanzado.",
            "de": f"{connector_name}-Ratenlimit erreicht.",
            "it": f"Limite di velocità {connector_name} raggiunto.",
            "zh-CN": f"{connector_name} 速率限制已达到。",
        }

        return f"{base_msg.get(language, base_msg['en'])} {wait_msg.get(language, wait_msg['en'])}"

    @staticmethod
    def no_refresh_token_available(language: SupportedLanguage = "fr") -> str:
        """No refresh token available."""
        messages = {
            "fr": "Pas de refresh_token disponible. Veuillez réactiver le connecteur.",
            "en": "No refresh token available. Please reactivate the connector.",
            "es": "No hay token de actualización disponible. Por favor, reactive el conector.",
            "de": "Kein Aktualisierungstoken verfügbar. Bitte aktivieren Sie den Connector erneut.",
            "it": "Nessun token di aggiornamento disponibile. Riattivare il connettore.",
            "zh-CN": "没有可用的刷新令牌。请重新激活连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def oauth_token_refresh_failed(language: SupportedLanguage = "fr") -> str:
        """OAuth token refresh failed."""
        messages = {
            "fr": "Échec du renouvellement du token OAuth (erreur réseau). Veuillez réactiver le connecteur.",
            "en": "OAuth token refresh failed (network error). Please reactivate the connector.",
            "es": "Error al renovar el token OAuth (error de red). Por favor, reactive el conector.",
            "de": "OAuth-Token-Aktualisierung fehlgeschlagen (Netzwerkfehler). Bitte aktivieren Sie den Connector erneut.",
            "it": "Aggiornamento token OAuth fallito (errore di rete). Riattivare il connettore.",
            "zh-CN": "OAuth 令牌刷新失败（网络错误）。请重新激活连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def refresh_token_revoked(language: SupportedLanguage = "fr") -> str:
        """Refresh token was revoked or expired."""
        messages = {
            "fr": "Le refresh token a été révoqué ou a expiré. Veuillez réactiver le connecteur dans les paramètres.",
            "en": "The refresh token has been revoked or expired. Please reactivate the connector in settings.",
            "es": "El token de actualización ha sido revocado o ha expirado. Por favor, reactive el conector en la configuración.",
            "de": "Das Aktualisierungstoken wurde widerrufen oder ist abgelaufen. Bitte aktivieren Sie den Connector in den Einstellungen erneut.",
            "it": "Il token di aggiornamento è stato revocato o è scaduto. Riattivare il connettore nelle impostazioni.",
            "zh-CN": "刷新令牌已被撤销或已过期。请在设置中重新激活连接器。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def google_no_refresh_token_hint(language: SupportedLanguage = "fr") -> str:
        """Google didn't return refresh token - hint to revoke access."""
        messages = {
            "fr": "Google n'a pas retourné de refresh_token. Veuillez révoquer l'accès dans votre compte Google (https://myaccount.google.com/permissions) puis réessayer.",
            "en": "Google didn't return a refresh_token. Please revoke access in your Google account (https://myaccount.google.com/permissions) and try again.",
            "es": "Google no devolvió un refresh_token. Revoca el acceso en tu cuenta de Google (https://myaccount.google.com/permissions) e inténtalo de nuevo.",
            "de": "Google hat kein refresh_token zurückgegeben. Bitte widerrufen Sie den Zugriff in Ihrem Google-Konto (https://myaccount.google.com/permissions) und versuchen Sie es erneut.",
            "it": "Google non ha restituito un refresh_token. Revoca l'accesso nel tuo account Google (https://myaccount.google.com/permissions) e riprova.",
            "zh-CN": "Google 未返回 refresh_token。请在您的 Google 帐户中撤销访问权限 (https://myaccount.google.com/permissions)，然后重试。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reason_not_specified(language: SupportedLanguage = "fr") -> str:
        """Reason not specified."""
        messages = {
            "fr": "Raison non spécifiée",
            "en": "Reason not specified",
            "es": "Razón no especificada",
            "de": "Grund nicht angegeben",
            "it": "Motivo non specificato",
            "zh-CN": "原因未指定",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # ENTITY RESOLUTION MESSAGES
    # =========================================================================

    @staticmethod
    def entity_not_found(domain: str, query: str, language: SupportedLanguage = "fr") -> str:
        """Entity not found for query."""
        messages = {
            "fr": f"Aucun {domain} trouvé pour '{query}'",
            "en": f"No {domain} found for '{query}'",
            "es": f"No se encontró {domain} para '{query}'",
            "de": f"Kein {domain} für '{query}' gefunden",
            "it": f"Nessun {domain} trovato per '{query}'",
            "zh-CN": f"未找到 '{query}' 的 {domain}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def entity_missing_field(domain: str, field: str, language: SupportedLanguage = "fr") -> str:
        """Entity found but missing required field."""
        messages = {
            "fr": f"Le {domain} trouvé n'a pas de {field}",
            "en": f"The {domain} found has no {field}",
            "es": f"El {domain} encontrado no tiene {field}",
            "de": f"Das gefundene {domain} hat kein {field}",
            "it": f"Il {domain} trovato non ha {field}",
            "zh-CN": f"找到的 {domain} 没有 {field}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def invalid_choice(choice: str, language: SupportedLanguage = "fr") -> str:
        """Invalid choice in entity resolution."""
        messages = {
            "fr": f"Choix invalide: {choice}",
            "en": f"Invalid choice: {choice}",
            "es": f"Elección inválida: {choice}",
            "de": f"Ungültige Auswahl: {choice}",
            "it": f"Scelta non valida: {choice}",
            "zh-CN": f"无效选择: {choice}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def choice_out_of_bounds(index: int, max_value: int, language: SupportedLanguage = "fr") -> str:
        """Choice index out of bounds in entity resolution."""
        messages = {
            "fr": f"Choix hors limites: {index} (1-{max_value} attendu)",
            "en": f"Choice out of bounds: {index} (1-{max_value} expected)",
            "es": f"Elección fuera de límites: {index} (1-{max_value} esperado)",
            "de": f"Auswahl außerhalb des Bereichs: {index} (1-{max_value} erwartet)",
            "it": f"Scelta fuori dai limiti: {index} (1-{max_value} previsto)",
            "zh-CN": f"选择超出范围: {index} (预期 1-{max_value})",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def resolution_error(error_message: str, language: SupportedLanguage = "fr") -> str:
        """Resolution failed with error."""
        messages = {
            "fr": f"Erreur lors de la résolution: {error_message}",
            "en": f"Resolution error: {error_message}",
            "es": f"Error de resolución: {error_message}",
            "de": f"Auflösungsfehler: {error_message}",
            "it": f"Errore di risoluzione: {error_message}",
            "zh-CN": f"解析错误: {error_message}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def entity_no_target_field(domain: str, query: str, language: SupportedLanguage = "fr") -> str:
        """Entity found but missing target field."""
        messages = {
            "fr": f"Le {domain} '{query}' n'a pas le champ requis",
            "en": f"The {domain} '{query}' does not have the required field",
            "es": f"El {domain} '{query}' no tiene el campo requerido",
            "de": f"Der {domain} '{query}' hat nicht das erforderliche Feld",
            "it": f"Il {domain} '{query}' non ha il campo richiesto",
            "zh-CN": f"{domain} '{query}' 没有所需字段",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def multiple_options_available(count: int, language: SupportedLanguage = "fr") -> str:
        """Multiple options available for disambiguation."""
        messages = {
            "fr": f"Plusieurs options disponibles. Choisis parmi {count} possibilités.",
            "en": f"Multiple options available. Choose from {count} possibilities.",
            "es": f"Varias opciones disponibles. Elige entre {count} posibilidades.",
            "de": f"Mehrere Optionen verfügbar. Wähle aus {count} Möglichkeiten.",
            "it": f"Più opzioni disponibili. Scegli tra {count} possibilità.",
            "zh-CN": f"多个选项可用。从 {count} 个可能性中选择。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def multiple_matches_found(count: int, language: SupportedLanguage = "fr") -> str:
        """Multiple matches found, need disambiguation."""
        messages = {
            "fr": f"Plusieurs correspondances trouvées ({count}). Précise ton choix.",
            "en": f"Multiple matches found ({count}). Please specify your choice.",
            "es": f"Múltiples coincidencias encontradas ({count}). Especifica tu elección.",
            "de": f"Mehrere Übereinstimmungen gefunden ({count}). Bitte geben Sie Ihre Wahl an.",
            "it": f"Trovate più corrispondenze ({count}). Specifica la tua scelta.",
            "zh-CN": f"找到多个匹配项 ({count})。请指定您的选择。",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # FORMATTER DISPLAY MESSAGES
    # =========================================================================

    @staticmethod
    def unknown_name(language: SupportedLanguage = "fr") -> str:
        """Unknown name placeholder for contacts."""
        messages = {
            "fr": "Nom inconnu",
            "en": "Unknown name",
            "es": "Nombre desconocido",
            "de": "Unbekannter Name",
            "it": "Nome sconosciuto",
            "zh-CN": "未知姓名",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def date_unknown(language: SupportedLanguage = "fr") -> str:
        """Unknown date placeholder."""
        messages = {
            "fr": "Date inconnue",
            "en": "Unknown date",
            "es": "Fecha desconocida",
            "de": "Unbekanntes Datum",
            "it": "Data sconosciuta",
            "zh-CN": "未知日期",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def date_invalid(language: SupportedLanguage = "fr") -> str:
        """Invalid date placeholder."""
        messages = {
            "fr": "Date invalide",
            "en": "Invalid date",
            "es": "Fecha inválida",
            "de": "Ungültiges Datum",
            "it": "Data non valida",
            "zh-CN": "无效日期",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def sender_unknown(language: SupportedLanguage = "fr") -> str:
        """Unknown sender placeholder for emails."""
        messages = {
            "fr": "Expéditeur inconnu",
            "en": "Unknown sender",
            "es": "Remitente desconocido",
            "de": "Unbekannter Absender",
            "it": "Mittente sconosciuto",
            "zh-CN": "未知发件人",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_subject(language: SupportedLanguage = "fr") -> str:
        """No subject placeholder for emails."""
        messages = {
            "fr": "(Sans objet)",
            "en": "(No subject)",
            "es": "(Sin asunto)",
            "de": "(Kein Betreff)",
            "it": "(Nessun oggetto)",
            "zh-CN": "(无主题)",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def email_read_more_gmail(url: str, language: SupportedLanguage = "fr") -> str:
        """Link to continue reading email in webmail (legacy alias)."""
        return APIMessages.email_read_more(url, language)

    @staticmethod
    def email_read_more(url: str, language: SupportedLanguage = "fr") -> str:
        """Link to continue reading email in webmail (provider-agnostic)."""
        messages = {
            "fr": f"... [lire la suite]({url})",
            "en": f"... [read more]({url})",
            "es": f"... [leer más]({url})",
            "de": f"... [mehr lesen]({url})",
            "it": f"... [leggi di più]({url})",
            "zh-CN": f"... [阅读更多]({url})",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def message_truncated(language: SupportedLanguage = "fr") -> str:
        """Message truncated placeholder."""
        messages = {
            "fr": "... [message tronqué]",
            "en": "... [message truncated]",
            "es": "... [mensaje truncado]",
            "de": "... [Nachricht gekürzt]",
            "it": "... [messaggio troncato]",
            "zh-CN": "... [消息已截断]",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def attachment_placeholder(language: SupportedLanguage = "fr") -> str:
        """Attachment placeholder when filename is unknown."""
        messages = {
            "fr": "pièce jointe",
            "en": "attachment",
            "es": "adjunto",
            "de": "Anhang",
            "it": "allegato",
            "zh-CN": "附件",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # TOOL ERROR MESSAGES
    # =========================================================================

    @staticmethod
    def reminder_creation_error(error: str, language: SupportedLanguage = "fr") -> str:
        """Reminder creation failed."""
        messages = {
            "fr": f"Erreur lors de la création du rappel: {error}",
            "en": f"Error creating reminder: {error}",
            "es": f"Error al crear el recordatorio: {error}",
            "de": f"Fehler beim Erstellen der Erinnerung: {error}",
            "it": f"Errore nella creazione del promemoria: {error}",
            "zh-CN": f"创建提醒时出错: {error}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_list_error(error: str, language: SupportedLanguage = "fr") -> str:
        """Reminder list retrieval failed."""
        messages = {
            "fr": f"Erreur lors de la récupération des rappels: {error}",
            "en": f"Error retrieving reminders: {error}",
            "es": f"Error al recuperar los recordatorios: {error}",
            "de": f"Fehler beim Abrufen der Erinnerungen: {error}",
            "it": f"Errore nel recupero dei promemoria: {error}",
            "zh-CN": f"获取提醒时出错: {error}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_cancel_error(error: str, language: SupportedLanguage = "fr") -> str:
        """Reminder cancellation failed."""
        messages = {
            "fr": f"Erreur lors de l'annulation du rappel: {error}",
            "en": f"Error canceling reminder: {error}",
            "es": f"Error al cancelar el recordatorio: {error}",
            "de": f"Fehler beim Abbrechen der Erinnerung: {error}",
            "it": f"Errore nell'annullamento del promemoria: {error}",
            "zh-CN": f"取消提醒时出错: {error}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_pending_reminders(language: SupportedLanguage = "fr") -> str:
        """No pending reminders message."""
        messages = {
            "fr": "Tu n'as aucun rappel en attente.",
            "en": "You have no pending reminders.",
            "es": "No tienes recordatorios pendientes.",
            "de": "Sie haben keine ausstehenden Erinnerungen.",
            "it": "Non hai promemoria in sospeso.",
            "zh-CN": "您没有待处理的提醒。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def relative_trigger_invalid_format(value: str, language: SupportedLanguage = "fr") -> str:
        """Invalid relative_trigger format."""
        messages = {
            "fr": f"Format relative_trigger invalide: '{value}'. Attendu: 'DATETIME|OFFSET' ou 'DATETIME|OFFSET|@TIME'",
            "en": f"Invalid relative_trigger format: '{value}'. Expected: 'DATETIME|OFFSET' or 'DATETIME|OFFSET|@TIME'",
            "es": f"Formato relative_trigger inválido: '{value}'. Esperado: 'DATETIME|OFFSET' o 'DATETIME|OFFSET|@TIME'",
            "de": f"Ungültiges relative_trigger Format: '{value}'. Erwartet: 'DATETIME|OFFSET' oder 'DATETIME|OFFSET|@TIME'",
            "it": f"Formato relative_trigger non valido: '{value}'. Atteso: 'DATETIME|OFFSET' o 'DATETIME|OFFSET|@TIME'",
            "zh-CN": f"relative_trigger 格式无效: '{value}'。预期: 'DATETIME|OFFSET' 或 'DATETIME|OFFSET|@TIME'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def relative_trigger_invalid_datetime(value: str, language: SupportedLanguage = "fr") -> str:
        """Invalid datetime in relative_trigger."""
        messages = {
            "fr": f"Date/heure invalide dans relative_trigger: '{value}'",
            "en": f"Invalid datetime in relative_trigger: '{value}'",
            "es": f"Fecha/hora inválida en relative_trigger: '{value}'",
            "de": f"Ungültiges Datum/Uhrzeit in relative_trigger: '{value}'",
            "it": f"Data/ora non valida in relative_trigger: '{value}'",
            "zh-CN": f"relative_trigger 中的日期/时间无效: '{value}'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def relative_trigger_invalid_offset(value: str, language: SupportedLanguage = "fr") -> str:
        """Invalid offset in relative_trigger."""
        messages = {
            "fr": f"Offset invalide: '{value}'. Attendu: '-1d', '+2h', '-30m'",
            "en": f"Invalid offset: '{value}'. Expected: '-1d', '+2h', '-30m'",
            "es": f"Offset inválido: '{value}'. Esperado: '-1d', '+2h', '-30m'",
            "de": f"Ungültiger Offset: '{value}'. Erwartet: '-1d', '+2h', '-30m'",
            "it": f"Offset non valido: '{value}'. Atteso: '-1d', '+2h', '-30m'",
            "zh-CN": f"偏移量无效: '{value}'。预期: '-1d', '+2h', '-30m'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def relative_trigger_invalid_time(value: str, language: SupportedLanguage = "fr") -> str:
        """Invalid time override in relative_trigger."""
        messages = {
            "fr": f"Heure invalide: '{value}'. Attendu: '@HH:MM' (ex: @19:00)",
            "en": f"Invalid time: '{value}'. Expected: '@HH:MM' (e.g., @19:00)",
            "es": f"Hora inválida: '{value}'. Esperado: '@HH:MM' (ej: @19:00)",
            "de": f"Ungültige Zeit: '{value}'. Erwartet: '@HH:MM' (z.B. @19:00)",
            "it": f"Ora non valida: '{value}'. Atteso: '@HH:MM' (es: @19:00)",
            "zh-CN": f"时间无效: '{value}'。预期: '@HH:MM' (例如: @19:00)",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_trigger_params_conflict(language: SupportedLanguage = "fr") -> str:
        """Both trigger_datetime and relative_trigger provided."""
        messages = {
            "fr": "Impossible d'utiliser trigger_datetime et relative_trigger ensemble. Utilisez l'un ou l'autre.",
            "en": "Cannot use both trigger_datetime and relative_trigger. Use one or the other.",
            "es": "No se pueden usar trigger_datetime y relative_trigger juntos. Use uno u otro.",
            "de": "trigger_datetime und relative_trigger können nicht zusammen verwendet werden. Verwenden Sie eines von beiden.",
            "it": "Non è possibile usare trigger_datetime e relative_trigger insieme. Usare l'uno o l'altro.",
            "zh-CN": "不能同时使用 trigger_datetime 和 relative_trigger。请使用其中一个。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def reminder_trigger_params_missing(language: SupportedLanguage = "fr") -> str:
        """Neither trigger_datetime nor relative_trigger provided."""
        messages = {
            "fr": "trigger_datetime ou relative_trigger doit être fourni.",
            "en": "Either trigger_datetime or relative_trigger must be provided.",
            "es": "Se debe proporcionar trigger_datetime o relative_trigger.",
            "de": "trigger_datetime oder relative_trigger muss angegeben werden.",
            "it": "Deve essere fornito trigger_datetime o relative_trigger.",
            "zh-CN": "必须提供 trigger_datetime 或 relative_trigger。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_results_to_display(language: SupportedLanguage = "fr") -> str:
        """No results to display message."""
        messages = {
            "fr": "Aucun résultat à afficher.",
            "en": "No results to display.",
            "es": "No hay resultados para mostrar.",
            "de": "Keine Ergebnisse anzuzeigen.",
            "it": "Nessun risultato da visualizzare.",
            "zh-CN": "没有结果可显示。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_external_agent_called(language: SupportedLanguage = "fr") -> str:
        """No external agent was called message."""
        messages = {
            "fr": "Aucun agent externe n'a été appelé.",
            "en": "No external agent was called.",
            "es": "No se llamó a ningún agente externo.",
            "de": "Kein externer Agent wurde aufgerufen.",
            "it": "Nessun agente esterno è stato chiamato.",
            "zh-CN": "未调用外部代理。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_context_items(language: SupportedLanguage = "fr") -> str:
        """No items in current context message."""
        messages = {
            "fr": "Aucun item dans le contexte actuel.",
            "en": "No items in current context.",
            "es": "No hay elementos en el contexto actual.",
            "de": "Keine Elemente im aktuellen Kontext.",
            "it": "Nessun elemento nel contesto attuale.",
            "zh-CN": "当前上下文中没有项目。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_resolved_element(language: SupportedLanguage = "fr") -> str:
        """No resolved element for reference message."""
        messages = {
            "fr": "Aucun élément résolu pour cette référence.",
            "en": "No resolved element for this reference.",
            "es": "No hay elemento resuelto para esta referencia.",
            "de": "Kein aufgelöstes Element für diese Referenz.",
            "it": "Nessun elemento risolto per questo riferimento.",
            "zh-CN": "此引用没有已解析的元素。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def no_active_contacts_list(language: SupportedLanguage = "fr") -> str:
        """No active contacts list in memory message."""
        messages = {
            "fr": "Aucune liste 'contacts' active en mémoire.",
            "en": "No active 'contacts' list in memory.",
            "es": "No hay lista de 'contactos' activa en memoria.",
            "de": "Keine aktive 'Kontakte'-Liste im Speicher.",
            "it": "Nessuna lista 'contatti' attiva in memoria.",
            "zh-CN": '内存中没有活动的"联系人"列表。',
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def nested_interrupt_save_failed(language: SupportedLanguage = "fr") -> str:
        """Nested interrupt save failed message."""
        messages = {
            "fr": "Impossible de sauvegarder l'interruption imbriquée. Veuillez réessayer.",
            "en": "Unable to save nested interrupt. Please try again.",
            "es": "No se pudo guardar la interrupción anidada. Por favor, inténtelo de nuevo.",
            "de": "Verschachtelte Unterbrechung konnte nicht gespeichert werden. Bitte versuchen Sie es erneut.",
            "it": "Impossibile salvare l'interruzione nidificata. Si prega di riprovare.",
            "zh-CN": "无法保存嵌套中断。请重试。",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # PLANNER ERROR MESSAGES
    # =========================================================================

    @staticmethod
    def planner_error_header(error_message: str, language: SupportedLanguage = "fr") -> str:
        """Planning error header with emoji."""
        messages = {
            "fr": f"\n\n⚠️ **Problème de planification:**\n{error_message}\n\n",
            "en": f"\n\n⚠️ **Planning issue:**\n{error_message}\n\n",
            "es": f"\n\n⚠️ **Problema de planificación:**\n{error_message}\n\n",
            "de": f"\n\n⚠️ **Planungsproblem:**\n{error_message}\n\n",
            "it": f"\n\n⚠️ **Problema di pianificazione:**\n{error_message}\n\n",
            "zh-CN": f"\n\n⚠️ **规划问题:**\n{error_message}\n\n",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def planner_technical_details(language: SupportedLanguage = "fr") -> str:
        """Technical details section header."""
        messages = {
            "fr": "**Détails techniques:**\n",
            "en": "**Technical details:**\n",
            "es": "**Detalles técnicos:**\n",
            "de": "**Technische Details:**\n",
            "it": "**Dettagli tecnici:**\n",
            "zh-CN": "**技术细节:**\n",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def planner_unknown_error(language: SupportedLanguage = "fr") -> str:
        """Unknown error fallback message."""
        messages = {
            "fr": "Erreur inconnue",
            "en": "Unknown error",
            "es": "Error desconocido",
            "de": "Unbekannter Fehler",
            "it": "Errore sconosciuto",
            "zh-CN": "未知错误",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def planner_explanation(language: SupportedLanguage = "fr") -> str:
        """Planner error explanation for users."""
        messages = {
            "fr": "\n💡 **Explication:** Le planner n'a pas pu créer un plan d'exécution valide pour cette requête. Certaines opérations complexes (filtrage par date, conditions avancées) ne sont pas encore supportées.",
            "en": "\n💡 **Explanation:** The planner could not create a valid execution plan for this request. Some complex operations (date filtering, advanced conditions) are not yet supported.",
            "es": "\n💡 **Explicación:** El planificador no pudo crear un plan de ejecución válido para esta solicitud. Algunas operaciones complejas (filtrado por fecha, condiciones avanzadas) aún no son compatibles.",
            "de": "\n💡 **Erklärung:** Der Planer konnte keinen gültigen Ausführungsplan für diese Anfrage erstellen. Einige komplexe Operationen (Datumsfilterung, erweiterte Bedingungen) werden noch nicht unterstützt.",
            "it": "\n💡 **Spiegazione:** Il pianificatore non è riuscito a creare un piano di esecuzione valido per questa richiesta. Alcune operazioni complesse (filtro per data, condizioni avanzate) non sono ancora supportate.",
            "zh-CN": "\n💡 **说明:** 规划器无法为此请求创建有效的执行计划。某些复杂操作（日期筛选、高级条件）尚不支持。",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def plan_validation_failed(language: SupportedLanguage = "fr") -> str:
        """Plan validation failed default message."""
        messages = {
            "fr": "La validation du plan a échoué",
            "en": "Plan validation failed",
            "es": "La validación del plan falló",
            "de": "Planvalidierung fehlgeschlagen",
            "it": "Validazione del piano fallita",
            "zh-CN": "计划验证失败",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # OAUTH HEALTH CHECK NOTIFICATIONS
    # =========================================================================
    # Messages for push notifications when OAuth connector has status=ERROR.
    # Only sent when refresh failed and manual re-authentication is required.

    @staticmethod
    def oauth_health_critical_title(language: SupportedLanguage = "fr") -> str:
        """Title for push notification when OAuth connector has ERROR status."""
        messages = {
            "fr": "Reconnexion requise",
            "en": "Reconnection required",
            "es": "Reconexión necesaria",
            "de": "Wiederverbindung erforderlich",
            "it": "Riconnessione necessaria",
            "zh-CN": "需要重新连接",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def oauth_health_critical_body(connector_name: str, language: SupportedLanguage = "fr") -> str:
        """Body for push notification when OAuth connector has ERROR status."""
        messages = {
            "fr": f"{connector_name} nécessite une reconnexion manuelle.",
            "en": f"{connector_name} requires manual reconnection.",
            "es": f"{connector_name} requiere reconexión manual.",
            "de": f"{connector_name} erfordert manuelle Wiederverbindung.",
            "it": f"{connector_name} richiede riconnessione manuale.",
            "zh-CN": f"{connector_name} 需要手动重新连接。",
        }
        return messages.get(language, messages["en"])

    # =========================================================================
    # LABEL TOOL MESSAGES
    # =========================================================================

    @staticmethod
    def label_not_found(label_name: str, language: SupportedLanguage = "fr") -> str:
        """Label not found error message."""
        messages = {
            "fr": f"Label '{label_name}' introuvable",
            "en": f"Label '{label_name}' not found",
            "es": f"Etiqueta '{label_name}' no encontrada",
            "de": f"Label '{label_name}' nicht gefunden",
            "it": f"Etichetta '{label_name}' non trovata",
            "zh-CN": f"标签 '{label_name}' 未找到",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_already_exists(label_name: str, language: SupportedLanguage = "fr") -> str:
        """Label already exists error message."""
        messages = {
            "fr": f"Le label '{label_name}' existe déjà",
            "en": f"Label '{label_name}' already exists",
            "es": f"La etiqueta '{label_name}' ya existe",
            "de": f"Label '{label_name}' existiert bereits",
            "it": f"L'etichetta '{label_name}' esiste già",
            "zh-CN": f"标签 '{label_name}' 已存在",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_is_system(label_name: str, language: SupportedLanguage = "fr") -> str:
        """System label cannot be modified error message."""
        messages = {
            "fr": f"Le label '{label_name}' est un label système et ne peut pas être modifié",
            "en": f"Label '{label_name}' is a system label and cannot be modified",
            "es": f"La etiqueta '{label_name}' es una etiqueta del sistema y no puede ser modificada",
            "de": f"Label '{label_name}' ist ein Systemlabel und kann nicht geändert werden",
            "it": f"L'etichetta '{label_name}' è un'etichetta di sistema e non può essere modificata",
            "zh-CN": f"标签 '{label_name}' 是系统标签，无法修改",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_has_children(label_name: str, count: int, language: SupportedLanguage = "fr") -> str:
        """Label has children info message."""
        messages = {
            "fr": f"Le label '{label_name}' contient {count} sous-label(s) qui seront aussi supprimés",
            "en": f"Label '{label_name}' contains {count} sub-label(s) that will also be deleted",
            "es": f"La etiqueta '{label_name}' contiene {count} subetiqueta(s) que también serán eliminadas",
            "de": f"Label '{label_name}' enthält {count} Unterlabel(s), die ebenfalls gelöscht werden",
            "it": f"L'etichetta '{label_name}' contiene {count} sottoetichetta/e che verranno anche eliminate",
            "zh-CN": f"标签 '{label_name}' 包含 {count} 个子标签，也将被删除",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_no_children(label_name: str, language: SupportedLanguage = "fr") -> str:
        """Label has no children error message."""
        messages = {
            "fr": f"Le label '{label_name}' n'a pas de sous-labels",
            "en": f"Label '{label_name}' has no sub-labels",
            "es": f"La etiqueta '{label_name}' no tiene subetiquetas",
            "de": f"Label '{label_name}' hat keine Unterlabels",
            "it": f"L'etichetta '{label_name}' non ha sottoetichette",
            "zh-CN": f"标签 '{label_name}' 没有子标签",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def labels_applied_success(
        count: int, label_names: list[str], language: SupportedLanguage = "fr"
    ) -> str:
        """Labels applied successfully message."""
        labels_str = ", ".join(label_names)
        messages = {
            "fr": f"Label(s) '{labels_str}' appliqué(s) à {count} email(s)",
            "en": f"Label(s) '{labels_str}' applied to {count} email(s)",
            "es": f"Etiqueta(s) '{labels_str}' aplicada(s) a {count} correo(s)",
            "de": f"Label(s) '{labels_str}' auf {count} E-Mail(s) angewendet",
            "it": f"Etichetta/e '{labels_str}' applicata/e a {count} email",
            "zh-CN": f"标签 '{labels_str}' 已应用于 {count} 封邮件",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def labels_removed_success(
        count: int, label_names: list[str], language: SupportedLanguage = "fr"
    ) -> str:
        """Labels removed successfully message."""
        labels_str = ", ".join(label_names)
        messages = {
            "fr": f"Label(s) '{labels_str}' retiré(s) de {count} email(s)",
            "en": f"Label(s) '{labels_str}' removed from {count} email(s)",
            "es": f"Etiqueta(s) '{labels_str}' eliminada(s) de {count} correo(s)",
            "de": f"Label(s) '{labels_str}' von {count} E-Mail(s) entfernt",
            "it": f"Etichetta/e '{labels_str}' rimossa/e da {count} email",
            "zh-CN": f"标签 '{labels_str}' 已从 {count} 封邮件中移除",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_created_success(label_name: str, language: SupportedLanguage = "fr") -> str:
        """Label created successfully message."""
        messages = {
            "fr": f"Label '{label_name}' créé avec succès",
            "en": f"Label '{label_name}' created successfully",
            "es": f"Etiqueta '{label_name}' creada con éxito",
            "de": f"Label '{label_name}' erfolgreich erstellt",
            "it": f"Etichetta '{label_name}' creata con successo",
            "zh-CN": f"标签 '{label_name}' 创建成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_updated_success(
        old_name: str, new_name: str, language: SupportedLanguage = "fr"
    ) -> str:
        """Label updated successfully message."""
        messages = {
            "fr": f"Label '{old_name}' renommé en '{new_name}'",
            "en": f"Label '{old_name}' renamed to '{new_name}'",
            "es": f"Etiqueta '{old_name}' renombrada a '{new_name}'",
            "de": f"Label '{old_name}' in '{new_name}' umbenannt",
            "it": f"Etichetta '{old_name}' rinominata in '{new_name}'",
            "zh-CN": f"标签 '{old_name}' 已重命名为 '{new_name}'",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_deleted_success(label_name: str, language: SupportedLanguage = "fr") -> str:
        """Label deleted successfully message."""
        messages = {
            "fr": f"Label '{label_name}' supprimé avec succès",
            "en": f"Label '{label_name}' deleted successfully",
            "es": f"Etiqueta '{label_name}' eliminada con éxito",
            "de": f"Label '{label_name}' erfolgreich gelöscht",
            "it": f"Etichetta '{label_name}' eliminata con successo",
            "zh-CN": f"标签 '{label_name}' 删除成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def labels_deleted_success(count: int, language: SupportedLanguage = "fr") -> str:
        """Multiple labels deleted successfully message."""
        messages = {
            "fr": f"{count} label(s) supprimé(s) avec succès",
            "en": f"{count} label(s) deleted successfully",
            "es": f"{count} etiqueta(s) eliminada(s) con éxito",
            "de": f"{count} Label(s) erfolgreich gelöscht",
            "it": f"{count} etichetta/e eliminata/e con successo",
            "zh-CN": f"{count} 个标签删除成功",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def label_ambiguous(label_name: str, count: int, language: SupportedLanguage = "fr") -> str:
        """Ambiguous label name message."""
        messages = {
            "fr": f"Plusieurs labels correspondent à '{label_name}' ({count} trouvés). Précise le chemin complet.",
            "en": f"Multiple labels match '{label_name}' ({count} found). Please specify the full path.",
            "es": f"Varias etiquetas coinciden con '{label_name}' ({count} encontradas). Especifique la ruta completa.",
            "de": f"Mehrere Labels stimmen mit '{label_name}' überein ({count} gefunden). Bitte geben Sie den vollständigen Pfad an.",
            "it": f"Più etichette corrispondono a '{label_name}' ({count} trovate). Specificare il percorso completo.",
            "zh-CN": f"多个标签匹配 '{label_name}'（找到 {count} 个）。请指定完整路径。",
        }
        return messages.get(language, messages["en"])


# =============================================================================
# CACHED MESSAGE SETS FOR PERFORMANCE
# =============================================================================
# Pre-computed frozensets for efficient membership testing in hot paths.
# These avoid recreating sets on each function call.

# All supported languages for iteration
_ALL_LANGUAGES: tuple[SupportedLanguage, ...] = ("fr", "en", "es", "de", "it", "zh-CN")


def _build_empty_result_messages() -> frozenset[str]:
    """Build cached set of all 'empty result' messages across all languages."""
    messages: set[str] = set()
    for lang in _ALL_LANGUAGES:
        messages.add(APIMessages.no_results_to_display(lang))
        messages.add(APIMessages.no_external_agent_called(lang))
    return frozenset(messages)


def _build_no_agent_messages() -> frozenset[str]:
    """Build cached set of all 'no external agent' messages across all languages."""
    return frozenset(APIMessages.no_external_agent_called(lang) for lang in _ALL_LANGUAGES)


# Cached frozensets - computed once at module import
EMPTY_RESULT_MESSAGES: frozenset[str] = _build_empty_result_messages()
NO_EXTERNAL_AGENT_MESSAGES: frozenset[str] = _build_no_agent_messages()
