# ADR-191 : un outil doit être joignable depuis le domaine qu'on lui adresse, et un clic n'est pas une phrase

**Statut**: ✅ IMPLEMENTED (2026-08-01)
**Date**: 2026-08-01
**Décideurs**: Équipe LIA
**Complète**: [ADR-190](ADR-190-Overview-Scope-And-Full-Contact-Card.md) (portée du 360° et fiche complète), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (une contrainte appliquée doit être publiée), [ADR-141](ADR-141-Active-Knowledge-Layer.md) (outil 360°), [ADR-173](ADR-173-Card-Intent-Autosend.md) (`?intent=` auto-envoyé)

## Contexte

Le 2026-08-01, un point 360° lancé depuis une fiche relation revient amputé :
ni engagements ouverts, ni appels récents, ni messages relayés. L'assistant a
appelé `get_emails_tool`, `get_events_tool` et `get_contacts_tool` — trois
outils génériques qui, structurellement, ne savent rien de ces trois blocs.

### Ce que la mesure établit

L'enquête a écarté quatre hypothèses successives avant d'aboutir. La cause tient
en trois faits, chacun vérifiable dans le dépôt :

**1. L'outil 360° n'a qu'un seul domaine.**
`person_overview_manifest.py` déclare `agent="contact_agent"`, dont
`SmartCatalogueService._extract_domain` dérive le domaine `contact`. Un seul.

**2. Le filtrage de domaine passe avant le score sémantique.**
`normal_filtering.py` écarte tout manifeste dont le domaine n'est pas demandé
(`if tool_domain not in tools_by_domain: continue`) **avant** de consulter le
moindre score. Un outil hors domaine est éliminé sans que sa pertinence soit
jamais lue.

**3. Le prompt de l'analyseur impose le domaine qui exclut l'outil.**
`prompts/v1/query_analyzer_prompt.txt` : les données d'un utilisateur connecté
« sont joignables UNIQUEMENT par le domaine `peer` », et « lire le carnet
d'adresses (`contact`) ne peut pas répondre à cette question ». Les journaux de
production confirment la classification : `primary_domain: "peer"` sur un vrai
point 360°.

La chaîne est donc mécanique : le prompt pousse vers `peer` → le filtrage écarte
`contact` → l'outil disparaît. Reproduit de façon déterministe sur le registre
réel :

| `intelligence.domains` | Catalogue | `get_person_overview_tool` |
|---|---|---|
| `["peer"]` | 1 outil | **absent** |
| `["peer", "event"]` | 5 outils | **absent** |
| `["peer", "contact"]` | 5 outils | présent |

L'outil marquait **0,853** — le meilleur score de tout le catalogue, face à des
outils génériques à 0,000-0,005. Quand le point 360° fonctionnait, c'est que le
modèle avait émis `contact` **en plus**, contre la consigne du prompt. Une
bascule stochastique, pas un chemin nominal.

### Le second défaut, indépendant du premier

Rendre l'outil joignable le rend **visible**. Cela ne le rend pas **certain** :
le planificateur reste libre de ne pas le choisir. Or l'utilisateur n'a pas
formulé une intention, il a **appuyé sur un bouton**, sur une fiche nommée, avec
une portée cochée. Le système détient cette certitude avant qu'aucun modèle ne
soit consulté — puis il la sérialise en prose française et dépense trois étapes
stochastiques (analyseur, planificateur, validateur) à tenter de la
reconstituer. Aucun réglage de prompt ne rend ce chemin déterministe.

## Décision

### 1. Joignabilité — `serves_domains` sur le manifeste

`ToolManifest` gagne `serves_domains: list[str]` : les domaines **additionnels**
depuis lesquels l'outil est joignable, au-delà de celui de son agent.
`get_person_overview_tool` déclare `serves_domains=["peer"]`.

Une **implémentation unique** répond désormais à « cet outil est-il dans la
portée de cette requête ? » : `SmartCatalogueService.placement_domain`, appelée
par les deux stratégies de filtrage (normale et panic). Le domaine d'origine
l'emporte quand il est demandé, de sorte que la couverture par domaine continue
de placer les outils dans le seau qu'elle attend.

Toute valeur est **validée à l'enregistrement** contre `DOMAIN_REGISTRY` : un
domaine inconnu lève, il ne rend pas l'outil silencieusement injoignable.

**Ce que la décision n'est PAS** : ajouter `contact` aux `related_domains` de
`peer`. Ce correctif naïf a déjà causé un incident de production le 2026-07-30
— « lister contact comme lié tirait les outils Google Contacts dans CHAQUE plan
peer, et un scope contacts manquant invalidait alors le plan ENTIER »
(`registry/program_domain_configs.py`). Mesuré après correctif : un plan `peer`
gagne **exactement un** outil, en lecture seule, et aucun outil de mutation.

### 2. Garantie — la directive de capacité

`ChatRequest` gagne un champ optionnel `directive: {capability, subject}`, sur
la couture exacte de `hitl_decision` — la décision HITL en un clic qui
court-circuite déjà le classifieur de réponse plutôt que de demander à un LLM de
relire le clic de l'utilisateur.

