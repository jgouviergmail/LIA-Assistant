"""The approved source link is a standing instruction with later indexing costs."""

from src.core.i18n_types import Language

SOURCE_LINK_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Source à relier",
        "Cette confirmation relie ce dossier Drive ou label Gmail à cet espace et autorise son suivi automatique. Les synchronisations ultérieures peuvent consommer les quotas du fournisseur et entraîner des coûts d’indexation. Cette liaison seule ne lance aucune indexation immédiate et ne signifie pas que les documents sont déjà importés. Le suivi nécessite un espace actif et les capacités activées. La source, son nom, la destination, les limites, vos droits et la validité sont revérifiés. Un résultat incertain ne déclenche aucune relance automatique.",
    ),
    "en": (
        "Source to link",
        "This confirmation links this Drive folder or Gmail label to this space and authorizes automatic tracking. Later synchronizations can consume provider quotas and incur indexing costs. Linking alone starts no immediate indexing and does not mean documents are already imported. Tracking requires an active space and enabled capabilities. The source, name, destination, limits, authority and expiry are checked again. An uncertain result never triggers an automatic retry.",
    ),
    "de": (
        "Zu verknüpfende Quelle",
        "Diese Bestätigung verknüpft diesen Drive-Ordner oder dieses Gmail-Label mit dem Bereich und erlaubt die automatische Aktualisierung. Spätere Synchronisierungen können Anbieterkontingente verbrauchen und Indexierungskosten verursachen. Die Verknüpfung startet keine sofortige Indexierung und bedeutet nicht, dass Dokumente bereits importiert wurden. Die Aktualisierung erfordert einen aktiven Bereich und aktivierte Funktionen. Quelle, Name, Ziel, Grenzen, Berechtigungen und Ablauf werden erneut geprüft. Ein ungewisses Ergebnis wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Fuente que se vinculará",
        "Esta confirmación vincula esta carpeta Drive o etiqueta Gmail al espacio y autoriza su seguimiento automático. Las sincronizaciones posteriores pueden consumir cuotas del proveedor y generar costes de indexación. La vinculación por sí sola no inicia una indexación inmediata ni significa que los documentos ya estén importados. El seguimiento requiere un espacio activo y capacidades habilitadas. Se vuelven a comprobar fuente, nombre, destino, límites, permisos y caducidad. Un resultado incierto nunca se reintenta automáticamente.",
    ),
    "it": (
        "Fonte da collegare",
        "Questa conferma collega questa cartella Drive o etichetta Gmail allo spazio e autorizza il monitoraggio automatico. Le sincronizzazioni successive possono consumare quote del fornitore e generare costi di indicizzazione. Il collegamento da solo non avvia un’indicizzazione immediata e non significa che i documenti siano già importati. Il monitoraggio richiede uno spazio attivo e funzionalità abilitate. Fonte, nome, destinazione, limiti, autorizzazioni e scadenza vengono ricontrollati. Un risultato incerto non viene riprovato automaticamente.",
    ),
    "zh-CN": (
        "待关联的来源",
        "此确认将该 Drive 文件夹或 Gmail 标签关联到此空间，并授权自动跟踪。后续同步可能消耗提供商配额并产生索引费用。仅建立关联不会立即开始索引，也不意味着文档已导入。跟踪需要启用的空间和功能。系统会再次检查来源、名称、目标、限制、权限和有效期。结果不确定时不会自动重试。",
    ),
}
