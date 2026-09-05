# ADR-263 — Lot 4 : ce que le lot 3 devait livrer et n'a pas livré

État : plan écrit le 2026-09-04 après confrontation **ligne à ligne** de la
spécification §4.6 / §8 avec le code livré, et mesure sur l'instance réelle.

Ce plan ne contient aucune étape git : le propriétaire commite.

---

## 0. Ce que la mesure dit

### 0.1 Le tableau 28 affiche zéro — et c'est exact

Les trois séries existent dans Prometheus (`lia_effect_claims_total`,
`lia_effect_outcomes_total`, `lia_effect_claimed_orphans`) et les requêtes du
tableau répondent `0`, pas « No data » : le `or vector(0)` fait son travail.
Le tableau est donc **techniquement sain et fonctionnellement vide**, parce
qu'aucun effet n'a été compté depuis que les compteurs existent.

### 0.2 Pourquoi il est vide : le registre ne voit presque rien

Volume réel de l'instance, 30 jours (`agent_tool_invocations_total`) :

```
7  get_emails        4  get_events        3  get_places
1  get_weather_forecast                   0  send_email
```

**15 appels d'outils, 100 % des LECTURES.** Le registre, borné aux effets, est
structurellement vide sur cet usage. Ce n'est pas un défaut d'implémentation :
la spec dit « une ligne par **effet** » et §8 le nomme « la source des faits
d'**effet** ». Mais l'attente exprimée — *transparence sur les traitements,
vérification, garantie d'intégrité de la traçabilité* — est plus large que ce
périmètre. **C'est un arbitrage, pas un bug** ; il est posé en §2.

### 0.3 Douze manquements réels par rapport à la spec

Chacun vérifié dans le code, pas déduit.

| # | Promis | Mesuré |
|---|---|---|
| G1 | Registre lisible **exportable par l'utilisateur** sur une période, Markdown **et CSV** (§4.6, §8.2) | **Absent** : aucun endpoint, aucun bouton |
| G2 | Lignes portant la **référence fournisseur**, l'**autorité** (brouillon confirmé / carte / politique) et le **lien vers la conversation** ; **en-tête par jour** ; **fuseau d'affichage** de l'utilisateur | **Absent** : rendu plat, horodatage ISO, ni autorité ni référence |
| G3 | Page « Journal des actions » : filtres **période / outil** / statut | Statut seulement |
| G4 | Admin : extraction lisible d'**un, plusieurs ou tous** les utilisateurs **sur une période** | Vue JSON masquée mono-utilisateur ; **aucune extraction** |
| G5 | Technique : filtres **utilisateur(s)** et **run_id** | Absents de l'endpoint (le dépôt les supporte, ils ne sont pas exposés) |
| G6 | Technique : **`schema.json`** (dictionnaire de données) | **Absent** |
| G7 | Technique : **streamé depuis un curseur serveur, jamais chargé en mémoire** | **Chargé en mémoire**, plafonné — la classe de bug que la spec nomme |
| G8 | Technique : livraison **ADR-228** + **asynchrone au-delà d'un seuil** | Synchrone, aucune surface admin |
| G9 | §8.1 : les effets `SUCCEEDED` du run dans une **directive versionnée** au nœud de réponse — « l'email est parti » devient impossible sans ligne | **Absent** : je n'ai livré que la métadonnée d'affichage |
| G10 | §8.3 : panneau **approbations vs effets** dans `08-hitl.json` (l'écart doit valoir zéro) | **Absent** |
| G11 | §8.3 : `claim_duration_seconds` (histogramme) et `replays_avoided_total` | **Absents** |
| G12 | §8.3 : requête nommée ADR-247 « effets du dernier run » | **Absent** |

### 0.4 Ce que cet écart dit du processus (et ce qui change)

Mes tests validaient chaque pièce isolément et la chaîne sous un scope
**synthétique**. Aucun ne demandait : *« un tour réel produit-il quelque chose
de visible ? »*. C'est exactement ce qui a laissé passer le défaut du `run_id`
(effet classé sous le thread, carte introuvable), trouvé par l'usage et non par
la suite. Deux règles en découlent, appliquées dans le plan de test §4 :

1. **Un test de bout en bout part du point d'entrée RÉEL** (le nœud de réponse
   avec un vrai `config`), jamais d'un scope fabriqué à la main.
