"""Application confirmation vocabulary for the existing draft serializers."""

from typing import NamedTuple

from src.core.i18n_types import Language


class ApplicationDraftCopy(NamedTuple):
    summary: str
    success: str
    cancelled: str
    before: str
    after: str


class ApplicationExportCopy(NamedTuple):
    note: str
    title: str


class ApplicationMemoryPinCopy(NamedTuple):
    note: str
    title: str
    pinned: str
    unpinned: str


class ApplicationMemoryCreationCopy(NamedTuple):
    note: str
    title: str


APPLICATION_MEMORY_CREATION: dict[Language, ApplicationMemoryCreationCopy] = {
    "fr": ApplicationMemoryCreationCopy(
        "Confirmer la création de cette mémoire avec les valeurs affichées. Aucun enregistrement ni calcul d’embedding avant votre accord. Les embeddings utilisent ensuite le modèle et les coûts existants, sous contrôle des quotas. La mémoire peut être conservée sans vecteurs si ce calcul est indisponible. Les règles et directives sont épinglées à la création ; l’usage automatique des mémoires reste inchangé.",
        "Mémoire à créer",
    ),
    "en": ApplicationMemoryCreationCopy(
        "Confirm creating this memory with the displayed values. No write or embedding before approval. Embeddings then use the existing model and costs, subject to quotas. The memory may be stored without vectors if embedding is unavailable. Standing instructions are pinned at creation; automatic memory use stays unchanged.",
        "Memory to create",
    ),
    "de": ApplicationMemoryCreationCopy(
        "Bestätigen Sie diese Erinnerung mit den angezeigten Werten. Vor der Zustimmung wird nichts gespeichert oder eingebettet. Danach gelten das vorhandene Modell, seine Kosten und die Kontingente. Ist die Einbettung nicht verfügbar, kann die Erinnerung ohne Vektoren gespeichert werden. Dauerhafte Anweisungen werden anfangs angeheftet; die automatische Nutzung bleibt unverändert.",
        "Zu erstellende Erinnerung",
    ),
    "es": ApplicationMemoryCreationCopy(
        "Confirma crear este recuerdo con los valores mostrados. No se guarda ni se calculan embeddings antes de aprobar. Después se usa el modelo existente con sus costes y cuotas. Si el cálculo no está disponible, el recuerdo puede guardarse sin vectores. Las instrucciones permanentes se fijan al crearse; el uso automático no cambia.",
        "Recuerdo a crear",
    ),
    "it": ApplicationMemoryCreationCopy(
        "Conferma questo ricordo con i valori mostrati. Nessun salvataggio o embedding prima dell’approvazione. Poi si usano il modello, i costi e le quote esistenti. Se l’embedding non è disponibile, il ricordo può essere salvato senza vettori. Le istruzioni permanenti vengono fissate alla creazione; l’uso automatico resta invariato.",
        "Ricordo da creare",
    ),
    "zh-CN": ApplicationMemoryCreationCopy(
        "确认按显示的值创建这条记忆。批准前不会保存或计算嵌入向量。批准后使用现有模型及其费用，并检查配额。若向量计算不可用，仍可保存不含向量的记忆。长期指令在创建时固定；记忆自动使用设置保持不变。",
        "待创建的记忆",
    ),
}


APPLICATION_MEMORY_PIN: dict[Language, ApplicationMemoryPinCopy] = {
    "fr": ApplicationMemoryPinCopy(
        "Confirmer l’épinglage ou le désépinglage de cette mémoire exacte. Une mémoire épinglée est protégée de la suppression et de la fusion automatiques. Le désépinglage rétablit les règles de conservation ; les règles et directives conservent leur protection de catégorie. L’usage automatique des mémoires reste inchangé.",
        "Épinglage de la mémoire",
        "Épinglée",
        "Non épinglée",
    ),
    "en": ApplicationMemoryPinCopy(
        "Confirm pinning or unpinning this exact memory. Pinning protects it from automatic deletion and merging. Unpinning restores retention rules; standing instructions retain category protection. Automatic memory use stays unchanged.",
        "Memory pin",
        "Pinned",
        "Unpinned",
    ),
    "de": ApplicationMemoryPinCopy(
        "Bestätigen Sie das Anheften oder Lösen dieser genauen Erinnerung. Angeheftete Erinnerungen sind vor automatischem Löschen und Zusammenführen geschützt. Beim Lösen gelten wieder die Aufbewahrungsregeln; dauerhafte Anweisungen behalten ihren Kategorieschutz. Die automatische Nutzung bleibt unverändert.",
        "Erinnerung anheften",
        "Angeheftet",
        "Nicht angeheftet",
    ),
    "es": ApplicationMemoryPinCopy(
        "Confirma fijar o desfijar este recuerdo exacto. Fijarlo impide su eliminación y fusión automáticas. Desfijarlo restablece las reglas de conservación; las instrucciones permanentes mantienen la protección de su categoría. El uso automático de recuerdos no cambia.",
        "Fijación del recuerdo",
        "Fijado",
        "Sin fijar",
    ),
    "it": ApplicationMemoryPinCopy(
        "Conferma di fissare o rimuovere il fissaggio di questo ricordo esatto. Il fissaggio protegge da eliminazione e unione automatiche. Rimuoverlo ripristina le regole di conservazione; le istruzioni permanenti mantengono la protezione della categoria. L’uso automatico dei ricordi resta invariato.",
        "Fissaggio del ricordo",
        "Fissato",
        "Non fissato",
    ),
    "zh-CN": ApplicationMemoryPinCopy(
        "确认固定或取消固定这条确切的记忆。固定后，记忆不会被自动删除或合并。取消固定会恢复保留规则；长期指令仍受类别保护。记忆的自动使用设置保持不变。",
        "记忆固定状态",
        "已固定",
        "未固定",
    ),
}


APPLICATION_EXPORT_DOWNLOAD: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Confirmer le téléchargement de cette archive complète du compte, contenant vos données personnelles. Aucun fichier n’est transmis avant votre accord. Le navigateur d’origine lance ensuite la demande, une seule fois et avant l’échéance affichée. Une archive changée, supprimée ou expirée impose une nouvelle sélection. LIA peut confirmer la demande, pas l’enregistrement du fichier sur votre appareil.",
        "Archive du compte à télécharger",
    ),
    "en": ApplicationExportCopy(
        "Confirm downloading this complete account archive containing your personal data. No file is transferred before approval. The original browser then starts the request once, before the displayed deadline. A changed, removed or expired archive requires a fresh selection. LIA can confirm the request, not that the file was saved to your device.",
        "Account archive to download",
    ),
    "de": ApplicationExportCopy(
        "Den Download dieses vollständigen Kontoarchivs mit Ihren persönlichen Daten bestätigen. Vor Ihrer Zustimmung wird keine Datei übertragen. Der ursprüngliche Browser startet die Anfrage einmal vor der angezeigten Frist. Geänderte, entfernte oder abgelaufene Archive erfordern eine neue Auswahl. LIA kann die Anfrage bestätigen, nicht das Speichern auf Ihrem Gerät.",
        "Kontoarchiv zum Herunterladen",
    ),
    "es": ApplicationExportCopy(
        "Confirmar la descarga de este archivo completo de la cuenta con tus datos personales. No se transfiere ningún archivo antes de aprobar. El navegador original inicia la solicitud una sola vez antes del plazo mostrado. Un archivo cambiado, eliminado o caducado requiere una nueva selección. LIA puede confirmar la solicitud, no que se haya guardado en tu dispositivo.",
        "Archivo de la cuenta para descargar",
    ),
    "it": ApplicationExportCopy(
        "Confermare il download di questo archivio completo dell'account contenente dati personali. Nessun file viene trasferito prima del consenso. Il browser originale avvia la richiesta una sola volta entro la scadenza mostrata. Un archivio modificato, rimosso o scaduto richiede una nuova selezione. LIA può confermare la richiesta, non il salvataggio sul dispositivo.",
        "Archivio dell'account da scaricare",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认下载包含您个人数据的完整账户归档。未经同意不会传输文件。原浏览器在所示期限前仅发起一次请求。归档已改变、被删除或过期时需要重新选择。LIA可以确认请求，无法确认文件已保存到您的设备。",
        "待下载的账户归档",
    ),
}

APPLICATION_EXPORT_REQUEST: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Demander un export complet du compte après confirmation et réauthentification sécurisée. L’archive contient des données personnelles. Sa préparation est asynchrone ; elle devra être téléchargée depuis les réglages une fois prête.",
        "Demander un export complet du compte",
    ),
    "en": ApplicationExportCopy(
        "Request a full-account export after confirmation and secure reauthentication. The archive contains personal data. Preparation is asynchronous; download it from settings once it is ready.",
        "Request a full-account export",
    ),
    "de": ApplicationExportCopy(
        "Nach Bestätigung und sicherer erneuter Authentifizierung einen vollständigen Kontoexport anfordern. Das Archiv enthält personenbezogene Daten. Die Erstellung erfolgt asynchron; laden Sie es nach Fertigstellung in den Einstellungen herunter.",
        "Vollständigen Kontoexport anfordern",
    ),
    "es": ApplicationExportCopy(
        "Solicitar una exportación completa de la cuenta tras confirmar y volver a autenticarte de forma segura. El archivo contiene datos personales. Su preparación es asíncrona; descárgalo desde los ajustes cuando esté listo.",
        "Solicitar una exportación completa de la cuenta",
    ),
    "it": ApplicationExportCopy(
        "Richiedere un’esportazione completa dell’account dopo la conferma e una nuova autenticazione sicura. L’archivio contiene dati personali. La preparazione è asincrona; scaricalo dalle impostazioni quando è pronto.",
        "Richiedere un’esportazione completa dell’account",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认并完成安全重新认证后，申请完整账户导出。压缩包包含个人数据，将在后台异步生成。就绪后，请从设置页面下载。",
        "申请完整账户导出",
    ),
}


