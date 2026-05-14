# Refonte de la délégation aux sous-agents — Design

- **Date** : 2026-05-13
- **Statut** : Design validé (en attente de relecture avant plan d'implémentation)
- **Domaines impactés** : `agents` (planner, semantic_validator, parallel_executor, tools, prompts), `sub_agents`, `llm_config`, frontend i18n, docs
- **Déclencheur** : incident prod du 2026-05-12 — la requête « fais‑moi un résumé des 5 derniers emails envoyés par ma femme » a consommé **485 930 tokens** (0,56 €, ~95 s) au lieu de ~12 K.

---

## 1. Contexte & cause racine

### 1.1 L'incident

Trace prod `request_id 50855ec2‑…` (deux occurrences : 20:18 et 20:32, ~482‑486 K tokens chacune).

Décomposition par nœud (logs `token_usage_persisted` / `token_tracking_callback_tokens_extracted`) :

| Périmètre | prompt tokens |
|---|---|
| Pipeline principal (semantic_pivot, memory_ref ×2, query_analyzer 1,4 K, planner 3,2 K, semantic_validator, initiative, response 11,6 K, …) | ~28 000 |
| **Nœud `subagent:assistant de synthèse d'emails`** | **~457 000** |

À l'intérieur du sous-agent (`SubAgentExecutor`, pipeline bespoke), **3 appels LLM** :

| Appel interne | modèle | prompt tokens |
|---|---|---|
| `_analyze_instruction` → `analyze_query(query = expertise + "\n\n" + instruction)` | gpt‑5.2 | **115 196** |
| `SmartPlannerService.plan(intelligence=qi)` | gpt‑5.2 | **225 253** |
| `_synthesize_results` (`subagent_synthesis_prompt`, slot `{instruction}`) | deepseek‑v4‑flash | **115 090** |

### 1.2 La chaîne de causes

1. Le **planner principal** a produit un plan en 2 étapes : `step_1 = get_emails_tool` (4 emails → registre), `step_2 = delegate_to_sub_agent_tool(expertise="assistant de synthèse d'emails (resume, extraction…)", instruction="…$steps.step_1.<champ>…")`.
2. À l'exécution, le `ReferenceResolver` (`condition_evaluator.resolve_args` → `_resolve_embedded_references` → `_format_resolved_value` qui fait `f"({str(resolved_value)})"`, **sans aucune borne de taille**) a remplacé `$steps.step_1.<champ>` par la sérialisation complète des emails (corps HTML bruts, headers, métadonnées) → **`instruction` ≈ 114 K tokens** (~450 Ko de texte).
3. `delegate_to_sub_agent_tool` a passé ce `instruction` de 114 K tokens à `SubAgentExecutor.execute()`, qui exécute son **propre mini‑pipeline** : `_analyze_instruction` → `SmartPlannerService.plan` → `execute_plan_parallel` → `_synthesize_results`. Le blob de 114 K est **ré‑injecté dans les 3 appels LLM** (analyse : `expertise + instruction` ; planner : `qi.original_query = instruction` + `__user_message = instruction` du config ≈ ×2 ; synthèse : `{instruction}` dans le template). D'où 115 K + 225 K + 115 K ≈ 455 K.
4. Le sous‑agent a en plus **re‑fetché les emails** (`get_emails_tool`, 5 items) — il ne « voit » pas que les données sont déjà collées dans son instruction.
5. Le `semantic_validator` a vu `requires_hitl: true` (le manifest de `delegate_to_sub_agent_tool` a `hitl_required=True`), mais `approval_gate_node` est un **passthrough inconditionnel** depuis `v1.14.5` (« HITL plan‑level redondant car chaque mutation tool a son HITL downstream » — faux pour `delegate_to_sub_agent_tool` qui est read‑only et n'a aucun HITL downstream). Aucune confirmation n'est partie. (→ hors périmètre, cf. §8.)

### 1.3 Diagnostic structurel — les 5 vides

Le contrat de délégation existe sur le papier (le prompt `{sub_agents_section}` dit déjà « WHEN NOT TO DELEGATE: Simple factual queries… » et « BAD: step_1=web_search, step_2=delegate(use $steps.step_1) — GOOD: step_1=delegate(expert, 'research X') »), mais **rien ne l'enforce structurellement** : tout repose sur l'obéissance du LLM, et les garde‑fous qui *devraient* rattraper sont morts.

| # | Vide | État actuel |
|---|---|---|
| 1 | **Quand déléguer** | Décision libre du planner, guidée par de la prose. Aucun backstop. Le planner sur‑délègue. |
| 2 | **Quoi passer au sous‑agent** | `instruction` borné à 5000 caractères *avant* résolution des `$ref` (template ≈ 50 car.), puis explose à 114 K *après* résolution. La contrainte ne sert à rien. Le resolver n'a aucune borne. |
| 3 | **Combien il peut dépenser** | `SubAgentTokenGuard` (`sub_agents/token_guard.py`) écrit + testé mais **jamais branché** dans l'exécution (la doc `SUB_AGENTS.md` l'admet). `subagent_max_token_budget=50000` jamais appliqué → l'exécution a tourné à 457 K (9×). |
| 4 | **Pipeline interne disproportionné** | Même une délégation bien formée fait 3 appels LLM (2 sur le modèle cher) en pur overhead avant le travail réel. |
| 5 | **HITL cassé** | `hitl_required=True` dans le manifest, `requires_hitl=True` calculé par le validator, mais `approval_gate_node` ne déclenche jamais d'`interrupt()`. Le code F6 de `_build_approval_request` (« Enrich reasons for sub‑agent delegation plans ») est mort. **→ hors périmètre de ce chantier (cf. §8).** |

---

## 2. Hypothèses validées (le nouveau contrat)

- **H1** — La délégation à un sous‑agent ne se fait **que** lorsque l'assistant estime qu'un *prompt expert spécialisé* donnera un meilleur résultat que s'il le fait lui‑même. (≠ « c'est complexe » → « est‑ce que l'expertise aide ici ». Pour « résume mes 5 emails » : non → pas de délégation, le nœud `response` le fait seul.)
- **H2** — Un plan **peut** contenir des dépendances entre sous‑agents (chaînage A→B→… autorisé) — ou non. Donc **aucune restriction sur `depends_on`** des `delegate` steps. La borne porte sur la *taille du payload* injecté, pas sur la topologie du plan.
- **H3** — Un sous‑agent = **une tâche unitaire simple mais experte**, avec un prompt spécialisé. C'est l'agent principal qui décompose / orchestre / consolide ; **le sous‑agent ne re‑planifie pas** — il exécute sa tâche unique (boucle ReAct cadrée), retourne du texte condensé.

Décision additionnelle : **HITL de délégation laissé tel quel** pour ce chantier (le `approval_gate_node` reste un passthrough). Conséquence assumée : la sécurité « tu vois passer la délégation et tu peux dire non » n'existe pas en Phase 1 ; les garde‑fous de ce chantier (H1 veto + cap `instruction` + token guard) la remplacent fonctionnellement (délégation rare, bornée, non explosive). Le HITL pourra être re‑activé en suivi, **couplé à H1** (sinon : « confirme un sous‑agent pour résumer 5 emails » = agacement sans bénéfice).

---

## 3. Insight architectural central : sous‑agent = `ReactSubAgentRunner` paramétré

LIA dispose déjà de `ReactSubAgentRunner` (`apps/api/src/domains/agents/tools/react_runner.py`, ADR‑062) : un runner ReAct générique construit sur `langgraph.prebuilt.create_react_agent`. Il fait : `get_llm(llm_type)` → `load_prompt(prompt_name).format(current_datetime=…, **prompt_vars)` → `create_react_agent(llm, tools, prompt, store)` → `ainvoke({"messages":[HumanMessage(task)]}, config=nested_config)` → extrait `final_message`, `messages`, `accumulated_registry`, `iteration_count`, `duration_ms`. Le `nested_config` isole le `thread_id`, propage `callbacks` du parent, et injecte `metadata["node_name_override"] = display_name` (→ le `TokenTrackingCallback` du parent attribue les tokens au nœud nommé `display_name`). Bornage natif via `recursion_limit`.

Il est **déjà utilisé** par `browser_task_tool` (`ReactSubAgentRunner("browser_agent", "browser_agent_prompt")`), `mcp_server_task_tool` (`ReactSubAgentRunner(llm_type, "mcp_react_agent_prompt")`), et les skills (`skill_react_agent_prompt`).

**Décision** : `delegate_to_sub_agent_tool` garde son interface `(expertise, instruction)` mais son corps utilise `ReactSubAgentRunner("subagent", "subagent_react_prompt")` au lieu de `SubAgentExecutor`. Le sous‑agent devient une boucle ReAct : `prompt = scaffold ReAct + {expertise}` (persona), `task = instruction`, `tools = sous‑ensemble read‑only`, `recursion_limit` serré, garde‑token par exécution.

> **Réponse explicite à la question « on supprime le LLM Sub‑Agent et on utilise le LLM ReAct Agent ? »** : **non**. On garde le LLM type `subagent` (id interne inchangé). C'est le pattern du codebase — chaque consommateur de `ReactSubAgentRunner` a son type (`browser_agent`, `mcp_react_agent`). Et `react_agent` ≠ sous‑agent : `react_agent` est la boucle autonome du *mode ReAct du chat* (tous les tools, historique conversationnel complet, graphe à 4 nodes) ; un sous‑agent est une tâche experte cadrée (tools read‑only, pas d'historique, budget serré). Les garder séparés permet de leur donner un modèle distinct (probablement plus économique pour les délégations). Seul le **label affiché** change (cf. §4.7).

