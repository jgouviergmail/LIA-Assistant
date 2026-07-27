# ADR-159: Les quatre thèmes du journal doivent rester atteignables — classement par sujet, ancrage à trois voies, harnais de mesure

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-088 (restraint d'écriture), ADR-079 (journal stratifié), ADR-057 (journaux personnels)

## Contexte

Le journal personnel classe ses entrées en quatre thèmes (`learnings`,
`user_observations`, `self_reflection`, `ideas_analyses`). Mesuré le 2026-07-27
sur les bases dev et prod, pour le compte principal :

| Base | `learnings` | `user_observations` | `self_reflection` | `ideas_analyses` |
|---|---|---|---|---|
| dev | 4 | 1 | **0** | **0** |
| prod | 11 | 2 | **0** | **0** |

Rien n'avait échoué. Les suites étaient vertes, les prompts restaient
plausibles à la lecture, et le défaut n'était visible que dans la colonne
`theme` de `journal_entries`. Il a vécu du **2026-06-02** (v1.20.19, ADR-088) au
2026-07-27.

Deux mécanismes indépendants, tous deux confirmés par la mesure.

### 1. La création — la porte d'ancrage exclut les signaux démontrés

ADR-088 a réécrit `journal_introspection_prompt.txt` pour supprimer le bruit, et
a remplacé l'arbre de classification par une barre d'entrée unique :

> GROUNDED in an EXPLICIT signal from the user THIS conversation […] **that you
> could quote**.

Le modèle lit « explicite et citable » comme « dit avec des mots ». Or un
`ideas_analyses` est *par construction* une abstraction inter-sujets inférée, et
un `user_observations` peut être un trait **montré** sans jamais être énoncé.
La réécriture a également laissé `ideas_analyses` comme **seul thème sans
illustration**, et posé `learnings` en attracteur explicite (« The strongest,
best-grounded theme; prefer it » ; « One good `learnings` note and nothing else
is a perfect output »).

Mesure A/B — mêmes conversations, même modèle, même température, seul le prompt
change (8 répétitions par cellule, contexte fidèle : section psyché renseignée et
entrée `learnings` existante dans le jeu de travail) :

| Scénario | prompt livré | prompt d'avant le 2026-06-02 |
|---|---|---|
| `self_reflection` explicite | 8/8 → `learnings` | `self_reflection` produit |
| `self_reflection` réaliste | 8/8 silence | `self_reflection` produit |
| `ideas_analyses` explicite | 8/8 → `user_observations` | `ideas_analyses` produit |
| `ideas_analyses` implicite | 8/8 silence | `ideas_analyses` produit |

**Zéro** entrée de ces deux thèmes sur 24 exécutions sous le prompt livré.
L'ablation du persona analyste donne des résultats identiques : la faute est
dans le prompt principal, pas dans `journal_analyst_persona.txt`.

### 2. La survie — un cliquet à sens unique dans la consolidation

`journal_consolidation_prompt.txt` ordonnait (STEP 2, répété dans l'auto-audit) :
toute entrée dont la clause `BECAUSE` cite un événement passé **et** classée
`user_observations` ou `self_reflection` → reclasser en `learnings`.

Or le prompt d'extraction **exige** qu'un `self_reflection` soit « grounded in
the user's reaction » — donc qu'il porte précisément une telle clause.
L'intersection est vide : le thème est inatteignable en régime permanent,
indépendamment du modèle.

Mesure, contrôle positif et négatif, 6 exécutions chacun :

| Entrée `self_reflection` soumise | Résultat |
|---|---|
| **avec** clause `BECAUSE` (la forme imposée par l'extraction) | **6/6 reclassées en `learnings`** |
| **sans** clause `BECAUSE` (l'exemple du prompt lui-même) | 5/6 intactes |

Preuve en production : l'entrée `8bc35289` a `source=user_correction`, or le code
créait obligatoirement ces entrées en `theme="self_reflection", level="L0"`. Elle
figure en base en `learnings`/`L1`. Le cliquet a agi sur données réelles.

### 3. Le seul producteur restant utilisait le mauvais thème

`feedback_hooks.record_correction` et le levier de retour sur portrait écrivaient
`theme="self_reflection"` en dur. Un retour utilisateur n'est pas une réflexion
de l'assistant sur sa propre posture. Tant que le thème était par ailleurs
inatteignable, ce mauvais étiquetage en était **l'unique producteur vivant** —
ce qui a contribué à masquer le défaut.

## Décision

### A — Le classement se fait par SUJET, jamais par forme d'ancrage

Section 3 du prompt d'extraction devient une échelle ordonnée de quatre
questions portant sur **ce dont la directive parle** : ma propre diction →
`self_reflection` ; un signal valable quel que soit le sujet → `ideas_analyses` ;
un trait stable de l'utilisateur → `user_observations` ; une leçon sur le monde
ou ma méthode → `learnings`. Chaque thème reçoit une illustration travaillée et
nomme l'ancrage qui l'admet.

La consolidation applique **la même échelle**. La règle qui reclassait
`self_reflection` en `learnings` sur la présence d'une clause `BECAUSE` est
supprimée : tous les thèmes en portent une, ce discriminant fire sur tout.

### B — L'ancrage a trois voies, pas une

Section 1 énumère exactement trois ancrages admissibles :

- **(a) SAID** — correction, instruction ou préférence énoncée ; citable.
- **(b) SHOWN** — comportement répété **au moins deux fois** sous les yeux de
  l'assistant. Ancrage **plein**, pas dégradé. Deux occurrences sur des sujets
  *différents* est la forme la plus forte : elle prouve l'indépendance au sujet.
- **(c) REACTED** — réaction visible de l'utilisateur à ce que l'assistant a
  fait. **Une** réaction claire suffit, les deux côtés étant pointables.

`self_reflection` exige **(c) et uniquement (c)** : sans réaction utilisateur, pas
d'entrée. C'est ce verrou qui ramène le bruit à zéro alors que le rappel monte.

L'interdit B est durci en conséquence : un trait de **surface** (longueur, ton,
ponctuation, orthographe) reste exclu de (b) **quelle que soit sa fréquence** —
(b) porte sur ce que l'utilisateur *fait*, jamais sur l'allure de ses phrases.

### C — Les retours utilisateurs sont étiquetés par sujet

`JOURNAL_RESPONSE_FEEDBACK_THEME = "learnings"` (retour sur une réponse : une
leçon sur ce que l'assistant a fait) et `JOURNAL_PORTRAIT_FEEDBACK_THEME =
"user_observations"` (retour sur le portrait : correction du modèle de
l'utilisateur). Ni l'un ni l'autre n'est `self_reflection`.

### D — La propriété devient une règle vérifiée, et une mesure reproductible

Deux artefacts, sur le modèle éprouvé du domaine Psyché (garde statique
`test_mood_reachability.py` + instrument `apps/api/scripts/measure_psyche.py`) :

- **`apps/api/tests/unit/domains/journals/test_theme_reachability.py`** — garde CI, analyse
  textuelle pure, sans LLM ni base. Vérifie la **parité** (chaque thème a un
  en-tête, une illustration et un ancrage nommé) et la **non-contradiction** (nulle
  règle de consolidation ne réécrit `self_reflection` en `learnings` ; l'audit se
  déclare « by SUBJECT »). Falsifiée contre l'état antérieur : les quatre familles
  rougissent, la garde du cliquet pointant le texte fautif exact.
- **`apps/api/scripts/measure_journal_themes.py`** — batterie de 13 conversations
  (deux positives par thème, explicite et implicite, plus **cinq négatives** qui
  doivent rester silencieuses), rapportant rappel par thème, volume, taux de bruit
  et coût en jetons. Le rendu passe par
  `apps/api/src/domains/journals/prompt_builders.py`, le module que le runtime
  utilise — le harnais ne peut pas diverger de la production. Placé sous
  `apps/api/scripts/` pour embarquer dans l'image prod (`Dockerfile.prod` fait
  `COPY . .` depuis ce contexte ; le `scripts/` racine, non).

**Règle d'oracle** adoptée pendant la calibration : *un scénario négatif n'est
valide que si aucun ancrage (a)/(b)/(c) n'y existe*. Deux négatifs initiaux la
violaient et ont été réparés plutôt que de brider un comportement correct — dans
les deux cas le modèle écrivait une entrée **légitime** (une préférence énoncée,
une leçon de méthode autorisée par l'interdit A).

## Conséquences

Mesure finale, 8 répétitions × 13 scénarios (104 appels), batterie corrigée :

| Configuration | `learnings` | `user_obs` | `self_reflection` | `ideas_analyses` | volume positif | **bruit négatif** |
|---|---|---|---|---|---|---|
| Prompt livré, `effort=none` | 1,00 | 0,58 | **0,00** | **0,00** | 0,65 | 0,00 |
| Nouveau prompt, `effort=none` | 1,00 | 1,00 | 0,50 | 0,13 | 0,75 | 0,00 |
| Nouveau prompt, `effort=low` | **1,00** | **1,00** | **1,00** | **1,00** | 1,00 | **0,00** |

Le prompt seul lève l'inatteignabilité structurelle et corrige
`user_observations`, **sans aucun coût en bruit** : il est sûr à livrer même si la
configuration LLM n'est pas touchée. L'effort de raisonnement transforme
l'atteignabilité en fiabilité.

**Action de configuration restante, hors code** : l'override en base
(`llm_config_overrides`) fixe `journal_extraction` à `gpt-5.2` avec
`{"effort": "none"}`, en dev **et** en prod. Le défaut *du code*
(`LLM_DEFAULTS`) est déjà `low`. Il s'agit donc d'une dérive de configuration
introduite par l'administration, pas d'un défaut logiciel. Coût mesuré du
passage à `low` : entrée inchangée (3 512 jetons), sortie **64 → 178 jetons par
tour**. L'entrée dominant la facture, l'impact réel est marginal.

## Alternatives écartées

- **Revenir au prompt d'avant le 2026-06-02.** Mesuré : ce prompt produit 2 à 3
  entrées par tour, y compris des `self_reflection` sur signaux faibles —
  exactement le bruit qu'ADR-088 avait supprimé. La régression thématique et la
  régression de bruit ne sont pas un couple à arbitrer : la mesure montre qu'on
  obtient les quatre thèmes **à volume et bruit constants**.
- **Ne corriger que la consolidation (A).** Aurait laissé `ideas_analyses` à
  0,00 : le cliquet n'explique que `self_reflection`.
- **Ne corriger que l'extraction (B).** Le cliquet aurait vidé
  `self_reflection` à la consolidation suivante, à 6/6.
- **Régler le problème par la seule montée d'effort.** Sans le prompt,
  `ideas_analyses` reste inatteignable : la porte d'ancrage l'exclut par
  construction, quel que soit le budget de raisonnement.
- **Imposer une distribution cible entre thèmes.** C'est la pression qu'ADR-088
  a supprimée à raison. L'équilibre est un **résultat** observé, jamais une
  consigne : les prompts continuent d'interdire d'écrire pour remplir un quota.
