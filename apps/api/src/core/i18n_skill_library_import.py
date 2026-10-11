"""Library consent states exact source/commit, scripts, audits and possible cache refresh."""

from src.core.i18n_types import Language

SKILL_LIBRARY_IMPORT_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Compétence de bibliothèque à installer ou mettre à jour",
        "Installe uniquement la version et la source affichées après confirmation. Les scripts restent soumis au bac à sable existant. Un changement des fichiers locaux, de la source ou des droits exige une nouvelle validation ; tout rafraîchissement de cache en attente est signalé.",
    ),
    "en": (
        "Library skill to install or update",
        "Installs only the displayed version and source after confirmation. Scripts retain existing sandbox isolation. Changed local files, source or permissions require fresh approval; pending cache refresh is reported.",
    ),
    "de": (
        "Bibliotheks-Skill installieren oder aktualisieren",
        "Installiert nach Bestätigung nur die angezeigte Version und Quelle. Skripte bleiben in der bestehenden Sandbox. Geänderte lokale Dateien, Quellen oder Rechte erfordern eine neue Freigabe; ausstehende Cache-Aktualisierung wird angezeigt.",
    ),
    "es": (
        "Competencia de biblioteca para instalar o actualizar",
        "Instala solo la versión y fuente mostradas tras confirmar. Los scripts conservan el aislamiento existente. Cambios en archivos locales, fuente o permisos requieren nueva aprobación; se indica la actualización pendiente de caché.",
    ),
    "it": (
        "Competenza della libreria da installare o aggiornare",
        "Installa solo versione e origine mostrate dopo conferma. Gli script restano nella sandbox esistente. Modifiche a file locali, origine o permessi richiedono nuova approvazione; viene indicato l'aggiornamento della cache in attesa.",
    ),
    "zh-CN": (
        "要安装或更新的技能库技能",
        "仅在确认后安装显示的版本和来源。脚本仍受现有沙盒隔离。本地文件、来源或权限变更需要重新批准；标明待刷新的缓存状态。",
    ),
}
