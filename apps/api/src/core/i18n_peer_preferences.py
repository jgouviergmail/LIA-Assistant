"""Consent confirmation names the two independent source audiences precisely."""

from src.core.i18n_types import Language

PEER_PREFERENCES_COPY: dict[Language, tuple[str, str, str]] = {
    "fr": (
        "Être trouvable par les autres utilisateurs",
        "Montrer mon adresse aux connexions acceptées",
        "Ces consentements sont indépendants : être trouvable autorise la recherche exacte de votre compte ; montrer votre adresse la rend visible uniquement à vos connexions acceptées. Seuls les réglages affichés changent. Aucune invitation ni aucun message n’est envoyé.",
    ),
    "en": (
        "Be discoverable by other users",
        "Show my address to accepted connections",
        "These consents are independent: discoverability permits exact searches for your account; address visibility reveals it only to accepted connections. Only the displayed settings change. No invitation or message is sent.",
    ),
    "de": (
        "Für andere Nutzer auffindbar sein",
        "Meine Adresse akzeptierten Verbindungen zeigen",
        "Diese Einwilligungen sind unabhängig: Auffindbarkeit erlaubt die exakte Suche nach Ihrem Konto; Ihre Adresse wird nur akzeptierten Verbindungen angezeigt. Nur die angezeigten Einstellungen ändern sich. Es werden keine Einladungen oder Nachrichten gesendet.",
    ),
    "es": (
        "Permitir que otros usuarios me encuentren",
        "Mostrar mi dirección a conexiones aceptadas",
        "Estos consentimientos son independientes: la visibilidad permite búsquedas exactas de tu cuenta; tu dirección se muestra solo a conexiones aceptadas. Solo cambian los ajustes mostrados. No se envía ninguna invitación ni mensaje.",
    ),
    "it": (
        "Essere trovabile dagli altri utenti",
        "Mostrare il mio indirizzo alle connessioni accettate",
        "Questi consensi sono indipendenti: la reperibilità permette ricerche esatte del tuo account; il tuo indirizzo è visibile solo alle connessioni accettate. Cambiano solo le impostazioni mostrate. Non viene inviato alcun invito o messaggio.",
    ),
    "zh-CN": (
        "允许其他用户搜索到我",
        "向已接受的连接显示我的邮箱地址",
        "这两项同意互相独立：可发现性允许精确搜索您的账户；邮箱地址仅向已接受的连接显示。仅更改列出的设置，不发送邀请或消息。",
    ),
}
