"""
Similarity threshold calibration v2 — Large-scale realistic test.

Each domain has:
- A realistic BANK of stored items (80-100 memories, 30 journal entries, etc.)
- A large set of QUERIES (30+ real user messages per domain)
- Expected match labels for precision/recall analysis

Uses Gemini embedding-001 with asymmetric task types.
"""

import os
import sys
import time
from dataclasses import dataclass, field

import numpy as np
from langchain_google_genai import GoogleGenerativeAIEmbeddings

API_KEY = os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "models/gemini-embedding-001"
DIMS = 1536


def cos_sim(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def batch_embed(
    client: GoogleGenerativeAIEmbeddings,
    texts: list[str],
    task_type: str,
    batch_size: int = 80,
) -> list[list[float]]:
    all_embs: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embs = client.embed_documents(
            batch, task_type=task_type, output_dimensionality=DIMS
        )
        all_embs.extend(embs)
        if i + batch_size < len(texts):
            time.sleep(1.5)
    return all_embs


# =============================================================================
# 1. MEMORY BANK — 80 memories of a realistic user
# =============================================================================
MEMORY_BANK = [
    # -- Family --
    "Mon frere s'appelle Alexandre Gouvier, il habite a Nantes avec sa compagne Julie.",
    "Ma soeur Camille est veterinaire a Montpellier, elle a deux enfants.",
    "Mon epouse Hua est d'origine vietnamienne, on s'est maries en 2018 a Lyon.",
    "Mes parents vivent a Toulouse dans le quartier des Carmes depuis 2010.",
    "Ma belle-mere Nguyen Thi Lan vit a Ho Chi Minh Ville au Vietnam.",
    "Mon fils Leo a 8 ans, il est en CE2 a l'ecole Montessori de Villeurbanne.",
    "Ma fille Emma a 5 ans, elle est en grande section de maternelle.",
    "Mon oncle Bernard est a la retraite, ancien ingenieur chez Airbus.",
    "Ma cousine Sophie travaille dans la finance a Londres.",
    "Le chien de mes parents s'appelle Filou, c'est un labrador de 7 ans.",
    # -- Friends --
    "Mon meilleur ami Thomas est professeur de maths au lycee, on se connait depuis le college.",
    "Marc est un collegue dev, on dejeune ensemble le mercredi au japonais.",
    "Stephanie est ma voisine du 2eme, elle garde parfois les enfants.",
    "Paul est mon partenaire de jogging du dimanche.",
    "David est un ami d'enfance, il vit maintenant a Montreal.",
    # -- Home --
    "J'habite au 34 rue Vendome, Lyon 3eme, appartement au 4eme etage.",
    "Le code de l'immeuble est 45B12.",
    "Le syndic est gere par Foncia, contact: Mme Renard.",
    "Parking souterrain place 42, acces par la rue Duquesne.",
    "Le voisin du dessus Patrick fait du bruit le soir apres 22h.",
    # -- Work --
    "Je suis developpeur senior full-stack chez TechCorp depuis janvier 2020.",
    "Mon manager s'appelle Laurent Dubois.",
    "Je travaille principalement sur le projet LIA, un assistant IA conversationnel.",
    "Mon salaire brut est de 65000 euros annuels.",
    "Je fais du teletravail 3 jours par semaine (lundi, mardi, jeudi).",
    "Le bureau est au 15 rue de la Republique, Lyon 2eme, 3eme etage.",
    "Les sprint reviews sont chaque vendredi a 10h en visio.",
    "Mon collegue backend est Julien, il gere l'infra DevOps.",
    # -- Health --
    "Allergique aux arachides (reaction severe) et intolerant au gluten.",
    "Medecin traitant: Dr Martin, 12 rue Garibaldi, Lyon 3eme.",
    "Dentiste: Dr Faure, prochain RDV le 15 mai.",
    "Opticien Atol des Halles, derniere visite en fevrier.",
    "Je prends du magnesium et de la vitamine D en complement.",
    "Groupe sanguin O positif.",
    "Pediatre des enfants: Dr Leroy, clinique du Parc.",
    # -- Transport --
    "Je conduis une Tesla Model 3 blanche immatriculee FG-456-HJ.",
    "Assurance auto chez Maif, contrat numero 123456.",
    "Le plein de charge se fait a la borne Ionity de Part-Dieu.",
    "Abonnement TCL (transports en commun Lyon) pour les jours au bureau.",
    "Velo electrique Decathlon range dans la cave, cadenas code 7531.",
    # -- Hobbies --
    "J'aime le jazz: Miles Davis, John Coltrane, Bill Evans.",
    "Je fais du jogging 3 fois par semaine, objectif semi-marathon en octobre.",
    "Abonnement salle de sport Basic Fit Villeurbanne, expire en septembre.",
    "Je joue de la guitare depuis l'adolescence, j'ai une Fender Stratocaster.",
    "Passion pour la domotique: Home Assistant + capteurs Zigbee dans l'appart.",
    "Je contribue a des projets open source Python le week-end.",
    "Collection de vinyles jazz, environ 150 disques.",
    "Je fais de la photographie de rue quand je me balade en ville.",
    # -- Food & drink --
    "Cafe filtre le matin avec un V60, grains torrefies par Mokxa Lyon.",
    "The vert l'apres-midi, marque preferee Palais des Thes.",
    "Restaurant prefere: Le Comptoir du Sud, place Bellecour.",
    "Sushi prefere: restaurant Koya, rue Merciere.",
    "J'adore la cuisine vietnamienne, Hua me fait souvent des pho.",
    "Intolerant au gluten donc je mange sans gluten au quotidien.",
    # -- Tech --
    "IDE principal: VSCode avec theme Dracula et police JetBrains Mono.",
    "Clavier mecanique Keychron K8, switches Brown.",
    "Ecran principal LG 32 pouces 4K, ecran secondaire Dell 24 pouces.",
    "MacBook Pro M2 pour le boulot, PC fixe Linux pour le perso.",
    "NAS Synology DS920+ pour les backups et le media server.",
    "Forfait Free Mobile a 20 euros par mois.",
    # -- Finance --
    "Compte courant Boursobank, carte Visa Premier.",
    "PEA chez Bourse Direct, principalement des ETF World.",
    "Budget mensuel courses alimentaires: environ 600 euros.",
    "Pret immobilier LCL, il reste 18 ans, mensualite 1200 euros.",
    "Assurance habitation Maif, contrat multi-risques.",
    # -- Culture --
    "Je lis en ce moment Meditations de Marc Aurele.",
    "Derniere serie regardee: The Bear sur Disney+.",
    "Abonnement Netflix, Disney+ et Spotify Premium famille.",
    "J'aime les films de Christopher Nolan et Denis Villeneuve.",
    "Podcast prefere: Lex Fridman pour la tech, Transfert pour les histoires.",
    # -- Planning --
    "Vacances d'ete: Crete du 1er au 15 aout, hotel Minos Beach.",
    "Anniversaire de mariage le 3 juin.",
    "Toussaint: chez mes parents a Toulouse.",
    "Noel chez les parents de Hua a Paris cette annee.",
    "Semi-marathon de Lyon le 12 octobre.",
    "Concert de jazz au Periscope le 20 mai.",
    # -- Misc --
    "Plombier de confiance: M. Dupuis, 06 12 34 56 78.",
    "Electricien: SOS Depannage Lyon, numero sur le frigo.",
    "Mot de passe WiFi: inscrit sur le post-it du frigo.",
    "Leo fait du judo le mercredi a 14h.",
    "Emma a cours de danse le samedi matin a 10h.",
]

# 30 realistic user messages that should trigger memory retrieval
MEMORY_QUERIES = [
    # -- Direct fact lookups --
    ("je vais chez mon frere le 23 mai", ["Alexandre"]),
    ("comment s'appelle ma femme deja", ["Hua"]),
    ("rappelle moi mes allergies", ["arachides", "gluten", "Allergique"]),
    ("c'est quand mon anniversaire de mariage", ["3 juin"]),
    ("ou est-ce que j'habite exactement", ["34 rue Vendome"]),
    ("c'est quoi mon groupe sanguin", ["O positif"]),
    ("qui est mon medecin", ["Dr Martin"]),
    ("ma voiture c'est quoi comme modele", ["Tesla Model 3"]),
    ("les prenoms de mes enfants", ["Leo", "Emma"]),
    ("on part ou cet ete", ["Crete", "Minos Beach"]),
    ("qui c'est mon manager", ["Laurent Dubois"]),
    ("je gagne combien", ["65000"]),
    ("le numero du plombier", ["Dupuis", "06 12"]),
    ("ma soeur fait quoi dans la vie", ["veterinaire", "Montpellier"]),
    ("c'est quoi le code de l'immeuble", ["45B12"]),
    # -- Contextual / conversational --
    ("je suis fatigue ce soir, j'ai pas envie de cuisiner", ["Koya", "Comptoir", "restaurant", "pho"]),
    ("j'hesite a changer de banque", ["Boursobank"]),
    ("faut que j'aille faire les courses", ["600 euros", "gluten"]),
    ("je cherche un nouveau livre a lire", ["Meditations", "Marc Aurele"]),
    ("on fait quoi ce week-end avec les enfants", ["judo", "danse", "Leo", "Emma"]),
    ("j'ai un probleme avec ma box internet", ["WiFi", "Free"]),
    ("je vais courir demain matin", ["jogging", "semi-marathon", "Paul"]),
    ("j'ai rendez-vous chez le dentiste bientot", ["Dr Faure", "15 mai"]),
    ("ma belle-mere arrive la semaine prochaine", ["Nguyen Thi", "Vietnam"]),
    ("le voisin fait encore du bruit", ["Patrick", "22h"]),
    ("je dois appeler mon pote a Montreal", ["David", "Montreal"]),
    ("Hua veut qu'on aille voir ses parents a Noel", ["Paris", "Noel"]),
    ("faut que je regarde la pression des pneus", ["Tesla", "FG-456"]),
    ("on amene les enfants chez le pediatre demain", ["Dr Leroy", "clinique du Parc"]),
    ("je veux organiser un truc pour l'anniversaire de Thomas", ["Thomas", "professeur", "maths"]),
]


# =============================================================================
# 2. JOURNAL BANK — 30 behavioral directives (realistic format)
# =============================================================================
JOURNAL_BANK = [
    "WHEN discussing LIA project THEN reference the current sprint goals and LangGraph architecture decisions.",
    "WHEN user mentions fatigue or tiredness THEN acknowledge empathetically, suggest lighter tasks or rest.",
    "WHEN user talks about brother Alexandre THEN remember he lives in Nantes, they are close.",
    "WHEN discussing deployment THEN reference previous SSL certificate issues on Cloudflare tunnel.",
    "WHEN user asks about cooking THEN suggest quick/simple recipes, he prefers efficient meals.",
    "WHEN user mentions exercise or running THEN encourage, reference semi-marathon goal in October.",
    "WHEN discussing productivity THEN note morning 7h-11h is his peak window, prefer scheduling deep work there.",
    "WHEN user talks about music THEN reference jazz preferences: Miles Davis, Coltrane, Bill Evans.",
    "WHEN discussing family vacation THEN reference Crete trip August 1-15, hotel Minos Beach already booked.",
    "WHEN user is stressed about work THEN remind him of past successes and suggest breaking tasks down.",
    "WHEN discussing children's activities THEN Leo has judo Wednesday 14h, Emma dance Saturday 10h.",
    "WHEN user asks about budget THEN reference 600 euros monthly grocery budget, ongoing mortgage at LCL.",
    "WHEN discussing investments THEN PEA at Bourse Direct, ETF World strategy, long-term horizon.",
    "WHEN user mentions wife Hua THEN be warm and respectful, Vietnamese heritage, married 2018.",
    "WHEN user discusses home automation THEN reference Home Assistant + Zigbee setup, enthusiast level.",
    "WHEN user talks about reading THEN currently reading Marcus Aurelius Meditations, likes Stoic philosophy.",
    "WHEN discussing code reviews THEN user gets frustrated by slow reviews, prefers async feedback.",
    "WHEN user mentions photography THEN he does street photography, casual hobby not professional.",
    "WHEN user discusses guitar THEN plays since teenager, owns Fender Stratocaster, jazz/blues style.",
    "WHEN user talks about Paris THEN wife's parents live there, visits at Christmas usually.",
    "WHEN discussing health issues THEN critical: peanut allergy (severe), gluten intolerance.",
    "WHEN user mentions colleague Marc THEN weekly Wednesday lunch at Japanese restaurant together.",
    "WHEN discussing remote work THEN 3 days WFH (Mon, Tue, Thu), office Wed and Fri.",
    "WHEN user mentions Toulouse THEN parents live there, visits at Toussaint holiday.",
    "Observation: user responds better to structured action items than open-ended suggestions.",
    "Observation: user dislikes small talk, prefers getting straight to the point.",
    "Observation: user values precision and correctness over speed.",
    "Observation: user appreciates when AI remembers context from previous conversations.",
    "Preference: always use 24h time format, metric system, European date format.",
    "Preference: respond in French unless discussing code/technical docs.",
]

JOURNAL_QUERIES = [
    ("je suis creve aujourd'hui", ["fatigue", "tiredness"]),
    ("on deploie LIA en prod ce soir", ["LIA project", "deployment"]),
    ("mon frere m'a appele ce matin", ["brother Alexandre"]),
    ("je vais courir ce soir apres le boulot", ["exercise", "running", "semi-marathon"]),
    ("qu'est-ce qu'on mange ce soir", ["cooking"]),
    ("j'ai une reunion sur l'archi LangGraph", ["LIA project"]),
    ("Leo a son cours cet apres-midi", ["children's activities", "judo"]),
    ("Hua veut qu'on aille voir ses parents", ["wife Hua", "Paris"]),
    ("j'arrive pas a me concentrer", ["productivity", "stressed"]),
    ("je lis un truc super en ce moment", ["reading"]),
    ("faut que je check le budget courses", ["budget"]),
    ("le PR de Marc traine depuis 3 jours", ["code reviews", "colleague Marc"]),
    ("j'ai un souci avec mon systeme Zigbee", ["home automation"]),
    ("on va a Toulouse pour la Toussaint", ["Toulouse"]),
    ("j'ai pris ma guitare ce soir", ["guitar"]),
    ("faut que je check mon PEA", ["investments"]),
    ("je bosse de la maison demain", ["remote work"]),
    ("les enfants ont quoi comme activites cette semaine", ["children's activities"]),
    ("Emma a son spectacle de danse samedi", ["children's activities", "dance"]),
    ("je suis stresse par la deadline", ["stressed"]),
]


# =============================================================================
# 3. INTEREST DEDUP — 40 existing interests + 20 new extractions
# =============================================================================
INTEREST_BANK = [
    "Intelligence artificielle et machine learning",
    "Developpement Python",
    "Jazz et musique improvisee",
    "Course a pied et trail running",
    "Domotique et maison connectee",
    "Cuisine vietnamienne",
    "Photographie de rue",
    "Guitare jazz et blues",
    "Philosophie stoicienne",
    "Cinema science-fiction",
    "DevOps et infrastructure cloud",
    "Investissement ETF et bourse",
    "Open source et communaute Python",
    "Cuisine sans gluten",
    "Podcasts technologie",
    "Series television",
    "Vins naturels et biodynamiques",
    "Urbanisme et architecture Lyon",
    "Parentalite et education Montessori",
    "Vehicules electriques et Tesla",
]

# New topics to test dedup against existing interests
# Format: (new topic, expected match label or None if new)
INTEREST_DEDUP_TESTS = [
    # Should MERGE (same topic)
    ("IA generative et LLM", "Intelligence artificielle"),
    ("Deep learning et reseaux de neurones", "Intelligence artificielle"),
    ("Programmation Python avancee", "Developpement Python"),
    ("FastAPI et frameworks web Python", "Developpement Python"),
    ("Miles Davis et jazz modal", "Jazz et musique improvisee"),
    ("Footing et preparation marathon", "Course a pied et trail running"),
    ("Home Assistant et Zigbee", "Domotique et maison connectee"),
    ("Pho et cuisine asiatique", "Cuisine vietnamienne"),
    ("Street photography noir et blanc", "Photographie de rue"),
    ("ETF World et gestion passive", "Investissement ETF et bourse"),
    ("Docker et Kubernetes", "DevOps et infrastructure cloud"),
    ("Voitures electriques et bornes de recharge", "Vehicules electriques et Tesla"),
    # Should NOT merge (different topic)
    ("Cuisine italienne et pasta", None),
    ("Randonnee en montagne", None),
    ("Jeux video et gaming", None),
    ("Jardinage et permaculture", None),
    ("Yoga et meditation", None),
    ("Plongee sous-marine", None),
    ("Astronomie amateur", None),
    ("Brassage de biere artisanale", None),
    ("Impression 3D et maker", None),
    ("Escalade en salle", None),
    # Borderline (related but distinct)
    ("Developpement JavaScript et React", None),  # near Python but different
    ("Musique classique et orchestrale", None),  # near jazz but different
    ("Cyclisme sur route", None),  # near running but different
    ("Cuisine japonaise et sushi", None),  # near Vietnamese but different
    ("Videographie et montage video", None),  # near photo but different
    ("Piano jazz", None),  # near guitar jazz but different
    ("Bouddhisme zen", None),  # near stoicism but different
    ("Films d'animation japonaise", None),  # near SF cinema but different
]


# =============================================================================
# 4. INTEREST CONTENT DEDUP — 15 recent + 15 new articles
# =============================================================================
CONTENT_RECENT = [
    "OpenAI devoile GPT-5 avec une fenetre de contexte de 2 millions de tokens et des capacites de raisonnement ameliorees.",
    "Tesla annonce le Robotaxi pour 2027 avec conduite 100% autonome sans volant ni pedales.",
    "Python 3.13 sort avec le JIT compiler experimental et le mode sans GIL pour le multi-threading.",
    "Le PSG se qualifie pour les demi-finales de la Ligue des Champions apres une victoire 3-1 contre le Bayern.",
    "Apple lance le Vision Pro 2 plus leger et moins cher, compatible avec les apps iPad.",
    "Le guide Michelin 2026 decerne 3 etoiles a un restaurant lyonnais pour la premiere fois en 10 ans.",
    "Anthropic publie Claude 4.5 Sonnet avec des performances record sur les benchmarks de code.",
    "Record de chaleur en France: 42 degres en avril, du jamais vu selon Meteo France.",
    "Le Salon de l'Agriculture 2026 met l'accent sur l'agriculture regenerative et les circuits courts.",
    "Netflix perd 2 millions d'abonnes en Europe suite a la hausse des prix de 20%.",
    "SpaceX reussit le premier vol habite vers Mars avec un equipage de 4 astronautes.",
    "La BCE baisse ses taux directeurs a 2% pour stimuler la croissance en zone euro.",
    "Lyon inaugure sa 5eme ligne de metro reliant Part-Dieu a l'aeroport Saint-Exupery.",
    "Google DeepMind annonce Gemini 3.0 Ultra avec un score parfait sur le benchmark MATH.",
    "La France adopte une loi imposant la reparabilite de tous les appareils electroniques.",
]

CONTENT_NEW = [
    # Should be flagged as DUPLICATE (same news rephrased)
    ("GPT-5 d'OpenAI: raisonnement avance et contexte de 2M tokens, une revolution pour les agents.", True, "GPT-5"),
    ("Le Robotaxi Tesla sans volant prevu pour 2027, Elon Musk promet une conduite entierement autonome.", True, "Tesla Robotaxi"),
    ("Python 3.13: le compilateur JIT et le no-GIL mode ouvrent la voie au vrai parallelisme.", True, "Python 3.13"),
    ("Claude 4.5 Sonnet d'Anthropic pulverise les records sur les benchmarks de programmation.", True, "Claude 4.5"),
    ("La 5eme ligne de metro de Lyon connecte enfin la Part-Dieu a Saint-Exupery.", True, "Metro Lyon"),
    ("Gemini 3.0 Ultra de Google obtient un score parfait sur les tests mathematiques.", True, "Gemini 3.0"),
    # Should NOT be flagged (different news, same general topic)
    ("Meta lance Llama 4 en open source avec 400 milliards de parametres.", False, "Llama 4"),
    ("Google annonce Android 16 avec un redesign complet de l'interface Material You 3.", False, "Android 16"),
    ("Un nouveau record du monde au marathon par un Kenyan en 1h57min.", False, "Marathon record"),
    ("La Banque de France prevoit une croissance de 1.5% pour 2027.", False, "Croissance FR"),
    ("Microsoft rachete Discord pour 30 milliards de dollars.", False, "Microsoft Discord"),
    ("Le James Webb Telescope decouvre une exoplanete potentiellement habitable a 40 annees-lumiere.", False, "JWST"),
    ("La Chine lance sa propre station spatiale avec un module scientifique europeen.", False, "Station spatiale"),
    ("Nvidia annonce la RTX 6090 avec 48 Go de VRAM pour les charges IA.", False, "RTX 6090"),
    ("Le Tour de France 2026 partira de Barcelone pour la premiere fois.", False, "Tour de France"),
]


# =============================================================================
# 5. RAG CHUNKS — 25 doc chunks + 15 queries
# =============================================================================
RAG_BANK = [
    "Pour configurer le rate limiting, editez src/infrastructure/rate_limit.py. Le middleware utilise Redis comme backend avec un TTL configurable par route. Les limites par defaut: 100 req/min pour les endpoints publics, 500 pour les authentifies.",
    "Les agents LangGraph sont enregistres via registry.register_agent() dans main.py au demarrage. Chaque agent definit ses tools via le decorateur @tool et son prompt systeme dans prompts/v1/.",
    "L'authentification utilise OAuth2 PKCE avec tokens JWT signes en RS256. La rotation des cles est automatique toutes les 24h. Le refresh token a un TTL de 30 jours.",
    "Les tests utilisent pytest avec asyncio_mode=auto. Markers disponibles: @pytest.mark.unit, integration, slow, e2e, benchmark. Coverage minimum: 43%.",
    "Les migrations Alembic sont dans alembic/versions/. Creer avec: task db:migrate:create -- 'description'. Verifier la chaine: alembic heads. Rollback: task db:migrate:down.",
    "Le deploiement utilise Docker Compose avec un tunnel Cloudflare sur Raspberry Pi 5. Le script deploy.sh orchestre build, push et restart des conteneurs.",
    "Les prompts sont versionnes dans src/domains/agents/prompts/v1/. Charger via load_prompt('nom') avec fallback automatique. Versions configurables par env var.",
    "Le cache Redis utilise un TTL de 3600s par defaut. Les cles sont prefixees par domaine: 'memory:', 'journal:', 'interest:'. Invalidation manuelle via le endpoint /admin/cache/clear.",
    "L'observabilite utilise Prometheus + Grafana. 500+ metriques definies dans src/infrastructure/observability/. Dashboard principal: grafana.internal/d/api-overview.",
    "Les settings Pydantic sont dans src/core/config/. Chaque module (agents, auth, llm, etc.) herite de BaseSettings. Composition via MRO dans __init__.py.",
    "Le systeme de memoire utilise pgvector avec des embeddings Gemini 1536 dimensions. Recherche par similarite cosinus avec dual-vector (content + keyword).",
    "Le HITL (Human-in-the-Loop) a 6 niveaux d'approbation: plan, clarification, draft critique, destructive confirm, FOR_EACH, modifier review. Classification dans hitl_classifier.py.",
    "Les connecteurs Google/Apple/Microsoft partagent une abstraction commune dans src/domains/connectors/. Un seul provider actif par categorie fonctionnelle.",
    "Le streaming SSE envoie les reponses au frontend via Server-Sent Events. Le endpoint /v1/chat/stream gere la connexion longue avec heartbeat toutes les 15s.",
    "Les tools retournent ToolResponse.model_dump() en cas de succes et ToolErrorModel.from_exception() en cas d'erreur. Toujours utiliser ToolErrorCode pour le type d'erreur.",
    "La factory LLM dans src/infrastructure/llm/factory.py supporte OpenAI, Anthropic, Google, DeepSeek et Ollama. Chaque provider a un adaptateur dans providers/.",
    "Le systeme de journals extrait des directives comportementales des conversations. Format: WHEN [context] THEN [action]. Stockage avec embeddings pour retrieval semantique.",
    "Les interests sont extraits automatiquement des conversations. Deduplication par embedding similarity. Notifications via content sources (RSS, API, LLM generation).",
    "Le QueryAnalyzer categorise les requetes en 'conversational' ou 'actionable'. Les actionables passent par le planner pour generer un ExecutionPlan.",
    "Le task orchestrator execute les plans en parallele quand possible. Chaque tache est un appel a un domain agent specifique (calendar, email, contacts, etc.).",
    "L'architecture DDD organise le code en bounded contexts: agents, auth, connectors, voice, interests, heartbeat, user_mcp, conversations, reminders, journals.",
    "Les variables d'environnement sont documentees dans .env.example. Feature flags: MCP_ENABLED, CHANNELS_ENABLED, HEARTBEAT_ENABLED, SCHEDULED_ACTIONS_ENABLED.",
    "Le frontend Next.js 16 utilise React 19 avec App Router. Les traductions sont dans apps/web/locales/{lang}/translation.json pour 6 langues.",
    "Les exceptions utilisent des raisers centralises: raise_user_not_found(), raise_permission_denied(). Jamais de HTTPException brut dans les services.",
    "Le psyche engine modelise l'etat psychologique de l'utilisateur: humeur, emotions, relation. Mis a jour a chaque interaction via le PsycheService.",
]

RAG_QUERIES = [
    ("comment configurer le rate limiting", ["rate limit"]),
    ("comment deployer en production", ["deploiement", "Docker Compose", "Cloudflare"]),
    ("comment ecrire des tests", ["pytest", "tests"]),
    ("comment gerer les prompts", ["prompts", "versionnes"]),
    ("comment fonctionne le cache Redis", ["cache Redis"]),
    ("comment creer une migration de base de donnees", ["migrations Alembic"]),
    ("comment fonctionne l'authentification", ["OAuth2", "JWT"]),
    ("comment creer un nouvel agent", ["agents LangGraph", "register_agent"]),
    ("c'est quoi le HITL", ["HITL", "6 niveaux"]),
    ("comment marche le streaming", ["SSE", "streaming"]),
    ("comment gerer les erreurs dans les tools", ["ToolResponse", "ToolErrorModel"]),
    ("quels providers LLM sont supportes", ["factory LLM", "OpenAI", "Anthropic"]),
    ("comment marche l'extraction des interests", ["interests", "extraits"]),
    ("c'est quoi le psyche engine", ["psyche engine", "humeur"]),
    ("comment fonctionne le query analyzer", ["QueryAnalyzer", "conversational", "actionable"]),
]


# =============================================================================
# 6. JOURNAL DEDUP — pairs of entries to test merge/no-merge
# =============================================================================
JOURNAL_DEDUP_PAIRS = [
    # Should MERGE
    ("WHEN user is tired THEN suggest rest and lighter tasks.",
     "WHEN user mentions fatigue or tiredness THEN acknowledge empathetically, suggest lighter tasks or rest.", True),
    ("WHEN discussing code reviews THEN user prefers async feedback, gets frustrated by delays.",
     "WHEN user talks about code reviews THEN note frustration with slow reviews, prefers async feedback.", True),
    ("WHEN user mentions brother THEN he lives in Nantes, they are close.",
     "WHEN user talks about brother Alexandre THEN remember he lives in Nantes, they are close.", True),
    ("WHEN discussing exercise THEN encourage, semi-marathon in October.",
     "WHEN user mentions running THEN reference semi-marathon goal in October, 3 runs per week target.", True),
    ("WHEN user talks about music THEN jazz preferences: Miles, Coltrane.",
     "WHEN discussing music preferences THEN reference jazz: Miles Davis, Coltrane, Bill Evans.", True),
    ("WHEN user mentions productivity THEN best window is morning 7-11h.",
     "WHEN discussing work focus THEN morning 7h-11h is peak performance window.", True),
    ("WHEN user talks about wife THEN married 2018, Vietnamese heritage.",
     "WHEN discussing Hua THEN be warm, Vietnamese origin, married in 2018.", True),
    ("WHEN user is stressed THEN break tasks down, remind of past successes.",
     "WHEN user mentions work stress THEN acknowledge, suggest task decomposition and recall past wins.", True),

    # Should NOT merge (different topics)
    ("WHEN user mentions fatigue THEN suggest rest.",
     "WHEN user discusses productivity THEN morning is peak window.", False),
    ("WHEN discussing LIA deployment THEN reference SSL issues.",
     "WHEN discussing LIA architecture THEN reference LangGraph decisions.", False),
    ("WHEN user talks about exercise THEN encourage running.",
     "WHEN user talks about diet THEN remember gluten intolerance.", False),
    ("WHEN user mentions Toulouse THEN parents live there.",
     "WHEN user mentions Paris THEN wife's parents live there.", False),
    ("WHEN discussing budget THEN 600 euros monthly groceries.",
     "WHEN discussing investments THEN PEA ETF World strategy.", False),
    ("WHEN user talks about brother THEN lives in Nantes.",
     "WHEN user talks about sister THEN veterinarian in Montpellier.", False),
    ("WHEN discussing children's judo THEN Leo Wednesday 14h.",
     "WHEN discussing children's dance THEN Emma Saturday 10h.", False),
    ("Observation: user prefers structured action items.",
     "Observation: user values precision over speed.", False),
]


# =============================================================================
# MAIN
# =============================================================================

def run_domain_test(
    client: GoogleGenerativeAIEmbeddings,
    name: str,
    bank: list[str],
    queries: list[tuple[str, list[str]]],
    asymmetric: bool,
) -> dict:
    """Test query->bank retrieval and return score distributions."""
    print(f"\n{'='*90}")
    print(f"  {name}")
    print(f"  Bank: {len(bank)} items | Queries: {len(queries)} | {'ASYMMETRIC' if asymmetric else 'SYMMETRIC'}")
    print(f"{'='*90}")

    # Embed bank
    print(f"  Embedding bank ({len(bank)} items)...")
    bank_embs = batch_embed(client, bank, "RETRIEVAL_DOCUMENT")
    time.sleep(1.5)

    # Embed queries
    query_texts = [q for q, _ in queries]
    if asymmetric:
        print(f"  Embedding queries ({len(queries)} items, RETRIEVAL_QUERY)...")
        query_embs = batch_embed(client, query_texts, "RETRIEVAL_QUERY")
    else:
        print(f"  Embedding queries ({len(queries)} items, RETRIEVAL_DOCUMENT)...")
        query_embs = batch_embed(client, query_texts, "RETRIEVAL_DOCUMENT")
    time.sleep(1.0)

    all_match_scores: list[float] = []
    all_noise_scores: list[float] = []
    query_stats: list[dict] = []

    for (query_text, match_keywords), q_emb in zip(queries, query_embs):
        scores = []
        for i, (mem_text, m_emb) in enumerate(zip(bank, bank_embs)):
            sim = cos_sim(q_emb, m_emb)
            is_match = any(kw.lower() in mem_text.lower() for kw in match_keywords)
            scores.append((sim, is_match, mem_text[:60]))

        scores.sort(reverse=True)

        match_scores = [s for s, m, _ in scores if m]
        noise_scores = [s for s, m, _ in scores if not m]

        if match_scores:
            all_match_scores.extend(match_scores)
        all_noise_scores.extend(noise_scores)

        min_match = min(match_scores) if match_scores else None
        max_noise = max(noise_scores) if noise_scores else 0

        counts = {t: sum(1 for s, _, _ in scores if s >= t)
                  for t in [0.55, 0.58, 0.60, 0.63, 0.65, 0.67, 0.70, 0.72, 0.75]}

        query_stats.append({
            "query": query_text,
            "min_match": min_match,
            "max_noise": max_noise,
            "counts": counts,
            "top5": scores[:5],
        })

    # Print per-query details
    print()
    for qs in query_stats:
        gap = (qs["min_match"] - qs["max_noise"]) if qs["min_match"] else None
        gap_str = f"{gap:+.4f}" if gap else "  N/A "
        mm_str = f"{qs['min_match']:.4f}" if qs['min_match'] else " N/A "
        c = qs["counts"]
        print(f"  Q: \"{qs['query'][:55]:55s}\"")
        print(f"    match_min={mm_str} noise_max={qs['max_noise']:.4f} gap={gap_str}"
              f"  | 0.60={c[0.60]:2d} 0.63={c[0.63]:2d} 0.65={c[0.65]:2d}"
              f" 0.67={c[0.67]:2d} 0.70={c[0.70]:2d} 0.72={c[0.72]:2d}")

    # Global stats
    print(f"\n  {'─'*86}")
    for label, vals in [("MATCH", all_match_scores), ("NOISE", all_noise_scores)]:
        if vals:
            arr = np.array(vals)
            print(f"  {label:5s} (n={len(vals):4d}): "
                  f"min={arr.min():.4f} p5={np.percentile(arr,5):.4f} "
                  f"p25={np.percentile(arr,25):.4f} med={np.median(arr):.4f} "
                  f"p75={np.percentile(arr,75):.4f} p95={np.percentile(arr,95):.4f} "
                  f"max={arr.max():.4f}")

    # Threshold analysis
    print(f"\n  THRESHOLD ANALYSIS:")
    thresholds = [0.55, 0.58, 0.60, 0.63, 0.65, 0.67, 0.70, 0.72, 0.75]
    for t in thresholds:
        tp = sum(1 for s in all_match_scores if s >= t)
        fn = sum(1 for s in all_match_scores if s < t)
        fp = sum(1 for s in all_noise_scores if s >= t)
        tn = sum(1 for s in all_noise_scores if s < t)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        avg_retrieved = np.mean([qs["counts"][t] for qs in query_stats])
        print(f"    {t:.2f}: P={precision:.3f} R={recall:.3f} F1={f1:.3f}"
              f"  avg_retrieved={avg_retrieved:.1f}/query"
              f"  (TP={tp} FP={fp} FN={fn})")

    return {"match_scores": all_match_scores, "noise_scores": all_noise_scores, "query_stats": query_stats}


def run_dedup_test(
    client: GoogleGenerativeAIEmbeddings,
    name: str,
    pairs: list[tuple[str, str, bool]],
) -> dict:
    """Test doc<->doc dedup pairs."""
    print(f"\n{'='*90}")
    print(f"  {name}")
    print(f"  Pairs: {len(pairs)} | SYMMETRIC doc<->doc")
    print(f"{'='*90}")

    all_texts = []
    for a, b, _ in pairs:
        all_texts.extend([a, b])

    print(f"  Embedding {len(all_texts)} texts...")
    all_embs = batch_embed(client, all_texts, "RETRIEVAL_DOCUMENT")

    merge_scores: list[float] = []
    no_merge_scores: list[float] = []

    for i, (a, b, should_merge) in enumerate(pairs):
        emb_a = all_embs[i * 2]
        emb_b = all_embs[i * 2 + 1]
        sim = cos_sim(emb_a, emb_b)

        if should_merge:
            merge_scores.append(sim)
            mark = "MERGE"
        else:
            no_merge_scores.append(sim)
            mark = "KEEP "

        print(f"  [{mark}] {sim:.4f} | {a[:40]:40s} <-> {b[:40]}")

    print(f"\n  {'─'*86}")
    for label, vals in [("MERGE", merge_scores), ("KEEP", no_merge_scores)]:
        if vals:
            arr = np.array(vals)
            print(f"  {label:5s} (n={len(vals):2d}): "
                  f"min={arr.min():.4f} p25={np.percentile(arr,25):.4f} "
                  f"med={np.median(arr):.4f} p75={np.percentile(arr,75):.4f} "
                  f"max={arr.max():.4f}")

    thresholds = [0.80, 0.85, 0.87, 0.89, 0.90, 0.91, 0.92, 0.93, 0.95]
    print(f"\n  THRESHOLD ANALYSIS:")
    for t in thresholds:
        tp = sum(1 for s in merge_scores if s >= t)
        fn = sum(1 for s in merge_scores if s < t)
        fp = sum(1 for s in no_merge_scores if s >= t)
        tn = sum(1 for s in no_merge_scores if s < t)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"    {t:.2f}: P={precision:.3f} R={recall:.3f} F1={f1:.3f}"
              f"  (TP={tp} FP={fp} FN={fn})")

    return {"merge": merge_scores, "keep": no_merge_scores}