2. **Une surface livrée est vérifiée NON VIDE** après un tour simulé : un
   panneau, une page ou un export qui ne peut rien montrer est un livrable qui
   n'a pas été essayé.

---

## 1. Y a-t-il un quatrième lot ?

Le plan approuvé comptait les lots 0, 1, 2, 3 et 3b — **3b était le dernier**,
et il est **incomplet** (G1 à G8). Le présent lot 4 n'ajoute donc pas un
périmètre neuf : il **termine** 3b et les trois oublis du 3a (G9, G10, G11,
G12), plus l'arbitrage §2 s'il est retenu.

---

## 2. L'arbitrage à prendre : quel périmètre pour la traçabilité ?

Le registre répond aujourd'hui à « **qu'a-t-elle FAIT ?** ». La question posée
est « **qu'a-t-elle TRAITÉ ?** ». Trois options, avec leur coût mesuré.

| | Option A — périmètre effets (spec) | Option B — une ligne par appel d'outil | Option C — un résumé de consultation par tour |
|---|---|---|---|
| **Contenu** | mutations, brouillons confirmés | + toutes les lectures | + « quelles capacités consultées, combien de fois » |
| **Coût par lecture** | **0** (mesuré : 0,64 µs, zéro session) | 1 écriture (≈ 1 ms) × N appels | 1 écriture par TOUR |
| **Volume 30 j (instance)** | 1 ligne | ~15 lignes | ~10 lignes |
| **Surface PII** | libellé chiffré d'une action | **arguments de lecture** : « a cherché *Marie* » | aucune (compteurs par capacité) |
| **Répond à « qu'a-t-elle traité ? »** | non | oui, finement | oui, au niveau du tour |
| **Garantie « une approbation, une exécution »** | oui | inchangée | inchangée |

### Arbitrage rendu (propriétaire, 2026-09-04)

> « Il faut deux listes distinctes ACTIONS et TRAITEMENTS. »

Retenu, et meilleur que mes trois options : elles cherchaient toutes à décider
ce qu'on met DANS le registre d'effets. La réponse est de ne pas y toucher.

| | **ACTIONS** (`agent_effects`, livré) | **TRAITEMENTS** (`agent_treatments`, lot 4a) |
|---|---|---|
| Répond à | qu'a-t-elle **fait** ? | qu'a-t-elle **consulté** pour répondre ? |
| Une ligne = | un effet sur le monde | un appel de capacité |
| Cycle de vie | réclamé AVANT, clos depuis un résultat explicite, jeton propriétaire | **observé**, écrit après coup — rien à réclamer, rien à rejouer |
| Contenu | libellé chiffré, résultat chiffré, référence fournisseur | capacité, issue, durée — **aucun argument, aucun libellé nommant quelqu'un** |
| Garantie | une approbation = une exécution | exhaustivité du tour |

**Pourquoi aucun argument dans les traitements.** « A envoyé un e-mail à Marie »
consigne un ACTE que l'utilisateur a demandé. « A cherché les e-mails de
Marie » révèle une RECHERCHE qu'il n'a jamais demandé de consigner : même
donnée nominative, intrusion supérieure. La liste des traitements dit *quelle
capacité, quand, avec quelle issue* — cela suffit à vérifier et à recouper, et
cela ne crée aucune surface PII nouvelle.

**Pourquoi le chemin de lecture reste gratuit.** La propriété mesurée du
portail — 0,64 µs et **zéro session** sur une lecture — est ce qui rend la
porte acceptable sur le chemin chaud. Écrire une ligne par appel la
détruirait. Donc : **collecte en mémoire pendant le tour** (une liste dans un
ContextVar, ajoutée par la porte au moment du `PASS_THROUGH`), **une seule
écriture par lot en fin de tour**, au même endroit que la lecture des effets.
Le coût passe de « N écritures » à « une », et le chemin d'appel ne touche
jamais la base.

**Ordre d'exécution** (délégué au réalisateur, arbitré ainsi) : le modèle
d'abord, sinon les exports seraient écrits deux fois.

---

## 2 bis. Conception du lot 4a, mesurée avant d'écrire

Six hypothèses portaient la conception. Chacune a été mise à l'épreuve ; deux
l'ont renversée.

### H1 — le portail voit-il vraiment toutes les lectures ? **OUI, et plus que prévu**

