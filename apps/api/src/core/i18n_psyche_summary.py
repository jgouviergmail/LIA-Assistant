"""Paid companion prose, source initialization and provider fallback are disclosed."""

from src.core.i18n_types import Language

PSYCHE_SUMMARY_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Résumé psychologique de LIA",
        "Générer le résumé de l’humeur et de la relation de LIA avec les réglages affichés. Cette action peut initialiser un état absent et consomme des tokens plateforme sous quotas. Un échec du modèle peut produire le résumé de secours existant malgré un coût engagé. Le texte décrit LIA et n’est pas un diagnostic de l’utilisateur ; il n’est pas enregistré comme récit. Données modifiées, droits retirés ou accord expiré : refuser les étapes restantes et ne pas divulguer un texte devenu obsolète. Ne pas rejouer automatiquement un résultat partiel ou incertain.",
    ),
    "en": (
        "LIA psyche summary",
        "Generate LIA’s mood and relationship summary using the displayed settings. This action may initialize absent state and consumes platform tokens under quotas. A model failure may return the existing template fallback despite incurred cost. Text describes LIA, is not a diagnosis of the user and is not saved as a narrative. Changed data, withdrawn rights or expired approval refuse remaining phases and suppress stale prose. Never automatically replay partial or uncertain results.",
    ),
    "de": (
        "Psychologischer Überblick von LIA",
        "LIAs Stimmung und Beziehung mit den angezeigten Einstellungen zusammenfassen. Fehlender Zustand kann initialisiert werden; Plattform-Token unterliegen Quoten. Bei Modellfehlern kann trotz Kosten die vorhandene Ersatzvorlage erscheinen. Der Text beschreibt LIA, stellt keine Diagnose des Nutzers dar und wird nicht als Erzählung gespeichert. Geänderte Daten, entzogene Rechte oder abgelaufene Zustimmung stoppen weitere Phasen und unterdrücken veralteten Text. Teilweise oder unsichere Ergebnisse nie automatisch wiederholen.",
    ),
    "es": (
        "Resumen psicológico de LIA",
        "Generar el resumen del ánimo y relación de LIA con los ajustes indicados. Puede inicializar un estado ausente y consume tokens de plataforma sujetos a cuotas. Un fallo del modelo puede devolver la plantilla existente pese al coste. El texto describe LIA, no diagnostica al usuario y no se guarda como relato. Cambios, permisos retirados o aprobación caducada impiden las fases restantes y ocultan texto obsoleto. No repetir automáticamente resultados parciales o inciertos.",
    ),
    "it": (
        "Sintesi psicologica di LIA",
        "Generare la sintesi dell’umore e della relazione di LIA con le impostazioni mostrate. Può inizializzare uno stato assente e consuma token della piattaforma con quote. Un errore del modello può restituire il modello di testo esistente nonostante i costi. Il testo descrive LIA, non diagnostica l’utente e non viene salvato come narrazione. Modifiche, permessi revocati o consenso scaduto impediscono le fasi rimanenti e nascondono testo obsoleto. Non ripetere automaticamente risultati parziali o incerti.",
    ),
    "zh-CN": (
        "LIA心理状态摘要",
        "按显示的设置生成LIA的情绪和关系摘要。该操作可能初始化尚不存在的状态，并在配额限制下消耗平台令牌。模型失败时可能返回现有模板摘要，仍可能产生费用。文本描述LIA，不诊断用户，也不保存为叙事。数据变化、权限撤销或批准过期时拒绝后续阶段并禁止披露过时文本。不得自动重放部分完成或不确定的结果。",
    ),
}
