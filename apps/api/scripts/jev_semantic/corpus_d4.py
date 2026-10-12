"""D4 — which ontology entities a request must read or look up first (Contact, Place, CalendarEvent, EmailMessage).

``required``: entities without which the request cannot be fulfilled. ``optional``:
entities a reasonable plan may also read without being wrong. Everything else
must not be selected. Hand-written; the independent split shares no phrasing.
"""

from scripts.jev_semantic.cases import Case, Split
from scripts.jev_semantic.questions import D4_ENTITIES

LABELS = frozenset(D4_ENTITIES)
C, P, E, M = "Contact", "Place", "CalendarEvent", "EmailMessage"

# (language, family, query, required, optional)
Row = tuple[str, str, str, tuple[str, ...], tuple[str, ...]]
CALIBRATION: tuple[Row, ...] = (
    ("fr", "relation_route", "Itinéraire pour aller chez mon frère", (C,), ()),
    (
        "fr",
        "event_weather",
        "Quelle météo pour mon rendez-vous chez le dentiste demain ?",
        (E,),
        (),
    ),
    ("fr", "reply_mail", "Réponds au dernier mail de Paul pour confirmer", (M,), (C,)),
    ("fr", "place_search", "Trouve 3 cafés près de montbéliard", (P,), ()),
    ("fr", "named_landmark", "Itinéraire vers la tour Eiffel", (), (P,)),
    ("fr", "explicit_email", "Envoie un mail à marc@example.test pour dire bonjour", (), ()),
    ("fr", "named_person_email", "Envoie un mail à Sophie Martin pour lui dire bonjour", (C,), ()),
    (
        "fr",
        "event_attendees",
        "Invite les participants de la réunion de demain à un déjeuner",
        (E,),
        (C, P),
    ),
    (
        "fr",
        "mail_to_person",
        "Transfère la facture de mon dernier mail à mon comptable",
        (M, C),
        (),
    ),
    ("fr", "event_place", "Réserve un restaurant près de mon prochain rendez-vous", (E, P), ()),
    ("fr", "event_route", "Combien de temps pour aller à ma réunion de 14 h ?", (E,), (P,)),
    ("fr", "previous_place", "Appelle le restaurant d'hier soir", (P,), (E,)),
    ("fr", "explicit_city_weather", "Quel temps fait-il à Lyon ?", (), ()),
    ("fr", "reminder", "Ajoute un rappel à 18 h pour sortir le chien", (), ()),
    ("fr", "contact_address", "Quelle est l'adresse de mon médecin ?", (C,), (P,)),
    (
        "fr",
        "mail_sender",
        "Écris à l'expéditeur du mail sur la livraison pour le remercier",
        (M,),
        (C,),
    ),
    (
        "fr",
        "event_guests",
        "Préviens les invités du dîner de samedi que je serai en retard",
        (E,),
        (C,),
    ),
    ("fr", "relation_place_search", "Pharmacies ouvertes près de chez ma mère", (C, P), ()),
    ("fr", "event_location_route", "Itinéraire vers le lieu de ma réunion de demain", (E,), (P,)),
    ("fr", "mail_search", "Qui m'a écrit à propos du loyer ?", (M,), ()),
    ("fr", "pronoun_person", "Envoie-lui le compte rendu, c'est Thomas Girard", (C,), ()),
    ("fr", "distance_explicit", "Combien de kilomètres entre Paris et Lyon ?", (), ()),
    ("fr", "mail_content", "Dis-moi ce que contient le mail de la banque", (M,), ()),
    (
        "fr",
        "named_venue_booking",
        "Réserve une table au restaurant Le Comptoir du Relais pour 20 h",
        (P,),
        (),
    ),
    ("fr", "contact_birthday", "Ajoute l'anniversaire de mon frère à mon agenda", (C,), ()),
    ("fr", "event_move", "Déplace mon rendez-vous de jeudi à vendredi", (E,), ()),
    ("fr", "event_list", "Quels sont mes rendez-vous demain ?", (E,), ()),
    ("fr", "contact_list", "Liste mes contacts qui habitent à Lyon", (C,), ()),
    ("fr", "mail_unread", "Trouve mes mails non lus", (M,), ()),
    ("fr", "general_knowledge", "Qui a écrit Les Misérables ?", (), ()),
    (
        "fr",
        "event_from_mail",
        "Ajoute à mon agenda le rendez-vous proposé dans le mail de Léa",
        (M,),
        (C,),
    ),
    ("fr", "place_details", "À quelle heure ferme la boulangerie Au Pain Doré ?", (P,), ()),
    ("fr", "call_relation", "Appelle ma sœur", (C,), ()),
    ("fr", "explicit_address_route", "Itinéraire jusqu'au 12 rue des Lilas à Lyon", (), ()),
    ("en", "relation_route", "How long to drive to my parents' house?", (C,), ()),
    ("en", "event_weather", "Will it rain during my tennis match on Saturday?", (E,), ()),
    ("en", "mail_sender", "Reply to whoever sent me the invoice yesterday", (M,), (C,)),
    ("en", "place_search", "Find a vegan restaurant near Covent Garden", (P,), ()),
    ("en", "named_person_email", "Email Daniel Wright the meeting notes", (C,), ()),
    ("en", "event_place", "Book a taxi to my 3 pm meeting", (E,), (P,)),
    ("en", "general_knowledge", "How tall is Mount Everest?", (), ()),
    ("es", "relation_route", "Ruta a casa de mi abuela", (C,), ()),
    ("es", "mail_content", "¿Qué dice el último correo de mi jefe?", (M,), (C,)),
    ("es", "event_list", "¿Tengo reuniones el lunes?", (E,), ()),
    ("de", "place_search", "Finde eine Apotheke in der Nähe vom Hauptbahnhof", (P,), ()),
    ("de", "event_guests", "Sag den Teilnehmern des Meetings morgen ab", (E,), (C,)),
    ("it", "named_person_email", "Scrivi a Giuseppe Rossi che arrivo domani", (C,), ()),
    ("it", "mail_unread", "Ci sono email non lette dalla banca?", (M,), ()),
    ("zh", "relation_route", "去我妈妈家怎么走", (C,), ()),
    ("zh", "event_weather", "明天开会的时候会下雨吗", (E,), ()),
)

