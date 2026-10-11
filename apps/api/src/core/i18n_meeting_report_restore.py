"""Whole generated-version replacement scope, without report text in the prompt."""

MEETING_REPORT_RESTORE_COPY = {
    "fr": (
        "Restaurer le compte rendu généré",
        "Remplace entièrement le compte rendu actuel par la version générée enregistrée. L’aperçu contient uniquement les titres, les nombres exacts de participants et de sections et jusqu’à douze intitulés de sections : le texte complet n’est pas affiché. Toutes les modifications du compte rendu actuel seront remplacées. La localisation, l’audio et la transcription sont conservés. La réindexation documentaire d’origine est lancée après une sauvegarde confirmée ; elle peut entraîner les coûts habituels d’indexation et n’est pas encore terminée. Aucun nouveau compte rendu ni courriel n’est généré. Un traitement déjà en cours peut ensuite publier une autre version. Une version déjà identique ne produit aucun changement. Une sauvegarde incertaine ne sera pas répétée automatiquement.",
    ),
    "en": (
        "Restore generated minutes",
        "Replaces the entire current minutes with the saved generated version. The preview shows only titles, exact participant and section counts, and up to twelve section headings: full text is not displayed. All current report edits will be replaced. Location, audio and transcript are preserved. Original document reindexing starts after a confirmed save; it may incur the usual indexing costs and is not yet complete. No new synthesis or email is generated. Processing already in progress may later publish another version. An already identical version makes no change. An uncertain save will not be repeated automatically.",
    ),
    "de": (
        "Generiertes Protokoll wiederherstellen",
        "Ersetzt das gesamte aktuelle Protokoll durch die gespeicherte generierte Version. Die Vorschau zeigt nur Titel, genaue Teilnehmer- und Abschnittszahlen sowie bis zu zwölf Abschnittsüberschriften; der vollständige Text wird nicht angezeigt. Alle aktuellen Änderungen werden ersetzt. Ort, Audio und Transkript bleiben erhalten. Die ursprüngliche Dokument-Neuindexierung startet nach bestätigter Speicherung, kann die üblichen Indexierungskosten verursachen und ist noch nicht abgeschlossen. Keine neue Zusammenfassung oder E-Mail wird erzeugt. Eine laufende Verarbeitung kann später eine andere Version veröffentlichen. Eine bereits identische Version bleibt unverändert. Eine ungewisse Speicherung wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Restaurar las actas generadas",
        "Sustituye todas las actas actuales por la versión generada guardada. La vista previa muestra solo títulos, cantidades exactas de participantes y secciones y hasta doce encabezados; no muestra el texto completo. Se sustituirán todas las modificaciones actuales. Se conservan ubicación, audio y transcripción. La reindexación documental original comienza tras confirmar el guardado; puede tener los costes habituales de indexación y aún no ha terminado. No genera nuevas actas ni correo. Un procesamiento en curso puede publicar otra versión después. Una versión ya idéntica no cambia nada. Un guardado incierto no se repetirá automáticamente.",
    ),
    "it": (
        "Ripristina il verbale generato",
        "Sostituisce l’intero verbale attuale con la versione generata salvata. L’anteprima mostra solo titoli, conteggi esatti di partecipanti e sezioni e fino a dodici intestazioni; il testo completo non viene mostrato. Tutte le modifiche attuali saranno sostituite. Posizione, audio e trascrizione vengono conservati. La reindicizzazione documentale originale parte dopo il salvataggio confermato; può comportare i normali costi di indicizzazione e non è ancora completata. Non genera nuovi verbali né email. Un’elaborazione già in corso può pubblicare successivamente un’altra versione. Una versione già identica non cambia nulla. Un salvataggio incerto non sarà ripetuto automaticamente.",
    ),
    "zh-CN": (
        "恢复生成的会议纪要",
        "将当前整份纪要替换为已保存的生成版本。预览仅显示标题、准确的参与者和章节数量以及最多十二个章节标题，不显示全文。当前纪要的所有编辑都将被替换。保留地点、音频和转录。保存确认后会启动原有的文档重新索引，可能产生常规索引费用，目前尚未完成。不会生成新纪要或邮件。正在进行的处理之后可能发布另一版本。版本已相同时不会更改。保存结果不确定时不会自动重试。",
    ),
}
