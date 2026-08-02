# ADR-193 — Une capacité de lecture par domaine, et une identité que l'utilisateur peut corriger

**Statut** : accepté — 2026-08-01
**Portée** : catalogue d'outils, contrat de sortie des outils, CRM Relations, injection de contexte
**Remplace/complète** : ADR-184 (limites publiées), ADR-185 (comptes exacts, pliage unique), ADR-190 (portée du 360°), ADR-191 (capacités atteignables)

## Le déclencheur

Deux formulations de la même question, le même jour, le même utilisateur :

| Formulation | Plan produit |
|---|---|
| « de quand date mon dernier appel à ma femme ? » | 1 étape → `get_person_overview_tool` ✅ |
| « c'était quand mon dernier appel à ma femme ? » | 2 étapes → **passer un appel téléphonique** ❌ |

Le second plan cherchait le contact, puis **téléphonait à la personne pour lui demander**
quand avait eu lieu le dernier appel. Seul l'échec d'une référence l'a arrêté.

L'enquête a montré que ce n'était pas un caprice du modèle mais la seule façon
d'obéir : le prompt annonce `Primary domain: telephony`, et le catalogue du
domaine `telephony` ne contenait **qu'une capacité — écrire**.

## Décisions

### 1. Un domaine qui ne sait qu'écrire poussera à écrire

Trois capacités de lecture sont ajoutées, **chacune dans le domaine qui en
manquait** : `get_calls_tool` (telephony), `get_open_loops_tool` (task),
`get_peer_messages_tool` (peer).

Elles ne sont **pas** rattachées à `contact_agent` avec `serves_domains`.
Mesure à l'appui : le catalogue du planificateur est plafonné, et rendre trois
outils atteignables depuis `contact` évinçait `reply_email_tool`,
`forward_email_tool` et `delete_email_tool` de la combinaison contact+email,
plus les trois mutations d'agenda de contact+event+email.

> **Une capacité de lecture ne doit pas coûter une capacité d'écriture.**

Les trois projettent le même `RelationsService.build_detail` : une seule
résolution d'identité, donc l'outil et la fiche ne peuvent pas diverger
(ADR-185). Chacune publie sa borne (ADR-184) et rend le total exact à côté de
sa page (ADR-185).

Elles n'appliquent **pas** `RelationOverviewScope` : cette portée répond à
« que peut lire un *point 360°* », écrite au clic depuis la fiche. Une question
tapée dans le chat n'en porte aucune, et refuser d'y répondre au nom d'un
réglage fait pour une autre capacité serait un refus inventé.

### 2. Une lecture ne doit jamais produire un plan qui écrit

Règle déterministe, avant tout appel LLM : *intention non mutative détectée +
plan appelant un outil de mutation → plan invalide, retour au planificateur
avec une consigne*. Elle s'exécute avec les trois autres règles pré-LLM, donc
**hors de portée** de l'exemption `well_formed_cross_domain_mutation` — laquelle
dispensait de vérification tout plan à deux étapes bien chaîné se terminant par
une mutation, c'est-à-dire exactement la forme fautive. Plus le plan était bien
formé, moins il était vérifié.

### 3. Un chemin publié est un chemin qui existe

`get_contacts_tool` publiait `contacts[0].name` ; aucun de ses trois modes ne
produit ce champ (tous passent le `person` brut du fournisseur). Le validateur
de références **approuvait** ce chemin — il valide contre les
`reference_examples` avant toute autre chose. Le manifeste était donc la seule
autorité, et il mentait.

- Le champ `name` est **promu** dans le payload, comme `subject`/`from` le sont
  déjà pour les mails. Il répare du même geste la référence publiée, la
  résolution conversationnelle (« Marie » ne matchait jamais) et l'étiquette
  des confirmations HITL.
- `total` est remplacé par `count` (mesuré : les six outils unifiés produisent
  `count`) ou retiré des manifestes qui ne le produisent pas.
- Une garde CI résout désormais chaque `reference_example` contre une sortie
  réelle.

### 4. Le domaine d'un outil est déclaré, pas deviné

`place_phone_call_tool` était rattaché au domaine `places` — son nom commence
par `place_`. La règle censée détecter un plan qui abandonne son domaine
primaire se déclenchait donc à tort sur **toute** demande d'appel, et restait
muette sur le plan à deux étapes qui l'abandonnait vraiment.

