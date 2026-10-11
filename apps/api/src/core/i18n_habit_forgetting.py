"""Full forgetting states retained history and incomplete temporary cleanup explicitly."""

from src.core.i18n_types import Language

HABIT_FORGET_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Données d’apprentissage des habitudes",
        "Toutes les habitudes, y compris les blocages, le rythme et les traces d’activité seront effacés. Les traces temporaires seront aussi nettoyées ; un nettoyage incomplet sera signalé. Vos conversations et votre historique sont conservés. Le réglage d’apprentissage reste inchangé : un nouvel apprentissage ou un recalcul pourra reconstituer des habitudes depuis cet historique.",
    ),
    "en": (
        "Habit-learning data",
        "All habits, including blocks, rhythm and activity records will be erased. Temporary traces will also be cleaned; incomplete cleanup will be reported. Conversations and history are retained. Learning settings are unchanged: later learning or a recompute may rebuild habits from that history.",
    ),
    "de": (
        "Lerndaten zu Gewohnheiten",
        "Alle Gewohnheiten einschließlich Blockierungen, Rhythmus und Aktivitätsdaten werden gelöscht. Temporäre Spuren werden ebenfalls bereinigt; unvollständige Bereinigung wird gemeldet. Gespräche und Verlauf bleiben erhalten. Die Lerneinstellung bleibt unverändert: Späteres Lernen oder Neuberechnen kann daraus Gewohnheiten wiederherstellen.",
    ),
    "es": (
        "Datos de aprendizaje de hábitos",
        "Se borrarán todos los hábitos, incluidos bloqueos, ritmo y registros de actividad. También se limpiarán las trazas temporales; se indicará cualquier limpieza incompleta. Se conservan las conversaciones y el historial. El ajuste de aprendizaje no cambia: un aprendizaje posterior o un nuevo cálculo puede reconstruir hábitos desde ese historial.",
    ),
    "it": (
        "Dati di apprendimento delle abitudini",
        "Saranno cancellate tutte le abitudini, inclusi blocchi, ritmo e registri di attività. Saranno ripulite anche le tracce temporanee; verrà segnalata ogni pulizia incompleta. Conversazioni e cronologia restano conservate. L’impostazione di apprendimento non cambia: un apprendimento successivo o un ricalcolo può ricostruire abitudini da tale cronologia.",
    ),
    "zh-CN": (
        "习惯学习数据",
        "将删除所有习惯，包括屏蔽记录、节奏及活动记录。也会清理临时痕迹，清理不完整时会明确提示。对话与历史记录保留，学习设置不变；后续学习或重新计算可能从这些历史记录重建习惯。",
    ),
}

HABIT_FORGET_COUNTS: dict[Language, tuple[str, str, str]] = {
    "fr": ("Habitudes conservées", "Profil de rythme", "Jours d’activité conservés"),
    "en": ("Saved habits", "Rhythm profile", "Saved activity days"),
    "de": ("Gespeicherte Gewohnheiten", "Rhythmusprofil", "Gespeicherte Aktivitätstage"),
    "es": ("Hábitos guardados", "Perfil de ritmo", "Días de actividad guardados"),
    "it": ("Abitudini salvate", "Profilo del ritmo", "Giorni di attività salvati"),
    "zh-CN": ("已保存的习惯", "节奏画像", "已保存的活动天数"),
}
