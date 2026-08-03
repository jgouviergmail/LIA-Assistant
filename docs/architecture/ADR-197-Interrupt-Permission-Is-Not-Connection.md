# ADR-197 : être connecté à un service et être interrompu par lui sont deux décisions

**Statut**: ✅ IMPLEMENTED (2026-08-03)
**Date**: 2026-08-03
**Décideurs**: Équipe LIA
**Complète**: [ADR-085](ADR-085-Draft-Display-Registry.md) (assert de complétude au démarrage), [ADR-135](ADR-135-Heartbeat-Interest-Quality.md) (heartbeat et intérêts), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (ce qui est appliqué doit être publié)

## Contexte

Le panneau du heartbeat affichait chaque source comme **connectée ou non**. Il
n'offrait aucune décision : pour cesser de recevoir des notifications
proactives tirées des mails, la seule voie documentée était de **déconnecter le
connecteur mail** — ce qui retire aussi l'outil avec lequel on demande ses
mails. Un seul interrupteur pour deux questions sans rapport.

### Ce que la lecture du code établit

Trois faits, chacun vérifié :

- **La liste affichée était fausse.** Le frontend codait **sept** noms en dur
  quand `_compute_available_sources` en calculait **huit** : `health_signals`
  n'a jamais été affiché.
- **Onze sources peuvent déclencher une notification**, pas huit :
  l'agrégateur récupère aussi les anniversaires, les engagements et le conseil
  d'heure de départ.
- **Le point de coupure existe et il est unique.**
  `ContextAggregator.aggregate` n'a **qu'un seul appelant** — la tâche
  proactive. Filtrer là retire la source de la décision proactive **sans
  toucher aux outils de l'agent**.

## Décision

**La permission d'interrompre est une préférence distincte de la connexion.**

Onze interrupteurs, un par source, tous activés par défaut. Le filtrage a lieu
**avant la récupération**, si bien qu'une source refusée cesse aussi de coûter
un appel d'API — bénéfice secondaire, pas la raison.

**La préférence est stockée comme l'ensemble des REFUS**, pas des
autorisations. `NULL` signifie donc « jamais exprimé » : chaque compte existant
garde son comportement exact sans migration de données, et une source ajoutée
plus tard est active tant qu'elle n'est pas refusée — plutôt qu'absente en
silence de la liste blanche de tout le monde.

**Le vocabulaire est publié** (`all_sources`), en plus des refus et de la
disponibilité. Le client ne redéclare jamais une liste qu'il n'applique pas :
c'est exactement cette redéclaration qui avait perdu `health_signals`.

**Lecture tolérante, écriture stricte.** Une colonne JSONB éditée à la main ne
doit pas faire taire une source par accident : toute valeur inattendue est lue
comme « tout activé ». À l'écriture au contraire, une clé inconnue est refusée
en 422 — un refus silencieusement ignoré serait une préférence que
l'utilisateur croit avoir posée.

**Ce qui n'est pas une source ne se coupe pas.** Les fenêtres d'anti-redondance
et le contexte d'activité disent au décideur *ce qui a déjà été envoyé* ; les
couper ferait répéter l'assistant, pas se taire. Ils sont absents du registre,
donc jamais filtrés — et un test l'épingle.

**Un interrupteur qui ne peut rien produire le dit.** `fetch_departure_advice`
ouvre sur `if not calendar_events: return None` : refuser `calendar` neutralise
`departure`, qui reste allumé et ne produit plus rien, sans que rien ne
l'explique. La dépendance est donc **déclarée**
(`HEARTBEAT_SOURCE_DEPENDENCIES`), vérifiée au démarrage dans les deux sens, et
**publiée** au panneau (`source_dependencies`), qui affiche « nécessite X » sur
l'interrupteur concerné — application directe d'ADR-184 : ce qu'un système
applique, son producteur doit pouvoir le lire.

`journals` et `memories` sont volontairement absents de cette table : ils
consomment eux aussi la première passe, mais à travers une requête qui retombe
sur une formulation générique — ils se dégradent, ils ne se taisent pas.

La table n'est pas signalée quand la source dépendante est refusée elle aussi :
le lecteur l'a éteinte, il n'y a plus de surprise à expliquer et le dire
ajouterait du bruit sur une décision déjà prise.

## Conséquences

Le registre et son ordre d'affichage sont confrontés **dans les deux sens** au
démarrage (ADR-085) : une clé présente d'un seul côté masquerait un
interrupteur que le backend honore, ou en publierait un qui ne fait rien.

**L'agrégateur reste sous son plafond gelé** (697 / 705 SLOC logiques) : la
table de spécifications a remplacé la liste de noms parallèle au `gather`, et
la seconde passe est devenue une méthode à part — extraction imposée par le
ratchet de complexité, que les trois gardes de source faisaient franchir à
`aggregate` (CC 17 → 8). Le plafond n'a pas été relevé.

**Deux pièges évités à l'écriture**, l'un et l'autre mesurés : une coroutine
construite puis non attendue fuit et avertit — les sources refusées sont donc
écartées **avant** que la leur ne soit créée ; et la note « non connecté »
placée dans le `<label>` devenait une partie du **nom accessible** du contrôle
(« Tâches Non connecté »), le faisant lire comme un état de l'interrupteur.
Elle passe par `aria-describedby`.

**Interface**. Une source non connectée reste **autorisée** : l'utilisateur n'a
rien décidé à son sujet, et l'afficher éteinte énoncerait un choix qu'il n'a
pas fait — puis exigerait un second passage ici après connexion. Pendant une
écriture, les interrupteurs portent `aria-disabled` et le gestionnaire garde :
`disabled` retirerait du parcours de tabulation le contrôle qui a le focus.

## Alternatives écartées

**Stocker la liste des sources autorisées.** Impose de migrer toutes les lignes
existantes, et fait qu'une source ajoutée plus tard est muette pour tout le
monde jusqu'à ce que chacun la réactive — l'inverse du comportement attendu.

**Une colonne booléenne par source.** Onze colonnes, une migration par source
ajoutée, et 542 → 553 SLOC sur un modèle `users` déjà proche de son plafond.

**Filtrer après la récupération.** Plus simple d'une ligne, mais la source
serait toujours interrogée : le quota dépensé, l'appel visible dans le journal
d'audit du fournisseur, et l'utilisateur en droit de demander pourquoi.