APPLICATION_DRAFT_COPY: dict[Language, ApplicationDraftCopy] = {
    "en": ApplicationDraftCopy(
        "Change application settings",
        "Application settings saved",
        "Change cancelled",
        "Before",
        "After",
    ),
    "fr": ApplicationDraftCopy(
        "Modifier les réglages de l’application",
        "Réglages de l’application enregistrés",
        "Modification annulée",
        "Avant",
        "Après",
    ),
    "de": ApplicationDraftCopy(
        "Anwendungseinstellungen ändern",
        "Anwendungseinstellungen gespeichert",
        "Änderung abgebrochen",
        "Vorher",
        "Nachher",
    ),
    "es": ApplicationDraftCopy(
        "Cambiar ajustes de la aplicación",
        "Ajustes de la aplicación guardados",
        "Cambio cancelado",
        "Antes",
        "Después",
    ),
    "it": ApplicationDraftCopy(
        "Modificare le impostazioni dell’applicazione",
        "Impostazioni dell’applicazione salvate",
        "Modifica annullata",
        "Prima",
        "Dopo",
    ),
    "zh-CN": ApplicationDraftCopy(
        "更改应用设置", "应用设置已保存", "已取消更改", "更改前", "更改后"
    ),
}

APPLICATION_EXPIRY_LABELS: dict[Language, str] = {
    "en": "Valid until",
    "fr": "Valable jusqu’au",
    "de": "Gültig bis",
    "es": "Válido hasta",
    "it": "Valido fino a",
    "zh-CN": "有效期至",
}

APPLICATION_INTERACTION_WAIT: dict[Language, dict[str, str]] = {
    "fr": {
        "secure": "L’action attend votre réauthentification dans l’interface sécurisée.",
        "device": "L’action attend une confirmation d’exécution du navigateur concerné.",
    },
    "en": {
        "secure": "The action awaits your reauthentication in the secure interface.",
        "device": "The action awaits an execution acknowledgement from the addressed browser.",
    },
    "de": {
        "secure": "Die Aktion wartet auf Ihre erneute Anmeldung in der sicheren Oberfläche.",
        "device": "Die Aktion wartet auf eine Ausführungsbestätigung vom betreffenden Browser.",
    },
    "es": {
        "secure": "La acción espera tu reautenticación en la interfaz segura.",
        "device": "La acción espera una confirmación de ejecución del navegador correspondiente.",
    },
    "it": {
        "secure": "L’azione attende la tua riautenticazione nell’interfaccia sicura.",
        "device": "L’azione attende una conferma di esecuzione dal browser interessato.",
    },
    "zh-CN": {
        "secure": "此操作正在等待您在安全界面中重新验证身份。",
        "device": "此操作正在等待指定浏览器确认执行结果。",
    },
}

APPLICATION_WAITING_COUNT: dict[Language, str] = {
    "fr": "{count} interaction(s) en attente",
    "en": "{count} interaction(s) pending",
    "de": "{count} ausstehende Interaktion(en)",
    "es": "{count} interacción(es) pendiente(s)",
    "it": "{count} interazione/i in attesa",
    "zh-CN": "{count} 项交互等待中",
}

APPLICATION_NOOP_MESSAGES: dict[Language, str] = {
    "en": "The requested settings are already applied; no change was made.",
    "fr": "Les réglages demandés sont déjà appliqués ; aucune modification effectuée.",
    "de": "Die gewünschten Einstellungen sind bereits angewendet; keine Änderung vorgenommen.",
    "es": "Los ajustes solicitados ya están aplicados; no se realizó ningún cambio.",
    "it": "Le impostazioni richieste sono già applicate; nessuna modifica effettuata.",
    "zh-CN": "所请求的设置已生效，未进行任何更改。",
}

APPLICATION_UNAVAILABLE: dict[Language, str] = {
    "en": "This proposal is invalid. Request a new preview.",
    "fr": "Cette proposition est invalide. Demande une nouvelle prévisualisation.",
    "de": "Dieser Vorschlag ist ungültig. Fordere eine neue Vorschau an.",
    "es": "Esta propuesta no es válida. Solicita una nueva vista previa.",
    "it": "Questa proposta non è valida. Richiedi una nuova anteprima.",
    "zh-CN": "此提议无效。请重新请求预览。",
}

APPLICATION_CHANNEL_UNLINK: dict[Language, str] = {
    "fr": "Ce rattachement sera supprimé. Ce canal ne permettra plus d’échanger avec LIA ; une nouvelle association depuis les réglages sera nécessaire.",
    "en": "This binding will be removed. This channel will no longer let you talk to LIA; link it again from settings to reconnect.",
    "de": "Diese Verknüpfung wird entfernt. Über diesen Kanal ist kein Austausch mit LIA mehr möglich; verbinden Sie ihn erneut in den Einstellungen.",
    "es": "Se eliminará esta vinculación. Este canal ya no permitirá hablar con LIA; vincúlelo de nuevo desde los ajustes para reconectar.",
    "it": "Questo collegamento verrà rimosso. Il canale non consentirà più di parlare con LIA; collegalo nuovamente dalle impostazioni.",
    "zh-CN": "此绑定将被删除。此渠道将无法再与 LIA 对话；需要在设置中重新关联。",
}

APPLICATION_CONNECTOR_UNLINK: dict[Language, str] = {
    "fr": "Cette connexion locale sera supprimée. Les autres services restent associés et les autorisations chez le fournisseur sont conservées. Une nouvelle association sera nécessaire pour réutiliser ce service dans LIA.",
    "en": "This local connection will be removed. Other services remain linked and provider permissions are retained. Reconnect to use this service in LIA again.",
    "de": "Diese lokale Verbindung wird entfernt. Andere Dienste bleiben verbunden; Berechtigungen beim Anbieter bleiben bestehen. Verbinden Sie den Dienst erneut, um ihn wieder in LIA zu nutzen.",
    "es": "Se eliminará esta conexión local. Los otros servicios siguen vinculados y se conservan los permisos del proveedor. Vuelve a conectar el servicio para usarlo en LIA.",
    "it": "Questo collegamento locale verrà rimosso. Gli altri servizi restano collegati e le autorizzazioni del fornitore sono mantenute. Ricollega il servizio per usarlo di nuovo in LIA.",
    "zh-CN": "此本地连接将被删除。其他服务保持关联，服务提供商的权限将保留。需要重新关联才能在 LIA 中再次使用此服务。",
}

_APPLICATION_FIELD_NAMES = (
    "timezone",
    "language",
    "personality_id",
    "theme",
    "color_theme",
    "font_family",
    "font_size",
    "image_generation_enabled",
    "image_generation_default_quality",
    "image_generation_default_size",
    "image_generation_output_format",
    "image_generation_prompt_enhancement",
    "exchange_rhythm",
)

APPLICATION_FIELD_LABELS: dict[Language, dict[str, str]] = {
    "en": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "Timezone",
                "Language",
                "Personality",
                "Theme",
                "Colour theme",
                "Font",
                "Font size (px)",
                "Image generation",
                "Image quality",
                "Image size",
                "Image format",
                "Image prompt enhancement",
                "Exchange rhythm",
            ),
            strict=True,
        )
    ),
    "fr": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "Fuseau horaire",
                "Langue",
                "Personnalité",
                "Thème",
                "Couleur du thème",
                "Police",
                "Taille de police (px)",
                "Génération d’images",
                "Qualité d’image",
                "Taille d’image",
                "Format d’image",
                "Amélioration du prompt d’image",
                "Rythme des échanges",
            ),
            strict=True,
        )
    ),
    "de": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "Zeitzone",
                "Sprache",
                "Persönlichkeit",
                "Design",
                "Designfarbe",
                "Schrift",
                "Schriftgröße (px)",
                "Bilderzeugung",
                "Bildqualität",
                "Bildgröße",
                "Bildformat",
                "Bildprompt-Verbesserung",
                "Gesprächsrhythmus",
            ),
            strict=True,
        )
    ),
    "es": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "Zona horaria",
                "Idioma",
                "Personalidad",
                "Tema",
                "Color del tema",
                "Fuente",
                "Tamaño de fuente (px)",
                "Generación de imágenes",
                "Calidad de imagen",
                "Tamaño de imagen",
                "Formato de imagen",
                "Mejora del prompt de imagen",
                "Ritmo de conversación",
            ),
            strict=True,
        )
    ),
    "it": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "Fuso orario",
                "Lingua",
                "Personalità",
                "Tema",
                "Colore del tema",
                "Carattere",
                "Dimensione del carattere (px)",
                "Generazione di immagini",
                "Qualità dell’immagine",
                "Dimensione dell’immagine",
                "Formato dell’immagine",
                "Miglioramento del prompt",
                "Ritmo della conversazione",
            ),
            strict=True,
        )
    ),
    "zh-CN": dict(
        zip(
            _APPLICATION_FIELD_NAMES,
            (
                "时区",
                "语言",
                "个性",
                "主题",
                "主题颜色",
                "字体",
                "字号（像素）",
                "图像生成",
                "图像质量",
                "图像尺寸",
                "图像格式",
                "图像提示词优化",
                "交流节奏",
            ),
            strict=True,
        )
    ),
}

