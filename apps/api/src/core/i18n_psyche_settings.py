"""Exact sparse psyche-setting labels explain preservation, not inferred deletion."""

from src.core.i18n_types import Language

PSYCHE_SETTINGS_COPY: dict[Language, tuple[str, str, str, str, str]] = {
    "fr": (
        "Activer la psyché",
        "Afficher l’avatar émotionnel",
        "Sensibilité émotionnelle (0–100)",
        "Stabilité de l’humeur (0–100)",
        "Seuls les réglages affichés changent. L’état et l’historique sont conservés ; une analyse déjà commencée peut se terminer. Cette action ne réinitialise pas la psyché.",
    ),
    "en": (
        "Enable psyche",
        "Show emotional avatar",
        "Emotional sensitivity (0–100)",
        "Mood stability (0–100)",
        "Only the displayed settings change. State and history are retained; an analysis already started may finish. This action does not reset the psyche.",
    ),
    "de": (
        "Psyche aktivieren",
        "Emotionalen Avatar anzeigen",
        "Emotionale Sensibilität (0–100)",
        "Stimmungsstabilität (0–100)",
        "Nur die angezeigten Einstellungen ändern sich. Zustand und Verlauf bleiben erhalten; eine begonnene Analyse kann enden. Diese Aktion setzt die Psyche nicht zurück.",
    ),
    "es": (
        "Activar la psique",
        "Mostrar avatar emocional",
        "Sensibilidad emocional (0–100)",
        "Estabilidad del ánimo (0–100)",
        "Solo cambian los ajustes mostrados. Se conservan el estado y el historial; un análisis ya iniciado puede terminar. Esta acción no reinicia la psique.",
    ),
    "it": (
        "Attiva la psiche",
        "Mostra avatar emotivo",
        "Sensibilità emotiva (0–100)",
        "Stabilità dell’umore (0–100)",
        "Cambiano solo le impostazioni mostrate. Stato e cronologia sono conservati; un’analisi già iniziata può terminare. Questa azione non reimposta la psiche.",
    ),
    "zh-CN": (
        "启用心理引擎",
        "显示情感头像",
        "情感敏感度（0–100）",
        "情绪稳定性（0–100）",
        "仅更改显示的设置，保留状态和历史；已经开始的分析可能继续完成。此操作不会重置心理状态。",
    ),
}
