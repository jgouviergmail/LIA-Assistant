"""URL import confirmation names immutable bytes, exact replacement and third-party isolation."""

from src.core.i18n_types import Language

SKILL_URL_IMPORT_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Compétence à importer depuis une URL",
        "Installe uniquement le paquet validé et remplace uniquement la compétence indiquée. Un changement du téléchargement ou des fichiers actuels exige une nouvelle confirmation. Les scripts restent isolés dans le bac à sable ; tout rafraîchissement de cache en attente est signalé.",
    ),
    "en": (
        "Skill to import from a URL",
        "Installs only the reviewed package and replaces only the named skill. Changed downloaded bytes or current files require fresh approval. Scripts retain sandbox isolation; pending cache refresh is reported.",
    ),
    "de": (
        "Skill aus einer URL importieren",
        "Installiert nur das geprüfte Paket und ersetzt nur den benannten Skill. Geänderte Downloads oder vorhandene Dateien erfordern neue Freigabe. Skripte bleiben isoliert; ausstehende Cache-Aktualisierung wird angezeigt.",
    ),
    "es": (
        "Competencia para importar desde URL",
        "Instala solo el paquete revisado y reemplaza únicamente la competencia indicada. Cambios en la descarga o los archivos actuales requieren nueva confirmación. Los scripts siguen aislados; se indica la actualización pendiente de caché.",
    ),
    "it": (
        "Competenza da importare da URL",
        "Installa solo il pacchetto verificato e sostituisce solo la competenza indicata. Modifiche al download o ai file esistenti richiedono nuova approvazione. Gli script restano isolati; viene indicato l'aggiornamento della cache in attesa.",
    ),
    "zh-CN": (
        "从 URL 导入的技能",
        "仅安装审核过的包，并仅替换指定技能。下载内容或当前文件变更需要重新确认。脚本仍在沙盒中隔离；标明待刷新的缓存状态。",
    ),
}
