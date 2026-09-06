# Lot 4 — Dire une récurrence en conversation

**But :** qu'un lecteur puisse dire « tous les lundis et jeudis à 8h et 18h,
jusqu'à fin décembre » et que LIA le transcrive juste — dans les six langues —
puis mesurer factuellement à quel point c'est vrai.

**Architecture :** aucune capacité nouvelle du moteur. Le lot ajoute une
SURFACE de dictée au-dessus de `core/recurrence`, et une mesure de sa fiabilité.

**Amont :** lots 1/2A/2B/3 livrés, ADR-268.

## Ce que l'analyse a établi (tout mesuré, rien supposé)

### A. Ce que le catalogue sait exprimer

| # | Constat | Preuve |
|---|---|---|
| A1 | Sur **109 manifestes / 296 paramètres** : 213 chaînes, 36 entiers, 27 booléens, 18 tableaux, 1 nombre, **1 seul objet** | balayage de tous les manifestes chargés |
| A2 | Aucun paramètre natif ne porte de JSON Schema ; le champ existe et sert aux outils **MCP** | `registration.py:897` + `compact_schema` |
| A3 | **`compact_schema` écrase les sous-modèles référencés** : `times` et `end` de `RecurrenceSpec` sont publiés comme `{"type":"string"}` | mesuré : `times -> {"type": "string"}` |
| A4 | Le schéma compacté pèse ~132 tokens, pour un budget catalogue de ~200 tokens/outil | mesuré |
| A5 | L'unique paramètre objet du dépôt décrit sa forme **en prose** | `local_query_engine_tool.query` |

**Conséquence A3 est décisive** : publier le spec imbriqué par le chemin
existant annoncerait au planificateur un contrat **faux** — il produirait
`"times": "08:00"`, le validateur refuserait, et la réponse rapporterait un
échec pour une obéissance. C'est l'anti-patron ADR-184 dans sa forme la pire.
Deux issues seulement : corriger `compact_schema` (chemin MCP partagé, risque
tiers) ou **ne pas publier d'objet**.

### B. Où une mesure à vrais appels peut vivre

| # | Constat | Preuve |
|---|---|---|
| B1 | **La CI n'a aucune clé fournisseur** | `ci.yml` : uniquement `GITHUB_TOKEN`, `FERNET_KEY`, `CODECOV_TOKEN` |
| B2 | **Aucun test du dépôt n'appelle un fournisseur** — tous mockent `get_llm` | balayage de `tests/` |
| B3 | L'allowlist F006 est **shrink-only** et une entrée devenue non-orpheline **fait échouer** la porte | `marker_coverage_allowlist.json` |
| B4 | `tests/agents/` tourne en CI (`ci.yml:236`) mais **ni dans le hook ni dans `ci:fast`** | Taskfile + workflow |
| B5 | Précédents de mesure à la demande + résultat figé : `mobile:probe`, `llm:catalogue:fetch`, `golden_kwargs.json`, `legacy_cron_golden.json` | dépôt |

**Conséquence** : le harnais à vrais appels est un **script**, jamais un test.
Le test qui tourne en CI vérifie la traduction **déterministe** ; la mesure LLM
est lancée à la main et son résultat est **publié**, jamais impliqué.

### C. Trois défauts trouvés sur le chemin du lot

**C1 — `create_reminder_tool` déclare `mutation_policy="draft"` et écrit
immédiatement.** `draft` est *pass-through* dans `effects/gate.py:104` — la
porte le laisse passer *parce que* « draft ne fait que CONSTRUIRE la
confirmation ; l'effet a lieu plus tard ». Or l'outil appelle
`service.create_reminder` puis `db.commit()` et rend `action_success`, sans
aucun brouillon. Donc : **ni demande à l'utilisateur, ni ligne au registre des
effets**, sur un outil dont la déclaration affirme le contraire. L'outil des
routines, qui déclare la même politique, construit lui un vrai brouillon.

**C2 — `tests/agents/` est un angle mort LOCAL** : en CI mais hors du hook et
de `ci:fast`. A frappé quatre fois (mémoire). Toute suite posée là doit être
lancée explicitement avant de conclure.

**C3 — Quatre descriptions de paramètres destinées au MODÈLE sont en
français** dans `reminder_tools.py`, alors qu'ADR-256 impose l'anglais
technique — et que le manifeste des mêmes paramètres est en anglais. Les deux
surfaces se contredisent.

### D. La forme à enseigner : ce que dit l'évidence

