"""Human confirmations state the source lifecycle and relearning effects."""

from src.core.i18n_types import Language

HABIT_ACTION_COPY: dict[Language, tuple[str, str, str]] = {
    "fr": (
        "Habitude",
        "En pause : l’habitude reste conservée et ses observations peuvent être actualisées. Bloquée : elle reste conservée pour empêcher son réapprentissage. La réactiver lève ce blocage. Une offre déjà lancée peut se terminer.",
        "Seule cette habitude sera supprimée, y compris son éventuel blocage. Elle pourra être réapprise. Le rythme, les autres habitudes et les preuves d’activité sont conservés.",
    ),
    "en": (
        "Habit",
        "Paused: the habit stays stored and its observations may refresh. Blocked: it stays stored to prevent relearning. Activating it lifts that block. An offer already started may finish.",
        "Only this habit will be removed, including its block if any. It may be learned again. Rhythm, other habits and activity evidence are retained.",
    ),
    "de": (
        "Gewohnheit",
        "Pausiert: Die Gewohnheit bleibt gespeichert und Beobachtungen können aktualisiert werden. Blockiert: Sie bleibt gespeichert, um erneutes Lernen zu verhindern. Aktivieren hebt die Blockierung auf. Ein bereits gestartetes Angebot kann enden.",
        "Nur diese Gewohnheit wird entfernt, einschließlich ihrer möglichen Blockierung. Sie kann erneut gelernt werden. Rhythmus, andere Gewohnheiten und Aktivitätsnachweise bleiben erhalten.",
    ),
    "es": (
        "Hábito",
        "En pausa: el hábito se conserva y sus observaciones pueden actualizarse. Bloqueado: se conserva para impedir volver a aprenderlo. Activarlo elimina el bloqueo. Una oferta ya iniciada puede terminar.",
        "Solo se eliminará este hábito, incluido su posible bloqueo. Puede aprenderse de nuevo. Se conservan el ritmo, los demás hábitos y las pruebas de actividad.",
    ),
    "it": (
        "Abitudine",
        "In pausa: l’abitudine resta conservata e le osservazioni possono aggiornarsi. Bloccata: resta conservata per impedirne il riapprendimento. Attivarla rimuove il blocco. Un’offerta già iniziata può terminare.",
        "Verrà rimossa solo questa abitudine, incluso l’eventuale blocco. Potrà essere appresa di nuovo. Ritmo, altre abitudini e prove di attività restano conservati.",
    ),
    "zh-CN": (
        "习惯",
        "暂停后仍保留习惯，观察记录可能更新。屏蔽后保留记录以防止再次学习。重新启用会解除屏蔽。已经开始的建议可能继续完成。",
        "仅删除此习惯及其可能的屏蔽记录，之后可能再次学习。节奏、其他习惯与活动依据仍会保留。",
    ),
}
