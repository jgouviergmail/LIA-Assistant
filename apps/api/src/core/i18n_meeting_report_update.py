"""Exact sparse report editing scope in the application's six languages."""

MEETING_REPORT_UPDATE_COPY = {
    "fr": (
        "Modifier le compte rendu",
        "Enregistre uniquement les valeurs affichées. Les participants et les sections fournis remplacent entièrement ces listes ; une liste vide les efface. Les champs non demandés restent inchangés. Le choix du modèle est disponible uniquement avant le traitement. Sa référence est enregistrée ; les instructions affichées sont celles de la confirmation. Une modification ultérieure du modèle peut affecter le futur traitement. Aucun enregistrement, nouveau compte rendu ni courriel n’est lancé. La réindexation documentaire d’origine démarre après une sauvegarde confirmée et peut entraîner ses coûts habituels ; elle n’est pas encore terminée. Une modification concurrente exige une nouvelle confirmation. Une sauvegarde incertaine ne sera pas répétée automatiquement.",
    ),
    "en": (
        "Edit meeting minutes",
        "Saves only the displayed values. Supplied participants and sections replace those entire lists; an empty list clears them. Unrequested fields stay unchanged. Template selection is available only before processing. Its reference is stored; displayed instructions are those at confirmation. Later template edits may affect future processing. No recording, new synthesis or email starts. Original document reindexing starts after a confirmed save and may incur its usual costs; it is not yet complete. Concurrent changes require new consent. An uncertain save will not be repeated automatically.",
    ),
    "de": (
        "Besprechungsprotokoll bearbeiten",
        "Speichert nur die angezeigten Werte. Teilnehmer und Abschnitte ersetzen jeweils die gesamte Liste; eine leere Liste löscht sie. Nicht angeforderte Felder bleiben unverändert. Die Vorlagenauswahl ist nur vor der Verarbeitung verfügbar. Ihre Referenz wird gespeichert; die angezeigten Anweisungen gelten bei Bestätigung. Spätere Vorlagenänderungen können die künftige Verarbeitung beeinflussen. Keine Aufnahme, neue Zusammenfassung oder E-Mail startet. Die ursprüngliche Dokument-Neuindexierung startet nach bestätigter Speicherung, kann die üblichen Kosten verursachen und ist noch nicht abgeschlossen. Gleichzeitige Änderungen erfordern neue Zustimmung. Eine ungewisse Speicherung wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Editar las actas",
        "Guarda solo los valores mostrados. Los participantes y secciones proporcionados sustituyen cada lista completa; una lista vacía la borra. Los campos no solicitados permanecen iguales. La selección de plantilla solo está disponible antes del procesamiento. Se guarda su referencia; las instrucciones mostradas corresponden a la confirmación. Los cambios posteriores de la plantilla pueden afectar al futuro procesamiento. No inicia grabación, nueva síntesis ni correo. La reindexación documental original comienza tras confirmar el guardado, puede tener sus costes habituales y aún no ha terminado. Los cambios simultáneos requieren nuevo consentimiento. Un guardado incierto no se repetirá automáticamente.",
    ),
    "it": (
        "Modifica il verbale",
        "Salva solo i valori mostrati. Partecipanti e sezioni forniti sostituiscono le intere liste; una lista vuota le cancella. I campi non richiesti restano invariati. La scelta del modello è disponibile solo prima dell’elaborazione. Si salva il riferimento; le istruzioni mostrate sono quelle al momento della conferma. Modifiche successive del modello possono influire sull’elaborazione futura. Non avvia registrazioni, nuove sintesi né email. La reindicizzazione documentale originale parte dopo il salvataggio confermato, può comportare i normali costi e non è ancora completata. Modifiche contemporanee richiedono nuovo consenso. Un salvataggio incerto non sarà ripetuto automaticamente.",
    ),
    "zh-CN": (
        "编辑会议纪要",
        "仅保存显示的值。提供的参与者和章节将替换整份列表，空列表会清空它们。未请求的字段保持不变。模板选择仅在处理之前可用。保存的是模板引用，显示的指令为确认时的版本。之后修改模板可能影响后续处理。不会启动录音、新纪要生成或邮件发送。保存确认后启动原有文档重新索引，可能产生常规费用，目前尚未完成。并发修改需要重新确认。保存结果不确定时不会自动重试。",
    ),
}