_ASSISTANT_FIELD_NAMES = (
    "memory_enabled",
    "health_metrics_agents_enabled",
    "execution_mode",
    "use_last_known_location",
    "voice_enabled",
    "voice_mode_enabled",
    "voice_stt_mode",
    "tokens_display_enabled",
    "login_notifications_enabled",
    "onboarding_completed",
    "debug_panel_enabled",
    "response_display_mode",
)
_ASSISTANT_FIELD_COPY: dict[Language, tuple[str, ...]] = {
    "en": (
        "Long-term memory",
        "Health data use",
        "Execution mode",
        "Saved location use",
        "Spoken responses",
        "Voice input",
        "Speech recognition mode",
        "Token display",
        "Login notifications",
        "Onboarding completed",
        "Debug panel",
        "Response display mode",
    ),
    "fr": (
        "Mémoire à long terme",
        "Utilisation des données de santé",
        "Mode d’exécution",
        "Utilisation de la position enregistrée",
        "Réponses vocales",
        "Saisie vocale",
        "Mode de reconnaissance vocale",
        "Affichage des tokens",
        "Notifications de connexion",
        "Parcours de bienvenue terminé",
        "Panneau de diagnostic",
        "Mode d’affichage des réponses",
    ),
    "de": (
        "Langzeitgedächtnis",
        "Nutzung von Gesundheitsdaten",
        "Ausführungsmodus",
        "Nutzung des gespeicherten Standorts",
        "Gesprochene Antworten",
        "Spracheingabe",
        "Spracherkennungsmodus",
        "Token-Anzeige",
        "Anmeldebenachrichtigungen",
        "Einführung abgeschlossen",
        "Diagnosebereich",
        "Antwortanzeigemodus",
    ),
    "es": (
        "Memoria a largo plazo",
        "Uso de datos de salud",
        "Modo de ejecución",
        "Uso de ubicación guardada",
        "Respuestas habladas",
        "Entrada de voz",
        "Modo de reconocimiento de voz",
        "Visualización de tokens",
        "Notificaciones de inicio de sesión",
        "Bienvenida completada",
        "Panel de diagnóstico",
        "Modo de visualización de respuestas",
    ),
    "it": (
        "Memoria a lungo termine",
        "Uso dei dati sanitari",
        "Modalità di esecuzione",
        "Uso della posizione salvata",
        "Risposte vocali",
        "Input vocale",
        "Modalità di riconoscimento vocale",
        "Visualizzazione dei token",
        "Notifiche di accesso",
        "Introduzione completata",
        "Pannello diagnostico",
        "Modalità di visualizzazione delle risposte",
    ),
    "zh-CN": (
        "长期记忆",
        "健康数据使用",
        "执行模式",
        "已保存位置使用",
        "语音回复",
        "语音输入",
        "语音识别模式",
        "令牌显示",
        "登录通知",
        "引导已完成",
        "诊断面板",
        "回复显示模式",
    ),
}
for _language, _copy in _ASSISTANT_FIELD_COPY.items():
    APPLICATION_FIELD_LABELS[_language].update(zip(_ASSISTANT_FIELD_NAMES, _copy, strict=True))

APPLICATION_LOCATION_CLEAR: dict[Language, str] = {
    "en": "The saved location will be removed when this change is confirmed.",
    "fr": "La position enregistrée sera supprimée à la confirmation de cette modification.",
    "de": "Der gespeicherte Standort wird bei Bestätigung dieser Änderung entfernt.",
    "es": "La ubicación guardada se eliminará al confirmar este cambio.",
    "it": "La posizione salvata verrà rimossa alla conferma di questa modifica.",
    "zh-CN": "确认此更改后，将删除已保存的位置。",
}

_LAYOUT_FIELD_NAMES = ("briefing_preferences", "chat_shortcuts", "settings_shortcuts")
_LAYOUT_FIELD_COPY: dict[Language, tuple[str, ...]] = {
    "en": ("Briefing grid", "Chat shortcuts", "Pinned settings sections"),
    "fr": ("Grille du briefing", "Raccourcis du chat", "Sections de réglages épinglées"),
    "de": ("Briefing-Raster", "Chat-Kurzbefehle", "Angeheftete Einstellungsbereiche"),
    "es": ("Cuadrícula del resumen", "Atajos del chat", "Secciones de ajustes fijadas"),
    "it": ("Griglia del briefing", "Scorciatoie della chat", "Sezioni delle impostazioni fissate"),
    "zh-CN": ("简报网格", "聊天快捷指令", "固定的设置栏目"),
}
for _language, _copy in _LAYOUT_FIELD_COPY.items():
    APPLICATION_FIELD_LABELS[_language].update(zip(_LAYOUT_FIELD_NAMES, _copy, strict=True))

_LOCATION_FIELD_COPY: dict[Language, tuple[str, str]] = {
    "en": ("Home address", "Saved last-known position"),
    "fr": ("Adresse du domicile", "Dernière position enregistrée"),
    "de": ("Heimatadresse", "Zuletzt gespeicherter Standort"),
    "es": ("Dirección del domicilio", "Última posición guardada"),
    "it": ("Indirizzo di casa", "Ultima posizione salvata"),
    "zh-CN": ("家庭地址", "最近保存的位置"),
}
for _language, _copy in _LOCATION_FIELD_COPY.items():
    APPLICATION_FIELD_LABELS[_language].update(
        zip(("home_location", "last_known_location"), _copy, strict=True)
    )

_HEARTBEAT_FIELDS = (
    "heartbeat_enabled",
    "heartbeat_notify_start_hour",
    "heartbeat_notify_end_hour",
    "heartbeat_disabled_sources",
    "moment_kinds_disabled",
)
_HEARTBEAT_COPY: dict[Language, tuple[str, ...]] = {
    "fr": (
        "Notifications proactives",
        "Début de la plage de notification",
        "Fin de la plage de notification",
        "Sources proactives refusées",
        "Types de moments refusés",
    ),
    "en": (
        "Proactive notifications",
        "Notification window start",
        "Notification window end",
        "Refused proactive sources",
        "Refused moment kinds",
    ),
    "de": (
        "Proaktive Benachrichtigungen",
        "Beginn des Benachrichtigungszeitraums",
        "Ende des Benachrichtigungszeitraums",
        "Abgelehnte proaktive Quellen",
        "Abgelehnte Momenttypen",
    ),
    "es": (
        "Notificaciones proactivas",
        "Inicio del horario de notificación",
        "Fin del horario de notificación",
        "Fuentes proactivas rechazadas",
        "Tipos de momentos rechazados",
    ),
    "it": (
        "Notifiche proattive",
        "Inizio della fascia di notifica",
        "Fine della fascia di notifica",
        "Fonti proattive rifiutate",
        "Tipi di momenti rifiutati",
    ),
    "zh-CN": (
        "主动通知",
        "通知时段开始",
        "通知时段结束",
        "已拒绝的主动信息来源",
        "已拒绝的时刻类型",
    ),
}
for _language, _copy in _HEARTBEAT_COPY.items():
    APPLICATION_FIELD_LABELS[_language].update(zip(_HEARTBEAT_FIELDS, _copy, strict=True))

_INTEREST_SETTING_FIELDS = (
    "interests_enabled",
    "interests_notify_start_hour",
    "interests_notify_end_hour",
    "interests_notify_min_per_day",
    "interests_notify_max_per_day",
)
_INTEREST_SETTINGS_COPY: dict[Language, tuple[str, ...]] = {
    "fr": (
        "Notifications d’intérêt",
        "Début de la plage (heure locale)",
        "Fin de la plage (heure locale)",
        "Minimum enregistré par jour",
        "Maximum enregistré par jour",
    ),
    "en": (
        "Interest notifications",
        "Window start (local hour)",
        "Window end (local hour)",
        "Saved daily minimum",
        "Saved daily maximum",
    ),
    "de": (
        "Interessenbenachrichtigungen",
        "Beginn (Ortszeit)",
        "Ende (Ortszeit)",
        "Gespeichertes Tagesminimum",
        "Gespeichertes Tagesmaximum",
    ),
    "es": (
        "Notificaciones de intereses",
        "Inicio (hora local)",
        "Fin (hora local)",
        "Mínimo diario guardado",
        "Máximo diario guardado",
    ),
    "it": (
        "Notifiche degli interessi",
        "Inizio (ora locale)",
        "Fine (ora locale)",
        "Minimo giornaliero salvato",
        "Massimo giornaliero salvato",
    ),
    "zh-CN": (
        "兴趣通知",
        "开始时间（当地小时）",
        "结束时间（当地小时）",
        "保存的每日最小次数",
        "保存的每日最大次数",
    ),
}
for _language, _copy in _INTEREST_SETTINGS_COPY.items():
    APPLICATION_FIELD_LABELS[_language].update(zip(_INTEREST_SETTING_FIELDS, _copy, strict=True))

_CHANNEL_COPY: dict[Language, str] = {
    "fr": "Rattachement du canal",
    "en": "Channel binding",
    "de": "Kanalverknüpfung",
    "es": "Vinculación del canal",
    "it": "Collegamento del canale",
    "zh-CN": "消息渠道绑定",
}
for _language, _channel_label in _CHANNEL_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["channel_binding"] = _channel_label

_CONNECTOR_COPY: dict[Language, str] = {
    "fr": "Préférences du connecteur",
    "en": "Connector preferences",
    "de": "Konnektoreinstellungen",
    "es": "Preferencias del conector",
    "it": "Preferenze del connettore",
    "zh-CN": "连接器偏好设置",
}
for _language, _connector_label in _CONNECTOR_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["connector_preferences"] = _connector_label

_CONNECTION_COPY: dict[Language, str] = {
    "fr": "Connexion à déconnecter",
    "en": "Connection to disconnect",
    "de": "Zu trennende Verbindung",
    "es": "Conexión que se desconectará",
    "it": "Connessione da scollegare",
    "zh-CN": "要断开的连接",
}
for _language, _connection_label in _CONNECTION_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["connector_to_disconnect"] = _connection_label

_LIVE_REFLEX_COPY: dict[Language, str] = {
    "fr": "Réglages de conversation Live",
    "en": "Live conversation settings",
    "de": "Live-Gesprächseinstellungen",
    "es": "Ajustes de conversación Live",
    "it": "Impostazioni della conversazione Live",
    "zh-CN": "实时对话设置",
}
for _language, _live_label in _LIVE_REFLEX_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["live_reflexes"] = _live_label

