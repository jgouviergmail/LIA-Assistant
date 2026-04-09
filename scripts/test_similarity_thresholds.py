"""
Similarity threshold calibration script for Gemini embedding-001.

Comprehensive test with large datasets to determine optimal values for:
- MEMORY_MIN_SEARCH_SCORE (retrieval gate, query->doc asymmetric)
- MEMORY_RELEVANCE_THRESHOLD (usage tracking, query->doc asymmetric)
- JOURNAL_CONTEXT_MIN_SCORE (context injection, query->doc asymmetric)
- JOURNAL_DEDUP_SIMILARITY_THRESHOLD (merge guard, doc->doc symmetric)
- INTEREST_DEDUP_SIMILARITY_THRESHOLD (topic merge, doc->doc symmetric)
- INTEREST_CONTENT_SIMILARITY_THRESHOLD (notif dedup, doc->doc symmetric)
- RAG_SPACES_RETRIEVAL_MIN_SCORE (chunk retrieval, query->doc asymmetric)

NOTE: QUERY_ENGINE_SIMILARITY_THRESHOLD uses SequenceMatcher (Levenshtein),
not embeddings -- tested separately at the end.

Uses Gemini embedding-001 with asymmetric task types.
"""

import os
import sys
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# -- Config --
API_KEY = os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "models/gemini-embedding-001"
DIMS = 1536


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


@dataclass
class TC:
    label: str
    text_a: str
    text_b: str
    expected: str  # "match", "near", "unrelated"


# =============================================================================
# 1. MEMORY RETRIEVAL (query -> stored memory doc) -- asymmetric
#    Impact: too low = noise/tokens wasted (up to 50 memories x 150 tok)
#            too high = AI loses user context, feels impersonal
# =============================================================================
MEMORY_TESTS = [
    # --- MATCH: query should retrieve this memory ---
    TC("Wife name", "ma femme", "Mon epouse s'appelle Hua Gouvier, mariee depuis 2018.", "match"),
    TC("Wife name v2", "parle-moi de Hua", "Mon epouse s'appelle Hua Gouvier, elle est d'origine vietnamienne.", "match"),
    TC("Email", "mon adresse email", "L'adresse email de l'utilisateur est jean.gouvier@gmail.com", "match"),
    TC("Home", "ou j'habite", "L'utilisateur habite a Lyon, 3eme arrondissement, quartier Part-Dieu.", "match"),
    TC("Birthday", "mon anniversaire", "L'utilisateur est ne le 15 mars 1985 a Villeurbanne.", "match"),
    TC("Music pref", "ma musique preferee", "L'utilisateur aime le jazz et Debussy. Il ecoute souvent Miles Davis.", "match"),
    TC("Work", "mon travail", "L'utilisateur est developpeur senior chez TechCorp depuis 2020.", "match"),
    TC("Allergy", "mes allergies", "L'utilisateur est allergique aux arachides et au gluten.", "match"),
    TC("Pet name", "mon chat", "L'utilisateur a deux chats: Mochi (siamois) et Pixel (noir).", "match"),
    TC("Language", "les langues que je parle", "L'utilisateur parle francais (natif), anglais (courant) et un peu de vietnamien.", "match"),
    TC("Car", "ma voiture", "L'utilisateur conduit une Tesla Model 3 blanche, achetee en 2023.", "match"),
    TC("Morning routine", "ma routine du matin", "L'utilisateur se leve a 6h30, fait 20min de yoga puis prepare un cafe filtre.", "match"),
    TC("Fav restaurant", "mon restaurant prefere", "Le restaurant prefere de l'utilisateur est Le Comptoir du Sud a Lyon.", "match"),
    TC("Kids school", "l'ecole des enfants", "Les enfants de l'utilisateur sont scolarises a l'ecole Montessori de Villeurbanne.", "match"),
    TC("Health", "mon medecin", "Le medecin traitant de l'utilisateur est le Dr. Martin, cabinet rue Garibaldi.", "match"),

    # --- NEAR: related but not a direct answer ---
    TC("Vacation tangent", "mes vacances", "L'utilisateur a voyage en Italie l'ete dernier avec sa famille.", "near"),
    TC("Family partial", "mes enfants", "La famille de l'utilisateur comprend sa femme Hua et leurs deux chats.", "near"),
    TC("Sport adjacent", "le sport", "L'utilisateur fait du jogging le dimanche matin dans le parc de la Tete d'Or.", "near"),
    TC("Food general", "ce que j'aime manger", "L'utilisateur va souvent au restaurant japonais Koya le vendredi soir.", "near"),
    TC("Tech hobby", "mes hobbies", "L'utilisateur contribue a des projets open-source Python le week-end.", "near"),
    TC("Reading tangent", "mes livres", "L'utilisateur s'interesse a la philosophie stoicienne et cite souvent Marc Aurele.", "near"),
    TC("Friend mention", "mes amis", "L'utilisateur dejeune regulierement avec son collegue Marc le mercredi.", "near"),
    TC("Weekend vague", "mon week-end", "L'utilisateur prefere passer ses samedis en famille et ses dimanches en solo.", "near"),

    # --- UNRELATED: should NOT be retrieved ---
    TC("Weather vs IDE", "la meteo demain", "L'utilisateur prefere les IDE JetBrains pour le developpement.", "unrelated"),
    TC("Recipe vs Python", "recette de gateau", "L'utilisateur utilise Python 3.12 et FastAPI pour ses projets.", "unrelated"),
    TC("Politics vs Netflix", "actualites politiques", "L'utilisateur a un abonnement Netflix et Disney+.", "unrelated"),
    TC("Gardening vs DB", "conseil jardinage", "L'utilisateur utilise PostgreSQL avec pgvector pour les embeddings.", "unrelated"),
    TC("Math vs coffee", "equation differentielle", "L'utilisateur boit du cafe filtre le matin et du the vert l'apres-midi.", "unrelated"),
    TC("Football vs code", "resultat du match", "L'utilisateur a configure son environnement VSCode avec le theme Dracula.", "unrelated"),
    TC("Cinema vs car", "film a voir", "L'utilisateur conduit une Tesla Model 3 et la recharge chez lui.", "unrelated"),
    TC("Travel plan vs allergy", "reserver un vol", "L'utilisateur est allergique aux arachides et au gluten.", "unrelated"),
]

