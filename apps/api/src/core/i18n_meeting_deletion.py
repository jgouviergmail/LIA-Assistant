"""Whole-data consent distinguishes database deletion from physical cleanup."""

MEETING_DELETION_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Réunion à supprimer",
        "Supprime définitivement cette réunion, ses comptes rendus actuels et générés, sa transcription conservée, son répertoire audio et sa projection documentaire avec ses fragments. Les comptes rendus dérivés et leurs transcriptions sont conservés ; seul leur lien vers cette source est effacé. Le contenu complet n’est pas affiché ici. La suppression en base et le nettoyage physique des fichiers sont deux résultats distincts ; un nettoyage échoué ou interrompu ne sera pas annoncé comme terminé. Aucun nouveau traitement payant n’est lancé ; un traitement déjà en cours peut avoir consommé des coûts. Une source modifiée exige une nouvelle confirmation. Un résultat de commit incertain ne sera pas rejoué automatiquement.",
    ),
    "en": (
        "Meeting to delete",
        "Permanently delete this meeting, its current/generated minutes, retained transcript, audio directory and knowledge-space projection/chunks. Derived minutes and their transcripts remain; only their source link is cleared. Complete content is not displayed here. Database deletion and physical file cleanup are separate results; failed or interrupted cleanup is never reported complete. No new paid work starts; an existing job may already have consumed billed work. Changed source needs new confirmation. An unknown commit result is never automatically replayed.",
    ),
    "de": (
        "Besprechung löschen",
        "Löscht diese Besprechung, aktuelle/generierte Protokolle, aufbewahrtes Transkript, Audioverzeichnis und Dokumentprojektion samt Fragmenten dauerhaft. Abgeleitete Protokolle und Transkripte bleiben erhalten; nur der Quellenverweis entfällt. Vollständige Inhalte werden hier nicht angezeigt. Datenbanklöschung und physische Dateibereinigung sind getrennte Ergebnisse; fehlgeschlagene oder unterbrochene Bereinigung wird nie als abgeschlossen gemeldet. Keine neue kostenpflichtige Arbeit; ein laufender Auftrag kann bereits Kosten verursacht haben. Geänderte Quellen erfordern neue Bestätigung. Unklarer Commit wird nie automatisch wiederholt.",
    ),
    "es": (
        "Eliminar reunión",
        "Elimina definitivamente esta reunión, sus actas actuales/generadas, transcripción conservada, directorio de audio y proyección documental con fragmentos. Las actas derivadas y sus transcripciones se conservan; solo se borra su vínculo con la fuente. Aquí no se muestra el contenido completo. El borrado en base y la limpieza física son resultados distintos; la limpieza fallida o interrumpida nunca se anuncia terminada. No inicia trabajo de pago nuevo; uno en curso puede haber generado costes. Una fuente modificada requiere nueva confirmación. Un commit incierto nunca se repite automáticamente.",
    ),
    "it": (
        "Eliminare la riunione",
        "Elimina definitivamente questa riunione, verbali attuali/generati, trascrizione conservata, cartella audio e proiezione documentale con frammenti. Verbali derivati e trascrizioni restano; viene eliminato solo il collegamento alla fonte. Il contenuto completo non è mostrato qui. Eliminazione in database e pulizia fisica sono risultati distinti; una pulizia fallita o interrotta non viene mai dichiarata completata. Nessun nuovo lavoro a pagamento; uno già in corso può avere generato costi. Una fonte modificata richiede nuova conferma. Un commit incerto non viene ripetuto automaticamente.",
    ),
    "zh-CN": (
        "删除会议",
        "永久删除该会议、当前及生成的纪要、保留的转录、音频目录以及知识空间中的文档和片段。衍生纪要及其转录仍保留，只清除指向此来源的引用。此处不显示完整内容。数据库删除与物理文件清理是不同结果；失败或中断的清理绝不会被报告为完成。不启动新的付费工作；已有任务可能已经产生费用。来源变化需要重新确认。提交结果不明时不会自动重试。",
    ),
}
