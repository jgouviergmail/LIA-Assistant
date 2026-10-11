"""Skill archive metadata-only browser-transfer consent."""

from src.core.i18n_types import Language

SKILL_DOWNLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Compétence à télécharger",
        "Archive complète de la compétence et de ses ressources. Les instructions ne sont pas exposées dans le consentement. Seul le navigateur d’origine peut demander ce transfert une fois ; le téléchargement demandé ne prouve pas la réception ni l’enregistrement.",
    ),
    "en": (
        "Skill to download",
        "Complete archive of the skill and resources. Instructions are excluded from consent. Only the original browser may request this transfer once; a requested download does not prove reception or saving.",
    ),
    "de": (
        "Skill herunterladen",
        "Vollständiges Archiv des Skills und seiner Ressourcen. Anweisungen werden im Einwilligungsdialog nicht offengelegt. Nur der ursprüngliche Browser darf die Übertragung einmal anfordern; dies bestätigt weder Empfang noch Speicherung.",
    ),
    "es": (
        "Competencia para descargar",
        "Archivo completo de la competencia y sus recursos. Las instrucciones no se muestran en la confirmación. Solo el navegador original puede solicitar la transferencia una vez; solicitarla no confirma la recepción ni el guardado.",
    ),
    "it": (
        "Competenza da scaricare",
        "Archivio completo della competenza e delle risorse. Le istruzioni non sono mostrate nel consenso. Solo il browser originale può richiedere il trasferimento una volta; la richiesta non conferma ricezione o salvataggio.",
    ),
    "zh-CN": (
        "要下载的技能",
        "包含技能及资源的完整归档。确认信息不公开技能指令。只有原浏览器能请求一次传输；请求下载不证明已接收或保存。",
    ),
}
