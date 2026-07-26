# ADR-155: Aucune suite de tests ne se désactive sur une clé de provider absente

**Statut**: ✅ IMPLEMENTED (2026-07-26)
**Date**: 2026-07-26
**Décideurs**: Équipe LIA

## Contexte

Dix modules de test portaient, au niveau module, la forme suivante :

```python
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY"
)
```

Aucune variable `OPENAI_API_KEY` n'est présente dans l'environnement CI du job
`test-backend` — ni sur le poste d'un développeur qui n'en a pas configuré une.
Ces dix fichiers étaient donc **intégralement sautés**, à chaque exécution,
depuis leur écriture.

Un test sauté est vert. Rien ne le signale : ni le résumé pytest, qui agrège les
sauts en une ligne noyée dans le décompte, ni la couverture, qui mesure les
lignes atteintes et non les assertions exécutées, ni la revue de code, qui voit
un fichier de tests et en conclut que la surface est protégée.

Mesure du 2026-07-26 : ces dix fichiers contenaient **219 fonctions de test**
(234 cas une fois le paramétrage déplié), couvrant le classifieur HITL, la
reprise après approbation, l'exécuteur de brouillons, la construction du graphe
LangGraph et le mixin de streaming — c'est-à-dire précisément les points de
passage où une régression est la plus coûteuse.

Réactivés avec une clé factice, **142 revenaient au rouge** (125 échecs, 17
erreurs de collecte ou de fixture) contre 92 verts. Les causes n'ont rien
d'exotique : ils avaient été écrits contre `AIMessage.content` avant la
migration LangChain 1.x vers `.text`, et contre un classifieur antérieur au
passage en sortie structurée. Personne ne les avait cassés — ils avaient dérivé
pendant des mois, sans contradicteur.

Les réparer a exhumé quatre défauts de production réels (frontières de phrase de
la synthèse vocale, bail non relâché sur un rappel échu, titres de notification
en anglais pour un utilisateur chinois, reformulation de modification câblée sur
un seul outil). Ces défauts étaient dans le périmètre déclaré des tests sautés.

## Décision

**Un module de test ne se désactive jamais sur l'absence d'une clé de provider.**
Trois issues, dans cet ordre de préférence :

1. **Le test n'a besoin que de la _forme_ d'une réponse LLM** → on la simule.
   C'est un test unitaire, il vit sous `tests/unit/` sans aucune porte
   d'environnement. C'est le cas de la très grande majorité.
2. **Le test appelle réellement un provider payant** → il est marqué
   `@pytest.mark.e2e` (ou `integration`). Les filtres `-m` de la CI nomment ces
   marqueurs explicitement : l'exclusion devient **lisible dans la commande**
   au lieu d'être un silence dans le fichier.
3. **Un seul test a besoin d'une clé** → on garde le `skipif` sur _cette
   fonction_. Le reste du fichier continue de tourner.

La règle est portée par une garde exécutable,
`apps/api/tests/unit/test_no_env_skipped_suite_guard.py` : un balayage AST de
tout `tests/**/test_*.py` qui détecte un `pytestmark` de niveau module
conditionné à l'une des variables de credential (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `PERPLEXITY_API_KEY`,
`BRAVE_API_KEY`) **et** ne déclarant pas par ailleurs un marqueur désélectionné.

`ALLOWED_ENV_SKIPPED_MODULES` est un ratchet **shrink-only** : les entrées
sortent quand la suite est réparée, aucune n'entre. Elle est **vide** depuis le
2026-07-26 et doit le rester — une entrée y signifie des tests que personne
n'exécute.

Six tests d'auto-vérification épinglent le balayage lui-même (détection d'une
forme synthétique, non-détection d'un `skipif` de fonction, d'un marqueur non
lié à un credential, d'une simple liste de marqueurs, et acceptation de la
sortie de secours sanctionnée), plus un test qui refuse toute entrée périmée
dans la liste d'exemption : une exemption qui ne correspond plus à rien est pire
que pas d'exemption du tout, car le lecteur suivant lui fait confiance.

## Alternatives écartées

- **`--strict-markers` / `-W error::pytest.PytestUnknownMarkWarning`** — ne dit
  rien des sauts : le marqueur `skipif` est parfaitement légitime.
- **Faire échouer la CI sur tout test sauté (`-rs` + seuil)** — trop large. Les
  sauts conditionnés à la plateforme (Windows/POSIX) ou à un service absent sont
  légitimes et nombreux ; un seuil global serait relevé au premier faux positif.
- **Injecter une clé factice dans l'environnement CI** — rend les suites vertes
  sans les rendre honnêtes : celles qui appellent réellement un provider
  échoueraient en authentification, et on aurait déplacé le silence, pas
  supprimé.
- **Documenter la règle sans garde** — la règle existait déjà en substance dans
  `GUIDE_TESTING.md`. Elle n'a pas empêché dix fichiers de dériver. Une règle
  sans exécutant est une intention.

## Conséquences

**Positives**

- Le job CI « agents » passe de 978 à 1 158 tests réellement exécutés, zéro
  sauté.
- La classe entière de défaut est fermée : un onzième fichier de cette forme
  fait rougir la CI à l'ajout, avec le message qui nomme les trois issues.
- L'exclusion des suites qui appellent vraiment un provider est désormais
  visible dans la commande CI, donc auditable.

**Négatives / coûts**

- Deux suites relabellées `e2e` (32 tests) ne tournent plus dans le pipeline
  nominal, plus les 6 tests de `test_router_state` qui pilotent le graphe
  entier. C'est la vérité qui était **déjà** en vigueur — elle est simplement
  écrite là où on la voit.
- **La liste d'exemption F006 passe de 11 à 49 entrées** (`tests/marker_
  coverage_allowlist.json`, catégorie `provider_eval`). C'est le point délicat :
  cette liste est shrink-only. Elle grandit ici parce que **la garde F006 ne
  pouvait pas voir ces tests** — un test sauté sur credential reste *collecté et
  sélectionné* par le filtre `-m` du job, donc F006 le comptait comme couvert
  alors qu'il ne s'exécutait jamais. Le marqueur `e2e` rend l'exclusion visible
  des deux côtés. La sortie reste un harnais hermétique par suite, jamais une
  entrée de plus.
- Le balayage AST parse tous les modules de test à chaque exécution (~1 s).

## Références

- Garde : `apps/api/tests/unit/test_no_env_skipped_suite_guard.py`
- Doctrine de test : `docs/guides/GUIDE_TESTING.md`
- Précédent de même nature (une garde exécutable par classe de défaut) :
  [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md)
- Défauts exhumés par la réanimation de ces suites :
  [ADR-153](ADR-153-HITL-Action-Taxonomy.md),
  [ADR-154](ADR-154-TTS-Sentence-Boundaries.md)