def run_interest_dedup(client: GoogleGenerativeAIEmbeddings) -> dict:
    """Test interest topic dedup."""
    print(f"\n{'='*90}")
    print(f"  INTEREST_DEDUP_SIMILARITY_THRESHOLD")
    print(f"  Bank: {len(INTEREST_BANK)} interests | New: {len(INTEREST_DEDUP_TESTS)} | SYMMETRIC")
    print(f"{'='*90}")

    all_texts = INTEREST_BANK + [t for t, _ in INTEREST_DEDUP_TESTS]
    print(f"  Embedding {len(all_texts)} texts...")
    all_embs = batch_embed(client, all_texts, "RETRIEVAL_DOCUMENT")

    bank_embs = all_embs[:len(INTEREST_BANK)]
    new_embs = all_embs[len(INTEREST_BANK):]

    merge_scores: list[float] = []
    no_merge_scores: list[float] = []

    for (new_topic, expected_match), new_emb in zip(INTEREST_DEDUP_TESTS, new_embs):
        best_sim = 0.0
        best_label = ""
        for existing, e_emb in zip(INTEREST_BANK, bank_embs):
            sim = cos_sim(new_emb, e_emb)
            if sim > best_sim:
                best_sim = sim
                best_label = existing

        should_merge = expected_match is not None
        if should_merge:
            merge_scores.append(best_sim)
            mark = "MERGE"
        else:
            no_merge_scores.append(best_sim)
            mark = "NEW  "

        correct = (best_sim >= 0.90 and should_merge) or (best_sim < 0.90 and not should_merge)
        flag = " ok" if correct else " WRONG"
        print(f"  [{mark}] {best_sim:.4f} | {new_topic:42s} -> {best_label[:35]}{flag}")

    print(f"\n  {'─'*86}")
    for label, vals in [("MERGE", merge_scores), ("NEW", no_merge_scores)]:
        if vals:
            arr = np.array(vals)
            print(f"  {label:5s} (n={len(vals):2d}): "
                  f"min={arr.min():.4f} p25={np.percentile(arr,25):.4f} "
                  f"med={np.median(arr):.4f} p75={np.percentile(arr,75):.4f} "
                  f"max={arr.max():.4f}")

    thresholds = [0.80, 0.85, 0.87, 0.89, 0.90, 0.91, 0.92, 0.93, 0.95]
    print(f"\n  THRESHOLD ANALYSIS:")
    for t in thresholds:
        tp = sum(1 for s in merge_scores if s >= t)
        fn = sum(1 for s in merge_scores if s < t)
        fp = sum(1 for s in no_merge_scores if s >= t)
        tn = sum(1 for s in no_merge_scores if s < t)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"    {t:.2f}: P={precision:.3f} R={recall:.3f} F1={f1:.3f}"
              f"  (TP={tp} FP={fp} FN={fn})")

    return {"merge": merge_scores, "no_merge": no_merge_scores}