APPLICATION_LIVE_PREFERENCES: dict[Language, str] = {
    "fr": "Ces réglages s'appliqueront aux prochaines sessions Live. La session en cours et le choix du fournisseur restent inchangés.",
    "en": "These settings apply to future Live sessions. The current session and provider selection stay unchanged.",
    "de": "Diese Einstellungen gelten für künftige Live-Sitzungen. Die laufende Sitzung und die Anbieterauswahl bleiben unverändert.",
    "es": "Estos ajustes se aplicarán a las próximas sesiones Live. La sesión actual y el proveedor seleccionado no cambian.",
    "it": "Queste impostazioni si applicano alle future sessioni Live. La sessione in corso e il fornitore selezionato non cambiano.",
    "zh-CN": "这些设置适用于之后的实时对话。当前会话和已选择的提供商保持不变。",
}

APPLICATION_LIVE_CONNECTOR: dict[Language, str] = {
    "fr": "Le fournisseur choisi sera utilisé pour les prochaines sessions. La validation ouvre une courte connexion sur votre clé et peut consommer votre quota fournisseur. Le plafond est indicatif par session. Une session en cours conserve son modèle ; une sortie de veille peut relire ses réglages enregistrés.",
    "en": "The selected provider will be used for future sessions. Validation opens a short connection using your key and may consume provider quota. The ceiling is indicative per session. An existing session keeps its model; waking from standby may reread its saved settings.",
    "de": "Der gewählte Anbieter wird für künftige Sitzungen verwendet. Die Prüfung öffnet eine kurze Verbindung mit Ihrem Schlüssel und kann Anbieterquoten verbrauchen. Das Limit gilt indikativ pro Sitzung. Eine laufende Sitzung behält ihr Modell; beim Aufwachen können gespeicherte Einstellungen neu gelesen werden.",
    "es": "El proveedor elegido se usará en futuras sesiones. La validación abre una conexión breve con tu clave y puede consumir cuota del proveedor. El límite es orientativo por sesión. Una sesión existente conserva su modelo; al salir de espera puede releer sus ajustes guardados.",
    "it": "Il fornitore scelto verrà usato nelle future sessioni. La verifica apre una breve connessione con la tua chiave e può consumare quota del fornitore. Il limite è indicativo per sessione. Una sessione esistente conserva il modello; al risveglio può rileggere le impostazioni salvate.",
    "zh-CN": "所选提供商用于后续会话。验证会使用您的密钥建立短暂连接，可能消耗提供商配额。费用上限为每次会话的估算限制。已有会话保留其模型；从待机唤醒时可能重新读取已保存的设置。",
}
for _language in APPLICATION_LIVE_CONNECTOR:
    APPLICATION_FIELD_LABELS[_language]["live_connector_settings"] = _LIVE_REFLEX_COPY[_language]

_NOTIFICATION_DEVICE_COPY: dict[Language, str] = {
    "fr": "Appareil de notification à retirer",
    "en": "Notification device to remove",
    "de": "Zu entfernendes Benachrichtigungsgerät",
    "es": "Dispositivo de notificaciones que se eliminará",
    "it": "Dispositivo di notifica da rimuovere",
    "zh-CN": "要移除的通知设备",
}
for _language, _device_label in _NOTIFICATION_DEVICE_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["notification_device_to_remove"] = _device_label

APPLICATION_NOTIFICATION_DEVICE_REMOVE: dict[Language, str] = {
    "fr": "Cette action retire l'inscription de cet appareil aux notifications du serveur. La permission du navigateur ou du système reste inchangée. Réactivez les notifications sur cet appareil pour le réinscrire.",
    "en": "This removes the device's server notification registration. Browser or system permission stays unchanged. Enable notifications on that device again to register it.",
    "de": "Diese Aktion entfernt die Registrierung des Geräts für Serverbenachrichtigungen. Die Browser- oder Systemberechtigung bleibt unverändert. Aktivieren Sie Benachrichtigungen auf diesem Gerät erneut, um es zu registrieren.",
    "es": "Se elimina el registro del dispositivo para recibir notificaciones del servidor. El permiso del navegador o del sistema no cambia. Activa de nuevo las notificaciones en ese dispositivo para registrarlo.",
    "it": "Questa azione rimuove la registrazione del dispositivo alle notifiche del server. Il permesso del browser o del sistema non cambia. Riattiva le notifiche su quel dispositivo per registrarlo.",
    "zh-CN": "此操作移除该设备的服务器通知注册。浏览器或系统权限保持不变。请在该设备上重新启用通知以再次注册。",
}

_SHARED_MCP_COPY: dict[Language, str] = {
    "fr": "Serveur MCP partagé pour ce compte",
    "en": "Shared MCP server for this account",
    "de": "Gemeinsamer MCP-Server für dieses Konto",
    "es": "Servidor MCP compartido para esta cuenta",
    "it": "Server MCP condiviso per questo account",
    "zh-CN": "此账户的共享 MCP 服务器",
}
for _language, _shared_mcp_label in _SHARED_MCP_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["shared_mcp_server"] = _shared_mcp_label

_PHONE_PREFERENCES_COPY: dict[Language, str] = {
    "fr": "Réglages de contexte et de mode d’appel",
    "en": "Call context and mode settings",
    "de": "Anrufkontext und Moduseinstellungen",
    "es": "Ajustes de contexto y modo de llamada",
    "it": "Impostazioni del contesto e della modalità di chiamata",
    "zh-CN": "通话上下文和模式设置",
}
for _language, _phone_label in _PHONE_PREFERENCES_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["phone_preferences"] = _phone_label

APPLICATION_PHONE_PREFERENCES: dict[Language, str] = {
    "fr": "Le mode et le consentement de contexte concernent les prochains appels personnels. Les domaines désactivés sont refusés dès la prochaine consultation téléphonique ou vocale directe dans le navigateur, y compris en session. Une liste vide active tous les domaines proposés ; les futurs domaines suivent le même principe.",
    "en": "Mode and context consent apply to future owner calls. Disabled domains are refused at the next phone or direct-browser lookup, including during a session. An empty list enables all offered domains; future domains follow the same policy.",
    "de": "Modus und Kontextzustimmung gelten für künftige eigene Anrufe. Deaktivierte Bereiche werden ab der nächsten Telefon- oder direkten Browserabfrage abgelehnt, auch während einer Sitzung. Eine leere Liste aktiviert alle angebotenen Bereiche; künftige folgen derselben Regel.",
    "es": "El modo y el consentimiento de contexto se aplican a futuras llamadas personales. Los dominios desactivados se rechazan desde la próxima consulta telefónica o de voz directa del navegador, incluso durante una sesión. Una lista vacía activa todos los dominios ofrecidos; los futuros siguen la misma regla.",
    "it": "Modalità e consenso al contesto valgono per le future chiamate personali. I domini disattivati vengono rifiutati dalla prossima consultazione telefonica o vocale diretta nel browser, anche durante una sessione. Un elenco vuoto attiva tutti i domini disponibili; quelli futuri seguono la stessa regola.",
    "zh-CN": "模式和上下文授权适用于之后的本人通话。禁用的领域从下一次电话或浏览器直接语音查询起被拒绝，包括正在进行的会话。空列表启用所有提供的领域；未来的领域遵循相同规则。",
}

_PHONE_NUMBER_COPY: dict[Language, str] = {
    "fr": "Numéro personnel déclaré",
    "en": "Declared personal phone number",
    "de": "Angegebene persönliche Telefonnummer",
    "es": "Número de teléfono personal declarado",
    "it": "Numero di telefono personale dichiarato",
    "zh-CN": "已声明的本人电话号码",
}
for _language, _number_label in _PHONE_NUMBER_COPY.items():
    APPLICATION_FIELD_LABELS[_language]["phone_number"] = _number_label

APPLICATION_PHONE_NUMBER: dict[Language, str] = {
    "fr": "Le numéro affiché est celui qui sera enregistré après confirmation. Un changement ou un effacement retire sa vérification ; le même numéro la conserve. Cette action ne lance aucun appel et ne vérifie pas le numéro. Elle concerne les futurs appels personnels ; les appels en cours continuent.",
    "en": "The displayed number is saved after confirmation. Changing or clearing it removes verification; the same number keeps it. This action places no call and does not verify ownership. It applies to future owner calls; running calls continue.",
    "de": "Die angezeigte Nummer wird nach Bestätigung gespeichert. Eine Änderung oder Löschung entfernt die Verifizierung; dieselbe Nummer behält sie. Diese Aktion startet keinen Anruf und bestätigt keine Inhaberschaft. Sie gilt für künftige eigene Anrufe; laufende Anrufe werden fortgesetzt.",
    "es": "El número mostrado se guarda tras la confirmación. Cambiarlo o borrarlo elimina la verificación; el mismo número la conserva. Esta acción no llama ni verifica la titularidad. Se aplica a futuras llamadas personales; las llamadas en curso continúan.",
    "it": "Il numero mostrato viene salvato dopo la conferma. Modificarlo o eliminarlo rimuove la verifica; lo stesso numero la conserva. Questa azione non chiama né verifica la titolarità. Vale per le future chiamate personali; quelle in corso continuano.",
    "zh-CN": "确认后将保存显示的号码。更改或清除号码会撤销验证；相同号码保留验证。此操作不会拨打电话，也不会验证号码归属。它适用于之后的本人通话；正在进行的通话继续。",
}

APPLICATION_NUMBER_STATUS: dict[Language, dict[str, str]] = {
    "fr": {
        "unset": "Aucun numéro déclaré",
        "unreadable": "Numéro enregistré illisible",
        "verified": "Vérifié",
        "unverified": "Non vérifié",
    },
    "en": {
        "unset": "No declared number",
        "unreadable": "Stored number unreadable",
        "verified": "Verified",
        "unverified": "Not verified",
    },
    "de": {
        "unset": "Keine angegebene Nummer",
        "unreadable": "Gespeicherte Nummer nicht lesbar",
        "verified": "Verifiziert",
        "unverified": "Nicht verifiziert",
    },
    "es": {
        "unset": "Ningún número declarado",
        "unreadable": "Número guardado ilegible",
        "verified": "Verificado",
        "unverified": "No verificado",
    },
    "it": {
        "unset": "Nessun numero dichiarato",
        "unreadable": "Numero salvato illeggibile",
        "verified": "Verificato",
        "unverified": "Non verificato",
    },
    "zh-CN": {
        "unset": "未声明号码",
        "unreadable": "保存的号码无法读取",
        "verified": "已验证",
        "unverified": "未验证",
    },
}

