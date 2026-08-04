# ADR-204 : expliquer l'incertitude vaut mieux que la noter

- **Statut** : accepté
- **Date** : 2026-08-04
- **Portée** : `domains/interests`, `domains/capabilities` (nouveau), carte des capacités frontend

## Contexte

Deux surfaces de LIA manipulent un chiffre que le lecteur ne voit pas : le
poids bayésien d'un centre d'intérêt, et l'état d'activation de chaque
sous-système. Toutes deux invitent naturellement à la même erreur — transformer
ce chiffre en score, en niveau, en pourcentage d'avancement. Cette erreur est
facile à commettre et coûteuse à défaire : elle crée une compétition que
personne n'a demandée, et elle remplace une information vraie (« pourquoi ce
sujet remonte ») par une information fausse (« vous êtes à 62 % »).

Deux constats de code, préalables aux décisions :

**Le taux de décroissance était divergent.** `get_top_weighted_interests` et
`calculate_effective_weight` portaient chacun leur propre valeur par défaut.
Deux surfaces pouvaient donc classer les mêmes intérêts différemment, sans
qu'aucune ne soit « la bonne ».

**L'état des capacités était résolu côté client.** La liste de démarrage
sondait sept sous-systèmes via sept hooks : douze requêtes au montage et douze
occasions pour deux réponses de se contredire sur la même question.

## Décision

**Le poids d'un intérêt s'explique, il ne se note pas.**
`GET /interests/{id}/explanation` publie ce qui compose le poids : le signal
d'origine, la dernière mention, la dernière notification, `prior_alpha` et
`prior_beta`, le taux de décroissance, le plancher, le nombre de jours depuis la
dernière mention, le poids de base et le poids effectif. Le lecteur peut donc
reconstituer le calcul. Aucun de ces champs n'est un rang ni un pourcentage.

**Le blocage garde son explication actuelle.** Un sujet bloqué l'est parce que
le lecteur l'a bloqué ; c'est déjà dit, et le redire autrement n'aurait rien
ajouté.

**Le taux de décroissance a une seule source.** Les deux fonctions lisent
`settings.interest_decay_rate_per_day` quand l'appelant n'impose rien, et
`INTEREST_DECAY_FLOOR` est extrait dans `core/constants.py`. Une valeur que
deux endroits appliquent doit venir d'un seul.

**Les capacités sont résolues en une passe, côté serveur.**
`GET /capabilities` renvoie une sonde par capacité — `available`, `active`,
`detail` — agrégées par `asyncio.gather`, **chaque sonde sur sa propre session**
(`AsyncSession` n'est pas sûre en concurrence). Une sonde qui échoue dégrade à
« pas prête » : une carte qui refuse de se dessiner parce qu'une table était
injoignable est pire qu'une carte avec un nœud éteint.

**Une capacité que l'instance a désactivée est ABSENTE, jamais grisée**
(gate-keeper, ADR-061). `live` et `total` décrivent les nœuds offerts, et rien
d'autre — ils ne peuvent donc pas contredire la liste.

**Rien de ce qui est publié n'est un niveau.** Un test l'énonce comme
contrainte de schéma : aucun champ nommé `level`, `xp`, `score`, `percent`,
`progress`, `rank`, `badge` ou `streak`. C'est une règle produit, pas une
préférence de nommage.

**Un compte affiché est exact, ou il n'existe pas** (ADR-185). `personality` et
`proactivity` sont des interrupteurs, pas des collections : ils ne portent aucun
décompte. `detail ?? 0` transformait cette absence en « Active — 0 élément(s) »,
qui se lit comme une capacité vide. Les deux surfaces passent par un seul
helper (`capability-state.ts`) qui dit « Active » tout court quand il n'y a rien
à compter.

## Conséquences

**La carte est une carte du ciel, et son dessin est décoratif.** Le SVG est
`aria-hidden` ; tout ce qui est atteignable est un `<Link>` avec un nom traduit
qui énonce l'état (« Mémoire — active, 412 éléments », « Voix — à configurer »).
Un `<circle>` avec un `onClick` aurait le même rendu et serait inutilisable sans
souris.

**La figure joint les capacités actives entre elles, en ordre ANGULAIRE.** Sa
forme est donc la configuration de ce compte, et personne d'autre n'a la même.
L'ordre angulaire n'est pas cosmétique : joindre dans l'ordre de placement
(anneau interne puis externe) produit un tracé qui se croise — mesuré au
navigateur, illisible.

**La scène garde sa nuit dans les deux thèmes.** Mesuré en thème clair : la
lueur des étoiles devenait une tache bleue et la poussière se lisait comme de la
saleté. Les jetons de la scène (`--capability-*`) sont donc indépendants du
thème, y compris l'anneau de focus — `--color-ring` s'inverse en quasi-noir en
thème clair, ce qui aurait donné un focus invisible sur fond sombre.

**Un téléphone, ou un lecteur qui demande l'immobilité, obtient la liste** —
mêmes données, même ordre, mêmes destinations. Sauf que demander l'immobilité
n'est pas demander moins d'information : le mouvement se tait, le graphique
reste.

**La carte n'a pas de créneau de navigation.** La barre d'en-tête est à sa
largeur limite avec six destinations ; la carte est un endroit qu'on visite, pas
un endroit où l'on vit. Sa porte est la barre d'accès rapide du tableau de bord,
visible sans défilement.

## Alternatives écartées

**Un pourcentage de complétion.** C'est le score déguisé : il classe des
capacités qui ne sont pas comparables (activer la voix n'est pas « la moitié »
d'activer les connecteurs) et il transforme un outil en liste de corvées.

**Un graphe de forces.** Non déterministe : le même compte dessinerait une carte
différente à chaque visite, ce qui empêche d'en garder une image mentale — et ne
laisse à un test que « quelque chose a bougé » comme oracle.

## Références

- ADR-061 — un sous-système désactivé est absent, jamais grisé
- ADR-185 — un compte affiché est exact, ou il n'existe pas
