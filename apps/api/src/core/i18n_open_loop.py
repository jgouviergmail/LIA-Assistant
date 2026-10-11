"""Native commitment confirmation copy, including the advisory deadline boundary."""

from src.core.i18n_types import Language

OPEN_LOOP_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Engagement",
        "Après confirmation, seul cet engagement est corrigé ou clôturé. L’échéance est indicative : aucun rappel ni message n’est envoyé. « Fait » signifie terminé ; « Plus d’actualité » signifie abandonné.",
    ),
    "en": (
        "Commitment",
        "After confirmation, only this commitment is corrected or closed. The deadline is advisory: no reminder or message is sent. Done means completed; dismissed means no longer relevant.",
    ),
    "de": (
        "Verpflichtung",
        "Nach Bestätigung wird nur diese Verpflichtung korrigiert oder geschlossen. Die Frist ist unverbindlich: Es wird keine Erinnerung oder Nachricht gesendet. Erledigt bedeutet abgeschlossen; verworfen bedeutet nicht mehr relevant.",
    ),
    "es": (
        "Compromiso",
        "Tras confirmar, solo este compromiso se corrige o cierra. La fecha es orientativa: no se envía ningún recordatorio ni mensaje. Hecho significa completado; descartado significa que ya no es pertinente.",
    ),
    "it": (
        "Impegno",
        "Dopo la conferma, viene corretto o chiuso solo questo impegno. La scadenza è indicativa: non vengono inviati promemoria né messaggi. Fatto significa completato; archiviato significa non più pertinente.",
    ),
    "zh-CN": (
        "承诺",
        "确认后，仅修改或关闭此承诺。期限仅供参考，不会发送提醒或消息。完成表示已经履行；放弃表示不再适用。",
    ),
}
