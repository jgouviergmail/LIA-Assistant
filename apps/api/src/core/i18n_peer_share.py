"""Calendar and task granularity are distinct human consents."""

from src.core.i18n_types import Language

PEER_SHARE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Partage de mes données avec cette connexion",
        "Seul mon partage du domaine affiché change. Calendrier : disponibilités ou détails ; tâches : titres uniquement. Une valeur vide retire ce partage. Les autres domaines et les partages de l’autre personne restent inchangés. Aucun message ni accès aux données n’est exécuté maintenant ; ce réglage autorise des lectures ultérieures.",
    ),
    "en": (
        "My data sharing with this connection",
        "Only my share of the displayed domain changes. Calendar: availability or details; tasks: titles only. An empty level revokes this share. Other domains and the other person's shares remain unchanged. No message or data access runs now; this setting permits later reads.",
    ),
    "de": (
        "Meine Datenfreigabe für diese Verbindung",
        "Nur meine Freigabe des angezeigten Bereichs ändert sich. Kalender: Verfügbarkeit oder Details; Aufgaben: nur Titel. Ein leerer Wert hebt diese Freigabe auf. Andere Bereiche und Freigaben der anderen Person bleiben unverändert. Jetzt werden keine Nachricht und kein Datenabruf ausgeführt; die Einstellung erlaubt spätere Lesezugriffe.",
    ),
    "es": (
        "Mis datos compartidos con esta conexión",
        "Solo cambia mi permiso del ámbito mostrado. Calendario: disponibilidad o detalles; tareas: solo títulos. Un valor vacío revoca este permiso. Los demás ámbitos y los permisos de la otra persona no cambian. Ahora no se envían mensajes ni se consultan datos; este ajuste permite lecturas posteriores.",
    ),
    "it": (
        "Condivisione dei miei dati con questa connessione",
        "Cambia solo la mia condivisione dell’ambito visualizzato. Calendario: disponibilità o dettagli; attività: solo titoli. Un valore vuoto revoca la condivisione. Gli altri ambiti e le condivisioni dell’altra persona restano invariati. Ora non vengono inviati messaggi né letti dati; l’impostazione consente letture successive.",
    ),
    "zh-CN": (
        "与此连接共享我的数据",
        "仅更改我对所示类别的共享权限。日历可共享空闲时间或详情；任务仅共享标题。空值撤销该项共享。其他类别及对方的共享权限保持不变。此操作不会立即发送消息或读取数据，仅允许后续读取。",
    ),
}
