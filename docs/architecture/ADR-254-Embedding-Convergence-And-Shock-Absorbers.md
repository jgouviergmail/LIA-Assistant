# ADR-254 — Trois mécanismes pour une convergence

**Statut** : Accepté — 2026-09-01
**Portée** : `infrastructure/llm/`, `infrastructure/rate_limiting/`, `infrastructure/startup/schedulers.py`, `infrastructure/utils/retry.py`
**Voisins** : [ADR-247](ADR-247-Self-Diagnostics-And-Answer-Resilience.md) (l'agent de diagnostic), [ADR-249](ADR-249-Ephemeral-Python-In-The-Existing-Sandbox.md) (le bac à sable Python)

## Le défaut, mesuré

Une heure de production, une instance à un à trois utilisateurs actifs :

| Fait | Valeur |
|---|---|
| Appels d'embedding | 24 |
| Échecs | **11 (46 %)** |
| Cause | `429 RESOURCE_EXHAUSTED`, quota **par minute** du modèle de base `gemini-embedding` |
| Tours de chat impliqués | **0** |
| Temps avant détection | ~30 minutes, à la lecture manuelle des logs |

Chaque échec dégradait quelque chose **en silence** : un contexte RAG absent
d'une réponse, un contexte de journaux absent, une mémoire jamais écrite, un
message jamais indexé, le scoring d'outils du routeur ignoré. Les deux du
milieu ne sont pas une réponse dégradée mais une **perte définitive** : rien ne
les rejoue plus tard.

**Le volume n'a jamais été le problème.** Un régime stable de quatre appels par
minute est passé sans une seule erreur. Ce qui casse, c'est la
**concentration** — et c'est une propriété du planificateur, pas du quota.

## La cause racine est arithmétique

Les périodes des tâches d'intervalle valaient 5, 5, 15, 30, 30 et 60 minutes —
**toutes multiples de cinq**. Toutes comptaient depuis le démarrage du
planificateur. Une seule portait un décalage, **aucune ne portait de `jitter`**.
L'alignement était donc permanent par construction : six tâches dans la même
seconde toutes les heures, chacune lançant un agent, chaque agent émettant
plusieurs embeddings.

## La décision : trois mécanismes, trois rôles distincts

Il serait tentant de n'en retenir qu'un. Aucun ne suffit, et les confondre
conduit à mal dimensionner les deux autres.

**Le `jitter` traite la cause.** Un décalage aléatoire de 15 % de la période,
plancher à 5 secondes — parce qu'un pourcentage d'une période courte s'arrondit
à zéro et laisserait alignées précisément les tâches qui se télescopent le plus.
Une seule exemption, écrite : l'exécuteur d'actions planifiées exécute des
actions **datées par l'utilisateur**, où décaler n'est pas étaler mais livrer en
retard.

**Le limiteur traite l'échelle.** Il ne change rien à l'incident observé — six
appels en une seconde passent sous n'importe quel plafond par minute — et c'est
justement pourquoi sa fenêtre est **courte** (8 appels / 10 s par défaut) : ce
qu'il faut plafonner est la concurrence instantanée. Il compose le limiteur
Redis distribué qui existait déjà plutôt que d'en ajouter un second : une seule
fenêtre glissante, un seul script Lua, un seul jeu de métriques.

**Le réessai traite le résidu.** Le 429 qui passe quand même, et le `500
INTERNAL` que le fournisseur renvoie aussi.

## Invariants

- **Le limiteur est un régulateur, jamais une porte, et CHAQUE tentative le
  consulte.** Prendre le créneau une seule fois hors de la boucle laisserait les
  reprises contourner la régulation — ajoutant de la charge exactement là où le
  fournisseur sature déjà, et transformant une rafale en tempête à mesure que
  les utilisateurs se multiplient. L'attente est bornée et **expire ouverte** : notre propre étranglement ne doit jamais être la raison
  pour laquelle une réponse perd sa mémoire. Il échoue également **ouvert** si
  Redis est injoignable — c'est une optimisation, pas une dépendance.
- **Le budget reste hors du chemin critique.** `user_message_embedding` partage
  son singleton avec le domaine mémoire : la même instance sert le tour d'un
  utilisateur et un lot de fond. Il n'y a donc **aucune instance** à qui donner
  un budget patient, et un drapeau par appel serait oublié un jour sur un site.
  Un profil unique et serré (0,4 s d'attente **par tentative**, une seule
  reprise) est la seule forme sûre — gardée par test, avec un plafond explicite.
- **Le réessai exige une FABRIQUE, pas un awaitable.** Une coroutine ne
  s'attend qu'une fois ; un point de couture tenant `client.aembed_query(...)`
  ne peut pas réessayer, la seconde attente lève au lieu de rappeler. C'est
  cette contrainte qui a dicté le refactor du goulot, et elle supprime au
  passage tout risque de coroutine jamais attendue.
- **Un seul classificateur, structurel d'abord.** Le réindexeur RAG en avait
  déjà un, et sa docstring dit pourquoi il lit le **code de statut** en
  remontant `__cause__` : *lire le texte d'un message, c'est ainsi qu'un
  changement de formulation chez le fournisseur transforme silencieusement un
  réessai en échec dur.* La version texte que ce chantier avait d'abord écrite a
  été supprimée au profit de la sienne. Le message reste lu **en repli**, et
  uniquement si aucun code n'existe dans la chaîne — c'est exactement ainsi que
  l'incident réel est arrivé. Quand un code EXISTE, il est final : sinon un
  nombre cité dans une phrase (« abandon après 429 tentatives ») renverserait le
  fait.
- **L'alerte lit les ISSUES, pas les appels.** Avec réessai, un échec récupéré
  vaut deux appels : alerter sur les appels ferait sonner des incidents qui se
  sont réparés seuls. Le compteur d'appels reste inchangé — c'est la vérité sur
  ce qu'a subi le fournisseur — et un second compteur répond à l'autre
  question : l'appelant a-t-il eu son vecteur ?

## Un faux négatif de garde, corrigé au passage

Deux agents (ADR-247, ADR-249) émettaient un avertissement à chaque
reconstruction du catalogue : leur domaine n'était pas déclaré. Un garde
existait pourtant — il parcourt le registre **vers l'extérieur** (pour chaque
domaine déclaré, ses agents), et ne peut donc structurellement pas voir un agent
dont le domaine n'existe pas. Le nouveau garde parcourt **dans l'autre sens**,
depuis les manifestes.