def run_content_dedup(client: GoogleGenerativeAIEmbeddings) -> dict:
    """Test interest content dedup."""
    print(f"\n{'='*90}")
    print(f"  INTEREST_CONTENT_SIMILARITY_THRESHOLD")
    print(f"  Recent: {len(CONTENT_RECENT)} | New: {len(CONTENT_NEW)} | SYMMETRIC")
    print(f"{'='*90}")

    all_texts = CONTENT_RECENT + [t for t, _, _ in CONTENT_NEW]
    print(f"  Embedding {len(all_texts)} texts...")
    all_embs = batch_embed(client, all_texts, "RETRIEVAL_DOCUMENT")

    recent_embs = all_embs[:len(CONTENT_RECENT)]
    new_embs = all_embs[len(CONTENT_RECENT):]

    dup_scores: list[float] = []
    new_scores: list[float] = []

    for (new_text, is_dup, label), new_emb in zip(CONTENT_NEW, new_embs):
        best_sim = max(cos_sim(new_emb, r_emb) for r_emb in recent_embs)

        if is_dup:
            dup_scores.append(best_sim)
            mark = "DUP "
        else:
            new_scores.append(best_sim)
            mark = "NEW "

        print(f"  [{mark}] {best_sim:.4f} | {label:20s} | {new_text[:60]}")

    print(f"\n  {'─'*86}")
    for label, vals in [("DUP", dup_scores), ("NEW", new_scores)]:
        if vals:
            arr = np.array(vals)
            print(f"  {label:5s} (n={len(vals):2d}): "
                  f"min={arr.min():.4f} p25={np.percentile(arr,25):.4f} "
                  f"med={np.median(arr):.4f} p75={np.percentile(arr,75):.4f} "
                  f"max={arr.max():.4f}")

    thresholds = [0.80, 0.85, 0.87, 0.89, 0.90, 0.91, 0.92, 0.93, 0.95]
    print(f"\n  THRESHOLD ANALYSIS:")
    for t in thresholds:
        tp = sum(1 for s in dup_scores if s >= t)
        fn = sum(1 for s in dup_scores if s < t)
        fp = sum(1 for s in new_scores if s >= t)
        tn = sum(1 for s in new_scores if s < t)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"    {t:.2f}: P={precision:.3f} R={recall:.3f} F1={f1:.3f}"
              f"  (TP={tp} FP={fp} FN={fn})")

    return {"dup": dup_scores, "new": new_scores}