`decide_effect` : `if policy is None or policy in {"read", "sandboxed", "draft"}
→ PASS_THROUGH`. Le portail voit donc les lectures, les outils **sans
manifeste** (23), les constructeurs de brouillon et le bac à sable. Un seul
point de collecte suffit — il n'y a pas de chemin d'appel à rattraper.

**Correction d'un chiffre que j'avais annoncé** : `LEDGERED_POLICIES` vaut
`{reversible, artefact, confirm}`. Ce sont **14** outils natifs qui écrivent
une ligne d'action (11 `reversible` + 3 `artefact`), pas 16 : `sandboxed`
traverse délibérément (aucun effet externe, et un tour ReAct l'appelle assez
souvent pour que ce soit du bruit).

### H2 — une collecte en mémoire survit-elle aux tâches asyncio ? **MESURÉ, et c'est ce qui décide de la conception**

Simulation des deux formes réelles (pipeline = `asyncio.gather`, ReAct =
`await` séquentiel) :

```
liste vivante partagée   : 6 traitements sur 6 collectés
ContextVar.set() dans gather      → PERDU par le parent
ContextVar.set() dans un await    → conservé
```

Un collecteur bâti sur `ContextVar.set()` **marcherait en ReAct et perdrait
silencieusement le pipeline** : un registre qui ment par omission, sur un mode
seulement. La conception retenue est donc : **le parent publie une LISTE
VIVANTE**, les enfants n'y font qu'`append`.

**Et cette simulation-là était synthétique** — exactement le défaut de méthode
qui a produit le bug du `run_id` : vérifier le MÉCANISME au lieu du CHEMIN.
Refaite sur un **vrai `StateGraph` compilé**, avec un nœud en éventail
(`asyncio.gather`, comme le `parallel_executor`), un nœud séquentiel (comme la
boucle ReAct), un nœud qui lève et une annulation :

```
1  graphe réel, éventail + séquentiel  -> 6 traitements sur 6
2  le tour LÈVE                        -> la liste garde ce qui précédait
3  le tour est ANNULÉ                  -> la liste garde ce qui précédait
4  aucun collecteur publié             -> les outils tournent, rien ne casse
```

### H3 — où écrire pour que TOUS les tours soient couverts ? **Un gestionnaire de contexte, pas le bloc d'archivage**