# =============================================================================
# 2. JOURNAL CONTEXT (query -> journal entry doc) -- asymmetric
#    Impact: too low = false behavioral directives injected (dangerous!)
#            too high = AI misses patterns/preferences
# =============================================================================
JOURNAL_TESTS = [
    # --- MATCH ---
    TC("Project direct", "mon projet LIA", "Aujourd'hui j'ai travaille sur l'architecture du module d'agents de LIA. Implemente le router node.", "match"),
    TC("Emotion query", "comment je me sentais hier", "Je me suis senti fatigue et un peu frustre par les bugs de deploiement.", "match"),
    TC("Meeting query", "ma reunion avec le client", "Reunion avec le client Acme Corp pour discuter du sprint review. Bonne avancee.", "match"),
    TC("Goals query", "mes objectifs cette semaine", "Cette semaine je veux finaliser le module de memoire et commencer les tests d'integration.", "match"),
    TC("Productivity", "comment je travaille le mieux", "J'ai remarque que je suis plus productif le matin entre 7h et 11h. Apres le dejeuner c'est plus difficile.", "match"),
    TC("Sleep pattern", "mon sommeil", "J'ai mal dormi cette nuit, reveille a 3h du matin. Le stress du deploiement probablement.", "match"),
    TC("Learning", "ce que j'ai appris", "Decouverte du pattern ReAct pour les agents LLM. Tres prometteur pour l'orchestration multi-outils.", "match"),
    TC("Workout", "mon entrainement", "Session de course a pied ce matin: 8km en 42 minutes. Bon rythme, pas de douleur au genou.", "match"),
    TC("Decision", "ma decision sur l'architecture", "Decide de passer de SQLite a PostgreSQL pour supporter les embeddings pgvector. Migration planifiee.", "match"),
    TC("Family event", "l'anniversaire de Hua", "Prepare la surprise pour l'anniversaire de Hua: reservation au restaurant Le Sud, bouquet de fleurs.", "match"),
    TC("Frustration", "ce qui m'enerve au travail", "Frustre par les revues de code interminables. 3 jours pour merger un PR de 50 lignes.", "match"),
    TC("Side project", "mon projet perso", "Avance sur mon side project de domotique: integration Home Assistant avec capteurs Zigbee.", "match"),

    # --- NEAR ---
    TC("Deploy tangent", "le deploiement", "La mise en production a ete retardee a cause d'un probleme de certificat SSL sur le tunnel Cloudflare.", "near"),
    TC("Morning tangent", "ce matin", "Session de travail productive ce matin sur le refactoring du systeme de prompts.", "near"),
    TC("Code review", "les revues de code", "Sprint review positive, le client a valide les 3 user stories principales.", "near"),
    TC("Health general", "ma sante", "Rendez-vous chez le dentiste la semaine prochaine. Penser a prendre le carnet de sante.", "near"),
    TC("Tech mention", "Docker", "Mise a jour de l'infrastructure: passage a Docker Compose v2 avec profiles pour dev/prod.", "near"),
    TC("Weekend", "mon dimanche", "Brunch en famille dimanche, puis promenade au parc. Les enfants ont adore le terrain de jeux.", "near"),
    TC("Budget", "mes depenses", "Achete un nouveau clavier mecanique (Keychron K8). Un peu cher mais le confort en vaut la peine.", "near"),

    # --- UNRELATED ---
    TC("Recipe vs sprint", "ma recette de cookies", "Sprint review tres positive, le client a valide les 3 user stories principales.", "unrelated"),
    TC("Elections vs debug", "les elections", "Debug du middleware d'authentification, trouve un race condition sur le token refresh.", "unrelated"),
    TC("Music vs deploy", "ecouter du jazz", "Deploiement en production reussi apres 3 tentatives. Le hotfix du rate limiter etait necessaire.", "unrelated"),
    TC("Gardening vs meeting", "planter des tomates", "Reunion d'equipe productive: roadmap Q3 validee, priorite sur la scalabilite.", "unrelated"),
    TC("Movie vs code", "film ce soir", "Refactoring majeur du module d'authentification, passage a OAuth2 PKCE.", "unrelated"),
    TC("Travel vs test", "vacances en Grece", "Ecriture de 15 tests d'integration pour le pipeline de memories.", "unrelated"),
    TC("Cooking vs infra", "diner ce soir", "Migration de l'infra monitoring vers Grafana Cloud. Dashboard latency configure.", "unrelated"),
]

