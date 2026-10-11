"""Skill removal discloses staged rows and pending disk/cache cleanup."""

from src.core.i18n_types import Language

SKILL_DELETE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Compétence personnelle à supprimer",
        "Supprime uniquement cette compétence personnelle et ses ressources après validation certaine. Une compétence de plugin se retire avec son plugin. Un fichier modifié ou une réinstallation est conservé ; tout nettoyage ou rafraîchissement encore en attente est signalé.",
    ),
    "en": (
        "Personal skill to delete",
        "Removes only this personal skill and its resources after known commit. Plugin skills leave through plugin uninstall. Changed files or reinstalled skills are retained; pending cleanup or cache refresh is reported.",
    ),
    "de": (
        "Persönlichen Skill löschen",
        "Entfernt diesen persönlichen Skill und seine Ressourcen nach bestätigtem Commit. Plugin-Skills werden mit ihrem Plugin entfernt. Geänderte Dateien und neu installierte Skills bleiben erhalten; ausstehende Bereinigung wird angezeigt.",
    ),
    "es": (
        "Competencia personal para eliminar",
        "Elimina esta competencia personal y sus recursos tras confirmar el registro. Las competencias de plugin se eliminan con su plugin. Los archivos cambiados y las reinstalaciones se conservan; se indica la limpieza pendiente.",
    ),
    "it": (
        "Competenza personale da eliminare",
        "Rimuove questa competenza personale e le risorse dopo commit confermato. Le competenze del plugin si rimuovono con il plugin. File modificati e reinstallazioni sono conservati; la pulizia pendente viene segnalata.",
    ),
    "zh-CN": (
        "要删除的个人技能",
        "只在确认提交后移除此个人技能及资源。插件技能随插件卸载。保留已变更或重新安装的文件；标明仍待清理或刷新缓存的状态。",
    ),
}