| Point candidat | Tour normal | Interruption HITL | Tour qui plante |
|---|---|---|---|
| Bloc d'archivage (`api/service.py:1091`) | oui | oui | **non** |
| `async with tracker:` (`:759`) — englobe le tour | oui | oui | **oui** (`__aexit__` s'exécute sur exception) |

Retenu : un `async with treatment_recorder(...)` **à côté du `tracker`**. Le
`__aexit__` d'un gestionnaire de contexte s'exécute aussi sur exception, donc
l'exhaustivité est acquise **par construction** plutôt que par vigilance.

**Correction d'une affirmation que j'avais posée sans la mesurer.** J'avais
écrit qu'un `await` nu dans `__aexit__` perd l'écriture sur annulation. Mesuré,
c'est faux dans le cas courant et vrai dans un autre :

```
UNE annulation (un client qui se déconnecte)      naïf: écrit   bouclier: écrit
annulation RE-DÉLIVRÉE pendant le nettoyage       naïf: RIEN    bouclier: écrit
(arrêt de conteneur, timeout englobant)
```

Le bouclier (`asyncio.shield`) est donc nécessaire — mais pour une raison plus
étroite que je ne l'avais dit : l'arrêt du conteneur, cas ordinaire sur un
Raspberry Pi qui redémarre.
Et comme le collecteur est publié par le PARENT, il n'est plus nécessaire de
toucher `LiaRuntimeContext` (frozen) ni son constructeur : le module des
traitements possède tout, et le fichier gelé ne prend qu'**une ligne**.

### H4 — une table neuve est-elle imposée, ou un discriminant suffit-il ? **Table neuve**

`agent_effects` porte `UNIQUE(thread_id, idempotency_key)` : une lecture n'a
pas de clé d'idempotence, et deux lectures du même outil dans un tour
entreraient en collision sans clé synthétique. `claim_token`, `status`,
`approval_kind` n'ont aucun sens pour une consultation. Un discriminant
obligerait toute requête existante à filtrer — et **la première qui l'oublie
fait mentir un compteur affiché**. Deux identités, deux tables.

### H5 — une table non déclarée passe-t-elle en CI ? **NON, et c'est voulu**

`test_every_metadata_table_is_classified` refuse toute table sans règle dans
`user_data_map`. La rétention, l'export de compte et la suppression sont donc
**forcés** par la garde, pas confiés à ma mémoire.

### H6 — les deux listes se recouvrent-elles ? **Non, par décision**

La liste des traitements enregistre **exactement le chemin `PASS_THROUGH`** :
lectures, constructeurs de brouillon, bac à sable, outils sans manifeste. Les
actions sont dans l'autre liste. Aucun recouvrement, donc aucun double compte,
donc deux totaux qu'on peut lire côte à côte sans les additionner par erreur.

### Ce que porte une ligne de traitement — et ce qu'elle ne porte pas

| Porte | Ne porte pas | Pourquoi |
|---|---|---|
| capacité, politique, mode, source | **arguments, libellé** | « a cherché les e-mails de Marie » révèle une recherche jamais demandée à consigner |
| issue (ok / échec), durée | résultat, nombre de résultats | le contenu appartient au tour, pas au registre |
| run, thread, horodatage | référence fournisseur | une consultation n'en produit pas |

Coût sur le chemin chaud : deux `perf_counter` et un `append` — la mesure
actuelle est 0,64 µs, l'ajout est du même ordre, et **aucune session de base
n'est ouverte pendant l'appel**. L'écriture est un seul lot en fin de tour.
La collecte ne peut jamais faire échouer un outil : tout le bloc est protégé.

### Volume et rétention

Row étroite (≈ 100 octets, aucun texte libre au-delà du nom d'outil).
À 100 appels/jour/utilisateur : ≈ 3,6 Mo/an. Même rétention que les actions —
jusqu'à la suppression du compte (CASCADE), déclarée dans `user_data_map`.
Pas de job de purge : un sous-système de plus pour 3,6 Mo serait
disproportionné, et le dire est plus honnête que de le construire.

### Le libellé d'une consultation : réutiliser, ne pas inventer

Trou trouvé en revue à froid : une liste qui affiche `get_emails_tool` est un
journal de logs, pas une surface utilisateur. J'allais écrire une table de
libellés — **450 formulations**.

Mesure : `execution.steps` porte déjà **97 clés par outil, en 6 langues**
(`get_contacts` → « Recherche de contacts… »), celles que la trace ⚙ résout.
Sur les **114 outils** qui traversent le portail, **71 sont déjà formulés**.

Décision : la liste des traitements résout `execution.steps.<outil>` — donc la
trace et le journal **disent la même chose de la même capacité**, ce qu'aucune
table parallèle n'aurait garanti. Les 43 manquants (dont les sous-outils du
navigateur et les lecteurs hérités, inatteignables) reçoivent une formulation
quand ils ont un manifeste, une **garde de complétude** shrink-only pour les
autres, et un repli générique — la page ne peut jamais afficher un nom
technique.

### Volume, re-dérivé honnêtement

J'avais annoncé ≈ 100 octets par ligne. En comptant vraiment : 3 UUID (48 o),
`tool_name` (~30), politique/mode/source/issue (~36), durée et horodatage (12),
plus l'en-tête de ligne PostgreSQL et **deux index** → **≈ 250 octets**.
À 100 appels/jour/utilisateur : **≈ 9 Mo/an**, pas 3,6. À 500 appels/jour :
45 Mo/an.

**Arbitrage rendu (propriétaire, 2026-09-04)** : *« pour l'instant on garde
tout et on mettra un mécanisme de purge si nécessaire par la suite. En effet on
supprime tout à la suppression du compte. Avoir des métriques suivies dans
Grafana pour supervision et alerting. »*

C'est la bonne façon de ne pas construire une chose : **ne pas bâtir la purge,
mais instrumenter la croissance**, pour que le jour où la question se pose elle
se tranche sur un chiffre et non sur une intuition. Deux jauges adossées à la
base, sur le patron déjà en place (`lifetime_metrics`, comme la jauge
d'orphelins), rafraîchies par la boucle périodique existante :

| Jauge | Ce qu'elle répond |
|---|---|
| `lia_ledger_rows{table}` | combien de lignes portent les deux registres |
| `lia_ledger_bytes{table}` | ce qu'ils **occupent réellement** (`pg_total_relation_size`, index compris) — le seul chiffre qui compte sur un disque de Raspberry Pi |

Un libellé borné (`table` ∈ {`agent_effects`, `agent_treatments`}), deux
panneaux sur le tableau 28, et **une alerte de seuil** (`Settings`, rendue par
environnement comme les autres) dont le runbook dit explicitement que la purge
n'est pas construite et comment décider de la construire. Rétention par
défaut : jusqu'à la suppression du compte (CASCADE), pour les deux tables.

### Ce que l'interface montre

La page « Journal des actions » devient deux listes sous un sélecteur
(**Actions** / **Traitements**), chacune avec ses filtres, son total exact et
son export. Deux totaux qu'on ne peut pas confondre, jamais additionnés.


---

## 3. Plan d'actions consolidé

### Lot 4a — le socle des TRAITEMENTS (arbitrage §2)

0. `agent_treatments` : table légère (run_id, thread_id, user_id, tool_name,
   mutation_policy, outcome, duration_ms, occurred_at), **sans** argument ni
   libellé, collectée en mémoire par la porte et écrite **une fois par tour**.
   Mêmes règles de vie que le registre d'actions : rétention jusqu'à la
   suppression du compte (CASCADE), déclarée dans `user_data_map`,
   `account_deletion_service` et l'export de compte.
1. **Supervision de la croissance** (arbitrage §2 bis) : `lia_ledger_rows` et
   `lia_ledger_bytes` par table, deux panneaux sur le tableau 28, une alerte de
   seuil et son runbook — la purge n'est pas construite, sa nécessité devient
   mesurable.

### Lot 4b — le registre lisible SORT, pour les DEUX listes (G1, G2, G3)

1. **Un rendu, deux formats, un seul constructeur.** `effects/readable_export.py` :
   `render_markdown(rows, language, timezone)` et `render_csv(rows, language,
   timezone)` partagent une seule projection de ligne (`readable_row`), pour que
   les deux formats ne puissent pas diverger. La ligne porte enfin ce que la
   spec demande : horodatage **dans le fuseau de l'utilisateur**, source,
   autorité (`approval_kind` ou politique), libellé, résultat (référence
   fournisseur, motif d'échec), lien de conversation (`thread_id`).
   **En-tête par jour** et **total exact** par période.
   `account_export` réutilise `render_markdown` — un seul rendu, pas deux.
2. **Endpoint utilisateur** `GET /effects/export?format=markdown|csv&since=&until=&tool=&status=`
   → fichier téléchargeable, portée utilisateur, plafond publié dans l'en-tête.
3. **Page** : filtres période (préréglages 7/30/90 jours + dates) et outil, et
   un bouton « Exporter » suivant `SectionToolbar` (CTA solide, ADR-207), les
   deux formats derrière un menu.

### Lot 4c — l'administrateur extrait (G4, G5, G6, G7, G8)

4. **Registre lisible admin** : `GET /admin/effects/export/readable` — période,
   `user_ids` (aucun = tous), format, **masqué par défaut**, `unmask=true`
   journalisé dans `AdminAuditLog` (déjà en place, étendu à la période et au
   nombre d'utilisateurs).
5. **Registre technique** : `user_ids` et `run_id` exposés ; **`schema.json`**
   généré depuis les mêmes constantes que les lignes (jamais retapé) ;
   **streaming réel** — `StreamingResponse` sur un générateur qui pagine par
   curseur (`claimed_at, id`), donc mémoire bornée quel que soit le volume ;
   au-delà du seuil `Settings`, bascule sur le **job** (patron `account_export` :
   `pending → running → ready`, expiration, téléchargement).
6. **Surface admin** (ADR-228) : les deux extractions au même endroit que les
   autres exports administrateur.

### Lot 4d — la preuve remonte au modèle et à l'opérateur (G9 à G12)

7. **Directive versionnée** : les effets `SUCCEEDED` du run injectés dans le
   nœud de réponse comme `plan_blockers` le fait déjà (prompt versionné, jamais
   de texte en dur), pour qu'une phrase « c'est envoyé » sans ligne devienne
   impossible à produire honnêtement.
8. **Panneau `08-hitl.json`** : approbations vs effets `SUCCEEDED`, l'écart doit
   valoir zéro.
9. **Deux métriques** : `lia_effect_claim_duration_seconds` (histogramme, la
   latence que la porte ajoute) et `lia_effect_replays_avoided_total` (chaque
   rejeu évité est une double mutation qui n'a pas eu lieu) — avec leurs
   panneaux, sinon le ratchet refuse.
10. **Requête nommée ADR-247** « effets du dernier run », pour que « tu l'as
    vraiment envoyé ? » se réponde depuis le registre.

### Ordre retenu

**4a → 4b → 4c → 4d.** Le modèle d'abord : les surfaces d'export doivent
couvrir les deux listes dès leur écriture, sinon elles seraient reprises
intégralement au lot suivant.

---

## 4. Plan de test (enrichi en implémentation, déroulé en revue)

**La règle nouvelle, née du défaut du `run_id`** : chaque surface est prouvée
**non vide** au bout d'un tour simulé depuis le point d'entrée réel.

| Famille | Ce qui doit rougir |
|---|---|
| Bout en bout réel | un tour passant par le nœud de réponse avec un `config` sans `run_id` (le cas de la reprise HITL) ne produit pas de ligne trouvable |
| Non-vacuité | après un tour simulé : la page journal, l'export utilisateur, l'export admin et le panneau debug rendent **au moins une ligne** |
| Rendu lisible | deux formats divergent ; un horodatage hors fuseau de l'utilisateur ; un en-tête de jour manquant ; un total qui n'est pas exact |
| Export admin | un non-superutilisateur passe ; un dévoilement non journalisé ; une période ignorée ; `user_ids` vide qui ne prend pas tous les comptes |
| Technique | `schema.json` désynchronisé des colonnes ; une ligne chargée en mémoire (test sur curseur : mémoire bornée sur 50 000 lignes) ; un `run_id` filtré à tort |
| Directive | une réponse affirmant un envoi sans ligne `SUCCEEDED` ; une directive présente alors qu'aucun effet n'a eu lieu |
| Observabilité | un panneau sans producteur ; une métrique sans panneau ; promtool sur les nouvelles règles |
| Non-régression | `task lint` · TU complets · `tests/agents` · intégration · front + couverture · ratchets · i18n ×6 |

### Cas propres au registre des TRAITEMENTS (4a)

| Ce qui doit rougir | Pourquoi il faut un test |
|---|---|
| un appel de lecture qui ne laisse aucune ligne | la collecte a manqué le chemin `PASS_THROUGH` |
| une ligne écrite pour un effet déjà dans le registre d'actions | les deux listes se recouvrent, donc les deux totaux mentent |
| les traitements du **pipeline** perdus alors que ReAct passe | la classe de défaut mesurée : un collecteur `ContextVar` qui ne traverse pas `asyncio.gather` |
| un tour qui LÈVE et n'écrit rien | `__aexit__` doit s'exécuter sur exception, sinon l'exhaustivité repose sur la vigilance |
| une interruption HITL qui perd ses consultations | le tour a bien consulté avant de s'interrompre |
| un argument, un libellé ou un nom de personne dans une ligne | la surface PII que la conception refuse ; garde par liste blanche de colonnes, comme l'export technique |
| une collecte qui fait échouer un outil | la collecte est best-effort ; un registre ne casse jamais ce qu'il observe |
| une session de base ouverte pendant l'appel d'outil | la propriété « zéro session sur une lecture » est ce qui rend la porte acceptable |
| deux appels du même outil dans un tour fusionnés en une ligne | une consultation n'est pas idempotente : deux appels, deux lignes |
| un tour sans aucun appel qui écrit un lot vide | une écriture pour rien, à chaque tour de conversation |
| un sous-agent ou une action planifiée dont la source n'est pas la bonne | l'autorité doit se lire aussi sur une consultation |
| la page qui additionne les deux totaux | deux listes distinctes, jamais un total confondu |

**Simulation exigée avant de déclarer 4a fini** : un tour RÉEL dans le
conteneur (une question qui déclenche `get_emails`), puis vérification que la
page « Traitements » et l'export ne sont **pas vides** — la règle née du défaut
du `run_id`.

**Edge cases explicitement couverts** : période vide, période inversée
(`since > until`), utilisateur sans aucun effet, 50 000 lignes, libellé
illisible, fuseau exotique, export pendant une rotation de clé, admin sans
dévoilement, CSV contenant un séparateur dans une valeur, et un utilisateur
supprimé pendant l'export.