# =============================================================================
# 3. JOURNAL DEDUP (doc -> doc) -- symmetric
#    Impact: too low = contradictory merges (lose nuance)
#            too high = journal bloat (duplicate entries)
# =============================================================================
JOURNAL_DEDUP_TESTS = [
    # --- MATCH (should merge) ---
    TC("Near dup auth", "Travaille sur le module d'authentification, corrige le bug de refresh token.",
       "Correction du bug de refresh token dans le module d'auth. Le probleme venait du timing.", "match"),
    TC("Same meeting", "Reunion d'equipe ce matin, discussion sur la roadmap Q2.",
       "Meeting d'equipe du matin: on a parle de la roadmap du deuxieme trimestre.", "match"),
    TC("Embedding migration", "J'ai migre les embeddings de OpenAI vers Gemini.",
       "Migration du modele d'embedding: passage de text-embedding-3-small a gemini-embedding-001.", "match"),
    TC("Productivity same", "Plus productif le matin, j'arrive mieux a me concentrer avant 10h.",
       "Ma meilleure plage de concentration est entre 7h et 10h le matin.", "match"),
    TC("Run duplicate", "Course a pied ce matin, 8km en 42 minutes dans le parc.",
       "Jogging matinal: 8 kilometres au parc de la Tete d'Or, pace correct.", "match"),
    TC("Client feedback same", "Le client Acme est satisfait de la demo, ils veulent avancer sur la phase 2.",
       "Demo reussie chez Acme Corp, feu vert pour la phase 2 du projet.", "match"),
    TC("Sleep issue same", "Mal dormi a cause du stress du deploiement, reveille a 3h.",
       "Insomnie cette nuit, le stress de la mise en production m'a reveille tres tot.", "match"),
    TC("Decision same", "Decide de passer a PostgreSQL pour les embeddings pgvector.",
       "Choix technique: migration vers PostgreSQL + pgvector pour le stockage vectoriel.", "match"),

    # --- NEAR (should NOT merge -- different events/nuances) ---
    TC("Redis cache vs debug", "Implemente le systeme de cache Redis pour les embeddings.",
       "Debogue le systeme de cache Redis, le TTL n'etait pas correctement configure.", "near"),
    TC("Mon vs Fri", "Lundi: revue de code et correction de bugs mineurs.",
       "Vendredi: deploiement en production et monitoring post-release.", "near"),
    TC("Same topic diff outcome", "Le client Acme a rejete notre proposition de prix.",
       "Le client Acme a valide le budget pour la phase 2.", "near"),
    TC("Morning vs evening run", "Course a pied ce matin: 8km, bon rythme.",
       "Course a pied ce soir: 5km de recuperation, rythme lent.", "near"),
    TC("Auth fix vs auth refactor", "Corrige le bug d'expiration du token JWT.",
       "Refactoring complet du module JWT: passage a RS256 et rotation des cles.", "near"),
    TC("Sprint plan vs retro", "Planning du sprint 12: 5 user stories, 34 points.",
       "Retrospective du sprint 11: trop de dette technique, besoin de refactoring.", "near"),
    TC("DB migrate vs optimize", "Migration de la base de donnees vers le nouveau schema v3.",
       "Optimisation des requetes SQL: ajout d'index sur les colonnes les plus sollicitees.", "near"),
    TC("Stress work vs stress health", "Stresse par la deadline du projet, trop de pression.",
       "Stresse par les resultats d'analyse de sang, rendez-vous chez le medecin.", "near"),

    # --- UNRELATED ---
    TC("Grocery vs code", "Course au supermarche, prepare le diner pour la famille.",
       "Refactorise le module de routing LangGraph pour supporter les sous-agents.", "unrelated"),
    TC("Dentist vs deploy", "Rendez-vous chez le dentiste a 14h, detartrage.",
       "Deploiement en production a 14h, fenetre de maintenance planifiee.", "unrelated"),
    TC("Garden vs test", "Plante des tomates et du basilic sur le balcon.",
       "Ecrit 20 tests unitaires pour le service de memoire.", "unrelated"),
    TC("Movie night vs sprint", "Soiree cinema: vu le dernier Nolan, excellent.",
       "Sprint review: 8 stories livrees sur 10, velocity en hausse.", "unrelated"),
    TC("Vacation vs infra", "Reserve les billets d'avion pour les vacances en Crete.",
       "Configure le monitoring Prometheus avec alertes sur la latence API.", "unrelated"),
]

