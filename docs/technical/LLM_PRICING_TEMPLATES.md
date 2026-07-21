# LLM_PRICING_TEMPLATES — Reasoning shape templates dans l'admin Pricing

> **Mécanisme de saisie/édition de la "forme reasoning" lors de l'ajout d'un nouveau modèle LLM via la page d'administration "Tarification LLM Texte".**
>
> **Date** : 2026-05-06
> **Statut** : ✅ Livré (v1.19.x)
> **Tables impactées** : `llm_models` (colonnes `kind`, `is_reasoning_model`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`, `reasoning_doc_i18n_key`, `supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty` ajoutées dans T20/T21).

---

## 📖 Contexte

Avant cette refonte, ajouter un nouveau modèle reasoning depuis l'admin était fragile : l'admin pouvait cocher `is_reasoning_model = true` mais aucun mécanisme ne lui permettait de déclarer **quelle forme** d'API reasoning le modèle expose (enum string, budget int, toggle+budget, always-on). Conséquence : `reasoning_widget` restait à sa valeur par défaut `'none'`, le builder backend ne savait pas formater les requêtes, et l'UI Configuration LLM n'affichait pas le widget approprié.

La refonte introduit un mécanisme de **templates dynamiques** dérivés de la table `llm_models` : l'admin choisit "ce nouveau modèle se comporte comme tel modèle existant" plutôt que de saisir manuellement les ~9 colonnes de la forme reasoning + sampling.

---

## 🎯 Architecture

### Trois couches de données

Pour chaque ligne de `llm_models`, on distingue :

1. **Catalogue + capacités classiques** (saisis explicitement par l'admin) : `provider`, `model_name`, `kind`, `max_input_tokens`, `max_output_tokens`, `supports_tools`, `supports_structured_output`, `supports_strict_mode`, `supports_streaming`, `supports_vision`.

2. **Forme reasoning ("shape")** — 4 colonnes copiables depuis un template :
   - `is_reasoning_model: bool`
   - `reasoning_widget: enum('none','enum','budget_int','toggle_budget')`
   - `reasoning_enum_values: list[str] | None` (uniquement si widget=enum)
   - `reasoning_budget_range: jsonb | None` (uniquement si widget budget_int/toggle_budget)

3. **Indépendants du template (saisie directe par modèle)** :
   - `kind` (chat / image / audio / realtime / tts / embedding)
   - `supports_temperature` / `supports_top_p` / `supports_frequency_penalty` / `supports_presence_penalty`
   - `reasoning_doc_i18n_key` (clé i18n du tooltip — family-specific)

### Pourquoi cette séparation ?

Deux modèles peuvent **partager la même forme reasoning** mais déclarer des matrices sampling différentes (ex : OpenAI o-series et Anthropic 4.5+ exposent tous deux un `enum` widget mais OpenAI rejette toute température alors qu'Anthropic l'accepte). Inversement, deux modèles avec le même `kind` peuvent avoir des shapes reasoning radicalement différentes (Gemini 2.0 vs Gemini 2.5+).

Mettre `kind`, sampling caps et `reasoning_doc_i18n_key` dans le template aurait soit explosé le nombre de templates uniques (chaque combinaison croisée = un template), soit forcé à ignorer ces dimensions à la copie. Les sortir du template = chaque dimension indépendante peut varier librement.

---

## 🔍 Flux : ajouter un nouveau modèle reasoning

### Cas A — Le modèle suit une famille existante (95% des cas)

L'admin :
1. Saisit `provider`, `model_name`, `kind`, max tokens, capacités classiques.
2. Toggle `Is reasoning model` → ON.
3. Le Select **"Copy reasoning shape from..."** apparaît, peuplé via `GET /admin/llm/reasoning-templates`.
4. L'admin choisit le template représentatif de la famille (ex : `gpt-5` pour les OpenAI o-series / GPT-5 reasoning, `claude-opus-4-5` pour Anthropic 4.5+, `deepseek-v4-flash` pour DeepSeek V4, etc.).
5. Le panneau readonly affiche les 4 valeurs qui seront copiées (`widget`, `enum_values` ou `budget_range`, `is_reasoning_model`).
6. L'admin saisit indépendamment les 4 toggles sampling et le `reasoning_doc_i18n_key` (optionnel).
7. Soumission. Le service `LLMModelService.create()` :
   - Snapshot-copie les 4 colonnes shape depuis la ligne du template.
   - Persiste les autres colonnes depuis le payload.

### Cas B — Modèle "disrupt" (nouvelle API jamais vue)

L'admin :
1. Toggle `Is reasoning model` → ON.
2. Choisit "Custom (advanced)" dans le Select template.
3. Saisit manuellement `reasoning_widget` + `reasoning_enum_values` ou `reasoning_budget_range` selon le widget choisi.
4. Tout le reste comme dans le Cas A.
5. Soumission. Le service valide la cohérence widget × valeurs (`reasoning_widget='enum'` exige `enum_values` non-vide ; `'budget_int'`/`'toggle_budget'` exigent `budget_range`).

Une fois créé, ce modèle Custom devient **automatiquement disponible** comme template pour les futurs ajouts qui partageraient la même forme. L'ensemble des templates s'auto-enrichit.

### Cas C — Modèle non-reasoning

L'admin laisse `Is reasoning model` → OFF. Le Select template et le Custom block sont masqués. Le service force `reasoning_widget='none'`, `enum_values=null`, `budget_range=null`.

---

## ⚙️ Implémentation

### Backend

#### Endpoint

`GET /admin/llm/reasoning-templates` — retourne la liste dédupliquée des comportements présents en DB.

```python
class ReasoningTemplate(BaseModel):
    template_model_name: str
    representative_provider: ProviderLiteral
    description: str           # "enum [low/medium/high] — like claude-opus-4-5 (14 models)"
    matching_count: int
    is_reasoning_model: bool
    reasoning_widget: ReasoningWidgetLiteral
    reasoning_enum_values: list[str] | None
    reasoning_budget_range: ReasoningBudgetRange | None
```

Auth : `Depends(get_current_superuser_session)`.

#### Service — fingerprint dynamique

`LLMModelService.list_templates()` groupe les lignes actives de `llm_models` par leur **fingerprint** (4 colonnes shape) et retourne un représentant par groupe.

```python
# src/domains/llm/service.py
_TEMPLATE_FIELDS: tuple[str, ...] = (
    "is_reasoning_model",
    "reasoning_widget",
    "reasoning_enum_values",
    "reasoning_budget_range",
)

@staticmethod
def _fingerprint(row: LLMModel) -> tuple[Any, ...]:
    return tuple(
        LLMModelService._normalise_shape_value(getattr(row, field))
        for field in _TEMPLATE_FIELDS
    )
```

Le **représentant** est choisi de manière déterministe (`min(members, key=lambda m: m.model_name)`) pour qu'il reste stable entre deux invocations.

#### Schemas — XOR Template / Custom

`ModelPriceCreate` et `ModelPriceUpdate` exposent à la fois :
- `reasoning_template: str | None` (Template mode)
- `is_reasoning_model`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range` (Custom mode)

Un `model_validator(mode="after")` enforce l'XOR :
- Template mode : les 4 explicit fields **doivent** être absents.
- Custom mode : `is_reasoning_model` + `reasoning_widget` requis ; widget-conditional pour les 2 autres.

#### Service — snapshot copy

`LLMModelService._copy_from_template_row(template_model_name)` :

```python
async def _copy_from_template_row(self, template_model_name: str) -> dict[str, Any]:
    template = await self.repo.get_by_name(template_model_name)
    if template is None:
        raise UnknownReasoningTemplateError(...)
    return {
        "is_reasoning_model": template.is_reasoning_model,
        "reasoning_widget": template.reasoning_widget,
        "reasoning_enum_values": list(template.reasoning_enum_values) if template.reasoning_enum_values else None,
        "reasoning_budget_range": dict(template.reasoning_budget_range) if template.reasoning_budget_range else None,
    }
```

**Snapshot semantics** : la copie capture les valeurs au moment de la création/édition. Si quelqu'un édite plus tard la ligne du template, les modèles qui en dérivent **ne suivent pas** — comportement voulu (un modèle reste stable une fois créé).

#### Hiérarchie d'exceptions

```python
class UnknownReasoningTemplateError(LookupError):
    """Sous-classe de LookupError → router catch BEFORE plain LookupError
    pour traduire vers 400 invalid_input plutôt que 404 not_found."""
```

| Erreur | Cas | HTTP |
|---|---|---|
| `ValueError` (dans `create`) | model_name déjà existant | 409 already_exists |
| `ValueError` (dans `update`) | rename target conflict | 409 already_exists |
| `LookupError` | modèle à updater introuvable | 404 not_found |
| `UnknownReasoningTemplateError` | `reasoning_template` ne match aucune row | 400 invalid_input |

### Frontend

`apps/web/src/components/settings/AdminLLMPricingSection.tsx` — modal d'édition.

Logique du toggle :
```typescript
// Toggle Is reasoning model OFF ⇒ reset shape + clear template
onCheckedChange={v => setFormData(prev => ({
  ...prev,
  is_reasoning_model: v,
  reasoning_template: v ? prev.reasoning_template : CUSTOM_TEMPLATE_VALUE,
  reasoning_widget: v ? prev.reasoning_widget : 'none',
}))}
```

Logique du payload :
```typescript
function buildReasoningSamplingPayload(formData: ModelPricingFormData): ReasoningSamplingPayload {
  const alwaysExplicit = { kind, supports_temperature, ..., reasoning_doc_i18n_key };

  // Non-reasoning ⇒ force widget=none, ignore le template.
  if (!formData.is_reasoning_model) {
    return { ...alwaysExplicit, is_reasoning_model: false, reasoning_widget: 'none', ... };
  }
  // Reasoning + Template mode
  if (formData.reasoning_template !== CUSTOM_TEMPLATE_VALUE) {
    return { ...alwaysExplicit, reasoning_template: formData.reasoning_template };
  }
  // Reasoning + Custom mode
  return { ...alwaysExplicit, is_reasoning_model: true, reasoning_widget, reasoning_enum_values, reasoning_budget_range };
}
```

À l'édition d'un modèle existant : `fingerprintMatches(template, model)` cherche le template qui correspond aux 4 fields et le pré-sélectionne dans le Select. Si aucun match, retombe sur "Custom".

### Audit log

Chaque create/update enregistre dans `admin_audit_logs.details` :
- `kind`
- `reasoning_template` (slug choisi par l'admin, ou `null` en Custom)
- `reasoning_widget` (post-update, après résolution template/custom)

Permet de retracer historiquement quel template un modèle a hérité.

---

## 🧪 Tests

| Niveau | Fichier | Couverture |
|---|---|---|
| Schema (pure Pydantic, sans DB) | `tests/unit/domains/llm/test_schemas_reasoning.py` | XOR Create/Update, widget×values cohésion, required catalogue fields, indépendance `kind`/sampling/doc_i18n_key |
| Service helpers (pure, sans DB) | `tests/unit/domains/llm/test_service_helpers.py` | `_fingerprint`, `_render_template_description`, `_validate_reasoning_cohesion` |
| Service intégration (avec DB) | `tests/unit/domains/llm/test_service.py` | `list_templates` dédup, snapshot copy, `UnknownReasoningTemplateError`, partial widget update cohésion |

---

## ❓ FAQ

### Pourquoi un `_normalise_shape_value` ?

Les colonnes JSONB (`reasoning_enum_values` liste, `reasoning_budget_range` dict) ne sont pas hashables telles quelles. Pour produire une clé de groupement stable, on convertit listes → tuples et dicts → tuples triés `(key, value)`. Le tri garantit que deux lignes avec la même structure mais des keys insérées dans un ordre différent (rare mais possible via JSONB) hashent identiquement.

### Pourquoi `reasoning_doc_i18n_key` est sorti du fingerprint ?

C'est une clé i18n provider-specific (`anthropic_4_5`, `openai_o_series`, etc.). Si on l'incluait dans le fingerprint, deux modèles partageant exactement la même API reasoning mais venant de providers différents (donc `doc_i18n_key` différent) apparaîtraient comme deux templates distincts — ce qui multiplierait artificiellement la liste sans valeur. Mesure mesurée sur le catalogue réel : ramène le nombre de templates de ~30 à ~15.

### Que se passe-t-il si je change la liste `reasoning_enum_values` d'un template plus tard ?

Snapshot semantics : les modèles qui ont copié le template à un moment T conservent leur copie. Si tu édites `gpt-5` pour ajouter une nouvelle valeur d'effort, les modèles qui ont hérité de `gpt-5` ne reçoivent pas la nouvelle valeur. Si c'est un changement à propager, il faut re-éditer chaque modèle dérivé (ou écrire un script).

### Comment "officialiser" un nouveau pattern famille en code ?

Si une nouvelle famille reasoning émerge (ex : Mistral sort une API reasoning native), suivre les étapes :
1. Importer le premier modèle de la famille en mode **Custom** via l'admin (saisie manuelle des 4 colonnes shape).
2. Ce modèle devient automatiquement template pour les suivants — l'admin peut copier dessus pour tout `mistral-*-reasoning` futur.
3. Si la famille devient large, mettre à jour le **builder reasoning** correspondant dans `apps/api/src/infrastructure/llm/providers/reasoning_builders.py` pour gérer le formatage de la requête côté provider.

---

## 🔗 Références

- Refonte initiale T20/T21 : *(doc de conception non conservé — `docs/superpowers/` ne garde que les specs/plans de juillet 2026)*
- Plan d'implémentation : *(non conservé — voir l'historique git si besoin)*
- ADR-078 (catalogue DB-source-of-truth) : `docs/architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md`
- Documentation pricing globale : [LLM_PRICING_MANAGEMENT.md](./LLM_PRICING_MANAGEMENT.md)
- Documentation Configuration LLM admin (consommateur des `supports_*`) : [LLM_CONFIG_ADMIN.md](./LLM_CONFIG_ADMIN.md)