APPLICATION_SESSION_REVOKE: dict[Language, str] = {
    "fr": "Cet appareil sera déconnecté. Si c'est votre session courante, la réponse peut être interrompue. Les tâches détachées continuent et les notifications de l'appareil restent enregistrées.",
    "en": "This device will be signed out. If it is your current session, the reply may be interrupted. Detached jobs continue and the device's notification registration remains.",
    "de": "Dieses Gerät wird abgemeldet. Bei Ihrer aktuellen Sitzung kann die Antwort unterbrochen werden. Hintergrundaufträge laufen weiter; die Benachrichtigungsregistrierung des Geräts bleibt bestehen.",
    "es": "Este dispositivo cerrará la sesión. Si es tu sesión actual, la respuesta puede interrumpirse. Las tareas en segundo plano continúan y se conserva el registro de notificaciones del dispositivo.",
    "it": "Questo dispositivo verrà disconnesso. Se è la sessione corrente, la risposta potrebbe interrompersi. Le attività in background continuano e la registrazione delle notifiche del dispositivo rimane.",
    "zh-CN": "此设备将退出登录。如果这是当前会话，回复可能会中断。后台任务继续运行，设备的通知注册将保留。",
}
APPLICATION_SESSION_CLOSED: dict[Language, str] = {
    "fr": "Session fermée",
    "en": "Session closed",
    "de": "Sitzung beendet",
    "es": "Sesión cerrada",
    "it": "Sessione chiusa",
    "zh-CN": "会话已关闭",
}
_SESSION_FIELD_LABELS: dict[Language, str] = {
    "fr": "Session à déconnecter",
    "en": "Session to sign out",
    "de": "Abzumeldende Sitzung",
    "es": "Sesión que se cerrará",
    "it": "Sessione da disconnettere",
    "zh-CN": "要退出的会话",
}
for _language, _session_label in _SESSION_FIELD_LABELS.items():
    APPLICATION_FIELD_LABELS[_language]["session_to_revoke"] = _session_label


class ApplicationFleetCopy(NamedTuple):
    note: str
    count_label: str
    current: str


APPLICATION_OTHER_SESSIONS: dict[Language, ApplicationFleetCopy] = {
    "fr": ApplicationFleetCopy(
        "Déconnecter toutes les autres sessions recensées dans cette proposition, après réauthentification sécurisée. La session actuelle est conservée. Les sessions ouvertes ensuite sont exclues ; celles qui ont déjà expiré ne sont pas affectées. Les tâches détachées continuent et les appareils restent inscrits aux notifications.",
        "Sessions à déconnecter",
        "Session actuelle conservée",
    ),
    "en": ApplicationFleetCopy(
        "Sign out all other sessions recorded in this proposal after secure reauthentication. The current session is kept. Sessions opened later are excluded; already expired sessions are unaffected. Detached jobs continue and device notification registrations remain.",
        "Sessions to sign out",
        "Current session kept",
    ),
    "de": ApplicationFleetCopy(
        "Alle anderen in diesem Vorschlag erfassten Sitzungen nach sicherer erneuter Authentifizierung abmelden. Die aktuelle Sitzung bleibt bestehen. Später eröffnete Sitzungen sind ausgenommen; bereits abgelaufene Sitzungen bleiben unberührt. Hintergrundaufträge laufen weiter; die Benachrichtigungsregistrierungen bleiben bestehen.",
        "Abzumeldende Sitzungen",
        "Beibehaltene aktuelle Sitzung",
    ),
    "es": ApplicationFleetCopy(
        "Cerrar todas las demás sesiones registradas en esta propuesta tras volver a autenticarte de forma segura. Se conserva la sesión actual. Se excluyen las sesiones abiertas después; las ya caducadas no se ven afectadas. Las tareas en segundo plano continúan y se conservan los registros de notificaciones.",
        "Sesiones que se cerrarán",
        "Sesión actual conservada",
    ),
    "it": ApplicationFleetCopy(
        "Chiudere tutte le altre sessioni registrate in questa proposta dopo una nuova autenticazione sicura. La sessione corrente viene conservata. Le sessioni aperte in seguito sono escluse; quelle già scadute non vengono modificate. Le attività in background continuano e le registrazioni delle notifiche rimangono.",
        "Sessioni da disconnettere",
        "Sessione corrente conservata",
    ),
    "zh-CN": ApplicationFleetCopy(
        "完成安全重新认证后，退出此提案中记录的所有其他会话。保留当前会话，不包括之后新建的会话，已过期的会话不受影响。后台任务继续运行，设备通知注册保持不变。",
        "要退出的会话数",
        "保留的当前会话",
    ),
}


class ApplicationRoutineCopy(NamedTuple):
    note: str
    title: str
    enabled: str
    disabled: str


APPLICATION_ROUTINE_STATE: dict[Language, ApplicationRoutineCopy] = {
    "fr": ApplicationRoutineCopy(
        "La pause empêche les prochains déclenchements ; une exécution en cours se termine. L’activation reprend selon la configuration existante et peut entraîner des coûts LLM. La réservation d’une exécution en cours est conservée.",
        "Automatisation",
        "Activée",
        "En pause",
    ),
    "en": ApplicationRoutineCopy(
        "Pausing prevents future triggers; a running execution finishes. Enabling resumes the existing configuration and may incur LLM costs. A running execution reservation is preserved.",
        "Routine",
        "Enabled",
        "Paused",
    ),
    "de": ApplicationRoutineCopy(
        "Eine Pause verhindert künftige Auslösungen; eine laufende Ausführung endet regulär. Die Aktivierung setzt die bestehende Konfiguration fort und kann LLM-Kosten verursachen. Die Reservierung einer laufenden Ausführung bleibt bestehen.",
        "Routine",
        "Aktiviert",
        "Pausiert",
    ),
    "es": ApplicationRoutineCopy(
        "La pausa impide futuras activaciones; una ejecución en curso termina. La activación reanuda la configuración existente y puede generar costes de LLM. Se conserva la reserva de una ejecución en curso.",
        "Automatización",
        "Activada",
        "En pausa",
    ),
    "it": ApplicationRoutineCopy(
        "La pausa impedisce le attivazioni future; un’esecuzione in corso termina. L’attivazione riprende la configurazione esistente e può comportare costi LLM. La prenotazione di un’esecuzione in corso viene conservata.",
        "Automazione",
        "Attiva",
        "In pausa",
    ),
    "zh-CN": ApplicationRoutineCopy(
        "暂停可阻止未来触发，正在运行的执行会完成。启用会按现有配置恢复，可能产生 LLM 费用。正在运行的执行保留其预留状态。",
        "自动任务",
        "已启用",
        "已暂停",
    ),
}

APPLICATION_REMINDER_UPDATE: dict[Language, str] = {
    "fr": "Modifier ce rappel après confirmation selon les réglages affichés avant et après. Le texte seul conserve le calendrier et le fuseau existants. Une récurrence modifiée repart du premier déclenchement affiché. Si le rappel change, est en traitement ou si cette heure passe, une nouvelle confirmation est nécessaire. Les notifications conservent leurs coûts LLM comptabilisés et les quotas existants.",
    "en": "Change this reminder after confirmation using the displayed before and after settings. Content-only edits preserve the existing schedule and timezone. An edited recurrence starts at the displayed first trigger. If the reminder changes, is processing or that time passes, a new confirmation is required. Notifications retain accounted LLM costs and existing quotas.",
    "de": "Diese Erinnerung nach Bestätigung gemäß den angezeigten Einstellungen vorher und nachher ändern. Reine Textänderungen behalten Zeitplan und Zeitzone bei. Eine geänderte Wiederholung beginnt zum angezeigten ersten Termin. Bei Änderungen, laufender Verarbeitung oder überschrittenem Termin ist eine neue Bestätigung erforderlich. Benachrichtigungen behalten ihre erfassten LLM-Kosten und geltenden Kontingente.",
    "es": "Modificar este recordatorio tras confirmar los ajustes mostrados antes y después. Cambiar solo el texto conserva el calendario y la zona horaria. Una recurrencia modificada comienza en la primera activación mostrada. Si cambia, se está procesando o pasa esa hora, se requiere una nueva confirmación. Las notificaciones mantienen sus costes LLM contabilizados y las cuotas existentes.",
    "it": "Modificare questo promemoria dopo la conferma delle impostazioni mostrate prima e dopo. Il solo testo conserva calendario e fuso orario. Una ricorrenza modificata inizia dalla prima attivazione mostrata. Se cambia, è in elaborazione o l'ora passa, occorre una nuova conferma. Le notifiche mantengono costi LLM contabilizzati e quote esistenti.",
    "zh-CN": "确认后按所显示的修改前后设置更改此提醒。仅修改内容会保留原有日程和时区。更改重复规则后从所显示的首次触发时间开始。如果提醒已改变、正在处理或该时间已过，需要重新确认。通知仍遵循现有的LLM费用记录与配额。",
}

