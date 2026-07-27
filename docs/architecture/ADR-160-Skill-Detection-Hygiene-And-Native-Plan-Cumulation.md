# ADR-160: Hygiène de la détection de skill, cumul avec le plan natif, et les deux plafonds qui rendaient une fonctionnalité impossible

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA
**Amende**: ADR-118 (skills dialogue), ADR-117 (runs en arrière-plan), ADR-062 (outils MCP itératifs)

## Contexte

Le 2026-07-27, six tentatives consécutives de « Crée une image réaliste d'un
chat » en production. Aucune n'a produit d'image. Mesuré sur les logs de
`lia-api-prod` :

| Heure (UTC) | Pivot anglais analysé | `skill_name` | Issue |
|---|---|---|---|
| 05:16:27 | `Generate a realistic image of a cat` | `skill-generator` | détourné |
| 05:18:09 | `Create the realistic image of a cat` | `"null"` | `generate_image` tué à 90 s |
| 05:21:39 | `Create the realistic image of a cat` | `skill-generator` | détourné |
| 05:22:28 | `Create the realistic image of a cat` | `skill-generator` | détourné |
| 05:40:31 | `Create a realistic image of a cat` | `skill-generator` | détourné |
| 05:41:26 | `Create a realistic image of a cat` | `"null"` | image produite (47 s) |

Les deux dernières lignes portent **le même pivot anglais** et divergent : la
formulation française n'y est pour rien. Quatre défauts indépendants se
superposaient, chacun suffisant à faire échouer la demande.

## Décision

### 1. `skill_name` est normalisé à la frontière de parsing

Le prompt de l'analyseur demande, en prose, de « leave it null », et la sortie
structurée tourne en `strict_mode: false`. Le modèle écrit donc les quatre
caractères `null` — une chaîne non vide, donc *truthy* pour chaque
`if skill_name:` du pipeline. Mesuré sur 104 sondes contre l'analyseur de
production (`deepseek-v4-flash`), y compris sur le vrai chemin `analyze_full`
(20/20) : **84 à 100 % des analyses** d'une simple demande d'image revenaient
ainsi.

Un `field_validator` Pydantic sur `QueryAnalysisOutput.skill_name` applique
désormais `normalize_skill_name` : trim, puis rejet des sentinelles textuelles
(`null`, `none`, `nil`, `n/a`, `undefined`, `false`, `-`). Normaliser **au
parsing** plutôt qu'à chaque consommateur est ce qui empêche le chemin
« chat override » de journaliser `chat_override_cleared_skill_name(skill_name="null")`,
une ligne qui affirmait avoir effacé une skill jamais détectée.

### 2. Une skill nommée doit exister pour ce compte

`effective_skill_name` vérifie désormais que le nom correspond à une skill
joignable par l'utilisateur (`SkillsCache.get_by_name_for_user`), avec
**fail-open** si le cache n'est pas chargé — un cache vide signifie « au
démarrage », pas « aucune skill n'existe ». Le routeur donne à
`detected_skill_name` une priorité absolue : un nom halluciné pilotait le tour
entier. En 2026-07-21, `mcp_excalidraw` n'avait atterri sur le bon chemin que
**par accident**, parce qu'aucune skill ne portait ce nom.

### 3. Une skill script-only cumule avec le plan natif au lieu de le remplacer

Une skill *script-only* (scripts, sans `plan_template` déterministe) émettait un
**plan vide** pour court-circuiter le planificateur LLM. C'était un choix
délibéré : éviter les appels d'API « parasites » que le planificateur dérive du
domaine primaire. Le coût réel s'est vu en production : la demande d'image a
matché `skill-generator`, le plan vide a jeté `generate_image` — pourtant élu
par la sélection sémantique avec un **score de 1.0** — et le sous-agent n'a reçu
que quatre outils de skill (`activate_skill_tool`, `run_skill_script`,
`read_skill_resource`, `import_user_skill`).