- `capability` est un `Literal` **fermé** : Pydantic rejette toute autre valeur
  à la frontière HTTP. Le navigateur nomme une **capacité**, jamais un outil ;
  le serveur choisit quel outil en lecture seule l'implémente
  (`domains/agents/capability_directives.py`). Cette porte ne mène pas à
  `delete_email_tool`.
- Le transport jusqu'au planificateur est un `ContextVar`
  (`capability_directive_ctx`), posé au même endroit et avec la même discipline
  de réinitialisation que `active_skills_ctx`.
- La garantie est appliquée dans `planner_node_v3`, **avant la validation** —
  au même titre que le clamp des paramètres hors bornes et l'auto-correction de
  `for_each_max` : ce qui est mécaniquement réparable est réparé avant
  validation, jamais rapporté comme un défaut (doctrine ADR-184).

**Le plan est enrichi, jamais remplacé.** Les étapes produites par le modèle
survivent intactes ; le pas garanti n'est ajouté que s'il manque. Si le
planificateur a déjà produit l'appel, **ses paramètres l'emportent** — il a pu
résoudre un alias ou une orthographe plus complète.

**Un plan sans étape est laissé tel quel.** `ExecutionPlan` n'autorise cette
forme que pour deux cas — `needs_clarification` (le système pose une question à
l'utilisateur) et `skill_bypass_noop` (exécution déléguée à un skill). Semer
dans l'un ou l'autre répondrait de force à une question en attente, ou
exécuterait la capacité deux fois. **Une garantie qui écrase une question est un
bug, pas une garantie.**

### 3. Restitution — la charge doit atteindre le synthétiseur

Rendre l'outil joignable puis garanti ne sert à rien s'il parle dans le vide.
Mesuré sur l'API dev le 2026-08-01 : le pas `directive_1` s'exécute, la charge
contient messages relayés, engagements et souvenirs — et l'assistant répond
*« je n'ai aucune donnée sous la main »*.

Deux canaux seulement atteignent le prompt de réponse :

1. le **registre de données**, alimenté **exclusivement** par les outils
   déclarant un `context_key` (`generate_data_for_filtering` ne lit rien
   d'autre) ;
2. le champ **`message`** de `UnifiedToolOutput`
   (`formatters/agent_results._extract_action_success_messages`).

L'outil 360° n'a **pas** de `context_key` — délibérément : le registre
sérialise des **items** destinés au filtrage, une ligne tronquée chacun, ce qui
est la mauvaise forme pour le briefing d'**une** personne réparti sur neuf
blocs hétérogènes. Et son `message` valait `"overview built for X"` : la preuve
que l'outil a tourné, et **pas un seul fait**. Les journaux le disent
textuellement — `agent_results_summary = (empty)`, `registry_items_count = 1`,
`result_domains = ["events"]`.

Le `message` porte donc désormais la charge elle-même, en JSON compact (comme
le catalogue transmis au planificateur) : sans perte, et surtout **la
distinction d'ADR-190 survit** — un bloc illisible ne porte aucune clé et
figure dans `unavailable`, une liste vide veut dire « regardé, rien trouvé ».
Ce manque est répété **en tête** du message plutôt que laissé au fond d'une
clé : c'est la nuance qu'un modèle aplatit le plus facilement quand on ne la
lui dit pas en clair.

**Pourquoi les tests ne l'avaient pas vu** : ils vérifiaient tous
`structured_data` — ce que l'outil **produit**. Aucun ne vérifiait ce qui
**atteint** le modèle. Six oracles portent désormais sur le canal ; ils
tombent tous les six si l'on restaure l'ancien message.

### 4. Un pair connecté apporte sa propre adresse — s'il l'a partagée

Les sections fournisseurs interrogent le courrier et l'agenda **par adresse**, et
`_addresses_of` ne lisait que la fiche du carnet d'adresses. Un utilisateur
**connecté** mais absent du carnet n'avait donc aucune adresse : mail et
rendez-vous revenaient `NO_ADDRESS` pour quelqu'un avec qui l'utilisateur
échange **à travers ce produit même** (mesuré 2026-08-01 : `unavailable:
["events"]` sur un pair partageant pourtant son agenda).

`PeerConnectionProfile` porte désormais `peer_email`, rempli **uniquement**
quand le pair a activé `peer_email_visible`. L'adresse sert à apparier
correspondants et participants dans le courrier et l'agenda **de
l'utilisateur** — qu'il peut déjà lire — et n'est **jamais** réémise dans la
charge utile.

**Cela révise sciemment une clause d'ADR-189** : « l'opt-in n'alimente pas les
sections fournisseurs du CRM ». Cette clause protégeait contre l'adresse
devenant une source **par effet de bord**, contournant le réglage. Ici le
réglage est **lu**, et lui seul décide — le consentement du pair reste l'unique
porte. Le reste d'ADR-189 est intact : la découverte ne renvoie toujours que le
fragment masqué, et une demande en attente n'ouvre rien.

Le correctif vit dans `RelationContextService`, la couture que la **page et
l'assistant** appellent tous deux : ils ne peuvent donc pas diverger, et cela
vaut pour **toutes** les sections de la fiche (mails, rendez-vous), pas
seulement l'agenda.

### 5. Ne pas déborder : une capacité garantie écarte ce qu'elle recouvre

Quand le 360° annonce honnêtement qu'il n'a trouvé aucun rendez-vous partagé et
que le plan appelle **aussi** `get_events_tool`, ce dernier renvoie l'agenda
**de l'utilisateur**, sans le moindre filtre sur la personne — et l'assistant
présente « Goûter à la maison » comme un élément du 360°, alors que le pair ne
l'organise ni n'y participe.

Règle retenue : *si aucune adresse n'est disponible, ou si aucun rendez-vous n'a
le pair comme organisateur ou invité, on ne déborde pas sur le calendrier de
l'utilisateur — cela transmettrait une fausse information.*

Le spec de directive déclare donc `supersedes` : les outils que la capacité
recouvre **par sujet** sont retirés du plan quand la capacité est garantie. Le
manifeste déclarait déjà l'outil SELF-CONTAINED ; ceci rend cette déclaration
**contraignante** lorsque l'utilisateur a lui-même invoqué la capacité.

Deux garde-fous :

- une étape recouverte dont **une autre dépend** est conservée : porteuse avant
  d'être redondante, la retirer laisserait une référence `$steps` pendante —
  une phrase fausse échangée contre un plan cassé ;
- la suppression n'a lieu **que** sous directive. Un tour librement planifié qui
  appelle le 360° à côté d'une lecture d'agenda relève du raisonnement du
  planificateur et n'est pas touché.

Ce que l'utilisateur voulait conserver l'est : un sous-agent, une recherche web,
une tâche, un rappel restent au plan. Seul ce que la capacité répond déjà part.

### 6. Ce que la décision écarte explicitement

**Publier le score sémantique dans le catalogue.** Envisagé — le système calcule
une pertinence, s'en sert pour exclure des outils, puis la cache au seul acteur
qui doit choisir parmi les survivants. Écarté : aucune preuve n'établit que le
planificateur ignore l'outil *parce qu*'il ne voit pas le score, et le
changement modifierait le prompt de **toutes** les requêtes. Une hypothèse non
vérifiée ne se déploie pas.

## Conséquences

### Positives

- Le 360° sur un pair est **structurellement possible** — il ne l'était pas.
- Le bouton est **déterministe** : la capacité figure dans le plan, quoi que
  produise le modèle.
- Les autres appels d'outils sont **conservés**, comme demandé.
- Le texte libre (« prépare mon call avec Marie ») bénéficie de la joignabilité
  sans dépendre de la directive.
- Le champ est **purement additif** : absent, le comportement est identique.

### Négatives / limites

- `serves_domains` élargit l'ensemble des candidats pour **toutes** les requêtes
  du domaine ajouté. À déclarer avec parcimonie ; la garde au démarrage vérifie
  l'existence du domaine, pas la pertinence de la déclaration.
- La directive ne couvre que les surfaces qui l'émettent. Une demande tapée à la
  main reste sur le chemin probabiliste — c'est la raison d'être du volet 1.

### Preuve

- `tests/unit/domains/agents/services/catalogue/test_cross_domain_reachability.py`
  (15 tests) exerce le **registre réel** et les **vraies stratégies**. Retirer
  `serves_domains=["peer"]` en fait tomber 6.
- `tests/unit/domains/agents/test_capability_directives.py` (22 tests) : pas
  semé, plan du modèle préservé, plans-souches épargnés, registre complet,
  outils en lecture seule, frontière HTTP fermée.
- `apps/web/e2e/smoke/chat-360-deep-link.spec.ts` : le parcours complet en
  navigateur — la directive atteint le corps HTTP, la bulle de l'utilisateur
  survit au chargement de l'historique, un second 360° porte bien la seconde
  personne, et un `?intent=` ordinaire n'emporte aucune directive.

## Alternatives considérées

| Option | Pourquoi écartée |
|---|---|
| `related_domains=["contact"]` sur `peer` | A déjà cassé la production le 2026-07-30 : tire tout le CRUD Contacts dans chaque plan peer |
| Enregistrer un second manifeste sous `peer_agent` | Duplication d'un contrat ; deux sources de vérité pour un outil |
| Ajuster le prompt de l'analyseur pour émettre `contact` | Élargit un entonnoir sans rien garantir ; le défaut reste possible |
| Court-circuiter le planificateur (Router → orchestrateur) | Cette arête a été retirée volontairement (« was ambiguous », `graph.py`) ; et supprimerait les appels d'outils que l'utilisateur veut conserver |
| Rejouer la portée stockée comme signal de directive | Canal latéral daté et concurrent : se déclencherait sur un message sans rapport |

## Références

- `apps/api/src/domains/agents/capability_directives.py` — vocabulaire, registre, garantie
- `apps/api/src/domains/agents/services/smart_catalogue_service.py` — `placement_domain`
- `apps/api/src/domains/agents/registry/catalogue.py` — `ToolManifest.serves_domains`
- `apps/web/src/types/directive.ts` — contrat de fil côté navigateur