APPLICATION_REMINDER_REMOVAL: dict[Language, str] = {
    "fr": "Supprimer ce rappel après confirmation, y compris toutes ses occurrences restantes. Un rappel déjà en traitement ou dont les réglages ont changé exige une nouvelle sélection. Une notification déjà envoyée ne peut pas être rappelée.",
    "en": "Delete this reminder after confirmation, including all remaining occurrences. A reminder already processing or with changed settings requires a fresh selection. A notification already delivered cannot be recalled.",
    "de": "Diese Erinnerung nach Bestätigung einschließlich aller verbleibenden Termine löschen. Eine bereits verarbeitete Erinnerung oder geänderte Einstellungen erfordern eine neue Auswahl. Eine zugestellte Benachrichtigung kann nicht zurückgerufen werden.",
    "es": "Eliminar este recordatorio tras confirmar, incluidas todas las activaciones restantes. Si ya se está procesando o sus ajustes han cambiado, se requiere una nueva selección. Una notificación enviada no se puede retirar.",
    "it": "Eliminare questo promemoria dopo la conferma, incluse tutte le occorrenze restanti. Se è già in elaborazione o le impostazioni sono cambiate, occorre una nuova selezione. Una notifica già inviata non può essere ritirata.",
    "zh-CN": "确认后删除此提醒及其所有剩余触发次数。已在处理或设置发生变化的提醒需要重新选择。已发送的通知无法撤回。",
}

APPLICATION_REMINDER_CREATION: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Créer ce rappel après confirmation, avec le contenu, le fuseau et le premier déclenchement affichés. Aucun rappel n’est créé avant votre accord. Une heure dépassée impose une nouvelle confirmation. À la fin de ses occurrences, le rappel est supprimé. Les notifications peuvent consommer des tokens LLM, comptabilisés et soumis aux quotas existants.",
        "Paramètres du rappel",
    ),
    "en": ApplicationExportCopy(
        "Create this reminder after confirmation, using the displayed content, timezone and first trigger. No reminder is created before approval. An elapsed trigger requires fresh confirmation. After its final occurrence, the reminder is deleted. Notifications may consume LLM tokens, accounted for and subject to existing quotas.",
        "Reminder settings",
    ),
    "de": ApplicationExportCopy(
        "Diese Erinnerung nach Bestätigung mit dem angezeigten Inhalt, der Zeitzone und der ersten Auslösung erstellen. Vor Ihrer Zustimmung wird nichts erstellt. Eine verstrichene Auslösung erfordert eine neue Bestätigung. Nach dem letzten Termin wird die Erinnerung gelöscht. Benachrichtigungen können LLM-Tokens verbrauchen, die erfasst werden und bestehenden Kontingenten unterliegen.",
        "Erinnerungseinstellungen",
    ),
    "es": ApplicationExportCopy(
        "Crear este recordatorio tras confirmar, con el contenido, la zona horaria y la primera activación mostrados. No se crea antes de aprobar. Una hora vencida exige una nueva confirmación. Tras la última activación, se elimina el recordatorio. Las notificaciones pueden consumir tokens LLM, contabilizados y sujetos a las cuotas existentes.",
        "Ajustes del recordatorio",
    ),
    "it": ApplicationExportCopy(
        "Creare questo promemoria dopo la conferma, con contenuto, fuso orario e prima scadenza mostrati. Non viene creato prima dell’approvazione. Una scadenza trascorsa richiede una nuova conferma. Dopo l’ultima occorrenza, il promemoria viene eliminato. Le notifiche possono consumare token LLM, contabilizzati e soggetti alle quote esistenti.",
        "Impostazioni del promemoria",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后按显示的内容、时区和首次触发时间创建提醒。批准前不会创建。触发时间已过时需要重新确认。最后一次触发后，提醒将被删除。通知可能消耗 LLM 令牌，相关用量会计入现有配额。",
        "提醒设置",
    ),
}

APPLICATION_ROUTINE_CREATION: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Créer cette automatisation active après confirmation. Aucun lancement immédiat. Les prochains déclenchements suivent ces paramètres, notamment le choix d’approbation préalable, et peuvent entraîner des coûts LLM soumis aux quotas existants.",
        "Paramètres de l’automatisation",
    ),
    "en": ApplicationExportCopy(
        "Create this enabled routine after confirmation. No immediate run. Future triggers follow these settings, including the prior-approval choice, and may incur LLM costs subject to existing quotas.",
        "Routine settings",
    ),
    "de": ApplicationExportCopy(
        "Diese aktive Routine nach Bestätigung erstellen. Kein sofortiger Lauf. Künftige Auslösungen folgen diesen Einstellungen einschließlich der vorherigen Genehmigung und können LLM-Kosten innerhalb der bestehenden Kontingente verursachen.",
        "Routineneinstellungen",
    ),
    "es": ApplicationExportCopy(
        "Crear esta automatización activa tras confirmar. Sin ejecución inmediata. Las activaciones futuras siguen estos ajustes, incluida la aprobación previa, y pueden generar costes de LLM sujetos a las cuotas existentes.",
        "Ajustes de la automatización",
    ),
    "it": ApplicationExportCopy(
        "Creare questa automazione attiva dopo la conferma. Nessuna esecuzione immediata. Le attivazioni future seguono queste impostazioni, inclusa l’approvazione preventiva, e possono comportare costi LLM soggetti alle quote esistenti.",
        "Impostazioni dell’automazione",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后创建此已启用的自动任务，不会立即执行。未来触发将遵循这些设置，包括事先审批选项，并可能产生受现有配额限制的 LLM 费用。",
        "自动任务设置",
    ),
}

APPLICATION_ROUTINE_RUN: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Demander un déclenchement manuel après confirmation et après ce tour de chat. Les conditions, l’approbation préalable, les questions en attente et les quotas restent appliqués. Des coûts LLM sont possibles. La demande enregistrée ne signifie pas que la routine a terminé : consultez son état et sa semaine pour le résultat. Une configuration modifiée avant le lancement sera refusée.",
        "Demande de lancement enregistrée ; consultez l’automatisation pour son résultat",
    ),
    "en": ApplicationExportCopy(
        "Request one manual trigger after confirmation and this chat turn. Conditions, prior approval, pending questions and quotas still apply. LLM costs may occur. A recorded request does not mean the routine finished: read its settings/week for the actual outcome. Configuration changes before launch are refused.",
        "Launch request recorded; check the routine for its result",
    ),
    "de": ApplicationExportCopy(
        "Eine manuelle Auslösung nach Bestätigung und diesem Chat-Turn anfordern. Bedingungen, vorherige Genehmigung, offene Fragen und Kontingente gelten weiterhin. LLM-Kosten sind möglich. Eine gespeicherte Anfrage bedeutet keinen abgeschlossenen Lauf: Einstellungen/Woche zeigen das Ergebnis. Änderungen vor dem Start werden abgelehnt.",
        "Startanfrage gespeichert; das Ergebnis finden Sie bei der Routine",
    ),
    "es": ApplicationExportCopy(
        "Solicitar una activación manual tras confirmar y finalizar este turno. Se mantienen condiciones, aprobación previa, preguntas pendientes y cuotas. Puede generar costes LLM. La solicitud guardada no significa que la rutina terminó: consulta sus ajustes y semana para el resultado. Se rechazan cambios de configuración antes de iniciar.",
        "Solicitud de inicio guardada; consulta la automatización para su resultado",
    ),
    "it": ApplicationExportCopy(
        "Richiedere un’attivazione manuale dopo la conferma e questo turno. Condizioni, approvazione preventiva, domande in sospeso e quote restano applicate. Sono possibili costi LLM. La richiesta salvata non indica che l’automazione è terminata: consultare impostazioni/settimana per il risultato. Modifiche prima dell’avvio vengono rifiutate.",
        "Richiesta di avvio salvata; consultare l’automazione per il risultato",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认并结束本轮聊天后请求一次手动触发。条件、事先审批、待答问题及配额仍然适用，可能产生 LLM 费用。请求已保存不代表任务已完成，请查看设置和本周记录获取结果。启动前的配置变更将被拒绝。",
        "启动请求已保存，请查看自动任务的结果",
    ),
}

APPLICATION_ROUTINE_UPDATE: dict[Language, str] = {
    "fr": "Modifier ces paramètres après confirmation, sans lancement immédiat. Une nouvelle échéance peut réactiver une routine terminée ; une pause manuelle est conservée. Les prochains déclenchements suivent la nouvelle consigne, le choix d’approbation et le mode d’exécution, avec les quotas et coûts LLM existants.",
    "en": "Change these settings after confirmation, without an immediate run. A future clock may revive a completed routine; a manual pause is preserved. Future triggers use the new instruction, approval choice and execution mode, with existing LLM quotas and costs.",
    "de": "Diese Einstellungen nach Bestätigung ändern, ohne sofortigen Lauf. Ein künftiger Termin kann eine abgeschlossene Routine reaktivieren; eine manuelle Pause bleibt erhalten. Künftige Auslösungen nutzen die neue Anweisung, Genehmigungswahl und den Ausführungsmodus mit bestehenden LLM-Kontingenten und Kosten.",
    "es": "Cambiar estos ajustes tras confirmar, sin ejecución inmediata. Una fecha futura puede reactivar una rutina terminada; se conserva una pausa manual. Las activaciones futuras usan la nueva instrucción, aprobación y modo de ejecución con las cuotas y costes LLM existentes.",
    "it": "Modificare queste impostazioni dopo la conferma, senza avvio immediato. Una scadenza futura può riattivare un’automazione conclusa; una pausa manuale viene conservata. Le attivazioni future usano le nuove istruzioni, approvazione e modalità con le quote e i costi LLM esistenti.",
    "zh-CN": "确认后修改这些设置，不会立即执行。新的未来时间可能重新启用已完成的自动任务，手动暂停将保留。未来触发使用新的指令、审批选择和执行模式，并遵循现有 LLM 配额及费用。",
}