L'impact fonctionnel était **nul** : le seul consommateur de l'index par
domaine n'a aucun appelant en production. Le risque était latent, et la
correction diffère selon l'agent :

- `diagnostics_agent` devient **`devops_diagnostics_agent`**. La description du
  domaine `devops` couvre déjà mot pour mot « deployment diagnostics,
  production error analysis, infrastructure troubleshooting », et le manifeste
  de l'agent se réfère lui-même à `devops_agent` comme son pendant actif. Il
  hérite d'un `result_key` réel.
- `python_sandbox_agent` est déclaré **capacité de plateforme**, pas domaine de
  données. `DomainConfig` **exige** un `result_key` ; cet agent ne produit
  aucune charge de domaine, seulement un calcul. L'y forcer inventerait une
  référence `$steps.step_N.pythons` que rien ne peut produire. C'est la même
  échappatoire que les domaines MCP dynamiques, pour la même raison.

Ce garde est un test **CI**, délibérément pas un assert au démarrage : ici un
assert ferait planter la production le jour où quelqu'un ajoute un agent nommé
hors convention. Un build rouge protège autant, sans la panne.

## Ce que ce chantier a aussi supprimé

- `retry_with_backoff` était **écrit, documenté, testé et sans aucun
  appelant** ; il porte désormais le réessai des embeddings, et son décorateur
  délègue au même cœur fonctionnel — une politique de backoff, un seul endroit.
- Le classificateur du réindexeur RAG a cessé d'être une copie.
- `geo_lat` / `geo_lon` étaient liés au contexte de **chaque requête** — 1099
  lignes en une heure, dont 1054 en INFO, ce que le dépôt interdit pour une
  donnée de localisation. Nuance mesurée : deux couples distincts, deux villes,
  donc de la géo-IP au niveau ville et non un relevé d'appareil. Et **zéro
  consommateur** : le compteur par pays, les deux panneaux du tableau géo et
  jusqu'à la carte du monde lisent le pays et la ville. Supprimés.

## Deux angles morts de « Santé de la plateforme », fermés au passage

Le propriétaire a posé deux constats sur le panneau d'administration. Ni l'un
ni l'autre n'était un défaut d'affichage.

### L'incident d'embedding n'y était pas détecté

Il ne pouvait pas l'être : rien ne mesurait le **résultat** d'un embedding. Le
compteur existant, `embedding_api_calls_total`, compte ce qui touche le
fournisseur — la vérité sur le fournisseur, et le mauvais dénominateur pour une
alerte dès lors qu'on réessaie : un échec rattrapé gonfle le taux d'erreur
alors que rien n'a été perdu.

D'où `embedding_call_outcomes_total`, **une ligne par opération logique**,
réessais repliés, qui répond à la seule question sur laquelle un exploitant
agit : l'appelant a-t-il eu son vecteur ? Le check `embedding_failure_rate` et
l'alerte `EmbeddingOperationsFailing` la lisent, convergent sur une même clé de
corrélation, et un panneau la rend visible.

Le seuil d'avertissement est **plus bas** que celui des complétions, à dessein :
un embedding manqué est invisible pour l'utilisateur — la réponse part quand
même, sans sa mémoire.

S'y ajoute `embedding_shaper_outcomes_total`, qui dit ce que le régulateur a
fait de chaque tentative. C'est le signal qui manquera le jour où trois
utilisateurs actifs en deviennent trente : `expired` veut dire que le budget est
devenu trop petit, `unavailable` que Redis est tombé et que plus rien n'est
lissé. Deux actions opposées, donc deux libellés — jamais un booléen.

