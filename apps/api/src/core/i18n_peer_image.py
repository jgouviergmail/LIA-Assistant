"""Consent describes a gallery copy and distinguishes it from best-effort delivery."""

from src.core.i18n_types import Language

PEER_IMAGE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Image partagée avec ma connexion",
        "Cette action copie l’image générée sélectionnée dans la galerie de cette personne, avec une nouvelle durée de conservation. Le commentaire est transmis littéralement. Les quotas de partage habituels s’appliquent. La notification est tentée après sauvegarde ; son échec n’annule pas la copie. Aucune copie ni notification avant votre confirmation.",
    ),
    "en": (
        "Image shared with my connection",
        "This action copies the selected generated image into this person's gallery with its own lifetime. The comment is transmitted literally. Existing sharing quotas apply. Notification is attempted after saving; failure does not undo the copy. No copy or notification before your confirmation.",
    ),
    "de": (
        "Mit meiner Verbindung geteiltes Bild",
        "Diese Aktion kopiert das gewählte generierte Bild mit eigener Aufbewahrungsdauer in die Galerie dieser Person. Der Kommentar wird wörtlich übertragen. Die bestehenden Freigabekontingente gelten. Eine Benachrichtigung wird nach dem Speichern versucht; ein Fehlschlag macht die Kopie nicht rückgängig. Keine Kopie oder Benachrichtigung vor Ihrer Bestätigung.",
    ),
    "es": (
        "Imagen compartida con mi conexión",
        "Esta acción copia la imagen generada seleccionada en la galería de esta persona con su propio plazo de conservación. El comentario se transmite literalmente. Se aplican las cuotas habituales. La notificación se intenta tras guardar; su fallo no revierte la copia. No hay copia ni notificación antes de confirmar.",
    ),
    "it": (
        "Immagine condivisa con il mio contatto",
        "Questa azione copia l’immagine generata selezionata nella galleria di questa persona con una nuova durata di conservazione. Il commento viene trasmesso letteralmente. Si applicano le quote esistenti. La notifica viene tentata dopo il salvataggio; un errore non annulla la copia. Nessuna copia o notifica prima della conferma.",
    ),
    "zh-CN": (
        "与我的联系人共享图片",
        "此操作将所选生成图片复制到此人的图库，并使用独立的保留期限。评论按原文传送。适用现有共享配额。保存后尝试发送通知；通知失败不会撤销副本。确认前不会复制图片或发送通知。",
    ),
}