APPLICATION_MEMORY_BULK: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Supprimer définitivement les mémoires du périmètre confirmé, y compris leur historique remplacé. L’option conserver les épinglées garde uniquement celles qui sont épinglées ; sinon elles sont supprimées, directives comprises. Les comptes affichés couvrent tout le périmètre. Un changement impose une nouvelle confirmation. Le rappel automatique reste inchangé et peut créer de nouvelles mémoires après la suppression. Les extractions antérieures sont bloquées ; aucun appel LLM ou embedding n’est nécessaire.",
        "Mémoires à supprimer",
    ),
    "en": ApplicationExportCopy(
        "Permanently erase the confirmed memory scope, including superseded history. Keep pinned preserves only pinned memories; otherwise they are erased, including instructions. Displayed counts cover the full scope. Changes require fresh confirmation. Automatic recall stays unchanged and may create new memories after erasure. Earlier extractions are fenced; no LLM or embedding call is needed.",
        "Memories to erase",
    ),
    "de": ApplicationExportCopy(
        "Den bestätigten Erinnerungsumfang einschließlich ersetzter Historie dauerhaft löschen. Fixierte behalten schützt nur fixierte Erinnerungen; andernfalls werden auch Anweisungen gelöscht. Die Zahlen umfassen den gesamten Bereich. Änderungen erfordern neue Bestätigung. Automatische Erinnerung bleibt wie eingestellt und kann später neue Erinnerungen erstellen. Frühere Extraktionen sind gesperrt; kein LLM- oder Embedding-Aufruf ist nötig.",
        "Zu löschende Erinnerungen",
    ),
    "es": ApplicationExportCopy(
        "Eliminar definitivamente el conjunto confirmado, incluido el historial sustituido. Conservar fijadas mantiene solo las memorias fijadas; de lo contrario también se eliminan las instrucciones. Los recuentos cubren todo el conjunto. Los cambios exigen nueva confirmación. El recuerdo automático no cambia y puede crear nuevas memorias después. Se bloquean las extracciones anteriores; no se necesita ninguna llamada LLM ni embedding.",
        "Memorias a eliminar",
    ),
    "it": ApplicationExportCopy(
        "Eliminare definitivamente il gruppo confermato, inclusa la cronologia sostituita. Conservare le fissate mantiene solo le memorie fissate; altrimenti anche le direttive vengono eliminate. I conteggi coprono l’intero gruppo. Le modifiche richiedono nuova conferma. Il richiamo automatico resta invariato e può creare nuove memorie in seguito. Le estrazioni precedenti sono bloccate; non serve alcuna chiamata LLM o embedding.",
        "Memorie da eliminare",
    ),
    "zh-CN": ApplicationExportCopy(
        "永久删除已确认范围内的记忆，包括已被替换的历史。保留固定记忆选项仅保留已固定的条目；否则包括指令在内都会删除。显示的计数涵盖全部范围。数据变化需要重新确认。自动回忆偏好保持不变，删除后可能创建新记忆。先前的提取被阻止；无需调用 LLM 或嵌入服务。",
        "待删除的记忆",
    ),
}


APPLICATION_MEMORY_REMOVAL: dict[Language, str] = {
    "fr": "Supprimer définitivement cette mémoire après confirmation, même si elle est épinglée ou contient une directive. Une correction ou un remplacement impose une nouvelle confirmation. Le rappel automatique reste inchangé ; les extractions déjà préparées ne peuvent pas recréer cette mémoire. Aucun appel LLM ou embedding n’est nécessaire à la suppression.",
    "en": "Permanently erase this memory after confirmation, even when pinned or containing an instruction. A correction or replacement requires fresh confirmation. Automatic recall stays unchanged; older prepared extractions cannot restore this memory. Erasure requires no LLM or embedding call.",
    "de": "Diese Erinnerung nach Bestätigung dauerhaft löschen, auch wenn sie fixiert ist oder eine Anweisung enthält. Korrekturen oder Ersetzungen erfordern neue Bestätigung. Automatische Erinnerung bleibt unverändert; ältere vorbereitete Extraktionen können sie nicht wiederherstellen. Kein LLM- oder Embedding-Aufruf ist nötig.",
    "es": "Eliminar definitivamente esta memoria tras confirmar, aunque esté fijada o contenga una instrucción. Una corrección o sustitución exige nueva confirmación. El recuerdo automático no cambia; las extracciones preparadas anteriormente no pueden restaurarla. No se requiere ninguna llamada LLM ni embedding.",
    "it": "Eliminare definitivamente questa memoria dopo la conferma, anche se fissata o contenente una direttiva. Correzioni o sostituzioni richiedono nuova conferma. Il richiamo automatico resta invariato; le estrazioni già preparate non possono ripristinarla. Non serve alcuna chiamata LLM o embedding.",
    "zh-CN": "确认后永久删除此记忆，即使已固定或包含指令。已修正或替换的记忆需要重新确认。自动回忆偏好保持不变；先前准备的提取不能恢复此记忆。删除无需调用 LLM 或嵌入服务。",
}


APPLICATION_MEMORY_UPDATE: dict[Language, str] = {
    "fr": "Modifier cette mémoire après confirmation des valeurs avant et après. L’épinglage et votre choix de rappel automatique sont conservés. Une correction concurrente impose une nouvelle confirmation. Seul un changement du texte ou du sujet prépare des embeddings, soumis aux quotas et coûts existants ; l’enregistrement peut réussir sans indexation sémantique si le service est indisponible.",
    "en": "Edit this memory after confirming the full before and after values. Pinning and automatic recall preference are preserved. A concurrent correction requires fresh confirmation. Only changed text or topic prepares embeddings under existing quotas and costs; storage may succeed without semantic indexing when the service is unavailable.",
    "de": "Diese Erinnerung nach Bestätigung aller bisherigen und neuen Werte ändern. Fixierung und automatische Erinnerung bleiben unverändert. Eine gleichzeitige Korrektur erfordert neue Bestätigung. Nur geänderter Text oder Thema erzeugt Embeddings mit bestehenden Kontingenten und Kosten; bei Dienstproblemen kann die Speicherung ohne semantische Indexierung gelingen.",
    "es": "Modificar esta memoria tras confirmar todos los valores anteriores y nuevos. Se conservan la fijación y la preferencia de recuerdo automático. Una corrección simultánea exige nueva confirmación. Solo cambiar texto o tema prepara embeddings con las cuotas y costes existentes; puede guardarse sin indexación semántica si el servicio no está disponible.",
    "it": "Modificare questa memoria dopo aver confermato tutti i valori precedenti e nuovi. Fissaggio e preferenza di richiamo automatico restano invariati. Una correzione simultanea richiede nuova conferma. Solo testo o argomento modificati preparano embedding con quote e costi esistenti; il salvataggio può riuscire senza indicizzazione semantica se il servizio non è disponibile.",
    "zh-CN": "确认全部修改前后数值后修改此记忆。固定状态和自动回忆偏好保持不变。并发修正需要重新确认。仅文本或主题变化才会在现有配额及费用限制下准备嵌入；服务不可用时可能成功保存但未建立语义索引。",
}


APPLICATION_ROUTINE_REMOVAL: dict[Language, str] = {
    "fr": "Supprimer définitivement cette automatisation et son historique d’exécution après confirmation. Les prochains déclenchements cessent ; une exécution déjà lancée peut se terminer et conserver ses coûts.",
    "en": "Permanently delete this routine and its run history after confirmation. Future triggers stop; an already running execution may finish and retain its costs.",
    "de": "Diese Routine und ihren Ausführungsverlauf nach Bestätigung dauerhaft löschen. Künftige Auslösungen enden; eine bereits laufende Ausführung kann mit ihren Kosten fortgesetzt werden.",
    "es": "Eliminar definitivamente esta automatización y su historial tras confirmar. Se detienen las activaciones futuras; una ejecución ya iniciada puede terminar y mantener sus costes.",
    "it": "Eliminare definitivamente questa automazione e la sua cronologia dopo la conferma. Le attivazioni future cessano; un’esecuzione già avviata può terminare e mantenere i relativi costi.",
    "zh-CN": "确认后永久删除此自动任务及其执行历史。未来触发停止；已经启动的执行可能完成并产生相应费用。",
}

APPLICATION_INTEREST_CREATION: dict[Language, ApplicationExportCopy] = {
    "fr": ApplicationExportCopy(
        "Créer ce centre d’intérêt avec les valeurs affichées après confirmation. Le calcul d’embedding éventuel intervient ensuite, sous les quotas et coûts existants. L’enregistrement peut réussir sans vecteur si le service est indisponible. Les notifications automatiques restent au réglage actuel.",
        "Centre d’intérêt à créer",
    ),
    "en": ApplicationExportCopy(
        "Create this interest with the displayed values after confirmation. Best-effort embedding then uses existing quotas and costs. Storage can succeed without a vector if the service is unavailable. Automatic notifications retain their current setting.",
        "Interest to create",
    ),
    "de": ApplicationExportCopy(
        "Dieses Interesse nach Bestätigung mit den angezeigten Werten erstellen. Eine mögliche Einbettung verwendet anschließend bestehende Kontingente und Kosten. Bei Dienstproblemen ist Speichern ohne Vektor möglich. Automatische Benachrichtigungen behalten ihre Einstellung.",
        "Zu erstellendes Interesse",
    ),
    "es": ApplicationExportCopy(
        "Crear este interés con los valores mostrados tras confirmar. El embedding posterior usa las cuotas y costes existentes. Puede guardarse sin vector si el servicio no está disponible. Las notificaciones automáticas mantienen su ajuste.",
        "Interés a crear",
    ),
    "it": ApplicationExportCopy(
        "Creare questo interesse con i valori mostrati dopo la conferma. L’eventuale embedding usa poi quote e costi esistenti. Se il servizio non è disponibile può essere salvato senza vettore. Le notifiche automatiche mantengono l’impostazione corrente.",
        "Interesse da creare",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后按显示的值创建此兴趣。随后可尝试计算嵌入，受现有配额和费用约束。服务不可用时仍可保存不含向量的兴趣。自动通知保持当前设置。",
        "待创建的兴趣",
    ),
}