> **Pourquoi pas réutiliser le mini‑pipeline bespoke en le « slimmant » ?** Parce que le mini‑pipeline (`query_analyzer` + `SmartPlannerService` + `execute_plan_parallel` + synthèse) est précisément la source du gonflement à 3 appels LLM, et qu'il duplique des composants (query analysis, planning) que le parent a déjà faits — le sous‑agent re‑planifie ce que le parent a déjà décomposé, en violation de H3. Réutiliser `ReactSubAgentRunner` = moins de code, code éprouvé, comportement « tâche unitaire » naturel, attribution de tokens dans le tracker parent gratuite via `node_name_override`.

---

## 4. Design détaillé

### 4.1 Réécriture de `delegate_to_sub_agent_tool`

Fichier : `apps/api/src/domains/agents/tools/sub_agent_tools.py`.

**Avant** (~270 lignes) : check préférence utilisateur → `get_db_context` → cleanup des `ephemeral_*` stale → `SubAgentService.create(...)` (record ORM éphémère) → `db.commit()` → `SubAgentExecutor().execute(subagent, instruction, …)` → `repo.delete(subagent)` → `db.commit()` → consolidation manuelle des tokens dans le tracker parent (`parent_tracker.record_node_tokens(node_name=f"subagent:{expertise[:30]}", …)`) → `UnifiedToolOutput`.

