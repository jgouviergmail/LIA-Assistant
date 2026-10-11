"""Independent routing expectations, not generated from taxonomy descriptions.

Cases describe fictional user requests. They execute no tools or providers.
Required domains must all be selected; acceptable domains are optional extras,
not alternatives to required domains. Empty acceptable sets forbid extra scope.
MCP menu variants require the evaluator's explicit fictional server fixtures.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from src.core.i18n_types import Language

MenuVariant = Literal["native", "user_mcp", "admin_mcp", "disabled_mcp", "user_mcp_iterative"]


@dataclass(frozen=True)
class TaxonomyRoutingCase:
    name: str
    query: str
    required_domains: tuple[str, ...]
    acceptable_domains: tuple[str, ...] = ()
    expected_primary: str | None = None
    expected_mutation: bool = False
    language: Language = "fr"
    menu_variant: MenuVariant = "native"


# Every exclusion is a deliberate routing decision, not an automatic omission
# when a new taxonomy entry appears. Coverage tests require a case or rationale.
TAXONOMY_EXEMPTIONS: dict[str, str] = {
    "context": "Internal reference and context utilities, injected rather than routed.",
    "query": "Internal post-retrieval analysis, not a user-selectable source domain.",
    "sub_agent": "Internal delegation capability, injected rather than routed.",
    "mcp": "Virtual fallback; concrete server domains are covered by explicit MCP fixtures.",
    "python": "Platform computation capability outside the data-domain taxonomy.",
}


def _single(
    name: str,
    query: str,
    domain: str,
    *,
    mutation: bool = False,
    language: Language = "fr",
    menu_variant: MenuVariant = "native",
) -> TaxonomyRoutingCase:
    """Package an independently chosen, explicit single-domain expectation."""
    return TaxonomyRoutingCase(
        name,
        query,
        (domain,),
        expected_primary=domain,
        expected_mutation=mutation,
        language=language,
        menu_variant=menu_variant,
    )


TAXONOMY_CASES: tuple[TaxonomyRoutingCase, ...] = (
    _single(
        "native_activity_register",
        "Dans ton registre d'activité, quelles actions as-tu effectuées pour moi cette semaine ?",
        "activity",
    ),
    _single(
        "native_weekly_automation",
        "Crée une automatisation récurrente qui me donne les actualités chaque lundi à 8 h.",
        "automation",
        mutation=True,
    ),
    _single(
        "native_brave_search",
        "Utilise Brave Search pour chercher des articles récents sur les trains de nuit européens.",
        "brave",
    ),
    _single(
        "native_interactive_browser",
        "Avec le navigateur interactif, ouvre https://public.example.test/catalogue et lis le titre de la page.",
        "browser",
    ),
    _single("native_exact_calculation", "Calcule exactement 17 × 23 + 8.", "calculation"),
    _single(
        "native_contact_directory",
        "Quelle adresse e-mail est enregistrée pour Clara Martin dans mes contacts ?",
        "contact",
    ),
    _single(
        "native_server_logs_read",
        "Lis les logs du conteneur API sur mon serveur, sans redémarrer ni modifier quoi que ce soit.",
        "devops",
    ),
    _single(
        "native_uploaded_documents",
        "Dans mes espaces de documents importés, retrouve la clause de résiliation de mon contrat de location.",
        "document",
    ),
    _single(
        "native_downloadable_document",
        "Crée un fichier CSV téléchargeable avec deux colonnes, Produit et Quantité, et une ligne Pommes, 3.",
        "document_generation",
        mutation=True,
    ),
    _single(
        "native_inbox_read",
        "Retrouve dans ma boîte e-mail le dernier message dont l'objet est Budget Atlas.",
        "email",
    ),
    _single(
        "native_calendar_agenda", "Quels rendez-vous figurent dans mon agenda demain ?", "event"
    ),
    _single("native_drive_file", "Trouve le fichier Budget 2026.xlsx dans mon Drive.", "file"),
    _single(
        "native_generated_gallery",
        "Retrouve dans la galerie LIA le PDF que tu as généré hier ; ne crée aucun nouveau fichier.",
        "generated_file",
    ),
    _single(
        "native_health_steps",
        "Combien de pas mes données de santé iPhone ont-elles enregistrés hier ?",
        "health",
    ),
    _single("native_hue_state", "Liste mes ampoules Philips Hue et leur état actuel.", "hue"),
    _single(
        "native_image_creation",
        "Génère une illustration d'un renard dans une forêt enneigée.",
        "image_generation",
        mutation=True,
    ),
    _single(
        "native_lia_journal",
        "Dans ton propre journal LIA, cherche une directive sur la manière de travailler avec moi.",
        "journal",
    ),
    _single(
        "native_conversation_memory",
        "Dans tes souvenirs de nos conversations, cherche le nom de mon ancien professeur de piano.",
        "memory",
    ),
    _single(
        "native_peer_connections",
        "Liste mes connexions acceptées aux autres utilisateurs LIA.",
        "peer",
    ),
    _single(
        "native_perplexity_search",
        "Utilise Perplexity pour rechercher les découvertes récentes en archéologie et fournir une réponse sourcée.",
        "perplexity",
    ),
    _single(
        "native_nearby_places",
        "Trouve les boulangeries près de la place Bellecour à Lyon.",
        "place",
    ),
    _single(
        "native_one_shot_reminder",
        "Rappelle-moi une seule fois demain à 9 h d'emporter mon passeport.",
        "reminder",
        mutation=True,
    ),
    _single(
        "native_explicit_route",
        "Calcule le trajet à pied de 1 place Bellecour, Lyon à 20 quai Claude Bernard, Lyon.",
        "route",
    ),
    _single(
        "native_saved_setting",
        "Quel fuseau horaire est enregistré dans mes paramètres personnels LIA ?",
        "setting",
    ),
    _single(
        "native_persistent_task",
        "Ajoute une tâche persistante intitulée Renouveler le passeport à ma liste de tâches, sans notification.",
        "task",
        mutation=True,
    ),
    _single(
        "native_outbound_call",
        "Passe un appel téléphonique au +33123456789 pour demander les horaires d'ouverture.",
        "telephony",
        mutation=True,
    ),
    _single(
        "native_workboard_tickets", "Montre les tickets ouverts de mon Workboard LIA.", "ticket"
    ),
    _single("native_city_weather", "Quelle météo prévoit-on demain à Lyon, France ?", "weather"),
    _single(
        "native_specific_web_page",
        "Lis le contenu de cette page précise : https://public.example.test/notice.",
        "web_fetch",
    ),
    TaxonomyRoutingCase(
        "native_multi_source_web_search",
        "Fais une recherche générale sur le Web à propos des trains de nuit européens et compare plusieurs sources.",
        ("web_search",),
        ("brave", "perplexity", "wikipedia"),
        "web_search",
    ),
    _single(
        "native_wikipedia_article",
        "Lis le résumé de l'article Wikipédia sur Ada Lovelace.",
        "wikipedia",
    ),
    TaxonomyRoutingCase(
        "chain_contact_to_email",
        "Trouve Clara Martin dans mes contacts, puis envoie-lui un e-mail intitulé Revue Atlas avec le texte Bonjour Clara.",
        ("contact", "email"),
        expected_primary="email",
        expected_mutation=True,
    ),
    TaxonomyRoutingCase(
        "chain_event_to_weather",
        "Retrouve mon événement Randonnée Atlas, puis donne la météo au lieu et à la date de cet événement.",
        ("event", "weather"),
        expected_primary="weather",
    ),
    TaxonomyRoutingCase(
        "chain_event_to_route",
        "Retrouve mon rendez-vous Réunion Atlas, puis calcule le trajet depuis 1 place Bellecour, Lyon jusqu'au lieu du rendez-vous.",
        ("event", "route"),
        expected_primary="route",
    ),
    TaxonomyRoutingCase(
        "distinguish_uploaded_documents_and_drive",
        "Cherche la clause de résiliation dans mes documents importés et retrouve séparément Budget 2026.xlsx dans mon Drive.",
        ("document", "file"),
    ),
    TaxonomyRoutingCase(
        "distinguish_memory_and_lia_journal",
        "Cherche dans tes souvenirs le nom de mon ancien professeur de piano et dans ton propre journal une directive pour travailler avec moi.",
        ("memory", "journal"),
    ),
    TaxonomyRoutingCase(
        "distinguish_reminder_task_and_automation",
        "Crée un rappel ponctuel demain à 9 h pour le passeport, une tâche persistante Renouveler le passeport sans notification, et une automatisation qui résume les actualités chaque lundi à 8 h.",
        ("reminder", "task", "automation"),
        expected_mutation=True,
    ),
    _single(
        "english_image_editing",
        "Edit my latest image to replace its background with a snowy forest.",
        "image_generation",
        mutation=True,
        language="en",
    ),
    _single(
        "german_one_shot_reminder",
        "Erinnere mich morgen um 9 Uhr einmalig daran, meinen Reisepass mitzunehmen.",
        "reminder",
        mutation=True,
        language="de",
    ),
    _single(
        "spanish_drive_file",
        "Busca el archivo Presupuesto 2026.xlsx en mi Drive, no en mis documentos importados.",
        "file",
        language="es",
    ),
    _single(
        "italian_conversation_memory",
        "Cerca nei ricordi delle nostre conversazioni il nome del mio vecchio insegnante di pianoforte, non nel tuo diario.",
        "memory",
        language="it",
    ),
    _single(
        "chinese_peer_connections",
        "列出我在 LIA 中已接受的其他用户连接，不是我的通讯录联系人。",
        "peer",
        language="zh-CN",
    ),
    _single(
        "nancy_explicit_city",
        "Donne la météo à Nancy, France. Nancy désigne ici la ville, pas une personne.",
        "weather",
    ),
    TaxonomyRoutingCase(
        "nancy_contact_home",
        "Donne la météo chez ma fille Nancy. Cherche son adresse postale dans mes contacts ; il ne s'agit pas de la ville Nancy.",
        ("contact", "weather"),
        expected_primary="weather",
    ),
    _single(
        "user_mcp_archives_read",
        "Sur le serveur MCP Archives Atlas, lis les détails du dossier D-42.",
        "mcp_archives_atlas",
        menu_variant="user_mcp",
    ),
    _single(
        "admin_mcp_catalogue_read",
        "Sur le serveur MCP Catalogue Polaris, liste les trois derniers livres du catalogue.",
        "mcp_catalogue_polaris",
        menu_variant="admin_mcp",
    ),
    _single(
        "disabled_mcp_does_not_capture_native_request",
        "Lis l'adresse e-mail de Clara Martin dans mes contacts LIA. Le serveur MCP Archives Atlas est désactivé : ne l'utilise pas.",
        "contact",
        menu_variant="disabled_mcp",
    ),
    _single(
        "iterative_user_mcp_diagram_creation",
        "Sur le serveur MCP Canvas Orion, crée un schéma contenant deux boîtes Atlas et Polaris reliées par une flèche.",
        "mcp_canvas_orion",
        mutation=True,
        menu_variant="user_mcp_iterative",
    ),
)


def assess_routing(
    case: TaxonomyRoutingCase,
    *,
    primary_domain: str | None,
    secondary_domains: Collection[str],
    is_mutation_intent: bool,
) -> tuple[str, ...]:
    """Compare parsed routing fields to independent business expectations only."""
    observed = set(secondary_domains)
    if primary_domain is not None:
        observed.add(primary_domain)
    required = set(case.required_domains)
    allowed = required | set(case.acceptable_domains)
    failures: list[str] = []
    missing = required - observed
    unwanted = observed - allowed
    if missing:
        failures.append("missing_domains:" + ",".join(sorted(missing)))
    if unwanted:
        failures.append("unwanted_domains:" + ",".join(sorted(unwanted)))
    if case.expected_primary is not None and primary_domain != case.expected_primary:
        failures.append("primary_domain:" + str(primary_domain))
    if required and primary_domain is None:
        failures.append("missing_primary_domain")
    if is_mutation_intent != case.expected_mutation:
        failures.append("mutation_intent:" + str(is_mutation_intent))
    return tuple(failures)