# =============================================================================
# 4. INTEREST DEDUP (doc -> doc) -- symmetric
#    Impact: too low = lost granularity (distinct interests merged)
#            too high = interest proliferation (duplicates accumulate)
# =============================================================================
INTEREST_DEDUP_TESTS = [
    # --- MATCH (same topic, should merge) ---
    TC("AI synonyms", "Intelligence artificielle", "IA et machine learning", "match"),
    TC("French cuisine", "Cuisine francaise", "Gastronomie francaise", "match"),
    TC("Python async", "Python asyncio", "Programmation asynchrone en Python", "match"),
    TC("Running", "Course a pied", "Jogging et running", "match"),
    TC("Photography", "Photographie numerique", "Photo et retouche d'images", "match"),
    TC("Home auto", "Domotique", "Maison connectee et IoT", "match"),
    TC("Crypto syn", "Cryptomonnaies", "Bitcoin et crypto-actifs", "match"),
    TC("Meditation", "Meditation et pleine conscience", "Mindfulness et meditation", "match"),
    TC("Electric cars", "Voitures electriques", "Vehicules electriques et Tesla", "match"),
    TC("DevOps syn", "DevOps et CI/CD", "Integration continue et deploiement", "match"),
    TC("Startup syn", "Entrepreneuriat", "Startups et creation d'entreprise", "match"),
    TC("Wine", "Oenologie", "Degustation de vin et viticulture", "match"),

    # --- NEAR (related but distinct interests, should NOT merge) ---
    TC("ML vs web", "Machine learning", "Developpement web", "near"),
    TC("Italian vs Japanese", "Cuisine italienne", "Cuisine japonaise", "near"),
    TC("Python vs JS", "Python", "JavaScript", "near"),
    TC("Running vs cycling", "Course a pied", "Cyclisme", "near"),
    TC("Photo vs video", "Photographie", "Videographie et montage", "near"),
    TC("Meditation vs yoga", "Meditation", "Yoga", "near"),
    TC("Backend vs frontend", "Developpement backend", "Developpement frontend", "near"),
    TC("Guitar vs piano", "Guitare", "Piano", "near"),
    TC("History vs geography", "Histoire de France", "Geographie europeenne", "near"),
    TC("Chess vs poker", "Echecs", "Poker strategique", "near"),
    TC("Tennis vs badminton", "Tennis", "Badminton", "near"),

    # --- UNRELATED ---
    TC("Garden vs crypto", "Jardinage", "Cryptomonnaies", "unrelated"),
    TC("Cooking vs infosec", "Cuisine", "Cybersecurite", "unrelated"),
    TC("Astronomy vs fashion", "Astronomie", "Mode et haute couture", "unrelated"),
    TC("Fishing vs AI", "Peche en riviere", "Intelligence artificielle", "unrelated"),
    TC("Knitting vs motorsport", "Tricot", "Sport automobile", "unrelated"),
    TC("Poetry vs devops", "Poesie", "DevOps et infrastructure", "unrelated"),
]

