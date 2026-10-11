"""Confirmation copy distinguishes future defaults from existing recordings."""

MEETING_PREFERENCE_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Préférences de réunion",
        "Ces réglages s’appliquent aux prochaines réunions. Aucun enregistrement, traitement ni e-mail n’est lancé. La conservation audio respecte le plafond affiché.",
    ),
    "en": (
        "Meeting preferences",
        "These settings apply to future meetings. No recording, processing or email is started. Audio retention respects the displayed ceiling.",
    ),
    "de": (
        "Besprechungseinstellungen",
        "Diese Einstellungen gelten für künftige Besprechungen. Es wird keine Aufnahme, Verarbeitung oder E-Mail gestartet. Die Audiospeicherung bleibt innerhalb der angezeigten Grenze.",
    ),
    "es": (
        "Preferencias de reuniones",
        "Estos ajustes se aplican a futuras reuniones. No se inicia ninguna grabación, procesamiento ni correo. La conservación de audio respeta el límite mostrado.",
    ),
    "it": (
        "Preferenze delle riunioni",
        "Queste impostazioni valgono per le riunioni future. Non viene avviata alcuna registrazione, elaborazione o email. La conservazione audio rispetta il limite mostrato.",
    ),
    "zh-CN": (
        "会议偏好",
        "这些设置适用于今后的会议。不会启动录音、处理或邮件发送。音频保留时间遵守所显示的上限。",
    ),
}
