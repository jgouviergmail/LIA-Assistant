"""Habit learning confirmation explains the retained-record scope in every locale."""

from src.core.i18n_types import Language

HABIT_SETTINGS_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Apprentissage des habitudes",
        "Ce réglage contrôle l’apprentissage futur. Les habitudes, le rythme et les preuves déjà conservés ne sont pas effacés ; une analyse déjà commencée peut se terminer.",
    ),
    "en": (
        "Habit learning",
        "This setting controls future learning. Retained habits, rhythm and evidence are not erased; an analysis already started may finish.",
    ),
    "de": (
        "Lernen von Gewohnheiten",
        "Diese Einstellung steuert künftiges Lernen. Gespeicherte Gewohnheiten, Rhythmus und Nachweise werden nicht gelöscht; eine bereits gestartete Analyse kann enden.",
    ),
    "es": (
        "Aprendizaje de hábitos",
        "Este ajuste controla el aprendizaje futuro. No se borran los hábitos, el ritmo ni las pruebas conservadas; un análisis ya iniciado puede terminar.",
    ),
    "it": (
        "Apprendimento delle abitudini",
        "Questa impostazione controlla l’apprendimento futuro. Abitudini, ritmo e prove conservate non vengono cancellati; un’analisi già iniziata può terminare.",
    ),
    "zh-CN": (
        "习惯学习",
        "此设置控制后续学习，不会删除已保存的习惯、节奏或依据；已经开始的分析可能继续完成。",
    ),
}