### « Insufficient evidence », à chaque fois

Le modèle n'était pas évasif, il était exact. Le dossier qu'on lui remettait
tenait en trois champs : un identifiant de check, un nombre, un détail court.
**Un nombre sans son seuil ne peut pas être jugé** : 46 est un incident pour un
check et anodin pour un autre, et rien ne disait lequel.

`evidence_for` complète donc le dossier avec ce qui est déjà en main quand un
check finit — l'unité, le verdict, les deux seuils franchis. L'enrichissement ne
coûte aucune requête et ne peut pas échouer. Ce qu'il ne va **pas** chercher est
tout aussi délibéré : un extrait de journaux est le travail de l'agent de
diagnostic (ADR-247), à la demande d'un exploitant — une tique de planificateur
ne doit pas se mettre à dépendre de Loki pour produire un diagnostic.

Le prompt a été durci en regard : dire ce qui manque et quel check le
trancherait, plutôt que « preuves insuffisantes ».

### Le diagnostic dans la langue de l'administrateur qui l'affiche

Le prompt finissait par *« Write in concise technical English »*. Tout le reste
de la page est localisé en six langues ; le seul texte écrit par le modèle ne
l'était pas.

La décision : **générer à l'écriture, pas traduire à la lecture**. Un diagnostic
est produit par une tique de planificateur, sans lecteur en vue ; le seul moyen
de satisfaire « la langue de l'admin qui affiche » sans un appel LLM à chaque
affichage est de l'écrire dans les langues que les administrateurs lisent
réellement. Avec un seul administrateur — le cas normal d'une instance
auto-hébergée — cela fait exactement un appel, dans la bonne langue.

Trois propriétés portent la compatibilité :

- la langue est **résolue paresseusement** : une tique dont le budget est déjà
  épuisé n'interroge pas la population d'administrateurs pour ne rien décider ;
- la première langue est aussi stockée **à plat**, donc tout lecteur existant
  retrouve les clés là où elles étaient, y compris une ligne écrite avant ce
  changement ;
- la **forme rendue ne dépend pas de la branche** qui l'a résolue : les
  métadonnées voyagent toujours, seuls les trois champs rédigés changent, et
  `by_language` ne quitte jamais le serveur — un lecteur n'a que faire des
  langues des autres, et les embarquer ferait grossir la charge utile à chaque
  administrateur ajouté.

## Ce que la revue de code a corrigé après coup

Quatre défauts trouvés en relisant l'implémentation, chacun invisible aux tests
qui existaient alors :

- **La chaîne de cause était rompue.** `MaxRetriesExceededError` garde la
  dernière erreur en attribut et était levée hors du `except` : `__cause__`
  s'arrêtait là. L'indexeur système, qui a son propre réessai et classe en
  remontant `__cause__` pour lire le code de statut, redevenait donc aveugle au
  429 qu'il avait justement appris à rattraper — il ne s'en sortait plus que par
  chance textuelle. Le `raise ... from last_exception` rétablit la chaîne, et
  les deux couches composent : la rapide absorbe un hoquet, la patiente survit à
  un fournisseur occupé pendant des minutes.
- **`"500"` était une sous-chaîne.** Le repli textuel classait « dépasse 1500
  jetons » comme transitoire : un échec permanent transformé en échec lent. Les
  codes sont désormais bornés sur des frontières de mot — et **dérivés** de la
  constante, où ils avaient déjà divergé (408 y figurait, pas dans la prose).
- **Le dénominateur des taux n'avait pas son `or vector(0)`.** Le numérateur
  l'avait, depuis l'incident du 2026-08-28 ; le dénominateur portait le même
  trou, et il s'ouvre exactement là où vit une instance auto-hébergée au repos :
  rien n'a encore été vectorisé, donc « aucune série », donc `unknown`, donc une
  plateforme saine affichée dégradée. Les trois requêtes de taux passent
  maintenant par une seule construction.
- **Le lisseur pouvait devenir sa propre charge** : un intervalle de sondage nul
  faisait tourner la boucle à vide contre Redis. Plancher posé.

## Conséquences

- Un embedding qui échoue coûte désormais au pire 1,8 s de plus (0,4 s
  d'attente de créneau par tentative, 1 s avant l'unique reprise) — et le plus souvent
  réussit. Le plafond est gardé par test parce que ce point de couture est sur
  le chemin critique d'un tour de chat.
- `EMBEDDING_RATE_LIMIT_MAX_CALLS=0` désactive entièrement le régulateur sans
  coûter un aller-retour Redis, et restaure le comportement antérieur.
- Le quota du fournisseur reste le vrai plafond à mesure que les utilisateurs
  se multiplient : ces trois mécanismes rendent l'échec gracieux, ils ne
  fabriquent pas de quota.
