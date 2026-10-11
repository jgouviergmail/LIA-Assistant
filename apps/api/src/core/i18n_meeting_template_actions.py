"""Literal template content and explicit library/default effects in confirmation."""

MEETING_TEMPLATE_ACTION_COPY: dict[str, tuple[str, str, str, str]] = {
    "fr": (
        "Création d’un modèle de compte rendu",
        "Modification d’un modèle de compte rendu",
        "Suppression d’un modèle de compte rendu",
        "Le contenu des sections est présenté intégralement. Cette action porte sur la bibliothèque ; elle ne lance aucun traitement ni e-mail. La suppression indique explicitement si le format par défaut revient au choix automatique et peut affecter les références encore utilisées par des réunions.",
    ),
    "en": (
        "Create a minutes template",
        "Update a minutes template",
        "Delete a minutes template",
        "Section content is shown in full. This action changes the library; it starts no processing or email. Deletion explicitly shows any default-format reset to automatic and may affect references still used by meetings.",
    ),
    "de": (
        "Protokollvorlage erstellen",
        "Protokollvorlage ändern",
        "Protokollvorlage löschen",
        "Abschnittsinhalte werden vollständig angezeigt. Diese Aktion betrifft die Bibliothek und startet keine Verarbeitung oder E-Mail. Beim Löschen wird eine Rücksetzung des Standardformats auf automatisch ausdrücklich angezeigt; noch verwendete Besprechungsverweise können betroffen sein.",
    ),
    "es": (
        "Crear una plantilla de actas",
        "Cambiar una plantilla de actas",
        "Eliminar una plantilla de actas",
        "El contenido de las secciones se muestra completo. Esta acción cambia la biblioteca y no inicia procesamiento ni correo. La eliminación muestra si el formato predeterminado vuelve a automático y puede afectar referencias aún usadas por reuniones.",
    ),
    "it": (
        "Crea un modello di verbale",
        "Modifica un modello di verbale",
        "Elimina un modello di verbale",
        "Il contenuto delle sezioni è mostrato integralmente. Questa azione riguarda la libreria e non avvia elaborazioni o email. L’eliminazione mostra esplicitamente il ripristino del formato predefinito automatico e può influire sui riferimenti ancora usati dalle riunioni.",
    ),
    "zh-CN": (
        "创建会议纪要模板",
        "修改会议纪要模板",
        "删除会议纪要模板",
        "完整显示各节内容。此操作更改模板库，不启动处理或邮件发送。删除时明确显示默认格式是否恢复自动选择，并可能影响会议仍在使用的引用。",
    ),
}
