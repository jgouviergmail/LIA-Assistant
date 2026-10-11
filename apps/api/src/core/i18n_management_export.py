"""Human-readable export scope and honest browser-request confirmation."""

from typing import NamedTuple

from src.core.i18n_types import Language


class ManagementExportCopy(NamedTuple):
    note: str
    interests: str


MANAGEMENT_EXPORT_COPY: dict[Language, ManagementExportCopy] = {
    "fr": ManagementExportCopy(
        "Exporter tous vos centres d’intérêt au format indiqué, y compris ceux bloqués ou dormants. Le poids correspond à la date affichée. Le navigateur d’origine lancera une seule demande après confirmation. Des données modifiées nécessitent un nouvel accord. LIA confirme la demande, pas l’enregistrement du fichier sur votre appareil.",
        "Centres d’intérêt à exporter",
    ),
    "en": ManagementExportCopy(
        "Export all your interests in the displayed format, including blocked and dormant topics. Weight is observed at the displayed date. The original browser starts one request after confirmation. Changed data requires fresh approval. LIA confirms the request, not that the file was saved on your device.",
        "Interests to export",
    ),
    "de": ManagementExportCopy(
        "Alle Ihre Interessen im angezeigten Format exportieren, einschließlich blockierter und ruhender Themen. Das Gewicht gilt zum angezeigten Zeitpunkt. Der ursprüngliche Browser startet nach Bestätigung eine Anfrage. Geänderte Daten erfordern eine neue Zustimmung. LIA bestätigt die Anfrage, nicht das Speichern auf Ihrem Gerät.",
        "Zu exportierende Interessen",
    ),
    "es": ManagementExportCopy(
        "Exportar todos tus intereses en el formato indicado, incluidos los bloqueados e inactivos. El peso corresponde a la fecha mostrada. El navegador original inicia una solicitud tras confirmar. Los datos modificados requieren otra aprobación. LIA confirma la solicitud, no que el archivo se haya guardado en tu dispositivo.",
        "Intereses que se exportarán",
    ),
    "it": ManagementExportCopy(
        "Esportare tutti i tuoi interessi nel formato indicato, inclusi quelli bloccati o inattivi. Il peso corrisponde alla data mostrata. Il browser originale avvia una sola richiesta dopo la conferma. I dati modificati richiedono un nuovo consenso. LIA conferma la richiesta, non il salvataggio sul dispositivo.",
        "Interessi da esportare",
    ),
    "zh-CN": ManagementExportCopy(
        "按显示的格式导出您的全部兴趣，包括已屏蔽和休眠的主题。权重以所示时间为准。确认后，原浏览器只发起一次请求。数据发生变化时需要重新批准。LIA可确认请求，但无法确认文件已保存到您的设备。",
        "待导出的兴趣",
    ),
}