def main() -> None:
    if not API_KEY:
        print("ERROR: Set GOOGLE_GEMINI_API_KEY or GOOGLE_API_KEY")
        sys.exit(1)

    client = GoogleGenerativeAIEmbeddings(model=MODEL, google_api_key=API_KEY)

    # 1. Memory retrieval
    mem_result = run_domain_test(
        client, "MEMORY_MIN_SEARCH_SCORE (80 memories, 30 queries)",
        MEMORY_BANK, MEMORY_QUERIES, asymmetric=True)

    # 2. Journal context
    jour_result = run_domain_test(
        client, "JOURNAL_CONTEXT_MIN_SCORE (30 entries, 20 queries)",
        JOURNAL_BANK, JOURNAL_QUERIES, asymmetric=True)

    # 3. RAG retrieval
    rag_result = run_domain_test(
        client, "RAG_SPACES_RETRIEVAL_MIN_SCORE (25 chunks, 15 queries)",
        RAG_BANK, RAG_QUERIES, asymmetric=True)

    # 4. Journal dedup
    jdedup_result = run_dedup_test(
        client, "JOURNAL_DEDUP_SIMILARITY_THRESHOLD (16 pairs)",
        JOURNAL_DEDUP_PAIRS)

    # 5. Interest dedup
    idedup_result = run_interest_dedup(client)

    # 6. Content dedup
    cdedup_result = run_content_dedup(client)

    # =================================================================
    # FINAL SUMMARY
    # =================================================================
    print(f"\n\n{'#'*90}")
    print(f"  FINAL SUMMARY")
    print(f"{'#'*90}")
    print(f"""
  Variable                                  | Current | Best F1 threshold
  ------------------------------------------+---------+------------------""")

    # Find best F1 for each (simplified)
    print(f"  See per-domain THRESHOLD ANALYSIS above for detailed P/R/F1 at each threshold.")


if __name__ == "__main__":
    main()