Un vocabulaire **plat** se projette exactement sur ce que le catalogue publie
et valide déjà (`enum`, `minimum`/`maximum`, `pattern`, tableau d'entiers) et
hérite gratuitement du bornage numérique (`planner/parameter_bounds.py`). Un
objet imbriqué exige de réparer `compact_schema`.

Ce n'est **pas** un second vocabulaire de stockage : les paramètres plats sont
une PROJECTION pour la surface LLM, traduite en `RecurrenceSpec` par **une
seule** fonction — exactement ce qu'est déjà le mini-langage
`relative_trigger`. Le vocabulaire stocké reste unique.

Mais la décision se **mesure**, elle ne se décrète pas : le lot commence par le
corpus, et le corpus tranche.

---

## Lot 4A — Le corpus, avant toute implémentation

**Fichier** : `apps/api/tests/unit/core/recurrence/transcription_corpus.json`

~90 formulations (15 par langue × 6), chacune avec le `RecurrenceSpec` attendu.
Couverture obligatoire :

- occurrence unique (« demain 10h », « le 3 mars à 8h »)
- quotidien, hebdo simple, hebdo multi-jours
- **plusieurs fois par jour** (« à 8h et 18h ») — ce que l'ancien modèle ne
  savait pas dire
- intervalle (« une semaine sur deux », « tous les trois jours »)
- mensuel par quantième (« le 15 de chaque mois ») et par nième jour
  (« le 2e mardi »)
- annuel (« chaque 14 juillet »)
- fin de série (« jusqu'au 31 décembre », « les 5 prochaines fois »)
- pas régulier (« toutes les 2 heures entre 9h et 17h »)
- **pièges** : « tous les 15 jours » (intervalle, pas quantième), « le week-end »,
  « en semaine », « tous les mois le 31 » (mois courts)

Le corpus est une DONNÉE, pas un test : il sert les deux lots suivants.

## Lot 4B — La traduction déterministe (TDD, CI)

Une fonction unique, `recurrence_from_parameters(...)`, dans
`src/core/recurrence/` ou `domains/agents/…/recurrence_input.py`, qui
transforme les paramètres plats en `RecurrenceSpec`.

**Tests** (unitaires, en CI, sans réseau) : chaque entrée du corpus dont les
paramètres plats sont donnés produit **exactement** le spec attendu ; les
plafonds sont injectés par appelant ; une combinaison impossible est refusée
avec un message que le modèle peut relayer.

## Lot 4C — Les deux outils, et le manifeste en phase

- `create_scheduled_action_tool` : élargi (aujourd'hui hebdo uniquement).
- `create_reminder_tool` : gagne la récurrence.
- **Manifestes mis à jour dans le MÊME changement** (ADR-184) — chaque borne
  imposée est publiée avec les primitives existantes.
- **C3** : descriptions passées en anglais technique (ADR-256).
- **C1** : la politique devient **`reversible`** (arbitrage du propriétaire,
  2026-09-06) — l'outil écrit sans demander, comme aujourd'hui, mais l'effet
  est désormais ENREGISTRÉ au registre (ADR-263). Zéro changement pour le
  lecteur : « rappelle-moi… » reste une phrase et une réponse ; la suppression,
  elle, continue de demander. Il faut donc aussi un libellé d'effet
  (`EFFECT_LABEL_BUILDERS`), qu'`effects/labels.py` exige pour toute politique
  agissante hors `draft`.

**Tests** : signature ↔ manifeste en phase (garde existante étendue) ;
un spec canonique en sortie ; un jour répété replié ; `golden_patterns`
inchangés.

## Lot 4D — La mesure à vrais appels (à la demande, hors CI)

`scripts/recurrence/measure_transcription.py` + `task recurrence:corpus:measure`.

- Rejoue le corpus contre un vrai modèle (slot choisi en argument), compare le
  spec produit au spec attendu **par instants**, pas par champs — deux specs
  différents qui produisent les mêmes instants sont une transcription juste.
- Sort un rapport par langue et par famille de formulation.
- **Aucune clé en CI**, donc jamais dans une porte. Le résultat est figé et
  publié dans l'ADR, avec sa date et son modèle.
- Si la forme plate et la forme imbriquée sont toutes deux candidates, le
  script mesure **les deux** et la décision est prise sur le chiffre.

## Lot 4E — Revue adversariale et portes

```
task lint                     # + ratchets, i18n, docs (preview si non stagé)
task test:backend:unit:fast
task test:backend:agents      # ANGLE MORT LOCAL — à lancer explicitement (C2)
task test:frontend
task test:markers             # F006 : aucun test dans zéro job
build managé e2e
```

## Plan de test (enrichi pendant l'implémentation)

| Axe | Ce qui doit être prouvé |
|---|---|
| Non-régression | un rappel « demain 10h » et une routine « en semaine à 8h » se comportent exactement comme avant |
| Traduction | les 90 entrées du corpus produisent le spec attendu, en déterministe |
| Plafonds | le manifeste publie ce que le validateur impose (ADR-184), vérifié champ par champ |
| Politique | l'outil de rappel déclare ce qu'il fait vraiment ; une ligne apparaît au registre des effets |
| Langue | zéro description française destinée au modèle (ADR-256) |
| Bornage | un intervalle hors bornes est CLAMPÉ, un enum invalide est REFUSÉ |
| Angle mort | `tests/agents/` lancé explicitement |
| Mesure LLM | exactitude par langue et par famille, publiée avec sa date et son modèle |
