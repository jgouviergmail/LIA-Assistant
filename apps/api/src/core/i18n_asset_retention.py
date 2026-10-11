"""Retention consent distinguishes keeping from a fresh future expiry."""

from src.core.i18n_types import Language

ASSET_RETENTION_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Conservation des fichiers",
        "Cette confirmation modifie la conservation des fichiers listés. Conserver retire leur expiration dans les quotas affichés. Libérer donne aux fichiers conservés une nouvelle échéance selon la durée affichée, sans suppression immédiate. Les fichiers déjà dans l’état demandé restent inchangés. Les contenus ne sont pas modifiés. Une sélection ou un quota modifié nécessite une nouvelle confirmation ; un résultat incertain ne sera pas relancé automatiquement.",
    ),
    "en": (
        "File retention",
        "This confirmation changes retention for the listed files. Keeping removes expiry within the displayed quotas. Releasing gives kept files a fresh deadline using the displayed duration, without immediate deletion. Files already in the requested state remain unchanged. Contents are not changed. Changed selections or quotas need fresh confirmation; an uncertain result is never automatically retried.",
    ),
    "de": (
        "Dateiaufbewahrung",
        "Diese Bestätigung ändert die Aufbewahrung der aufgeführten Dateien. Aufbewahren entfernt das Ablaufdatum innerhalb der angezeigten Kontingente. Freigeben setzt für aufbewahrte Dateien eine neue Frist mit der angezeigten Dauer, ohne sofortige Löschung. Dateien im gewünschten Zustand bleiben unverändert. Inhalte werden nicht geändert. Geänderte Auswahlen oder Kontingente erfordern eine neue Bestätigung; ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Conservación de archivos",
        "Esta confirmación cambia la conservación de los archivos enumerados. Conservar elimina su caducidad dentro de las cuotas mostradas. Liberar da a los archivos conservados una nueva fecha de caducidad según la duración mostrada, sin eliminación inmediata. Los archivos que ya están en el estado solicitado no cambian. Los contenidos no se modifican. Una selección o cuota modificada requiere otra confirmación; los resultados inciertos no se reintentan automáticamente.",
    ),
    "it": (
        "Conservazione dei file",
        "Questa conferma modifica la conservazione dei file elencati. Conservare rimuove la scadenza entro le quote mostrate. Rilasciare dà ai file conservati una nuova scadenza con la durata mostrata, senza eliminazione immediata. I file già nello stato richiesto restano invariati. I contenuti non cambiano. Selezioni o quote modificate richiedono una nuova conferma; i risultati incerti non vengono riprovati automaticamente.",
    ),
    "zh-CN": (
        "文件保留",
        "此确认将更改所列文件的保留状态。保留会在显示的配额内移除过期时间。取消保留会根据显示的时长为已保留文件设置新的期限，不会立即删除。已处于目标状态的文件保持不变，内容不会改变。选择或配额发生变化时需要重新确认；不确定的结果不会自动重试。",
    ),
}
