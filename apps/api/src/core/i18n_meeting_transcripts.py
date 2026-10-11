"""Exact personal transcript-purge scope in the six application languages."""

MEETING_TRANSCRIPT_COPY = {
    "fr": (
        "Supprimer la transcription de la réunion",
        "Supprime uniquement la transcription source de la réunion sélectionnée. Le compte rendu, sa projection documentaire et l’audio conservé restent présents : ils peuvent contenir des passages issus de la transcription. Les futures régénérations et reformattages nécessitant cette source ne seront plus possibles. Aucun traitement ni courriel n’est lancé. Une transcription déjà absente ne produit aucun changement. Une réponse de commit incertaine n’autorise pas une nouvelle suppression automatique.",
    ),
    "en": (
        "Delete the meeting transcript",
        "Deletes only the selected meeting’s source transcript. Its minutes, document projection and retained audio remain: they can contain transcript-derived passages. Future regeneration and reformatting requiring this source become unavailable. No processing or email starts. An already absent transcript produces no change. An uncertain commit response never authorizes automatic replay.",
    ),
    "de": (
        "Besprechungstranskript löschen",
        "Löscht nur das ursprüngliche Transkript der ausgewählten Besprechung. Protokoll, Dokumentprojektion und aufbewahrte Audiodaten bleiben erhalten und können aus dem Transkript stammende Passagen enthalten. Spätere Neuerstellung oder Umformatierung, die diese Quelle benötigt, ist nicht mehr möglich. Keine Verarbeitung oder E-Mail wird gestartet. Ein bereits fehlendes Transkript bewirkt keine Änderung. Eine ungewisse Commit-Antwort erlaubt keine automatische Wiederholung.",
    ),
    "es": (
        "Eliminar la transcripción de la reunión",
        "Elimina solo la transcripción original de la reunión seleccionada. Las actas, su proyección documental y el audio conservado permanecen y pueden contener pasajes derivados de la transcripción. Las futuras regeneraciones y reformateos que necesiten esta fuente dejarán de estar disponibles. No inicia procesamiento ni correo. Una transcripción ya ausente no produce cambios. Una respuesta de commit incierta nunca autoriza la repetición automática.",
    ),
    "it": (
        "Elimina la trascrizione della riunione",
        "Elimina solo la trascrizione originale della riunione selezionata. Il verbale, la sua proiezione documentale e l’audio conservato rimangono e possono contenere passaggi derivati dalla trascrizione. Le future rigenerazioni e riformattazioni che richiedono questa fonte non saranno più disponibili. Non avvia elaborazioni né email. Una trascrizione già assente non produce cambiamenti. Una risposta di commit incerta non autorizza mai la ripetizione automatica.",
    ),
    "zh-CN": (
        "删除会议转录",
        "仅删除所选会议的原始转录。会议纪要、文档投影和保留的音频仍然存在，其中可能含有源自转录的内容。需要此原始资料的后续重新生成和格式转换将不可用。不会启动处理或邮件发送。转录已不存在时不会产生更改。提交结果不确定时不得自动重复删除。",
    ),
}