# =============================================================================
# 5. INTEREST CONTENT DEDUP (doc -> doc) -- symmetric
#    Impact: too low = missed legitimate content (false positive dedup)
#            too high = notification spam (repetitive content sent)
# =============================================================================
INTEREST_CONTENT_TESTS = [
    # --- MATCH (duplicate content, should skip) ---
    TC("GPT5 same news", "OpenAI lance GPT-5 avec des capacites de raisonnement ameliorees et une fenetre de contexte de 1M tokens.",
       "GPT-5 devoile par OpenAI: raisonnement avance et contexte d'un million de tokens.", "match"),
    TC("iPhone same", "Apple annonce l'iPhone 16 avec une puce A18 et des fonctionnalites IA integrees.",
       "Le nouvel iPhone 16 d'Apple embarque la puce A18 et mise sur l'intelligence artificielle.", "match"),
    TC("Tesla earnings", "Tesla publie des resultats trimestriels records avec 25 milliards de revenus.",
       "Resultats financiers de Tesla: chiffre d'affaires record de 25 milliards au Q3.", "match"),
    TC("Python 3.13 same", "Python 3.13 est sorti avec le JIT compiler experimental et le no-GIL mode.",
       "Sortie de Python 3.13: introduction du compilateur JIT et du mode sans GIL.", "match"),
    TC("Docker sec same", "Une faille de securite critique decouverte dans Docker Desktop affecte les conteneurs Windows.",
       "Vulnerabilite critique dans Docker Desktop: les conteneurs Windows sont compromis.", "match"),
    TC("Climate same", "Le rapport du GIEC 2026 confirme l'acceleration du rechauffement climatique.",
       "Nouveau rapport GIEC: le rechauffement climatique s'accelere plus vite que prevu.", "match"),
    TC("EU AI Act same", "L'Union europeenne adopte l'AI Act, premiere reglementation mondiale de l'IA.",
       "L'AI Act europeen entre en vigueur: premiere loi mondiale encadrant l'intelligence artificielle.", "match"),

    # --- NEAR (same topic, different content -- should NOT skip) ---
    TC("Gemini vs GPT5", "Google DeepMind publie Gemini 2.0 avec des benchmarks record en mathematiques.",
       "OpenAI lance GPT-5 avec des capacites de raisonnement ameliorees.", "near"),
    TC("GPU related", "Le marche des GPU est en penurie a cause de la demande en IA.",
       "NVIDIA annonce la RTX 6090 avec 48GB de VRAM.", "near"),
    TC("Tesla diff angle", "Tesla rappelle 500 000 vehicules pour un defaut de direction assistee.",
       "Tesla publie des resultats trimestriels records avec 25 milliards de revenus.", "near"),
    TC("Python diff versions", "Python 3.13 apporte le JIT compiler experimental.",
       "Python 3.12 ameliore les messages d'erreur et introduit les type parameter syntax.", "near"),
    TC("Docker diff topics", "Docker annonce Docker Scout pour l'analyse de vulnerabilites.",
       "Kubernetes 1.30 introduit le sidecar containers pattern.", "near"),
    TC("AI diff regulation", "La Chine publie ses propres regles de regulation de l'IA generative.",
       "L'Union europeenne adopte l'AI Act, premiere reglementation mondiale de l'IA.", "near"),
    TC("Climate diff aspect", "Les energies renouvelables depassent les fossiles en Europe pour la premiere fois.",
       "Le rapport du GIEC 2026 confirme l'acceleration du rechauffement climatique.", "near"),

    # --- UNRELATED ---
    TC("Recipe vs sport", "Recette: comment faire un risotto aux champignons parfait.",
       "Le PSG remporte la Ligue des Champions face au Real Madrid.", "unrelated"),
    TC("Space vs cooking", "La NASA confirme la decouverte d'eau liquide sur Europa.",
       "Le guide Michelin 2026 decerne 3 etoiles a un restaurant lyonnais.", "unrelated"),
    TC("Crypto vs health", "Bitcoin atteint un nouveau record historique a 150 000 dollars.",
       "L'OMS publie de nouvelles recommandations sur l'activite physique.", "unrelated"),
    TC("Fashion vs tech", "La Fashion Week de Paris met en avant la mode durable.",
       "Microsoft lance Windows 12 avec une integration IA native.", "unrelated"),
    TC("Music vs science", "Beyonce annonce une tournee mondiale pour 2027.",
       "Des chercheurs du CERN observent une nouvelle particule subatomique.", "unrelated"),
]

# =============================================================================
# 6. RAG SPACES (query -> doc chunk) -- asymmetric
#    Impact: too low = off-topic chunks confuse LLM (max 5 chunks, 2000 tok)
#            too high = user knowledge underutilized
# =============================================================================
RAG_TESTS = [
    # --- MATCH ---
    TC("Rate limit config", "comment configurer le rate limiting",
       "Le rate limiting est configure via le middleware FastAPI dans src/infrastructure/rate_limit.py. Il utilise Redis avec un TTL configurable.", "match"),
    TC("Agent creation", "comment creer un nouvel agent",
       "Pour creer un nouvel agent, suivez le guide GUIDE_AGENT_CREATION.md. Enregistrez l'agent via registry.register_agent() dans main.py.", "match"),
    TC("Project structure", "structure du projet",
       "Le projet suit une architecture DDD avec des domaines separes: agents/, auth/, connectors/, voice/.", "match"),
    TC("Auth flow", "comment fonctionne l'authentification",
       "L'authentification utilise OAuth2 avec PKCE. Le token JWT est signe en RS256 avec rotation des cles.", "match"),
    TC("Memory system", "le systeme de memoire",
       "Les memoires sont stockees dans PostgreSQL avec pgvector. Chaque memoire a un embedding de 1536 dimensions.", "match"),
    TC("Deployment", "comment deployer en production",
       "Le deploiement utilise Docker Compose avec un tunnel Cloudflare. Le script deploy.sh orchestre le build et le push.", "match"),
    TC("Testing guide", "comment ecrire des tests",
       "Les tests utilisent pytest avec asyncio_mode=auto. Les markers disponibles: unit, integration, slow, e2e.", "match"),
    TC("Prompt system", "comment gerer les prompts",
       "Les prompts sont versionnes dans src/domains/agents/prompts/v1/. Charger via load_prompt() ou load_prompt_with_fallback().", "match"),
    TC("Database migration", "comment creer une migration",
       "Utiliser task db:migrate:create -- 'description' pour creer une migration Alembic. Verifier la chaine de revisions.", "match"),
    TC("Error handling", "gestion des erreurs",
       "Les erreurs utilisent des raisers centralises: raise_user_not_found(), raise_permission_denied(). Jamais de HTTPException brut.", "match"),

    # --- NEAR (related but not the answer) ---
    TC("Tests related", "les tests d'integration",
       "Les tests unitaires utilisent pytest avec le marker @pytest.mark.unit. Les fixtures sont scopees par session.", "near"),
    TC("Config related", "variables d'environnement",
       "Les settings sont composes de modules Pydantic dans src/core/config/. Chaque module herite de BaseSettings.", "near"),
    TC("Auth adjacent", "les tokens JWT",
       "Le middleware de rate limiting utilise Redis pour stocker les compteurs par IP et par utilisateur.", "near"),
    TC("DB adjacent", "les index de la base",
       "L'ORM utilise SQLAlchemy 2.x avec Mapped[Type] + mapped_column(). Les modeles heritent de UUIDMixin et TimestampMixin.", "near"),
    TC("Docker adjacent", "les conteneurs",
       "L'observabilite utilise Prometheus + Grafana. Les metriques sont definies dans src/infrastructure/observability/.", "near"),
    TC("Prompt adjacent", "le systeme de templates",
       "L'internationalisation utilise react-i18next avec les fichiers de locales dans apps/web/locales/{lang}/.", "near"),

    # --- UNRELATED ---
    TC("Cooking vs code", "comment cuisiner des pates",
       "Le systeme de cache utilise Redis avec un TTL de 3600 secondes. Les cles sont prefixees par domaine.", "unrelated"),
    TC("Weather vs auth", "previsions meteo Lyon",
       "Le OAuth2 flow utilise PKCE avec un code verifier de 128 octets genere aleatoirement.", "unrelated"),
    TC("Sports vs DB", "resultats Ligue 1",
       "Les migrations Alembic sont stockees dans alembic/versions/. Chaque migration a un upgrade() et downgrade().", "unrelated"),
    TC("Travel vs API", "hotels a Barcelone",
       "Les routes API sont definies dans src/api/v1/routes.py avec des guards d'authentification Depends().", "unrelated"),
    TC("Music vs monitoring", "playlist spotify",
       "Le dashboard Grafana surveille la latence API, le throughput et les erreurs 5xx. Alertes via Slack.", "unrelated"),
    TC("Garden vs cache", "entretenir des rosiers",
       "Le cache LRU des embeddings d'outils est initialise au demarrage avec un TTL de 24h.", "unrelated"),
]