INDEPENDENT: tuple[Row, ...] = (
    ("fr", "relation_route", "Combien de temps pour aller chez ma grand-mère en train ?", (C,), ()),
    (
        "fr",
        "event_weather",
        "Fera-t-il beau pour le pique-nique prévu dimanche dans mon agenda ?",
        (E,),
        (),
    ),
    ("fr", "reply_mail", "Réponds à Camille sur son mail de ce matin", (M,), (C,)),
    ("fr", "place_search", "Des boulangeries ouvertes le dimanche à Nogent-sur-Marne ?", (P,), ()),
    ("fr", "named_landmark", "Temps de trajet jusqu'au Mont-Saint-Michel", (), (P,)),
    ("fr", "explicit_email", "Écris à camille.b@example.test que le dîner est annulé", (), ()),
    ("fr", "named_person_email", "Envoie le planning à Julien Perrot", (C,), ()),
    ("fr", "event_attendees", "Remercie les participants de l'atelier d'hier", (E,), (C,)),
    ("fr", "mail_to_person", "Fais suivre le billet reçu par mail à ma femme", (M, C), ()),
    ("fr", "event_place", "Trouve un parking près de mon rendez-vous de jeudi", (E, P), ()),
    ("fr", "event_route", "À quelle heure partir pour mon entretien de demain ?", (E,), (P,)),
    ("fr", "previous_place", "Redonne-moi le numéro du garage d'hier", (P,), ()),
    ("fr", "explicit_city_weather", "Va-t-il neiger à Grenoble ce week-end ?", (), ()),
    ("fr", "reminder", "Rappelle-moi de payer le loyer le 5", (), ()),
    ("fr", "contact_address", "Où habite mon parrain ?", (C,), ()),
    ("fr", "mail_sender", "Remercie la personne qui m'a envoyé les photos", (M,), (C,)),
    (
        "fr",
        "event_guests",
        "Dis aux invités de l'anniversaire de Léo que ça commence à 15 h",
        (E,),
        (C,),
    ),
    ("fr", "relation_place_search", "Une boulangerie près de chez mon fils ?", (C, P), ()),
    ("fr", "event_location_route", "Itinéraire vers le lieu de mon cours de yoga", (E,), (P,)),
    ("fr", "mail_search", "Ai-je reçu le contrat du notaire ?", (M,), ()),
    ("fr", "pronoun_person", "Appelle-la, c'est Isabelle Fontaine, mon avocate", (C,), ()),
    ("fr", "distance_explicit", "Distance entre Marseille et Nice ?", (), ()),
    ("fr", "mail_content", "Résume le dernier mail de l'école", (M,), ()),
    ("fr", "named_venue_booking", "Réserve chez Brasserie Lipp samedi soir", (P,), ()),
    ("fr", "contact_birthday", "Quand est l'anniversaire de ma marraine ?", (C,), ()),
    ("fr", "event_move", "Annule mon dîner de vendredi", (E,), ()),
    ("fr", "event_list", "Qu'est-ce que j'ai de prévu ce week-end ?", (E,), ()),
    ("fr", "contact_list", "Quels contacts travaillent chez Michelin ?", (C,), ()),
    ("fr", "mail_unread", "Combien de mails non lus aujourd'hui ?", (M,), ()),
    ("fr", "general_knowledge", "Quelle est la capitale de l'Australie ?", (), ()),
    ("fr", "event_from_mail", "Crée l'événement du concert dont parle le mail de Hugo", (M,), (C,)),
    ("fr", "place_details", "Le musée Rodin est-il ouvert lundi ?", (P,), ()),
    ("fr", "call_relation", "Téléphone à mon oncle", (C,), ()),
    ("fr", "explicit_address_route", "Trajet jusqu'au 9 rue Nationale à Tours", (), ()),
    ("en", "relation_route", "Directions to my aunt's place", (C,), ()),
    ("en", "event_weather", "What's the weather for my flight on Friday?", (E,), ()),
    ("en", "mail_sender", "Thank the person who emailed me about the parcel", (M,), (C,)),
    ("en", "place_search", "Any good pubs near King's Cross?", (P,), ()),
    ("en", "named_person_email", "Send Natalie Brooks the quarterly figures", (C,), ()),
    ("en", "event_place", "Find a coffee shop close to my 10 am appointment", (E, P), ()),
    ("en", "general_knowledge", "When did the Berlin Wall fall?", (), ()),
    ("es", "relation_route", "¿Cuánto tardo en llegar a casa de mi primo?", (C,), ()),
    ("es", "mail_content", "¿De qué trata el correo de la escuela?", (M,), ()),
    ("es", "event_list", "¿Qué tengo en la agenda el jueves?", (E,), ()),
    ("de", "place_search", "Gibt es ein Café in der Nähe vom Marienplatz?", (P,), ()),
    ("de", "event_guests", "Schreib den Gästen der Feier am Samstag", (E,), (C,)),
    ("it", "named_person_email", "Manda a Lucia Esposito il preventivo", (C,), ()),
    ("it", "mail_unread", "Ho email non lette dal commercialista?", (M,), (C,)),
    ("zh", "relation_route", "去我姐姐家要多久", (C,), ()),
    ("zh", "event_weather", "周六的聚会会下雨吗", (E,), ()),
)


def build(split: Split) -> tuple[Case, ...]:
    """The split's cases, in a stable order."""
    rows = CALIBRATION if split == "calibration" else INDEPENDENT
    return tuple(
        Case(
            id=f"d4-{split[:3]}-{index:03d}",
            decision="d4",
            split=split,
            language=language,
            family=family,
            state={"query": query},
            required=frozenset(required),
            optional=frozenset(optional),
        )
        for index, (language, family, query, required, optional) in enumerate(rows, 1)
    )
