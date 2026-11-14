# ADR-280 — Un commutateur par capacité, et une carte qui ne ment pas

- **Statut** : Accepté
- **Date** : 2026-09-10
- **Amende** : ADR-216 (commutateurs de plateforme), ADR-085 (assertions de
  complétude au démarrage), ADR-185 (un compteur montré est exact ou n'existe
  pas), ADR-279 (un commutateur retire la capacité, jamais l'archive)
- **Périmètre** : `PlatformCapability` (12 → 25), `CAPABILITY_SPECS`, garde de
  route et points d'étranglement de service, `PLATFORM_CAPABILITY_NODES`,
  `COUNTED_NODES` / `SWITCH_NODE_KEYS`, panneau d'administration

## Contexte

### Treize fonctionnalités sans commutateur

Le panneau d'administration offrait **douze** capacités. Le produit livrait, en
plus : un tableau de travail (ADR-276), des journaux personnels, des habitudes
apprises (ADR-214), des notifications proactives, des connexions entre comptes,
un profil psychologique, des canaux externes, des fils ouverts, la mémoire à
long terme, le suivi des centres d'intérêt, des débriefs de relation (ADR-269),
la délégation à des sous-agents (ADR-083) et un Python éphémère (ADR-249).

Treize fonctionnalités qu'un exploitant ne pouvait **ni voir ni couper** sans
redéployer. C'est exactement la dérive contre laquelle ADR-085 a posé ses
assertions de complétude, pointée cette fois sur le registre des commutateurs
lui-même.

### Une étoile qui comptait autre chose que son nom

Mesuré le 2026-09-10 : le nœud de la constellation **clé `relations`, libellé
« Relations »**, comptait des lignes `OpenLoop`. Une personne lisait
« Relations : 4 » alors que la figure était « quatre fils non terminés ». La même
erreur courait sur toute la chaîne : la destination du nœud pointait vers la
section de réglages **« fils ouverts »**, donc cliquer sur « Relations » menait
aux fils ouverts.

### Un panneau qui disait « routes » d'un point d'étranglement

`enforced_on_routes` était calculé comme `route_enforced or service_enforced`.
Le champ nommait les routes et portait les deux, si bien que le panneau
annonçait « appliqué sur les routes » d'une capacité gardée à l'intérieur d'un
service. Avec cinq nouvelles capacités de ce type, l'imprécision devenait un
mensonge courant.

## Décision

### 1. Vingt-cinq capacités, et la partition est vérifiée dans les deux sens

`PlatformCapability` passe de douze à vingt-cinq membres. Un test compare
l'énumération à une **liste tenue par une personne** — pas dérivée du code — dans
les deux directions : une fonctionnalité livrée sans commutateur échoue, et un
commutateur que personne n'a décidé d'expédier échoue aussi.

Chaque spécification est vérifiée pièce par pièce : le plafond de déploiement
existe réellement sur `settings` (un attribut mal orthographié se lirait `False`
et couperait la fonctionnalité pour toujours), la clé du magasin de réglages
existe et **porte le nom de sa capacité** (une clé nommant une autre capacité
laisserait un exploitant en couper une pour une autre), et le libellé suit la
convention que le frontend résout.

### 2. Un commutateur retire la CAPACITÉ, jamais l'ARCHIVE

C'est la leçon d'ADR-279 généralisée. Deux formes d'application, choisies par ce
que la capacité EST :

- **la route est la capacité** — un tableau, des connexions, un canal vivant, un
  profil : la garde se pose sur le routeur (`workboard`, `journals`, `peers`,
  `psyche`, `channels`, `open_loops` ; `habits` et `heartbeat` ont quitté cette
  liste le 2026-09-11, voir l'amendement ci-dessous) ;
- **la capacité est un acte de FOND qui remplit une archive que la personne
  continue de lire** — extraire une mémoire, apprendre un intérêt, écrire un
  débrief : la garde se pose sur l'ACTE, et le routeur de l'archive reste ouvert
  (`memory`, `interests`, `relation_debrief`, plus `sub_agents` et
  `python_sandbox`, qui n'ont pas de routeur du tout).

Couper la mémoire arrête l'apprentissage de nouveaux faits ; chaque mémoire déjà
apprise reste lisible et supprimable. C'est la même phrase que pour les
téléversements et la galerie.

### 3. Les points d'étranglement lisent la CAPACITÉ, pas le drapeau brut

Les cinq gardes de service lisaient `settings.<flag>` directement, donc le
commutateur de l'exploitant n'y changeait rien. Elles lisent maintenant
`is_capability_enabled`, qui compose le plafond de déploiement ET le commutateur
— et le lisent **à l'appel**, parce qu'un commutateur basculé après le démarrage
doit prendre effet sans redémarrage.

Deux d'entre eux ont dû devenir asynchrones pour cela (`_enabled` du débrief, la
porte du sous-agent) : le magasin de réglages est derrière Redis, et lire le
drapeau brut annoncerait une capacité qu'un administrateur a coupée il y a une
heure.

### 4. Le nœud dit ce qu'il compte

Le nœud `relations` devient **`open_loops`**, libellé « Fils ouverts » dans les
six langues, et pointe vers la section « fils ouverts » qu'il désignait déjà.

Une VRAIE entrée « Relations » revient comme **nœud-commutateur**, sans compteur :
la page Relations est une LENTILLE sur les contacts et les messages, elle ne
possède aucune ligne, donc elle n'a rien d'exact à compter — et inventer un
nombre est précisément ce qu'ADR-185 interdit. Elle est exemptée de destination
de réglages : sa destination EST la page, où ADR-269 place déjà l'interrupteur
du débrief.

### 5. Cinq nœuds de plus, parce que la carte ne doit pas rester en arrière

`open_loops` (renommé), `workboard`, `reminders`, `generated_files` (ADR-279) et
`relations` (redevenu réel). Deux capacités restent **hors carte** avec une
raison écrite : la délégation et le Python éphémère sont ambiants — aucune
surface REST, aucun état par compte, une étoile qui ne pourrait qu'être allumée.

Deux compteurs passent par le module qui POSSÈDE leur règle plutôt que de la
réexprimer : le tableau de travail par `visible_predicate` (« propriétaire OU
porteur »), les fichiers générés par le vocabulaire `GENERATED_ORIGINS`. Une
seconde lecture de ces règles finirait par contredire la surface qu'elle décrit.

### 6. Le panneau dit OÙ un commutateur mord, et le dit par famille

`enforced_on_routes` et `enforced_in_service` sont séparés. Le panneau dit
« appliqué à un point d'étranglement interne » quand c'en est un, et le dit avec
la phrase qui compte : *la capacité s'arrête, ce qu'elle a déjà produit reste*.

Vingt-cinq lignes identiques en une colonne sont un mur qu'un exploitant fait
défiler ; le panneau les groupe en six familles (médias et voix, mémoire et
connaissances, portée et outils, travail et initiative, personnes, assistant).
**La famille est déclarée dans la spécification backend**, pas dans le frontend :
deux tables finiraient par ne plus être d'accord sur l'appartenance d'une
capacité. L'ordre des familles est celui de la déclaration et jamais celui de la
charge utile — un exploitant qui a basculé quelque chose doit retrouver le
panneau là où il l'a laissé — et une famille que le frontend ne sait pas nommer
est dessinée **en dernier plutôt que perdue** : un commutateur invisible est pire
qu'un commutateur mal placé.

### 7. La carte lit une table à la fois

Ajouter des nœuds a rendu visible ce que le `asyncio.gather` de la carte coûtait
déjà. Mesuré le 2026-09-10 avec un gestionnaire de session instrumenté :
`resolve_capabilities` tenait **dix-huit contextes de session ouverts au même
instant**, contre un pool de `database_pool_size` 20 plus
`database_max_overflow` 10 — un seul chargement de page en prenait l'essentiel,
et un deuxième lecteur attendait sur `database_pool_timeout`.

| Stratégie | Latence (5 essais, à chaud) | Sessions simultanées |
|---|---|---|
| `gather` | 10 ms | 18 |
| boucle | 21 ms | 1 |

Onze millisecondes rachètent dix-sept sessions simultanées sur une page qui en
coûte déjà des centaines : c'est la règle du dépôt lui-même — « pour une poignée
de requêtes indexées, une simple boucle séquentielle suffit et reste plus
simple » — appliquée à l'endroit qui l'enfreignait.

La boucle rend au passage **structurelle** une promesse que le module écrivait
déjà : chaque sonde échoue en DOUCEUR. `gather(return_exceptions=False)` ne la
tenait que parce que chaque compteur portait son propre `try` ; un compteur
écrit sans lui aurait vidé la page entière. Une lecture qui échoue est rapportée
DISPONIBLE et inactive — jamais indisponible, mot réservé à « l'instance l'a
coupé », qui ferait conclure au lecteur que la fonctionnalité est éteinte.

## Conséquences

**Positives**

- Toute fonctionnalité que vit une personne se coupe sans redéploiement.
- La carte des capacités décrit le produit d'aujourd'hui, et chaque étoile
  compte ce que son nom dit.
- Le panneau distingue les trois façons dont un commutateur mord.

**Coûts et limites**

- **Vingt-cinq lectures de capacité sur le chemin de requête.** Chacune passe
  par le cache Redis d'ADR-216 et retombe sur la valeur d'environnement en cas
  d'échec — une lecture ne lève jamais.
- Les drapeaux d'environnement gardent leur nom d'origine
  (`memory_extraction_enabled` pour la capacité `memory`,
  `python_sandbox_tool_enabled` pour `python_sandbox`) : les renommer aurait
  cassé tout `.env` existant pour un gain cosmétique.
- **La carte ne compte toujours pas les relations.** C'est voulu : le domaine ne
  possède pas de lignes, et un nombre inventé serait pire qu'aucun.

## Alternatives écartées

- **Un commutateur par drapeau `*_enabled`.** Il y en a 102, dont l'immense
  majorité sont des réglages internes (`llm_cache_enabled`,
  `semantic_pivot_enabled`, `router_debug_log_enabled`). Les exposer ferait du
  panneau un tableau de bord de réglages fins, où une erreur d'exploitation coûte
  plus cher que l'absence du commutateur. Ce que le panneau offre est ce qu'une
  PERSONNE vit.
- **Garder `relations` comme nœud compté, en comptant les débriefs.** Le nombre
  aurait été exact et illisible : « Relations : 2 » sur un compte qui suit
  quarante personnes et n'a ouvert que deux fiches.
- **Grouper les familles côté frontend.** Deux tables pour une appartenance,
  c'est la dérive que ce dépôt paie régulièrement — la famille voyage avec la
  spécification.

## Amendement 2026-09-11 — `habits` et `heartbeat` sont des actes de fond, gardés à l'acte

L'audit des habitudes (ADR-214, amendement c) a mesuré sur docker dev ce que
la garde de routeur ne tenait pas : `habits` OFF laissait le job nocturne
apprendre, le ledger enregistrer, le bloc heartbeat consommer le profil et le
scoring différer les ticks ; `heartbeat` OFF laissait le balayage périodique,
le balayage des réveils et celui des moments notifier. La route (`/habits`,
`/heartbeat/settings`) n'était pas la capacité : elle en est l'ARCHIVE et le
réglage, exactement le cas de la mémoire et des intérêts.

Les deux passent donc dans la seconde famille (`service_enforced=True`,
`route_enforced=False`) :

- `habits` est lu à l'acte par le job nocturne, l'écriture du ledger
  (`record_occurrence_if_allowed`, issue `feature_disabled` sur
  `recurrence_ledger_writes_total`), la promotion, le bloc heartbeat, le bloc
  ambiant, le scoring de tick et le ping de présence (`record_presence` rend
  `disabled`). Le routeur des habitudes reste ouvert — la personne consulte,
  met en pause, supprime, oublie — et seuls `/recompute` et `/presence`, qui
  sont des ACTES, portent `capability_dependencies(HABITS)` ;
- `heartbeat` est lu à l'acte par les trois balayages (`heartbeat_notification`,
  `heartbeat_wake_sweep`, `moment_sweep`, après la capacité `moments`), qui
  répondent `capability_disabled` sans rien servir. Le routeur reste ouvert :
  l'historique des notifications, les sujets refusés et les genres de moments
  sont des réglages que la personne doit pouvoir lire et changer capacité
  coupée.

Chaque lecture se fait par `is_capability_enabled` à l'appel, jamais par le
drapeau brut (décision 3). Le garde de câblage des routes lit la
déclaration et refuse un routeur gardé pour une capacité déclarée à l'acte.

## Amendement 2026-10-18 — un interrupteur retire ses outils du tour, dans les deux modes

Les outils d'une capacité coupée étaient retirés par le planificateur du mode
Pipeline seul (`merge_capability_exclusions`, sur son propre catalogue). La
boucle ReAct lisait le catalogue de la requête, qui ne le savait pas, liait les
outils d'une capacité que l'administrateur avait coupée — et `generate_image`
comme `generate_document`, qui ne lisaient que le drapeau de déploiement,
s'exécutaient. Le filtre est désormais appliqué une fois, là où la requête
construit son catalogue (`services/turn_catalogue.build_turn_catalogue`) : le
planificateur, la boucle ReAct, le classement du routeur et l'initiative lisent
tous cet instantané, un sous-agent délégué ne tient aucun outil qu'il n'offre
pas (il les prenait dans le registre global : ses outils de recherche par
défaut interrogeaient le web alors que la recherche web était coupée), un plan
tout fait de skill perd l'étape d'un outil que le tour retient (le validateur et
l'exécuteur résolvent les outils dans le registre global), et la fusion côté
planificateur a disparu. Les deux outils
lisent l'état effectif (`is_capability_enabled`) à leur entrée, comme le bac à
sable, la délégation et la recherche dans le journal. Les descriptions du
panneau disent « dans les deux modes d'exécution » plutôt que « du
planificateur ». Le menu des domaines du routeur suit le même instantané
(`analysis/domain_availability.py`) : un domaine dont un interrupteur peut retenir
les agents disparaît du menu quand le tour n'offre plus aucun de leurs outils —
le routeur le détectait encore et envoyait le planificateur vers un domaine sans
outil ; un domaine de connecteur reste au menu, sa réponse « aucun fournisseur
connecté » étant la vraie. Le planificateur ne rend la section de délégation
que si le tour offre `delegate_to_sub_agent_tool`, et le plan tout prêt d'une
skill juge chaque étape avec le résolveur canonique du tour
(`resolve_tool_manifest_named`), jamais par une égalité de noms plus stricte que
lui. Les interrupteurs du tableau de travail, des connexions, des
serveurs MCP et des skills ne nomment toujours aucun outil : ils ferment leurs
routes, comme leurs descriptions le disent, et la FAQ nomme désormais cette
exception au lieu de promettre que tout outil d'une capacité coupée disparaît.
Lus désormais à chaque tour, les interrupteurs le sont ensemble — une lecture
du cache, au plus une requête (`read_settings`) — et un interrupteur que
personne n'a jamais écrit est mis en cache comme absent : lu un par un, chacun
ouvrait sa session sur la base à chaque tour.

Côté web, la bulle n'offre plus de garder une nouvelle réponse quand `bookmarks`
est coupée (`bookmarkKeepingAvailable`, qui lit l'état publié dans
`capabilities`) : elle suivait le plafond de déploiement, et chaque clic était
refusé. Une réponse déjà gardée garde sa marque et peut être relâchée
(`bookmarksReadable`, le plafond), comme l'onglet des signets, puisque ces routes
restent ouvertes (décision 3 : l'interrupteur retire la capacité, jamais
l'archive). Les quatre lectures de l'état effectif d'une capacité côté web
(signets, radio, envoi par e-mail, connexions) passent par une seule règle,
`lib/capability-state.ts`.

## Amendement 2026-11-11 — une destination suit l'interrupteur, dans chacune de ses listes

Six destinations de l'en-tête sont montées par un plafond de déploiement et
fermées par un interrupteur dont la garde est sur le routeur : le monde, les
Outils, les SMS, les réunions, le tableau de travail et les espaces de
connaissances. L'en-tête en lisait quatre dans leur état effectif, épelés à la
main, et les réunions et les espaces sur leur plafond ; la liste
« Application » du monde 3D lisait les six plafonds, comme ses espaces de
travail (réunions, tableau, SMS) et les signaux privés qui y mènent. Coupée par
l'opérateur, une destination restait offerte et ouvrait sur un refus.

La liste a désormais UNE porte, `components/dashboard/offered-destinations.ts` :
chaque drapeau de la table y prend la réponse de la porte de sa capacité
(`worldAvailable`, `workbenchAvailable`, `smsAvailable`, `meetingsAvailable`,
`workboardAvailable`, `ragSpacesAvailable`, toutes sur `capabilityEnabled`).
L'objet est typé `Required` : un drapeau ajouté à la table sans sa porte échoue
au typage, il ne cache pas sa destination et ne relit pas un plafond. L'en-tête,
le menu du logo sur téléphone et le monde lisent cette liste ; les espaces de
travail et les signaux du monde lisent les mêmes portes. Un garde refuse tout
autre appelant du filtre de la table (`offered-destinations.guard.test.ts`) :
l'appel direct du monde compilait, avec des drapeaux de la bonne forme.

Le drapeau d'une capacité n'a plus qu'UN lecteur côté web, sa porte. Prouvée
dans un navigateur, la liste a montré son reste : interrupteur des réunions
coupé, la destination disparaissait et l'entrée « Enregistrer une réunion »
restait offerte. Le recensement qui a suivi a croisé chaque lecture d'un drapeau
de déploiement avec ce que l'interrupteur ferme côté serveur. Un lecteur pose
désormais l'une de DEUX questions, par la porte propre de sa capacité ou par la
porte commune `lib/capability-availability.ts` :

- **`capabilityAvailable`, pour un ACTE** — la capacité est-elle offerte
  maintenant, interrupteur compris. L'enregistreur de réunions, le « + » du
  composeur (réunion, import, documents des espaces, envoi de fichier), les
  sections de réglages des réunions, de l'avatar, du mode Live, des fils ouverts
  et des connexions, le bouton Live du chat, le partage de capacité, l'indice du
  portrait, les étapes de la liste de démarrage, les tickets, les messages de
  pairs et les propositions du hub des alertes, le bouton « Recalculer » des
  habitudes.
- **`capabilityMounted`, pour une ARCHIVE** — le déploiement la monte-t-il, quoi
  que dise l'interrupteur (décision 2). Les habitudes apprises, les
  autorisations du bac à sable, la clé d'un connecteur Live, l'historique des
  notifications proactives, les fichiers produits et les réponses gardées.

Un garde refuse toute autre lecture d'un drapeau de capacité, commentaires
compris, et lit la liste des drapeaux dans le registre du backend lui-même
(`lib/__tests__/capability-flags.guard.test.ts`). Rien n'est effacé : un
enregistrement en attente n'est plus offert tant que l'interrupteur est coupé,
et revient avec lui.

**Une section de réglages dont l'interrupteur ferme TOUTES les routes est
derrière sa capacité** (2026-11-11, suite). Un écran qui ne lit aucun drapeau
échappait au garde ci-dessus. Six routeurs portent `capability_dependencies` sur
le ROUTEUR, lectures comprises : les canaux, la psyché, les journaux, les
skills, les serveurs MCP personnels et les espaces de connaissances. Leurs
sections restaient listées et s'ouvraient sur un refus. Huit sections sont
concernées : les six de la personne, et deux d'administration (« skills
systèmes », « RAG système ») que l'administrateur ouvrait sur le refus de
l'interrupteur qu'il venait de couper.

La porte d'une section est son entrée dans l'index des réglages
(`SETTINGS_SEARCH_META`), pas un test dans le composant : le volet ne charge
RIEN qu'une porte décidable écarte (`SettingsPaneFrame`). Un seul verdict retire
donc la section du rail, de la vue d'ensemble, de la recherche, du choix des
raccourcis et du catalogue du monde, et un lien périmé dit que la section n'est
pas disponible sans envoyer une requête. Une section d'administration nomme sa
capacité EN PLUS du statut de super-utilisateur. La section des serveurs MCP de
l'instance reste : son routeur (`/mcp/admin-servers`) ne porte aucun
interrupteur.

Deux capacités n'ont pas de drapeau de déploiement publié par `/config` — la
psyché et les serveurs MCP personnels. La carte des capacités répond seule pour
elles (`CAPABILITY_CEILING` porte `null`) ; elle contient déjà le plafond du
déploiement, donc une instance qui ne monte pas la psyché n'en liste plus la
section. Un garde tient la table : chaque capacité de la porte commune est une
capacité du registre du backend, son drapeau est celui du registre, et une
entrée sans drapeau cesse d'être admise le jour où `/config` publie le sien. Le
raccourci « Ce que LIA comprend de toi » ne demande plus le portrait là où les
journaux ne sont pas offerts : la page lui passe le verdict qui liste la
section, il ne relit pas `/config` (chaque lecteur de la configuration émet sa
propre requête).

Prouvé : 32 mutants tués sur un miroir de l'arbre (porte, verdicts du hook,
huit portes de l'index, volet, raccourci et son câblage par la page,
bibliothèque de skills) ; dans un
navigateur, `smoke/settings-capability-doors.spec.ts` — les six sections
absentes du rail, un lien périmé qui dit l'absence, et AUCUNE requête vers l'un
des six routeurs — avec son témoin joué hors de l'arbre : rien de coupé, les
mêmes libellés sont dans le rail et chaque section montée envoie les requêtes
que le parcours guette. Une absence se constate sinon pour une mauvaise raison.

**Hors de l'index, personne ne demande une route que son interrupteur ferme**
(2026-11-12, suite). Le recensement de la veille nommait sept surfaces
restantes. Relu contre le code, il était inexact sur trois points, et les
corriger fait partie du lot :

- *le choix de la voix n'était pas un défaut* : `/voice/lia-voices` appartient à
  un routeur qu'aucun interrupteur ne ferme, à dessein — la page reste lisible
  et le serveur lui dit si LIA parle. Le balayage par préfixe l'avait confondu
  avec le routeur `/voice` de la dictée ;
- *le groupe téléphonie des connecteurs ne lit rien* : il OFFRE trois actes
  (valider une clé, activer, déconnecter) que le routeur refuse tous. Ce sont
  les deux sections voisines, « Mon téléphone » et « Appels récents », qui
  lisaient une route fermée — et le refus de l'interrupteur est un 403, là où
  leurs lecteurs ne reconnaissaient que le 404 d'un routeur non monté : sous
  l'interrupteur la première tournait sans fin et la seconde s'ouvrait sur une
  erreur ;
- *un cinquième lecteur manquait hors des réglages* : la bande « LIA est au
  téléphone » du chat, qui relit les appels à chaque tour de conversation.

Ce que le lot ferme :

- **Le chat.** La psyché du fil, les skills du menu « / » et la bande d'appel
  ne partent que là où leur capacité est offerte. `ChatWorkspace` tient la
  configuration de l'instance et passe le verdict (`capabilityAvailable`) à
  `ChatMessageList` et à `ActiveCallBanner` — deux propriétés OBLIGATOIRES : un
  second appelant ne peut pas l'oublier — et à `useSkills`. Les hooks
  `usePsyche`, `useSkills` et `useUserMCPServers` prennent un `enabled` que leur
  section de réglages n'a pas à passer : la porte de l'index la garde déjà.
- **Le formulaire d'une routine.** Les serveurs MCP personnels ne sont demandés
  que là où ils sont offerts (`useRoutinePreapprovableServers`) ; ceux de
  l'instance restent lus et proposés, leur routeur n'étant fermé par aucun
  interrupteur.
- **La carte de configuration MCP d'une réponse.** Ce lecteur-là n'était pas
  silencieux : il lit au clic et dit son échec. Il n'offre plus le formulaire
  là où l'instance a fermé les serveurs, ferme celui que l'interrupteur
  rattrape, et dit que l'action ne peut pas aboutir — APRÈS tout ce que la
  commande dit d'elle-même (enregistrée, en cours, expirée, incertaine). Tant
  que la configuration n'a pas répondu il n'offre rien et n'affirme rien.
- **Les réglages.** La génération d'images (ses options sont refusées sous
  l'interrupteur, et son commutateur personnel offrirait un générateur fermé),
  « Mon téléphone » et « Appels récents » passent derrière leur capacité.
  « Appels récents » reste une section `runtime` — vide tant qu'aucun appel n'a
  été passé, ce que l'index ne peut pas savoir — mais une porte `runtime` peut
  désormais NOMMER sa capacité : « vide aujourd'hui » est indécidable, « fermé
  par l'opérateur » ne l'est pas (ADR-172). Le groupe téléphonie des connecteurs
  est extrait (`TelephonyConnectorGroup`, sur le modèle du groupe Live) et
  décide de sa présence ; le connecteur reste en base et revient avec la
  capacité.
- **Le dock des raccourcis.** Il ne dessine que ce que le compte peut ouvrir, lu
  dans la configuration que la mise en page a déjà lue : ADR-277, D7 amendée.

La porte commune répond pour deux capacités de plus, sans drapeau publié comme
la psyché et les serveurs MCP : la génération d'images et la téléphonie
(`CAPABILITY_CEILING` porte quatre `null`). Les verdicts des sections ont UNE
lecture, `settingsCapabilityVerdicts`, que la page interroge sur sa propre
lecture de `/config` et le dock sur celle de la mise en page.

Le message d'absence d'une section disait « n'est peut-être pas disponible sur
ton compte ». Une section manque aussi parce que l'INSTANCE l'a fermée ou que
l'APPAREIL ne peut pas l'offrir (le retour haptique, ADR-172) : la phrase nomme
les trois, dans les six langues.

Prouvé : 55 mutants tués sur un miroir de l'arbre — la porte, les
verdicts de la page et ceux du dock, les portes de l'index, les cinq lecteurs,
la carte MCP et son message, le groupe téléphonie, la liste épinglée, le dock,
le sélecteur, l'appareil. Dans un navigateur,
`smoke/settings-capability-doors.spec.ts` : aucune des neuf sections dans le
rail, quatre liens périmés qui disent l'absence sans rien charger, aucune
requête vers un routeur fermé, une capacité coupée à la fois, le groupe
téléphonie, l'appareil sans API Vibration ; et
`smoke/capability-closed-readers.spec.ts` : le chat avec UNE capacité coupée à
la fois — les lecteurs des deux autres partent, celui de la capacité coupée non,
ce qui démasquerait un lecteur câblé sur la mauvaise capacité —, le formulaire
d'une routine, le dock et le compteur du sélecteur. Chaque absence a son
témoin sur la même page : rien de coupé, la requête part et la section est là.

**Ce que l'amendement ne fait pas.** Aucun garde mécanique ne relie encore un
module du web à la capacité dont il écrit une adresse : c'est ce garde, et non
un recensement de plus, qui aurait trouvé la bande d'appel. Mesuré le
2026-11-12, après ce lot : 120 modules écrivent une adresse sous l'un des 24
préfixes fermés vus ; 7 lisent une porte, 41 portent un `enabled`, 77 rien — la
plupart ne vivent que sous une page déjà gardée, et c'est ce que chacun aurait à
déclarer. `useTelephonyCallable`
lit la carte des capacités sans passer par la porte commune, et répond « non »
là où la porte répond « oui » (un serveur qui ne publie pas la carte). La
déconnexion du connecteur de téléphonie passe par le routeur que l'interrupteur
ferme : tant que la capacité est coupée, la personne ne peut pas retirer sa clé,
alors qu'une clé Live reste retirable (décision 2) ; la rendre retirable demande
de sortir cette route de la garde du routeur. La section des serveurs MCP
personnels suit `capabilities.mcp`, dont le plafond est `mcp_enabled`, alors que
leur routeur est monté par `mcp_user_enabled`, que `/config` ne publie pas : sur
un déploiement qui active l'un sans l'autre, la section s'ouvre sur un 404.
Enfin la porte lit `/config` au chargement : une page restée ouverte pendant que
l'opérateur coupe une capacité reçoit encore un refus à sa prochaine lecture.

## Amendement 2026-11-12 (suite) — la table des routes fermées, lue des deux côtés

Trois points que le paragraphe ci-dessus laissait écrits sous « ne fait pas ».

### La clé d'un connecteur est une archive : son retrait sort de l'interrupteur

`DELETE /telephony/connector` — qui efface aussi l'agent que LIA a créé chez le
fournisseur — était servi par le routeur que l'interrupteur ferme : capacité
coupée, la personne ne pouvait plus retirer sa clé, alors qu'une clé Live part
par la route des connecteurs, qu'aucun interrupteur ne ferme. Le domaine a
maintenant DEUX routeurs sous le même préfixe (`telephony/router.py`) :
`router` EST la capacité et garde sa garde ; `record_router` sert ce que
l'interrupteur doit laisser atteindre, et rien qui place un appel, en lise un
ou crée quoi que ce soit chez le fournisseur. Les deux restent montés par
`telephony_enabled`.

Le web distingue les deux moitiés du groupe des connecteurs : connecter une clé
est un ACTE (l'assistant de connexion crée un agent) et ne s'offre que là où la
téléphonie l'est ; une clé déjà stockée est une ARCHIVE, montrée avec son retrait
tant que le déploiement monte la téléphonie. Pour distinguer « coupée » de
« non montée », `/config` publie `telephony_enabled`, et la téléphonie prend sa
place parmi les capacités à drapeau de la porte commune. Un retrait qui échoue
le dit (il échouait sans un mot : c'est ce que la personne voyait sous
l'interrupteur).

### Un routeur monté par un drapeau qui n'est le plafond de personne

La carte des capacités dit « offerte » depuis le plafond ET l'interrupteur.
Elle ne peut pas dire qu'un routeur monté par un AUTRE drapeau est absent : les
serveurs MCP personnels (plafond `mcp_enabled`, les serveurs de l'instance ;
routeur monté par `mcp_user_enabled`) ouvraient leur section sur un 404 dès que
le déploiement activait le premier sans le second.

La règle est lue sur les routes elles-mêmes : tout drapeau qui monte une
opération fermée par une capacité est le plafond d'une capacité qui la ferme,
ou bien il est NOMMÉ (`router_flags`) et `/config` le publie. Sur 26 capacités
qui ferment des routes, un seul cas : `mcp`. La porte commune du web le lit
(`CAPABILITY_ROUTER_FLAGS`) : seul un « faux » explicite ferme, un serveur qui
ne publie pas le drapeau l'a précédé. Changer le plafond du registre aurait
ouvert les serveurs personnels sur tout déploiement qui les fermait par
`MCP_ENABLED=false` — le démonstrateur le fait.

### Le garde mécanique

Quelles routes un interrupteur ferme, l'API le sait — la garde est une
dépendance de chacune — et le web le devinait, préfixe par préfixe. Le
recensement par préfixe s'y est trompé (`/voice/lia-voices` n'était pas fermé).

`apps/api/tests/unit/capability_route_table.json` l'écrit UNE fois : chaque
opération servie sous une famille où un interrupteur en ferme au moins une,
avec les interrupteurs qui la ferment. `test_capability_route_table_guard.py`
tient le fichier égal à l'application, parcourue une fois, tous les drapeaux de
montage allumés, chaque dépendance suivie ; quel drapeau monte quel routeur est
lu là où c'est décidé (chaque `include_router` enregistré avec sa ligne, le
`if` qui l'entoure évalué drapeau par drapeau) — un rechargement par drapeau
disait la même chose en 67 secondes, sur 838 opérations, sans un écart. Mesuré :
838 opérations servies, 435 publiées sous 27 familles, 403 fermées.

`apps/web/src/lib/__tests__/capability-callers.guard.test.ts` résout contre
cette table chaque adresse qu'un module de `src/` écrit — littéral, constante
sur laquelle d'autres adresses sont bâties, table de chemins lue ailleurs
(l'adresse revient au module qui la LIT), trou d'un gabarit, méthode quand
l'appel la dit. Un couple (module, capacité) est FERMÉ quand aucune chaîne
d'imports ne mène d'une route de l'application au module sans rencontrer la
porte de cette capacité : un module qui la lit (`capabilityAvailable`, ou une
fonction de porte comme `workbenchAvailable`) ferme ce qu'il importe ; une
section de réglages n'est montée que si le verdict de sa porte tient (index et
verdicts lus tels quels) ; une mise en page qui rend ses pages dans une coquille
lisant la porte les ferme (`ROUTE_SHELLS`, déclaré et vérifié).
`capabilityMounted` n'est PAS une porte : il répond pour une archive que l'API
laisse ouverte, et une route que l'interrupteur ferme n'est pas derrière lui.

Mesuré le 2026-11-12 : 2 129 modules lus, 160 couples sur 141 modules et 26
capacités ; 93 fermés, 67 sans porte sur leur chemin. Ces 67 sont figés dans
`OPEN_CHAINS`, qui ne peut que décroître (un plafond l'y oblige) : un couple
nouveau fait échouer le garde, qui nomme la chaîne ; un couple fermé depuis doit
quitter la liste.

Ce que le garde ne voit pas, et ne prétend pas voir. Il raisonne par MODULE : un
module qui lit une porte ferme tout ce qu'il importe, que son code conditionne
ou non tel enfant. Un verdict passé vers le bas par un contexte ou une propriété
(la coquille des Outils donne `assists` à ses écrans, la page des réglages
`journalsOffered` au raccourci du portrait) et un acte qu'un seul clic envoie,
depuis un contrôle qu'un module voisin retire (le démarrage d'une session
Live), n'ont pas de porte sur leur propre chaîne : ils sont dans la liste, à
côté de lecteurs que personne n'avait fermés — le battement de présence posé
dans la mise en page racine, dont le refus est avalé ; la connexion d'une clé
Live, offerte sous l'interrupteur alors que ses routes refusent (lu dans la
table et le code, non exercé dans un navigateur). La liste dit « non prouvé »,
pas « défaut » : chaque ligne se lit avant de se corriger.

Prouvé : 33 mutants tués sur un miroir de l'arbre — dont la porte de la bande
d'appel retirée de `ChatWorkspace`, que le garde retrouve seul et nomme, une
section privée de sa porte dans l'index, la coquille des Outils qui ne lit plus
la sienne, une route que l'API ferme sous un module qui l'appelait déjà — et 11
en mémoire côté API. Dans un navigateur, `smoke/settings-capability-doors.spec.ts`
: une clé stockée reste visible et retirable sous l'interrupteur (la requête
part, la carte s'en va), aucune clé sur un déploiement qui ne monte pas la
téléphonie, aucune section des serveurs MCP personnels ni requête vers leur
routeur quand il n'est pas monté ; `smoke/capability-closed-readers.spec.ts` :
le formulaire d'une routine ne demande alors que les serveurs de l'instance.

**Ce que l'amendement ne fait pas.** Il ne ferme aucun des 67 couples : c'est
un lot par famille, à décider. Drapeau de déploiement coupé, une clé de
téléphonie n'est plus montrée, comme une clé Live aujourd'hui (la route
générique des connecteurs la retire toujours). Le numéro vérifié et l'historique
des appels restent sous l'interrupteur, ainsi que le webhook de fin d'appel (ce
qu'il advient d'un appel en cours au moment où l'opérateur coupe n'a pas été
mesuré). Le retrait de la clé appelle le fournisseur avec la session de la
requête encore ouverte (lu dans le code, non mesuré par `pg_stat_activity` ;
ADR-304). `route_enforced` reste faux pour `habits` et `tts`, dont des routes
portent pourtant la garde. Les onze constantes `API_ENDPOINTS.RAG_SPACES` ne
sont lues par aucun module de `src/`.

### Le même jour : quatre des points laissés ouverts sont fermés

**Les archives de la téléphonie sortent de l'interrupteur.** Le routeur sans
garde sert maintenant tout ce que la personne possède déjà, et rien d'autre :
le retrait de sa clé, la lecture de son numéro et son retrait, l'historique de
ses appels, et le webhook de fin d'appel — le fournisseur ne le livre qu'une
fois, et un appel placé avant la coupure doit se clore sur son résultat
(ADR-263). Restent la capacité, donc fermés : valider et activer une clé,
déclarer un numéro, le vérifier par un appel, confirmer le code, régler les
appels du propriétaire. Côté écran, « Mon téléphone » et « Appels récents »
suivent le drapeau de déploiement comme les habitudes apprises : sous
l'interrupteur, la première montre le numéro stocké en lecture seule avec son
retrait, et rien sans numéro (sa porte devient `runtime`).

**`route_enforced` dit ce qui est servi.** `habits` et `tts` portaient leur
garde sur des routes en déclarant le contraire, et le panneau d'administration
l'affichait. Les deux sont déclarés aux deux endroits, et le garde de la table
impose l'égalité dans les deux sens : une capacité est `route_enforced` si et
seulement si une route servie porte sa garde.

**Deux lecteurs que personne n'avait fermés.** Le battement de présence de la
mise en page racine n'est envoyé que là où l'instance apprend des habitudes (il
était refusé, sans un mot, sur chaque page de chaque personne connectée) ; il
ne demande la configuration que pour une personne connectée. La connexion d'une
clé Live n'est plus offerte sous l'interrupteur, où ses routes refusent ; la clé
stockée reste, avec son retrait. Trois lignes quittent `OPEN_CHAINS` (64).

**Onze constantes mortes retirées** : `API_ENDPOINTS.RAG_SPACES`, que le garde
avait trouvées sans lecteur.

Prouvé : mutants tués côté API et côté web (voir le compte rendu du lot) ; dans
un navigateur, le numéro stocké lisible et retirable sous l'interrupteur, sans
bouton d'appel ni d'enregistrement. Non prouvé : la clôture réelle d'un appel
dont le webhook arrive après la coupure — lue sur les routes servies, pas
exercée contre le fournisseur.

**Reste ouvert.** Les 64 couples, à décider famille par famille ; le retrait de
la clé qui appelle le fournisseur session ouverte (ADR-304) ; drapeau de
déploiement coupé, rien de la téléphonie n'est montré.