# =============================================================================
# 7. QUERY ENGINE DEDUP (string-based SequenceMatcher, NOT embeddings)
# =============================================================================
QUERY_STRING_TESTS = [
    # --- MATCH (true duplicates) ---
    ("Jean Dupont", "Jean Dupont", "match"),
    ("Jean Dupont", "jean dupont", "match"),
    ("Jean-Pierre Martin", "Jean Pierre Martin", "match"),
    ("marie.durand@gmail.com", "marie.durand@gmail.com", "match"),
    ("Dr. Sophie Lambert", "Dr Sophie Lambert", "match"),
    ("Societe Generale", "Societe Generale SA", "match"),
    ("Jean-Marc Duval", "Jean Marc Duval", "match"),

    # --- NEAR (typos, variations -- should detect) ---
    ("Jon Smith", "John Smith", "near"),
    ("Micheal", "Michael", "near"),
    ("Philippe", "Philipe", "near"),
    ("Christophe Blanc", "Cristophe Blanc", "near"),
    ("jean.dupont@gmail.com", "jean.dupont@yahoo.com", "near"),
    ("Restaurant Le Sud", "Restaurant du Sud", "near"),
    ("Boulangerie Martin", "Boulangerie Martins", "near"),

    # --- UNRELATED ---
    ("Jean Dupont", "Marie Lambert", "unrelated"),
    ("TechCorp SAS", "BioGenix Ltd", "unrelated"),
    ("Paris", "Lyon", "unrelated"),
    ("jean@gmail.com", "sophie@outlook.com", "unrelated"),
    ("Garage Renault", "Cabinet Dentaire", "unrelated"),
]


# =============================================================================
# BATCH EMBEDDING with rate limiting
# =============================================================================

