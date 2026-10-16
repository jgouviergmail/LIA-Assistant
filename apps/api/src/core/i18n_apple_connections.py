"""Safe, localized Apple connection receipts; provider prose is never interpolated."""

from typing import Literal

from src.core.i18n import resolve_language
from src.core.i18n_types import Language

MessageKind = Literal["failed", "authentication", "certificate", "success", "none", "response"]

_MESSAGES: dict[MessageKind, dict[Language, str]] = {
    "failed": {
        "en": "{protocol} connection failed. Check connectivity or contact the instance administrator.",
        "fr": "La connexion {protocol} a échoué. Vérifiez la connexion ou contactez l’administrateur de l’instance.",
        "de": "Die Verbindung über {protocol} ist fehlgeschlagen. Prüfen Sie die Verbindung oder wenden Sie sich an die Administration der Instanz.",
        "es": "La conexión {protocol} ha fallado. Comprueba la conexión o contacta con el administrador de la instancia.",
        "it": "Connessione {protocol} non riuscita. Verifica la connessione o contatta l’amministratore dell’istanza.",
        "zh-CN": "{protocol} 连接失败。请检查网络连接或联系实例管理员。",
    },
    "authentication": {
        "en": "{protocol} authentication failed. Check your Apple ID and app-specific password.",
        "fr": "L’authentification {protocol} a échoué. Vérifiez votre identifiant Apple et votre mot de passe pour application.",
        "de": "Die Anmeldung über {protocol} ist fehlgeschlagen. Prüfen Sie Ihre Apple-ID und Ihr app-spezifisches Passwort.",
        "es": "La autenticación {protocol} ha fallado. Comprueba tu ID de Apple y tu contraseña específica de la app.",
        "it": "Autenticazione {protocol} non riuscita. Verifica il tuo ID Apple e la password specifica per l’app.",
        "zh-CN": "{protocol} 身份验证失败。请检查 Apple ID 和 App 专用密码。",
    },
    "certificate": {
        "en": "The {protocol} server certificate could not be verified. Contact the instance administrator.",
        "fr": "Le certificat du serveur {protocol} n’a pas pu être vérifié. Contactez l’administrateur de l’instance.",
        "de": "Das Zertifikat des {protocol}-Servers konnte nicht geprüft werden. Wenden Sie sich an die Administration der Instanz.",
        "es": "No se ha podido verificar el certificado del servidor {protocol}. Contacta con el administrador de la instancia.",
        "it": "Impossibile verificare il certificato del server {protocol}. Contatta l’amministratore dell’istanza.",
        "zh-CN": "无法验证 {protocol} 服务器证书。请联系实例管理员。",
    },
    "success": {
        "en": "{protocol} connection successful",
        "fr": "Connexion {protocol} réussie",
        "de": "Verbindung über {protocol} erfolgreich",
        "es": "Conexión {protocol} correcta",
        "it": "Connessione {protocol} riuscita",
        "zh-CN": "{protocol} 连接成功",
    },
    "none": {
        "en": "No Apple service selected",
        "fr": "Aucun service Apple sélectionné",
        "de": "Kein Apple-Dienst ausgewählt",
        "es": "No se ha seleccionado ningún servicio de Apple",
        "it": "Nessun servizio Apple selezionato",
        "zh-CN": "未选择 Apple 服务",
    },
    "response": {
        "en": "Unexpected {protocol} response: HTTP {status_code}",
        "fr": "Réponse {protocol} inattendue : HTTP {status_code}",
        "de": "Unerwartete Antwort über {protocol}: HTTP {status_code}",
        "es": "Respuesta {protocol} inesperada: HTTP {status_code}",
        "it": "Risposta {protocol} inattesa: HTTP {status_code}",
        "zh-CN": "{protocol} 响应异常：HTTP {status_code}",
    },
}


def connection_message(
    kind: MessageKind, *, protocol: str = "", status_code: int = 0, language: Language | None = None
) -> str:
    """Only a protocol name and numeric status enter the account's declared language."""
    return _MESSAGES[kind][resolve_language(language)].format(
        protocol=protocol, status_code=status_code
    )