**Après** (~50‑70 lignes) :
1. `validate_runtime_config(runtime, "delegate_to_sub_agent_tool")`.
2. **Depth check** (inchangé) : si `config.session_id` / `thread_id` indique qu'on est déjà dans un sous‑agent → `UnifiedToolOutput.failure(error_code="DEPTH_LIMIT_EXCEEDED")`. (Belt‑and‑suspenders : un sous‑agent n'a de toute façon pas `delegate_to_sub_agent_tool` dans ses tools, cf. point 4.)
3. **Check préférence utilisateur** `sub_agents_enabled` (via `UserService` ; ouverture d'une `AsyncSession` courte uniquement pour ça, OU lire depuis le contexte si déjà chargé).
4. **Construire les tools read‑only** : `resolve_tools_for_subagent(allowed_tools=[], blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS, all_tools=<liste complète des BaseTool>)` (`sub_agents/skill_resolver.py`). Cette fonction exclut déjà les `*_sub_agent_tool` (anti‑récursion) ; **ajouter `TOOL_NAME_DELEGATE_SUB_AGENT` au set d'exclusion** — actuellement absent (le set contient `list_sub_agents_tool`, `execute_sub_agent_tool`, `create_sub_agent_tool`, `get_sub_agent_results_tool`, **pas** `delegate_to_sub_agent_tool`) → **bug latent à corriger**.
5. **Exécuter** :
   ```python
   runner = ReactSubAgentRunner("subagent", "subagent_react_prompt")
   react_result = await runner.run(
       task=instruction,
       tools=read_only_tools,
       prompt_vars={"expertise": expertise},
       parent_runtime=runtime,
       thread_prefix="subagent",
       recursion_limit=settings.subagent_default_max_iterations,   # cf. §4.8
       display_name=f"sub-agent: {expertise[:40]}",
   )
   ```
   Pas de `TrackingContext` dédié, pas de garde‑token callback, pas de budget journalier (cf. §4.5) : les tokens sont attribués au tracker parent via `node_name_override`, la borne dure est `recursion_limit`, et `max_tokens` du LLM `subagent` (10 K) borne la complétion par appel.
6. **Retour** :
   ```python
   summary = react_result.final_message[:200] + "…" if len(react_result.final_message) > 200 else react_result.final_message
   return UnifiedToolOutput.action_success(
       message=summary,
       structured_data={"analysis": react_result.final_message, "expertise": expertise, "type": "sub_agent_analysis"},
       metadata={"expertise": expertise, "duration_ms": react_result.duration_ms,
                 "iteration_count": react_result.iteration_count},
   )
   ```
   Sur erreur (`react_result.final_message.startswith("Error:")`, ou `GraphRecursionError` capté par le runner) → `UnifiedToolOutput.failure(...)` avec un message exploitable par le `response_node` (« le sous‑agent expert *X* n'a pas pu aboutir : … ; voici ce qu'il a produit : … »). Le `accumulated_registry` éventuel (widgets MCP/skills riches) est propagé via le mécanisme `registry_tool_output_detected` du `parallel_executor` (vérifier que `UnifiedToolOutput` + `accumulated_registry` se relient — c'est déjà le cas pour `mcp_server_task_tool`).

**Conséquences :**
- **Plus de record ORM `SubAgent` éphémère** créé/supprimé à chaque délégation du planner. La table `sub_agents` n'est plus alimentée par cette voie (elle reste pour les sous‑agents *persistants* utilisateur, cf. §6).
- **Plus de consolidation manuelle des tokens** : les appels LLM du sous‑agent traversent le `TokenTrackingCallback` du parent (propagé par `ReactSubAgentRunner`) avec `node_name_override = "sub-agent: <expertise>"` → attribution automatique dans le `MessageTokenSummary` du tour courant, coût SSE inclus. ⚠️ **À vérifier** : que le `TokenTrackingCallback` lit bien `metadata["node_name_override"]` (le commentaire de `react_runner` l'affirme ; confirmer par lecture de `infrastructure/observability/callbacks.py`).
- **Plus de budget journalier** sur la voie éphémère (le check/incrément Redis `subagent_daily_budget:{user_id}` n'est plus appelé ici) — décision validée : la borne `recursion_limit` + le veto H1 + le cap `instruction` suffisent ; le budget journalier reste appliqué sur la voie persistante (qui passe encore par `SubAgentExecutor`). Voir §8.
- `SubAgentExecutor`, `_analyze_instruction`, `_synthesize_results`, `subagent_synthesis_prompt.txt`, `SUBAGENT_SYNTHESIS_PROMPT_NAME`, `SUBAGENT_EXCLUDED_PLANNER_TOOLS` **ne sont plus utilisés par `delegate_to_sub_agent_tool`** — mais cf. §6 : ils restent référencés par la voie persistante (`POST /sub-agents/{id}/execute`, `execute_background`, le job `recover_stale_subagents`). **On ne les supprime PAS en Phase 1.** (Suppression = candidat Phase 2 une fois la voie persistante migrée ou retirée.)

### 4.2 Nouveau prompt `subagent_react_prompt.txt`

Fichier : `apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt` (nouveau).
Enregistrer le nom dans le `Literal PromptName` (`apps/api/src/domains/agents/prompts/prompt_loader.py`, ligne ~67‑125) : ajouter `"subagent_react_prompt"`. (Ne **pas** retirer `"subagent_synthesis_prompt"` du Literal en Phase 1 — encore utilisé par la voie persistante. Le retirera la Phase 2.)

Contenu (s'inspirer de `browser_agent_prompt.txt` / `mcp_react_agent_prompt.txt` pour le scaffold ReAct, et de `SUBAGENT_READ_ONLY_PREFIX` pour la contrainte) :
- Préambule : « Tu es un sous‑agent expert focalisé sur **une tâche unitaire**. Tu travailles de façon autonome avec un jeu d'outils **read‑only** ; tu ne peux ni envoyer, ni créer, ni modifier, ni supprimer. »
- Slot `{expertise}` : « Ton domaine d'expertise et tes directives : {expertise} »
- Slot `{current_datetime}` : injecté automatiquement par `ReactSubAgentRunner`.
- Consignes ReAct : utiliser les outils pour récupérer les informations nécessaires, raisonner, puis produire **un texte analytique condensé et factuel** (pas de salutations, pas de mise en forme décorative, inclure tous les points de données pertinents — chiffres, dates, noms, URLs, prix ; noter ce qui manque si un outil échoue ; répondre dans la langue de la tâche). Reprendre l'esprit des RULES de l'actuel `subagent_synthesis_prompt.txt` mais formulées pour une boucle agentique.
- Anti‑récursion : « tu ne peux pas déléguer à un autre sous‑agent. »

### 4.3 H1 — enforcement du « quand déléguer »

#### 4.3.1 Réécriture de `{sub_agents_section}` du prompt planner

Fichier : `apps/api/src/domains/agents/services/smart_planner_service.py`, méthode `_build_sub_agents_section()` (lignes ~953‑1003). Réécrire la section pour énoncer le **test H1** de façon nette et opérationnelle :
- « Délègue à un sous‑agent **uniquement si** une persona experte spécialisée produirait une réponse **matériellement meilleure** que toi avec tes outils normaux (analyse comptable/juridique/technique pointue, comparaison multi‑critères poussée, plusieurs pistes de recherche indépendantes à mener en parallèle). »
- « **Sinon, fais‑le toi‑même** : récupérer/lire des données et les résumer, lookups simples, opérations CRUD, tâches mono‑outil — n'utilise PAS `delegate_to_sub_agent_tool`. »
- « Un sous‑agent = **une tâche unitaire experte**. Ne lui passe pas de gros volume de données : il a ses propres outils read‑only et va chercher ce dont il a besoin. **N'écris pas** de référence `$steps.X.<données brutes>` dans `instruction` — au plus un petit identifiant ou la sortie `analysis` d'un autre sous‑agent. »
- « Sous‑agents indépendants → `depends_on` vide (parallèle). Chaînage A→B autorisé via `$steps.step_A.analysis`. »
- **Retirer** la phrase « ALWAYS set timeout_seconds: 120 for delegate steps » (cf. §4.6).
- Conserver/renforcer la section « AVOID DUPLICATING SUB‑AGENT WORK » (BAD: fetch+delegate / GOOD: delegate('research X')).

(Le `smart_planner_multi_domain_prompt.txt` référence aussi `{sub_agents_section}` — même substitution, rien à changer côté template.)

#### 4.3.2 Veto structurel dans le `semantic_validator`

Fichier : `apps/api/src/domains/agents/orchestration/semantic_validator.py`. Ajouter un check (nouveau `SemanticIssueType`, ex. `POINTLESS_SUB_AGENT_DELEGATION`) appliqué après les checks for_each existants :

**Condition de veto** (la délégation est présumée ne PAS satisfaire H1) :
- le plan contient ≥ 1 `delegate_to_sub_agent_tool` step ; **et**
- il y a **exactement 1** `delegate` step (pas de fan‑out — 2+ délégations parallèles vers des experts différents *sont* présumées légitimes, cf. l'exception déjà présente dans `validate_for_each_patterns` Check 1) ; **et**
- le `query_intelligence` a **un seul domaine réel** (`primary_domain` + `secondary_domains` vide, en ne comptant pas le pseudo‑domaine `sub_agent`) ; **et**
- le plan n'a **aucune** autre step substantielle que cette délégation et d'éventuelles steps de fetch que le planner a ajoutées *pour la délégation* (heuristique : nombre de `TOOL` steps ≤ 2, et la seule step « finale » est la délégation) — c.‑à‑d. la délégation **est** l'essentiel du travail.

**Action quand le veto se déclenche** : router vers `planner` avec `STATE_KEY_NEEDS_REPLAN = True` et `STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS = True` (mécanisme F6 existant : `planner_node_v3` lit `exclude_sub_agent_tools` et exclut `delegate_to_sub_agent_tool` du catalogue ; `_build_sub_agents_section` lit le ContextVar `exclude_sub_agents_from_prompt` et renvoie `""`). Le planner re‑génère un plan sans délégation (ici : `[get_emails_tool]` → `response_node` résume). Logger un événement `semantic_validator_vetoed_sub_agent_delegation` avec la query, les domaines, le nombre de steps.

**Kill-switch `.env`** : le veto est entièrement gouverné par un feature flag `subagent_veto_pointless_enabled: bool = Field(default=True, ...)` dans `config/agents.py` (env var `SUBAGENT_VETO_POINTLESS_ENABLED`). À `false` → le veto ne se déclenche jamais (le check n'est même pas évalué). Permet de désactiver l'heuristique en prod sans rebuild si elle produit des faux positifs observés.

⚠️ **Risque assumé — faux positifs.** Une tâche mono‑domaine, mono‑outil peut légitimement bénéficier d'une persona experte (ex. « rédige un brouillon d'email juridiquement carré sur X » → un seul outil de génération mais l'expertise juridique aide). L'heuristique va la vetoer. **Mitigations** : (a) commencer conservateur (le veto ne s'applique que si **toutes** les conditions sont réunies, y compris « la délégation est l'essentiel du travail ») ; (b) métrique + log à chaque déclenchement pour observer le taux et ajuster ; (c) la version 2 (hors périmètre) pourrait remplacer l'heuristique par un signal amont du `QueryAnalyzer`. À discuter en relecture si l'on veut un seuil plus permissif d'entrée de jeu.

**Plomberie** : vérifier que `route_from_semantic_validator` (`nodes/routing.py` ~374‑501) sait router vers `planner` quand `needs_replan` est posé (il le sait déjà pour le cas clarification → re‑plan). Vérifier qu'aucune boucle infinie n'est possible : après le re‑plan, `planner_node_v3` doit *clear* `needs_replan` (il le fait déjà : `should_clear_needs_replan`) ; et comme `exclude_sub_agent_tools=True` est conservé pendant ce re‑plan, le nouveau plan ne peut pas re‑déclencher le veto. Confirmer que `exclude_sub_agent_tools` est bien clearé après (ou laissé — pas grave, c'est un état de tour).

### 4.4 H2 — borne de `instruction` après résolution des `$ref`

Fichier : `apps/api/src/domains/agents/orchestration/parallel_executor.py`, fonction `_execute_tool_step` (ligne ~2118), juste après l'appel à `_resolve_step_references` (ligne ~2275, avant l'exécution du tool).

**Règle** : si `step.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT` et que la taille en **tokens** de `resolved_args.get("instruction", "")` dépasse un cap dur → la step échoue (`StepResult(success=False, error_code=ToolErrorCode.INVALID_INPUT, error="Sub-agent instruction too large after reference resolution (N tokens > cap M) — likely a $steps reference to a raw payload; the planner should pass a task statement, not data.")`).

**Unité = tokens** (cohérent avec l'unité de mesure du projet). Utiliser l'estimateur de tokens déjà en place dans le codebase (celui utilisé par `smart_planner` pour son `token_estimate`, ou le tokenizer/heuristique partagé — à identifier en implémentation ; à défaut, heuristique conservatrice `len(text) // 4` puis remplacer par un comptage exact si un tokenizer est dispo).

**Cap = paramétrable via `.env`** (règle projet : toute valeur ajustable passe par un Settings field, pas une constante en dur seule) :
- défaut dans `apps/api/src/core/constants.py` : `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT = 3_000` ;
- champ Settings dans `apps/api/src/core/config/agents.py` : `subagent_instruction_max_tokens_resolved: int = Field(default=SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT, ge=500, le=20_000, description="Hard cap (tokens) on the resolved `instruction` of `delegate_to_sub_agent_tool` after $steps reference expansion. Above this, the step fails with INVALID_INPUT — prevents the planner from shoving raw data payloads into a sub-agent.")` ;
- `.env.example` (et `.env.prod.example`) : ligne `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000` documentée ;
- le code lit `settings.subagent_instruction_max_tokens_resolved`. La valeur 3 000 est cohérente avec le `max_length=5000` chars du manifest qui était censé borner ça (relâché juste ce qu'il faut pour une `instruction` riche + une éventuelle sortie `analysis` chaînée).

**Effet** : `$steps.step_1.<emails-html>` résolu → ~450 Ko → dépasse → step en erreur. Le `task_orchestrator` → `response_node` synthétise alors à partir de ce qui est dans le registre (les emails de `step_1`) → réponse correcte, coût ~17‑25 K. (Optionnel : à terme, faire en sorte que cette erreur déclenche aussi le re‑plan `exclude_sub_agent_tools` plutôt que de juste tomber sur le `response_node` — mais le `response_node` suffit fonctionnellement et c'est plus simple ; à trancher en relecture.)

**Compatibilité H2** : zéro restriction sur `depends_on`. Une `delegate` step qui dépend d'une autre `delegate` step via `$steps.step_A.analysis` passe (un `analysis` est du texte synthétisé court). Seul un `$ref` vers une **donnée brute volumineuse** est tué — c'est exactement le bug.

**Note** : on **ne** modifie **pas** le `ReferenceResolver` lui‑même (pas de troncature silencieuse dans `_format_resolved_value` — ce serait un workaround qui masquerait le problème). La borne est un *contrôle de validité explicite* au point où la taille réelle est connue (post‑résolution), avec une erreur claire qui pointe la cause.

### 4.5 Garde‑consommation (vide #3) — borne par `recursion_limit`, pas de callback

**Décision validée** : pas de garde‑token par callback en Phase 1. La borne dure est **`recursion_limit`** du `create_react_agent` (cf. §4.8) — natif, infranchissable, capté proprement (`GraphRecursionError` → `try/except` de `ReactSubAgentRunner.run` → `ReactSubAgentResult(final_message="Error: …")`). En complément, `max_tokens=10000` du LLM type `subagent` borne la **complétion par appel**. Le scénario qui a explosé (114 K tokens d'`instruction` ré‑injectés ×3) est tué en amont par le cap `instruction` (§4.4) et le veto H1 (§4.3.2) ; au pire, une boucle ReAct de `recursion_limit` supersteps avec `instruction` bornée à ~3 K tokens reste de l'ordre de quelques dizaines de K tokens.

Conséquences :
- `apps/api/src/domains/sub_agents/token_guard.py` (`SubAgentTokenGuard`) reste **inchangé et toujours dormant** — candidat à un câblage ultérieur si l'observation montre que `recursion_limit` ne suffit pas. À mentionner dans `SUB_AGENTS.md`.
- **Pas d'extension** de `ReactSubAgentRunner.run` (`extra_callbacks`) — non nécessaire.
- `subagent_max_token_budget` (settings) reste défini mais n'est appliqué que sur la voie persistante (via `SubAgentExecutor`). Il sert de knob pour un futur garde ; documenté comme tel.

### 4.6 Quick win — retrait de `timeout_seconds` du prompt planner

`{sub_agents_section}` (`smart_planner_service._build_sub_agents_section`) dit « ALWAYS set timeout_seconds: 120 for delegate steps ». Or `delegate_to_sub_agent_tool` n'a **pas** de paramètre `timeout_seconds` (manifest : `expertise`, `instruction`) → le `parallel_executor` le strippe (`tool_hallucinated_params_stripped`) et le validator logge `INVALID_PARAM_VALUE: Unknown parameter 'timeout_seconds'`. → **Retirer cette ligne du prompt.** (Le timeout du sous‑agent est désormais géré par `recursion_limit` + le garde‑token ; pas besoin de l'exposer au planner.) Inclus dans la réécriture §4.3.1.

### 4.7 Renommage du label LLM type

Fichier : `apps/api/src/domains/llm_config/constants.py`, entrée `"subagent"` de `LLM_TYPES_REGISTRY` (~ligne 428) : `display_name="Sub-Agent"` → `display_name="Sub-Agent (ReAct)"` (cohérent avec `mcp_react_agent` = `"MCP Iterative (ReAct)"`). **L'`llm_type="subagent"` (id interne) ne change pas** — sinon ça casse les lignes de config en base, les overrides ORM, les références code.

i18n : la clé `settings.admin.llmConfig.types.subagent` (description) doit être mise à jour dans **les 6 locales** (`apps/web/locales/{en,fr,de,es,it,zh}/translation.json`, dans `settings.admin.llmConfig.types`) : remplacer « Executes delegated tasks via specialized sub‑agents (research, analysis, synthesis) » / « Exécute les tâches déléguées via des sous‑agents spécialisés (recherche, analyse, synthèse) » par une formulation reflétant la boucle ReAct cadrée (ex. en : « Runs a scoped ReAct loop (read‑only tools, tight iteration & token budget) for the planner's expert delegations »). Le hook pre‑commit impose la parité des clés — aucune clé ajoutée/retirée ici, juste des valeurs modifiées, donc parité préservée.

La config par défaut (`LLM_DEFAULTS["subagent"] = LLMAgentConfig(provider="qwen", model="qwen3.5-plus", temperature=0.2, max_tokens=10000, timeout_seconds=60.0, reasoning_effort disabled)`) reste valable pour une boucle ReAct ; `max_tokens=10000` = max **par appel** (raisonnable). Pas de changement requis, mais le mentionner dans `SUB_AGENTS.md`.

### 4.8 Configuration — `recursion_limit` du sous‑agent ReAct

**Décision validée** : réutiliser le setting existant `subagent_default_max_iterations` (`apps/api/src/core/config/agents.py`, défaut `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT = 5`, `ge=1, le=15`) comme `recursion_limit` passé à `ReactSubAgentRunner.run`. C'est cohérent avec le pattern du codebase (`browser_react_max_iterations` / `mcp_react_max_iterations` sont passés bruts comme `recursion_limit`). **Aucun nouveau setting**, aucune ligne `.env` ajoutée.

⚠️ **À noter** : `create_react_agent`'s `recursion_limit` compte les *supersteps* du graphe (~2 par tour d'outil : 1 appel LLM + 1 exécution d'outil). Donc défaut = 5 ⇒ ≈ 2 tours d'outils + 1 réponse finale. C'est volontairement serré (« tâche unitaire simple », H3) mais potentiellement trop pour certaines délégations légitimes (recherche multi‑pistes). Les précédents (`browser`/`mcp` = 10) suggèrent qu'on pourrait vouloir bumper le défaut de `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` de 5 à ~8‑10 — **point ouvert §11**. (Si on bumpe : seul `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` dans `core/constants.py` change ; le champ config et `.env*` ont déjà la borne `le=15`.)

---

## 5. Inventaire exhaustif des fichiers touchés

**Backend — modifications :**
- `apps/api/src/domains/agents/tools/sub_agent_tools.py` — réécriture du corps de `delegate_to_sub_agent_tool` (→ `ReactSubAgentRunner` ; plus de record ORM, plus de budget journalier, plus de garde‑token).
- `apps/api/src/domains/sub_agents/skill_resolver.py` — ajouter `delegate_to_sub_agent_tool` (constante `TOOL_NAME_DELEGATE_SUB_AGENT`) au set d'exclusion de `resolve_tools_for_subagent` (bug latent).
- `apps/api/src/domains/agents/services/smart_planner_service.py` — réécriture de `_build_sub_agents_section()` (test H1, retrait `timeout_seconds`).
- `apps/api/src/domains/agents/orchestration/semantic_validator.py` — nouveau check « pointless sub‑agent delegation » + nouveau `SemanticIssueType` ; intégration au flux de validation et au routage vers re‑plan.
- `apps/api/src/domains/agents/orchestration/parallel_executor.py` — borne `instruction` (en tokens) post‑résolution dans `_execute_tool_step`.
- `apps/api/src/domains/agents/prompts/prompt_loader.py` — ajouter `"subagent_react_prompt"` au `Literal PromptName`.
- `apps/api/src/domains/llm_config/constants.py` — `display_name` de `"subagent"` → `"Sub-Agent (ReAct)"`.
- `apps/api/src/core/constants.py` — `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT = 3_000` ; (éventuellement bumper `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` 5→~8‑10 — point ouvert §11).
- `apps/api/src/core/config/agents.py` — ajouter `subagent_instruction_max_tokens_resolved` et `subagent_veto_pointless_enabled` (Settings fields, cf. §4.4 et §4.3.2).
- `apps/api/src/domains/agents/sub_agents/catalogue_manifests.py` — actualiser la description du manifest `delegate_to_sub_agent_catalogue_manifest` (préciser que `instruction` est borné après résolution ; cost profile `est_tokens_in` plus réaliste, ex. ~3000 ; conserver `hitl_required=True` même si non câblé — c'est le contrat, pas le bug).

**Backend — créations :**
- `apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt` — scaffold ReAct + `{expertise}` + contraintes read‑only.

**Backend — NON modifiés / NON supprimés en Phase 1** : `apps/api/src/domains/agents/tools/react_runner.py` (réutilisé tel quel — pas d'`extra_callbacks`) ; `apps/api/src/domains/sub_agents/token_guard.py` (`SubAgentTokenGuard` reste dormant) ; `sub_agents/executor.py` (`SubAgentExecutor`, `_analyze_instruction`, `_synthesize_results`, `_format_completed_steps` — référencés par la voie persistante `/sub-agents/{id}/execute`, `execute_background`, job `recover_stale_subagents`), `prompts/v1/subagent_synthesis_prompt.txt`, `SUBAGENT_SYNTHESIS_PROMPT_NAME`, `SUBAGENT_EXCLUDED_PLANNER_TOOLS`, le budget journalier Redis `subagent_daily_budget:*` (utilisé par `SubAgentExecutor`). → candidats Phase 2.

**Frontend :**
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — mise à jour de la valeur `settings.admin.llmConfig.types.subagent` (description). (Aucune clé ajoutée/retirée → parité OK.)

**Config / env :**
- `.env.example` et `.env.prod.example` — ajouter `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED=3000` et `SUBAGENT_VETO_POINTLESS_ENABLED=true` (commentés + documentés). Pas d'ajout à `.env.min.prod` (settings optionnels avec défauts).
- `subagent_default_max_iterations` (déjà existant, `.env` = `SUBAGENT_DEFAULT_MAX_ITERATIONS`) est réutilisé tel quel pour le `recursion_limit` du sous‑agent ReAct.

**Docs :**
- `docs/technical/SUB_AGENTS.md` — réécrire les sections « Architecture » (pipeline = `ReactSubAgentRunner`, plus de mini‑pipeline pour les délégations éphémères), « Planner Integration », « Token Tracking » (consolidation auto via `node_name_override`), « V1 Known Limitations » (#1 token guard : maintenant branché ; ajouter une note sur le HITL passthrough), distinguer voie éphémère (planner) vs voie persistante (`/sub-agents`).
- `docs/INDEX.md`, `docs/architecture/ADR_INDEX.md` — ajouter une entrée ADR (cf. §10) ; `docs/ARCHITECTURE_AGENT.md` / `docs/architecture_langraph.md` si la délégation y est décrite.
- ADR à rédiger (cf. §10).

**Tests** (cf. §9) : `apps/api/tests/unit/domains/sub_agents/` (adapter `test_sub_agent_tools.py`, `test_semantic_validator_subagent.py`, `test_f6_prompt_suppression.py`, `test_approval_gate_fallback.py` ; ajouter des tests pour le veto, la borne `instruction`, le garde‑token, le runner ReAct du sous‑agent).

---

## 6. Pourquoi on ne touche pas `SubAgentExecutor` en Phase 1 — explication

Le domaine `sub_agents` sert **deux choses différentes** qui, aujourd'hui, partagent le **même moteur d'exécution** (`SubAgentExecutor` + son mini‑pipeline `_analyze_instruction → SmartPlannerService → execute_plan_parallel → _synthesize_results`) :

1. **La voie « éphémère » — la délégation du planner** : `delegate_to_sub_agent_tool(expertise, instruction)`. Le planner décide à la volée de créer un expert jetable. **C'est ce qui a explosé, et c'est tout ce que ce chantier corrige.**
2. **La voie « persistante » — les sous‑agents définis par l'utilisateur** : l'API REST `/sub-agents` (CRUD), les templates pré‑définis (`research_assistant`, `writing_assistant`, `data_analyst`), la table `sub_agents`, `POST /sub-agents/{id}/execute` (synchrone), `execute_background` (asynchrone + notification), le job APScheduler `recover_stale_subagents`, le `last_execution_summary` réinjecté, les overrides par sous‑agent (`llm_provider`/`llm_model`/`llm_temperature`, `skill_ids`, `allowed_tools`). Le planner **ne** délègue **jamais** à un de ces sous‑agents nommés aujourd'hui.

**Phase 1 = on débranche la voie #1 du moteur partagé** (`delegate_to_sub_agent_tool` appelle désormais `ReactSubAgentRunner`) **et on laisse la voie #2 telle quelle** (elle continue d'utiliser `SubAgentExecutor`). Donc, après Phase 1, **`SubAgentExecutor` existe toujours** — il n'est plus appelé que par la voie #2. On a temporairement **deux moteurs** : ReAct pour les délégations du planner, bespoke pour les sous‑agents persistants.

Pourquoi ce découpage et pas « tout migrer maintenant » :
- La voie #2 n'est pas ce qui a causé l'incident.
- La migrer proprement demande de gérer les **overrides de modèle par instance** (un sous‑agent persistant peut avoir son propre `llm_model`), ce que `ReactSubAgentRunner` ne sait pas faire aujourd'hui (`get_llm(llm_type)` → pas d'override) — c'est un sous‑chantier à part entière.
- C'est aussi l'occasion de décider du **sort de la voie #2** (la garder/l'enrichir/la retirer si elle est de facto inutilisée) — décision produit, pas technique, à prendre séparément.

→ Migration de la voie #2 (et suppression de `SubAgentExecutor` & co) = **Phase 2**, hors de ce spec. Ne pas tenter de tout faire d'un coup — c'est exactement ce qui a fait partir la discussion initiale en vrille.

**La question qu'il me faut confirmer auprès de toi (point ouvert §11.6)** : es‑tu d'accord avec ce découpage (Phase 1 = voie #1 seulement, deux moteurs coexistants temporairement), ou tu veux qu'on traite aussi la voie #2 maintenant, ou que je vérifie d'abord si la voie #2 est encore réellement utilisée (auquel cas Phase 2 = la supprimer plutôt que la migrer) ?

---

## 7. Effets attendus (chiffrés)

| Scénario | Avant | Après Phase 1 |
|---|---|---|
| « résume mes 5 derniers emails de ma femme » (le planner ne devrait plus déléguer — veto H1) | 485 930 tk / 0,56 € / 95 s | `[get_emails_tool] → response` ≈ **12‑15 K tk** (re‑plan inclus : ~20 K si le veto se déclenche après un premier plan) |
| Si malgré tout une délégation mono‑outil passe (faux négatif du veto), avec un `$steps.X.<données>` dans `instruction` | (idem) | borne `instruction` → step en erreur → `response_node` synthétise depuis le registre ≈ **~20 K tk** |
| Délégation **légitime** bien formée (fan‑out de 2 experts, recherche multi‑pistes) | 3 appels LLM internes ×N (~150 K+ par sous‑agent) | boucle ReAct cadrée : nombre d'appels LLM borné par `recursion_limit` (≈ `subagent_default_max_iterations`), `instruction` ≤ ~3 K tokens, `max_tokens` du LLM = 10 K par complétion → worst‑case de l'ordre de quelques dizaines de K tokens par sous‑agent ; `est_tokens_in` du manifest redevient réaliste |

---

## 8. Hors périmètre (explicitement)

- **#5 HITL de délégation** — **confirmé : on laisse le passthrough.** `approval_gate_node` reste inchangé. Re‑activation = suivi éventuel, **conditionnée** à H1 (sinon agaçant). Le code F6 (`_build_approval_request`, `test_approval_gate_fallback.py`, doc « HITL Rejection Fallback ») reste en place mais dormant.
- **Budget journalier de tokens (`subagent_max_total_tokens_per_day`)** — **confirmé : retiré de la voie éphémère.** Plus de check/incrément Redis dans `delegate_to_sub_agent_tool`. Il reste appliqué sur la voie persistante (via `SubAgentExecutor._check_daily_budget`/`_increment_daily_budget`). La protection de la voie éphémère = `recursion_limit` + veto H1 + cap `instruction`.
- **Garde‑token par exécution par callback** — non câblé en Phase 1 (cf. §4.5) ; borne = `recursion_limit`. `SubAgentTokenGuard` reste dormant.
- **Migration de la voie persistante** (`/sub-agents/{id}/execute`, `execute_background`, templates) vers `ReactSubAgentRunner` — Phase 2 (cf. §6).
- **Suppression de `SubAgentExecutor`** & co (`_analyze_instruction`, `_synthesize_results`, `subagent_synthesis_prompt.txt`, `SUBAGENT_SYNTHESIS_PROMPT_NAME`, `SUBAGENT_EXCLUDED_PLANNER_TOOLS`) — Phase 2 (après migration de la voie persistante).
- **Décision sur le sort de l'API `/sub-agents`** (la garder/l'enrichir/la retirer) — hors sujet ici, à voir en Phase 2.
- **Incohérences pré‑existantes des templates** (`data_analyst.suggested_tools` cite `search_emails_tool`/`get_email_details_tool` alors que le tool réel est `get_emails_tool` ; à vérifier) — à traiter à part, pas un blocage de ce chantier.
- **Refonte du `ReferenceResolver`** (borne générique sur toutes les substitutions) — non ; on borne uniquement `instruction` de `delegate_to_sub_agent_tool` au bon endroit.

---

## 9. Stratégie de tests

- **Unitaires `sub_agents`** :
  - `delegate_to_sub_agent_tool` : appelle bien `ReactSubAgentRunner` avec `llm_type="subagent"`, `prompt_name="subagent_react_prompt"`, `prompt_vars={"expertise": ...}`, `tools` = jeu read‑only filtré, `recursion_limit = settings.subagent_default_max_iterations`, `display_name="sub-agent: …"` ; mappe `final_message` → `structured_data["analysis"]` ; gère le cas erreur (`final_message` commençant par `"Error:"`) → `UnifiedToolOutput.failure` ; check préférence utilisateur `sub_agents_enabled` (→ `FEATURE_DISABLED`). **Ne crée plus** de record ORM, **n'appelle plus** le budget journalier.
  - `resolve_tools_for_subagent` exclut `delegate_to_sub_agent_tool` (en plus des `*_sub_agent_tool` existants) et les tools de `SUBAGENT_DEFAULT_BLOCKED_TOOLS`.
- **Unitaires `semantic_validator`** : veto déclenché pour `[get_emails, delegate]` mono‑domaine sans fan‑out → `needs_replan=True`, `exclude_sub_agent_tools=True` ; **non** déclenché pour `[delegate_a, delegate_b]` (fan‑out) ; **non** déclenché pour un plan multi‑domaines ; pas de boucle (le re‑plan suivant, avec `exclude_sub_agent_tools=True`, ne peut pas re‑déclencher le veto).
- **Unitaires `parallel_executor`** : `_execute_tool_step` pour `delegate_to_sub_agent_tool` avec `instruction` résolu > `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED` → `StepResult(success=False, INVALID_INPUT)` ; ≤ cap → exécution normale ; comptage en tokens (vérifier l'estimateur utilisé).
- **Unitaires `smart_planner`** : `_build_sub_agents_section()` ne contient plus `timeout_seconds` et contient le test H1 ; retourne `""` quand `sub_agents_enabled=False` ou `exclude_sub_agents_from_prompt=True` (régression couverte par `test_f6_prompt_suppression.py`).
- **Unitaires `llm_config`** : `LLM_TYPES_REGISTRY["subagent"].display_name == "Sub-Agent (ReAct)"` ; `test_llm_defaults_compliance` toujours vert ; i18n parity (les 6 locales ont la clé `...types.subagent`).
- **Régression** : `test_approval_gate_fallback.py` (HITL passthrough inchangé) reste vert ; vérifier que les tests existants de `test_sub_agent_tools.py` qui s'appuyaient sur le record ORM / `SubAgentExecutor` sont adaptés (ou que ces aspects sont déplacés vers des tests de la voie persistante).
- **Marqueurs** : `@pytest.mark.unit` ; pas d'intégration nécessaire (pas de DB ni de Redis pour la voie éphémère après refonte ; `ReactSubAgentRunner.run` mocké). Respecter `asyncio_mode = "auto"`.
- **Pré‑commit / CI** : `task pre-commit` (black, ruff, mypy strict, fast unit tests, i18n parity, eslint, tsc) doit passer. Vérifier le démarrage runtime via le conteneur Docker dev (`task dev:detach` puis health) — ne pas se contenter des linters/tests.

---

## 10. ADR & traçabilité

Rédiger un ADR (n° suivant dans `docs/architecture/`) — « Sub‑agent delegation as a parameterized ReAct loop, with structural over‑delegation veto and post‑resolution instruction bound » — décision : (a) le sous‑agent (voie éphémère) = `ReactSubAgentRunner` paramétré (`subagent` LLM type, prompt `subagent_react_prompt`, tools read‑only, `recursion_limit = subagent_default_max_iterations`) ; (b) veto `semantic_validator` sur les délégations non justifiées par l'expertise (H1) ; (c) borne dure (en tokens) de `instruction` après résolution des `$ref` (H2) ; (d) borne de coût d'une exécution = `recursion_limit` (le garde‑token callback et le budget journalier ne s'appliquent plus à la voie éphémère) ; (e) conserver le LLM type `subagent`, renommé « Sub‑Agent (ReAct) » en affichage ; (f) HITL de délégation et voie persistante hors périmètre (Phase 2). Référencer l'incident du 2026‑05‑12. Mettre à jour `docs/architecture/ADR_INDEX.md` et `docs/INDEX.md`.

---

## 11. Points ouverts / décisions à confirmer en relecture

**Tranchés (intégrés au design ci‑dessus)** :
- ✅ Cap `instruction` post‑résolution : **en tokens** (`SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED = 3_000`).
- ✅ `recursion_limit` du sous‑agent : **réutiliser `subagent_default_max_iterations`** (pas de nouveau setting).
- ✅ Garde‑token : **pas de callback en Phase 1** — borne = `recursion_limit` (+ `max_tokens` du LLM par appel). `SubAgentTokenGuard` reste dormant.
- ✅ Budget journalier : **retiré de la voie éphémère** (reste sur la voie persistante).
- ✅ HITL : **on garde le passthrough** (hors périmètre).

**Encore à confirmer** :
1. **Valeur du cap `instruction`** : 3 000 tokens — ok ? (rappel : laisse passer une instruction riche + une sortie `analysis` chaînée ; tue un `$ref` vers des données brutes).
2. **Défaut de `subagent_default_max_iterations`** : actuellement 5 ⇒ ≈ 2 tours d'outils comme `recursion_limit` ReAct. Volontairement serré (H3 « tâche unitaire ») mais les précédents browser/mcp = 10. On le laisse à 5, ou on bumpe à ~8‑10 ? (Si bumpé : seul `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` change ; champ config `le=15` inchangé.)
3. **Veto H1 — agressivité** : l'heuristique « mono‑domaine + exactement 1 `delegate` + pas de fan‑out + la délégation est l'essentiel du travail » — assez conservatrice (risque faux positifs faible) ? Ou seuil plus permissif d'entrée de jeu, quitte à resserrer après observation des métriques ? **Et** : la borne `instruction` (§4.4), quand elle se déclenche, doit‑elle aussi forcer un re‑plan `exclude_sub_agent_tools`, ou laisser le `response_node` rattraper depuis le registre suffit (plus simple) ?
4. **Découpage Phase 1 / Phase 2** (cf. §6) : OK pour ne toucher que la voie éphémère en Phase 1 (deux moteurs coexistants temporairement) ? Ou tu veux que je vérifie d'abord si la voie persistante (`/sub-agents`) est réellement utilisée (→ Phase 2 = la supprimer plutôt que la migrer) ?
