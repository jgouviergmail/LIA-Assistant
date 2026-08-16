# LLMCallsWithoutUsage — Runbook

**Sévérité** : warning
**Composant** : agents
**Impact** : la dépense des appels concernés n'a atteint **aucun grand livre** :
pas de ligne `token_usage_logs`, pas de contribution au `token_summary`, et le
plafond de dépense quotidien de l'instance (ADR-216) ne l'a pas vue. Sur un
provider payant, c'est de l'argent dépensé sans trace.

---

## Définition

```promql
sum by (node_name) (increase(llm_calls_without_usage_total[1h])) > 0
```

Le seuil zéro est volontaire : aucun appel payant ne doit se terminer sans
comptage. Le compteur est incrémenté par `MetricsCallbackHandler.on_llm_end`
quand le `LLMResult` ne porte aucune métadonnée d'usage (ADR-220) ; le même
événement produit un log `llm_call_without_usage` en WARNING avec le
`node_name`.

### Pourquoi cette alerte existe

Un provider OpenAI-compatible n'émet l'objet `usage` en streaming que si la
requête le demande (`stream_options.include_usage`). La branche DeepSeek de
l'adaptateur a expédié des mois sans ce drapeau — la comptabilité n'a survécu
que parce que DeepSeek envoyait l'usage spontanément, un comportement que rien
ne garantissait. Le seul signal était un libellé `model="unknown"` et un log
DEBUG. Cette alerte transforme cette classe entière de trous silencieux en
signal exploitable.

---

## Diagnostic

### 1. Quel nœud, quel volume ?

```promql
sum by (node_name) (increase(llm_calls_without_usage_total[24h]))
```

Croiser avec les logs (`docker logs lia-api-prod | grep llm_call_without_usage`)
pour le contexte, et avec la part d'appels non identifiés :

```promql
sum(rate(llm_api_calls_total{model="unknown"}[1h]))
```

### 2. Quel provider sert ce nœud ?

Réglages Administration → Configuration LLM (ou `LLM_DEFAULTS` +
`llm_config_overrides`). Trois cas :

- **Provider `stream_usage_flag`** (openai, qwen, deepseek) : le client est
  construit avec `stream_usage=True` — si l'usage manque quand même, le
  fournisseur a changé de comportement d'API ou un proxy intermédiaire
  l'écrase. Vérifier `PROVIDER_USAGE_CAPABILITIES`
  (`domains/llm_config/constants.py`) et la version du SDK.
- **Provider `native`** (anthropic, gemini) : l'usage arrive par le SDK sans
  demande — un manque signale une montée de version du SDK qui a changé la
  forme des métadonnées. Vérifier `TokenExtractor`.
- **Provider `excluded`** (ollama local, perplexity sur clé utilisateur) : un
  emplacement routé dessus PEUT déclencher cette alerte — c'est exact (les
  tokens ne sont pas comptés) et accepté (la dépense n'est pas imputable à
  LIA). Acquitter si l'affectation est volontaire.

### 3. Le garde-fou de boot

`validate_provider_usage_capabilities` (ADR-220) refuse de démarrer si un
provider de chat n'a pas d'entrée au registre — un provider ajouté sans
déclarer son mode de comptage ne peut pas atteindre la production.

---

## Remédiation

- Nouvelle branche provider sans drapeau : ajouter `stream_usage=True` dans
  `ProviderAdapter._prepare_provider_config` (ou le constructeur dédié) et
  l'entrée `stream_usage_flag` au registre — les deux sont épinglés par
  `test_provider_usage_options.py`.
- Changement de comportement fournisseur : ouvrir un correctif sur
  `TokenExtractor` avec la nouvelle forme, en gardant le test de contrat.
- Affectation volontaire d'un provider `excluded` : documenter et acquitter.

## Historique

- **2026-08-16** — Alerte créée (ADR-220), à la suite du contre-audit « Tokens
  fantômes » : la branche deepseek n'a jamais demandé l'usage et rien ne
  l'avait signalé. Mesuré en prod avant correctif : 510/510 appels `response`
  comptés sur 30 j uniquement grâce à la générosité du fournisseur.