Le manifeste fait foi : `context_key` d'abord, puis la convention de nommage
pour les outils sans manifeste (MCP, skills). La couverture de domaine lit
l'agent **et** `serves_domains` — sans ce second terme, le 360° sur un pair
cesserait de couvrir son propre domaine.

### 5. L'identité est pliée par le système, corrigée par l'utilisateur

`fold_name` répond à « est-ce littéralement la même orthographe ». Il ne peut
pas savoir que `0612345678` et `alice vernier` sont une seule relation. Seul
l'utilisateur le sait, donc la fusion est **manuelle et jamais proposée**.

- Table d'alias **plate** : un alias ne pointe jamais vers un autre alias. La
  compression de chemin est payée à l'écriture, si bien qu'une lecture est un
  seul lookup — aucune chaîne à parcourir, aucun cycle à détecter.
- **Aucun cycle ne peut être écrit** : la cible est résolue vers son canonique
  avant comparaison, donc fusionner en sens inverse est un no-op.
- **Réversible** : rien n'est réécrit dans les sources, qui gardent leurs
  orthographes. Annuler une fusion, c'est supprimer une ligne.
- La fusion est **affichée** sur la fiche avec son annulation : une fusion que
  personne ne voit est une fusion que personne ne peut corriger.
- Elle ne touche **jamais** l'annuaire des pairs. `peers_tools` résout un
  destinataire par `fold_name` pour décider quel assistant reçoit un message :
  une décision d'affichage prise par un utilisateur ne doit pas pouvoir
  rediriger un message vers un autre compte. Un test lit le source pour s'en
  assurer.

### 6. Nommer un pair, c'est déjà savoir des choses sur lui

Nommer une personne connectée ne corrigeait que le routage ; aucune donnée
n'était injectée, si bien que l'assistant annonçait une recherche pour des
faits déjà en base. Sont désormais injectés les **trois blocs locaux**
(engagements, appels, messages relayés) — pas les souvenirs, déjà injectés par
pertinence sémantique, ni les blocs adossés à un connecteur : un tour qui se
contente de **nommer** quelqu'un ne doit pas déclencher d'appel externe.

Ici, à l'inverse du point 1, la portée 360° **est** souveraine : l'utilisateur
n'a rien demandé, c'est le système qui décide d'injecter.

## Conséquences

- Une fusion est une **donnée personnelle** : elle dit qui, aux yeux de
  l'utilisateur, est la même personne. `relation_aliases` est donc classée dans
  la carte RGPD (`user_data_map.TABLE_RULES`) et purgée explicitement à la
  suppression du compte, comme `relation_favorites`. La garde de complétude a
  attrapé l'oubli : toute table non classée fait rougir la CI, ce qui est
  exactement le rôle d'un registre à assertion de complétude (ADR-085).
- Les plafonds de catalogue deviennent des réglages (`PLANNER_CATALOGUE_MAX_TOOLS`,
  `PLANNER_CATALOGUE_PANIC_MAX_TOOLS`), avec une garde au démarrage : **le
  plafond de secours n'est jamais inférieur au plafond nominal**, sans quoi le
  filet offrirait moins que le chemin qui vient d'échouer.
- Élargir le catalogue reste un arbitrage, pas un gain net : le filtrage est
  autant un réducteur de bruit qu'un budget de jetons, et le défaut de départ
  était un défaut de **sélection**. Les réglages existent pour être bougés sur
  mesure (`excluded_tools` dans les journaux), pas par précaution.
- ADR-191 est **nuancé** sur un point : l'adresse d'un pair déjà présente sur
  la fiche est promue pour survivre au plafond. La clause « APPENDED, never
  prepended » protégeait une adresse de la fiche contre une adresse
  *extérieure* ; ici l'adresse promue vient de la fiche, la promotion n'ajoute
  rien et choisit seulement qui perd le siège — en faveur de la seule identité
  que l'utilisateur a confirmée.

## Ce qui reste ouvert

- `is_mutation_intent` sur la requête d'origine n'a pas pu être relu (journaux
  perdus au redémarrage du conteneur). Si l'analyseur l'avait mis à `True`, la
  règle du point 2 serait inopérante sur ce cas précis — jamais nuisible.
- Le registre de schémas d'outils (`schema_registration`, 1229 lignes) est
  **mort** : ses trois entrées portent des noms d'outils hors catalogue depuis
  la v2.0, son seul autre consommateur n'est jamais appelé. Son retrait mérite
  son propre ADR.
- Le repli d'extrait de mail ne remplit que `snippet` : remplir `body` avec un
  aperçu tronqué ferait passer un extrait pour un message complet.