La stratégie cède désormais la main au planificateur LLM, qui émet les étapes
natives du domaine. La skill n'est pas perdue pour autant : `response_node`
(étape 3) l'active depuis `query_intelligence`, **indépendamment du plan**. Les
deux s'exécutent.

Le renversement est réversible : `SKILL_SCRIPT_ONLY_CUMULATES_NATIVE_PLAN=false`
restaure le court-circuit historique si les étapes natives s'avèrent être du
bruit sur un déploiement donné.

**Écarté** : « l'outil natif à score élevé l'emporte sur la skill ». Vérification
faite, `interactive-map` a exactement la même structure que `skill-generator`
(script-only, sans `plan_template`) : ce critère aurait supprimé la carte
interactive sur « montre-moi Paris ». Le cumul évite l'arbitrage entièrement.

### 4. La famille image obtient un plafond dédié

Latences mesurées contre `gpt-image-2` en production :

| Paramètres | Latence |
|---|---|
| `quality=medium` `1024x1536` | 47,2 s |
| `quality=high` `1024x1536` | **138,3 s** |

L'ancienne politique était un plancher de 90 s sous le plafond **générique** de
120 s (`MAX_TOOL_TIMEOUT_SECONDS`). 138,3 s dépasse le plafond lui-même :
`quality=high` était donc **impossible à quelque réglage que ce soit** — relever
`IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS` dans `.env` n'aurait rien changé. Comme
les familles navigateur, sous-agent et MCP-ReAct avant elle, la famille image a
maintenant son propre couple plancher/plafond : 180 s / 300 s.

### 5. Les détections retenues sont observables

`skill_detection_suppressed_total` ne décrivait que ce qui était jeté. Le
déclencheur du détournement `skill-generator` **n'a jamais été reproduit** (0 sur
104 sondes, contre 4 sur 6 tours de production, dans des conditions
d'état pourtant identiques — `messages_count: 1, turn_id: 1` après purge du
checkpoint). Sans signal sur les détections *conservées*, une récurrence n'aurait
rien à quoi se corréler. `skill_detection_retained_total{skill_name, primary_domain}`
comble ce trou ; sa cardinalité est bornée par le catalogue.

## Conséquences

- Une skill script-only déclenche désormais un appel de planification LLM là où
  elle l'évitait. C'est le coût assumé du cumul, réversible par configuration.
- `quality=high` devient atteignable ; une génération peut occuper une étape
  jusqu'à 300 s.
- Le déclencheur amont du détournement reste **non élucidé**. Les correctifs 1 à
  3 neutralisent le symptôme sans en dépendre ; le correctif 5 fournit le signal
  pour l'instruire si le cas se reproduit.

## Alternatives non retenues

- **Déclarer les domaines couverts par chaque skill** (`domains:` en frontmatter).
  Générique et sans régression grâce au fail-open, mais il fallait renseigner les
  14 skills système, inventer un marqueur pour les méta-skills, et les skills
  utilisateur restaient sans protection. Coût sans commune mesure avec le cumul.
- **Retirer `skill-generator` de la détection automatique**
  (`disable-model-invocation: true`). Une ligne, aucun risque — mais « crée-moi
  une compétence qui… » cesserait de la déclencher, et rien n'empêcherait une
  autre skill de dériver demain.

## Références

- `apps/api/src/domains/agents/services/analysis/skill_suppression.py`
- `apps/api/src/domains/agents/services/planner/strategies/skill_bypass.py`
- `apps/api/src/domains/agents/orchestration/parallel_executor.py` (`_compute_step_timeout`)
- `apps/api/tests/unit/domains/agents/services/analysis/test_skill_suppression.py`
- `apps/api/tests/unit/domains/agents/services/test_query_analysis_output_skill_name.py`
- `apps/api/tests/unit/domains/agents/services/test_skill_bypass_strategy.py`
- `apps/api/tests/unit/domains/agents/orchestration/test_parallel_executor_compute_step_timeout.py`