APPLICATION_INTEREST_UPDATE: dict[Language, ApplicationExportCopy] = {
    "en": ApplicationExportCopy(
        "Apply the displayed changes after confirmation. A renamed topic clears its derived subject and attempts an embedding under existing quotas. Competing configuration or signal changes require another confirmation.",
        "Interest configuration",
    ),
    "fr": ApplicationExportCopy(
        "Appliquer les changements affichés après confirmation. Renommer le sujet efface son regroupement dérivé et tente un embedding sous les quotas existants. Tout changement concurrent de configuration ou de signaux impose une nouvelle confirmation.",
        "Configuration du centre d’intérêt",
    ),
    "de": ApplicationExportCopy(
        "Die angezeigten Änderungen nach Bestätigung anwenden. Eine Umbenennung löscht die abgeleitete Gruppierung und versucht ein Embedding innerhalb bestehender Kontingente. Gleichzeitige Änderungen an Konfiguration oder Signalen erfordern eine neue Bestätigung.",
        "Interessenkonfiguration",
    ),
    "es": ApplicationExportCopy(
        "Aplicar los cambios mostrados tras confirmar. Renombrar el tema borra su agrupación derivada e intenta generar un embedding con las cuotas existentes. Los cambios simultáneos de configuración o señales requieren otra confirmación.",
        "Configuración del interés",
    ),
    "it": ApplicationExportCopy(
        "Applicare le modifiche mostrate dopo la conferma. Rinominare il tema cancella il raggruppamento derivato e tenta un embedding con le quote esistenti. Modifiche concorrenti a configurazione o segnali richiedono una nuova conferma.",
        "Configurazione dell’interesse",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后应用显示的更改。重命名主题会清除派生分组，并在现有配额内尝试生成嵌入。配置或信号的并发更改需要重新确认。",
        "兴趣配置",
    ),
}

APPLICATION_INTEREST_REMOVAL: dict[Language, ApplicationExportCopy] = {
    "en": ApplicationExportCopy(
        "Permanently delete this saved interest after confirmation. Previously delivered notification history remains available. Any competing change to the interest requires another confirmation.",
        "Interest to delete",
    ),
    "fr": ApplicationExportCopy(
        "Supprimer définitivement ce centre d’intérêt après confirmation. L’historique des notifications déjà reçues reste disponible. Toute modification concurrente du centre d’intérêt impose une nouvelle confirmation.",
        "Centre d’intérêt à supprimer",
    ),
    "de": ApplicationExportCopy(
        "Dieses gespeicherte Interesse nach Bestätigung endgültig löschen. Der Verlauf bereits zugestellter Benachrichtigungen bleibt verfügbar. Gleichzeitige Änderungen am Interesse erfordern eine neue Bestätigung.",
        "Zu löschendes Interesse",
    ),
    "es": ApplicationExportCopy(
        "Eliminar definitivamente este interés tras confirmar. El historial de notificaciones ya recibidas sigue disponible. Cualquier cambio simultáneo del interés requiere otra confirmación.",
        "Interés que se eliminará",
    ),
    "it": ApplicationExportCopy(
        "Eliminare definitivamente questo interesse dopo la conferma. La cronologia delle notifiche già ricevute resta disponibile. Modifiche concorrenti all’interesse richiedono una nuova conferma.",
        "Interesse da eliminare",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后永久删除此兴趣。已收到的通知历史仍然可用。兴趣的任何并发更改都需要重新确认。",
        "待删除的兴趣",
    ),
}

APPLICATION_INTEREST_REACTIVATION: dict[Language, ApplicationExportCopy] = {
    "en": ApplicationExportCopy(
        "After confirmation, reactivate this dormant interest with the displayed initial signals. Refresh last-mentioned at actual execution time and clear last-notified and dormant-since. Topic, category, subject and embedding remain. This does not enable notifications or promise a delivery.",
        "Interest to reactivate",
    ),
    "fr": ApplicationExportCopy(
        "Après confirmation, réactiver ce centre d’intérêt dormant avec les signaux initiaux affichés. Actualiser la dernière mention à l’heure réelle d’exécution et effacer les dates de dernière notification et de mise en dormance. Le sujet, la catégorie, le regroupement et l’embedding sont conservés. Cette action n’active pas les notifications et ne promet aucune livraison.",
        "Centre d’intérêt à réactiver",
    ),
    "de": ApplicationExportCopy(
        "Nach Bestätigung dieses ruhende Interesse mit den angezeigten Anfangssignalen reaktivieren. Die letzte Erwähnung auf den tatsächlichen Ausführungszeitpunkt setzen und Benachrichtigungs- sowie Ruhezeitpunkt löschen. Thema, Kategorie, Gruppe und Embedding bleiben erhalten. Dies aktiviert keine Benachrichtigungen und verspricht keine Zustellung.",
        "Zu reaktivierendes Interesse",
    ),
    "es": ApplicationExportCopy(
        "Tras confirmar, reactivar este interés inactivo con las señales iniciales mostradas. Actualizar la última mención a la hora real de ejecución y borrar las fechas de última notificación e inactividad. Se conservan tema, categoría, agrupación y embedding. Esto no activa las notificaciones ni promete entregas.",
        "Interés que se reactivará",
    ),
    "it": ApplicationExportCopy(
        "Dopo la conferma, riattivare questo interesse dormiente con i segnali iniziali mostrati. Aggiornare l’ultima menzione all’ora effettiva di esecuzione e cancellare le date dell’ultima notifica e della dormienza. Argomento, categoria, raggruppamento ed embedding restano. Non attiva le notifiche né promette consegne.",
        "Interesse da riattivare",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后按所示初始信号重新激活该休眠兴趣。最后提及时间更新为实际执行时间，并清除最后通知和休眠时间。主题、类别、分组和向量保留。此操作不会启用通知，也不承诺发送通知。",
        "待重新激活的兴趣",
    ),
}

APPLICATION_INTEREST_FEEDBACK: dict[Language, ApplicationExportCopy] = {
    "en": ApplicationExportCopy(
        "After confirmation, record the displayed verdict and signal/status changes. Notification scope updates only its audit and matching card. Interest scope marks all associated archived cards answered without guessing an audit notification. Feedback is human presence according to your habits settings.",
        "Interest feedback",
    ),
    "fr": ApplicationExportCopy(
        "Après confirmation, enregistrer l’avis affiché et les changements de signaux/statut. La portée notification met à jour son historique et sa carte précise. La portée centre d’intérêt marque toutes ses cartes archivées comme traitées, sans attribuer l’avis à une notification supposée. Le feedback compte comme présence humaine selon vos réglages d’habitudes.",
        "Avis sur le centre d’intérêt",
    ),
    "de": ApplicationExportCopy(
        "Nach Bestätigung das angezeigte Urteil sowie Signal- und Statusänderungen speichern. Der Benachrichtigungsumfang aktualisiert nur deren Verlauf und Karte. Der Interessenumfang markiert alle zugehörigen archivierten Karten als beantwortet, ohne eine Verlaufsbenachrichtigung zu erraten. Feedback gilt entsprechend Ihren Gewohnheitseinstellungen als menschliche Anwesenheit.",
        "Interessenfeedback",
    ),
    "es": ApplicationExportCopy(
        "Tras confirmar, registrar la valoración y los cambios de señales/estado mostrados. El alcance de notificación actualiza solo su historial y tarjeta. El alcance de interés marca todas sus tarjetas archivadas como respondidas sin atribuir la valoración a una notificación supuesta. La valoración cuenta como presencia humana según tus ajustes de hábitos.",
        "Valoración del interés",
    ),
    "it": ApplicationExportCopy(
        "Dopo la conferma, registrare il giudizio e le modifiche mostrate a segnali e stato. L’ambito notifica aggiorna solo il relativo storico e la scheda. L’ambito interesse segna tutte le sue schede archiviate come risposte senza attribuire il giudizio a una notifica ipotizzata. Il feedback conta come presenza umana secondo le impostazioni delle abitudini.",
        "Feedback sull’interesse",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后记录所示反馈及信号和状态变化。通知范围仅更新该通知记录及对应卡片。兴趣范围会将其所有已归档卡片标记为已处理，不会猜测反馈应归属于哪条通知。反馈是否计为人工在线活动遵循您的习惯设置。",
        "兴趣反馈",
    ),
}

APPLICATION_INTEREST_BULK: dict[Language, ApplicationExportCopy] = {
    "en": ApplicationExportCopy(
        "Permanently delete every saved interest in the displayed counts after confirmation, including blocked and dormant topics. Delivered notification history remains available. Added or changed interests require another confirmation.",
        "All interests to delete",
    ),
    "fr": ApplicationExportCopy(
        "Supprimer définitivement tous les centres d’intérêt comptés ci-dessous après confirmation, y compris les sujets bloqués et dormants. L’historique des notifications reçues reste disponible. Tout ajout ou changement impose une nouvelle confirmation.",
        "Tous les centres d’intérêt à supprimer",
    ),
    "de": ApplicationExportCopy(
        "Nach Bestätigung alle gezählten gespeicherten Interessen endgültig löschen, auch blockierte und ruhende Themen. Zugestellte Benachrichtigungen bleiben im Verlauf verfügbar. Hinzugefügte oder geänderte Interessen erfordern eine neue Bestätigung.",
        "Alle zu löschenden Interessen",
    ),
    "es": ApplicationExportCopy(
        "Eliminar definitivamente todos los intereses contabilizados tras confirmar, incluidos los bloqueados e inactivos. El historial de notificaciones recibidas sigue disponible. Cualquier interés añadido o modificado requiere otra confirmación.",
        "Todos los intereses que se eliminarán",
    ),
    "it": ApplicationExportCopy(
        "Eliminare definitivamente tutti gli interessi conteggiati dopo la conferma, inclusi quelli bloccati e dormienti. La cronologia delle notifiche ricevute resta disponibile. Interessi aggiunti o modificati richiedono una nuova conferma.",
        "Tutti gli interessi da eliminare",
    ),
    "zh-CN": ApplicationExportCopy(
        "确认后永久删除以下计数中的所有兴趣，包括屏蔽和休眠的主题。已收到的通知历史仍然可用。新增或更改兴趣需要重新确认。",
        "待删除的全部兴趣",
    ),
}