def batch_embed(client: GoogleGenerativeAIEmbeddings,
                texts: list[str],
                task_type: str,
                batch_size: int = 20) -> list[list[float]]:
    """Embed texts in batches to respect rate limits."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        if task_type == "RETRIEVAL_QUERY":
            # embed_query is for single text, use embed_documents with QUERY type
            embs = client.embed_documents(
                batch,
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=DIMS,
            )
        else:
            embs = client.embed_documents(
                batch,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=DIMS,
            )
        all_embeddings.extend(embs)
        if i + batch_size < len(texts):
            time.sleep(1.0)  # Rate limit pause between batches
    return all_embeddings


# =============================================================================
# ANALYSIS HELPERS
# =============================================================================

def analyze_group(group_name: str, scores_by_cat: dict[str, list[float]]) -> dict:
    """Analyze a test group and return stats + recommendation."""
    matches = scores_by_cat.get("match", [])
    nears = scores_by_cat.get("near", [])
    unrelateds = scores_by_cat.get("unrelated", [])

    stats = {}
    for cat, vals in [("MATCH", matches), ("NEAR", nears), ("UNRELATED", unrelateds)]:
        if vals:
            stats[cat] = {
                "min": min(vals), "max": max(vals),
                "avg": np.mean(vals), "std": np.std(vals),
                "p10": np.percentile(vals, 10),
                "p25": np.percentile(vals, 25),
                "p75": np.percentile(vals, 75),
                "p90": np.percentile(vals, 90),
                "count": len(vals),
            }

    # Compute optimal threshold
    rec = None
    if matches and (nears or unrelateds):
        noise = nears + unrelateds
        noise_max = max(noise)
        noise_p90 = np.percentile(noise, 90)
        match_min = min(matches)
        match_p10 = np.percentile(matches, 10)

        # Conservative: threshold between p10(match) and p90(noise)
        # This accepts 90% of matches and rejects 90% of noise
        rec = {
            "midpoint": (match_min + noise_max) / 2,
            "conservative": (match_p10 + noise_p90) / 2,
            "gap": match_min - noise_max,
            "gap_p10_p90": match_p10 - noise_p90,
        }

    return {"stats": stats, "recommendation": rec}


# =============================================================================
# MAIN
# =============================================================================

def run_tests() -> None:
    if not API_KEY:
        print("ERROR: Set GOOGLE_GEMINI_API_KEY or GOOGLE_API_KEY env variable")
        sys.exit(1)

    client = GoogleGenerativeAIEmbeddings(model=MODEL, google_api_key=API_KEY)

    # -- Define test groups --
    embedding_groups = [
        ("MEMORY_MIN_SEARCH_SCORE", MEMORY_TESTS, True,
         "Retrieval gate: too low=noise/token waste, too high=lost context"),
        ("JOURNAL_CONTEXT_MIN_SCORE", JOURNAL_TESTS, True,
         "Context injection: too low=false behavioral directives, too high=missed patterns"),
        ("JOURNAL_DEDUP_SIMILARITY_THRESHOLD", JOURNAL_DEDUP_TESTS, False,
         "Merge guard: too low=contradictory merges, too high=journal bloat"),
        ("INTEREST_DEDUP_SIMILARITY_THRESHOLD", INTEREST_DEDUP_TESTS, False,
         "Topic merge: too low=lost granularity, too high=interest proliferation"),
        ("INTEREST_CONTENT_SIMILARITY_THRESHOLD", INTEREST_CONTENT_TESTS, False,
         "Notif dedup: too low=missed content, too high=notification spam"),
        ("RAG_SPACES_RETRIEVAL_MIN_SCORE", RAG_TESTS, True,
         "Chunk filter: too low=off-topic noise, too high=thin context"),
    ]

    all_results: dict[str, dict] = {}

    for var_name, tests, is_asymmetric, description in embedding_groups:
        print(f"\n{'='*90}")
        print(f"  {var_name}")
        print(f"  {description}")
        mode = "ASYMMETRIC query->doc" if is_asymmetric else "SYMMETRIC doc<->doc"
        print(f"  Mode: {mode} | Test cases: {len(tests)}")
        print(f"{'='*90}")

        # Collect all texts for batch embedding
        texts_a = [tc.text_a for tc in tests]
        texts_b = [tc.text_b for tc in tests]

        if is_asymmetric:
            print("  Embedding queries (RETRIEVAL_QUERY)...")
            embs_a = batch_embed(client, texts_a, "RETRIEVAL_QUERY")
            time.sleep(1.0)
            print("  Embedding documents (RETRIEVAL_DOCUMENT)...")
            embs_b = batch_embed(client, texts_b, "RETRIEVAL_DOCUMENT")
        else:
            print("  Embedding all texts (RETRIEVAL_DOCUMENT)...")
            all_texts = texts_a + texts_b
            all_embs = batch_embed(client, all_texts, "RETRIEVAL_DOCUMENT")
            embs_a = all_embs[:len(texts_a)]
            embs_b = all_embs[len(texts_a):]

        print()
        scores_by_cat: dict[str, list[float]] = {"match": [], "near": [], "unrelated": []}

        for tc, ea, eb in zip(tests, embs_a, embs_b):
            sim = cosine_similarity(ea, eb)
            scores_by_cat[tc.expected].append(sim)
            marker = {"match": "+++", "near": "~~~", "unrelated": "---"}[tc.expected]
            print(f"  [{marker}] {tc.expected:10s} | {sim:.4f} | {tc.label}")

        result = analyze_group(var_name, scores_by_cat)
        all_results[var_name] = result

    # =========================================================================
    # STRING-BASED QUERY ENGINE (SequenceMatcher)
    # =========================================================================
    print(f"\n{'='*90}")
    print(f"  QUERY_ENGINE_SIMILARITY_THRESHOLD (SequenceMatcher, NOT embeddings)")
    print(f"  Duplicate detection: too low=false positives, too high=missed duplicates")
    print(f"  Mode: STRING ratio | Test cases: {len(QUERY_STRING_TESTS)}")
    print(f"{'='*90}")
    print()

    str_scores: dict[str, list[float]] = {"match": [], "near": [], "unrelated": []}
    for a, b, expected in QUERY_STRING_TESTS:
        ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
        str_scores[expected].append(ratio)
        marker = {"match": "+++", "near": "~~~", "unrelated": "---"}[expected]
        print(f"  [{marker}] {expected:10s} | {ratio:.4f} | '{a}' vs '{b}'")

    str_result = analyze_group("QUERY_ENGINE", str_scores)
    all_results["QUERY_ENGINE_SIMILARITY_THRESHOLD"] = str_result

    # =========================================================================
    # GLOBAL SUMMARY
    # =========================================================================
    print(f"\n\n{'#'*90}")
    print(f"  DETAILED STATISTICS & RECOMMENDATIONS")
    print(f"{'#'*90}")

    for var_name, data in all_results.items():
        stats = data["stats"]
        rec = data["recommendation"]

        print(f"\n{'─'*90}")
        print(f"  {var_name}")
        print(f"{'─'*90}")

        for cat in ["MATCH", "NEAR", "UNRELATED"]:
            if cat in stats:
                s = stats[cat]
                print(f"  {cat:10s} (n={s['count']:2d}): "
                      f"min={s['min']:.4f}  p10={s['p10']:.4f}  p25={s['p25']:.4f}  "
                      f"avg={s['avg']:.4f}  p75={s['p75']:.4f}  p90={s['p90']:.4f}  "
                      f"max={s['max']:.4f}  std={s['std']:.4f}")

        if rec:
            print(f"\n  Gap (min_match - max_noise)       : {rec['gap']:.4f}")
            print(f"  Gap (p10_match - p90_noise)        : {rec['gap_p10_p90']:.4f}")
            print(f"  Midpoint (min_match + max_noise)/2 : {rec['midpoint']:.4f}")
            print(f"  Conservative (p10 + p90_noise)/2   : {rec['conservative']:.4f}")

    # =========================================================================
    # FINAL RECOMMENDATION TABLE
    # =========================================================================
    print(f"\n\n{'#'*90}")
    print(f"  FINAL THRESHOLD RECOMMENDATIONS")
    print(f"{'#'*90}")
    print()
    print(f"  {'Variable':<45s} | {'Current .env':>12s} | {'Recommend':>10s} | {'Strategy'}")
    print(f"  {'─'*45}-+-{'─'*12}-+-{'─'*10}-+-{'─'*30}")

    current_values = {
        "MEMORY_MIN_SEARCH_SCORE": 0.70,
        "JOURNAL_CONTEXT_MIN_SCORE": 0.75,
        "JOURNAL_DEDUP_SIMILARITY_THRESHOLD": 0.75,
        "INTEREST_DEDUP_SIMILARITY_THRESHOLD": 0.82,
        "INTEREST_CONTENT_SIMILARITY_THRESHOLD": 0.81,
        "RAG_SPACES_RETRIEVAL_MIN_SCORE": 0.60,
        "QUERY_ENGINE_SIMILARITY_THRESHOLD": 0.85,
    }

    for var_name, data in all_results.items():
        rec = data["recommendation"]
        current = current_values.get(var_name, "?")

        if rec:
            # Choose strategy based on the variable's purpose
            if var_name in [
                "MEMORY_MIN_SEARCH_SCORE",
                "JOURNAL_CONTEXT_MIN_SCORE",
                "RAG_SPACES_RETRIEVAL_MIN_SCORE",
            ]:
                # Retrieval: prefer recall, use conservative (accepts 90% matches)
                chosen = rec["conservative"]
                strategy = "favor recall (conservative)"
            elif var_name in [
                "JOURNAL_DEDUP_SIMILARITY_THRESHOLD",
                "INTEREST_DEDUP_SIMILARITY_THRESHOLD",
                "INTEREST_CONTENT_SIMILARITY_THRESHOLD",
            ]:
                # Dedup: prefer precision, use midpoint+ (avoid false merges)
                chosen = rec["midpoint"]
                strategy = "favor precision (midpoint)"
            else:
                # Query engine: balanced
                chosen = rec["conservative"]
                strategy = "balanced (conservative)"

            # Round to 2 decimals
            chosen = round(chosen, 2)
            print(f"  {var_name:<45s} | {str(current):>12s} | {chosen:>10.2f} | {strategy}")

    # Also print MEMORY_RELEVANCE_THRESHOLD recommendation
    # (derived from MEMORY scores -- should be at p75 of match scores)
    mem_data = all_results.get("MEMORY_MIN_SEARCH_SCORE")
    if mem_data and "MATCH" in mem_data["stats"]:
        p75 = mem_data["stats"]["MATCH"]["p75"]
        print(f"  {'MEMORY_RELEVANCE_THRESHOLD':<45s} | {'0.70':>12s} | {round(p75, 2):>10.2f} | p75 of match scores")

    print()


if __name__ == "__main__":
    run_tests()
