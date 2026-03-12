# ADR-052: Union Validation Strategy for AgentResult.data

**Status**: ✅ ACCEPTED (2026-01-24)
**Deciders**: Architecture Team LIA
**Technical Story**: Analyse du risque de coercion Union Pydantic v2

---

## Context and Problem Statement

L'architecture utilise une **Union polymorphe** pour `AgentResult.data` afin de supporter plusieurs types de resultats domaines :

```python
# apps/api/src/domains/agents/orchestration/schemas.py (lines 237-244)
data: (
    ContactsResultData
    | EmailsResultData
    | PlacesResultData
    | MultiDomainResultData
    | dict[str, Any]
    | None
) = Field(default=None)
```

### Probleme Pydantic v2 Union Validation

Pydantic v2 valide les Union types **dans l'ordre de declaration** :

1. Essaie `ContactsResultData` → si validation reussit, s'arrete
2. Sinon essaie `EmailsResultData` → ...
3. Jusqu'a trouver un type valide ou echec

**Risque** : Si une classe a **tous ses champs avec des valeurs par defaut**, elle peut accepter N'IMPORTE QUEL dict :

```python
class PlacesResultData(BaseModel):
    places: list = Field(default_factory=list)      # Default
    total_count: int = Field(default=0)             # Default
    query: str | None = Field(default=None)         # Default
    # ... tous les champs ont des defaults

# DANGER: Ce dict pourrait etre coerce a PlacesResultData
some_dict = {"step_results": [...], "unknown_field": "value"}
# → PlacesResultData(places=[], total_count=0, ...)
# → "step_results" et "unknown_field" PERDUS SILENCIEUSEMENT !
```

**Question** : Comment proteger contre la coercion silencieuse des Union types ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Protection coercion** : Aucune perte silencieuse de donnees
2. **Performance** : Validation rapide (< 1ms overhead)
3. **Retrocompatibilite** : Code existant doit fonctionner sans modification

### Nice-to-Have:

- Clarte du code (pattern explicite vs implicite)
- Serialisation/deserialisation robuste (round-trip)
- Maintenabilite long-terme

---

## Considered Options

### Option 1: `extra="forbid"` sur base class

**Approach** : Configurer Pydantic pour rejeter les champs inconnus via `model_config`.

```python
class AgentResultData(BaseModel):
    """
    Base class for agent result data.

    **IMPORTANT**: Uses `extra='forbid'` to prevent Pydantic v2 Union coercion issues.
    Without this, a dict with arbitrary keys could be coerced to a domain-specific
    model (like PlacesResultData) when all its fields have default values, causing
    the dict's actual data (like step_results) to be silently discarded.
    """
    model_config = ConfigDict(extra="forbid")
```

**Pros**:
- ✅ Simple : 1 ligne de config sur base class
- ✅ Non-invasif : Aucun changement sur les classes derivees
- ✅ Herite automatiquement : Toutes les `*ResultData` protegees
- ✅ Documente : Commentaire explicatif present

**Cons**:
- ❌ Implicite : Protection via heritage, pas visible sur chaque classe
- ❌ Fragile : Si une classe oublie d'heriter, pas de protection
- ❌ Performance O(n) : Pydantic essaie chaque type sequentiellement

**Verdict**: ✅ ACCEPTED

---

### Option 2: Discriminated Union avec `result_type`

**Approach** : Ajouter un champ discriminant pour identification explicite du type.

```python
from typing import Annotated, Literal

class ContactsResultData(AgentResultData):
    result_type: Literal["contacts"] = "contacts"  # Discriminant
    contacts: list[dict] = Field(default_factory=list)
    ...

class EmailsResultData(AgentResultData):
    result_type: Literal["emails"] = "emails"
    emails: list[dict] = Field(default_factory=list)
    ...

class RawResultData(AgentResultData):
    result_type: Literal["raw"] = "raw"
    payload: dict[str, Any] = Field(default_factory=dict)

# Union discriminee
ResultDataUnion = Annotated[
    ContactsResultData | EmailsResultData | PlacesResultData | MultiDomainResultData | RawResultData,
    Field(discriminator="result_type")
]

class AgentResult(BaseModel):
    data: ResultDataUnion | None = None
```

**Pros**:
- ✅ Explicite : Type clairement identifie par `result_type`
- ✅ Performance O(1) : Pydantic lookup direct via discriminant
- ✅ Serialisation robuste : `result_type` preserve dans JSON, round-trip garanti
- ✅ Maintenable : Pattern standard Pydantic v2

**Cons**:
- ❌ Migration significative : Modifier toutes les classes `*ResultData`
- ❌ Churn code : Mettre a jour tous les points de creation dans `mappers.py`
- ❌ Tests a adapter : Round-trip tests a modifier
- ❌ Breaking change potentiel : Si serialisation JSON consommee externement

**Verdict**: ❌ REJECTED (ROI insuffisant)

---

### Option 3: Nested Unions par domaine

**Approach** : Separer les Union par categorie de domaine.

```python
ContactDomainResult = ContactsResultData | None
EmailDomainResult = EmailsResultData | None
# ...

data: ContactDomainResult | EmailDomainResult | MultiDomainResultData | dict[str, Any]
```

**Pros**:
- ✅ Separation claire par domaine

**Cons**:
- ❌ Complexite accrue
- ❌ Ne resout pas le probleme de coercion
- ❌ Validation encore plus lente

**Verdict**: ❌ REJECTED

---

## Decision Outcome

**Chosen option**: **Option 1 - `extra="forbid"` sur base class `AgentResultData`**

### Justification

1. **Le systeme fonctionne** : Aucun bug connu lie a la coercion Union
2. **Protection deja en place** : `extra="forbid"` herite par toutes les classes derivees
3. **Documentation explicite** : Le commentaire dans le code explique le "pourquoi"
4. **ROI insuffisant** : Le cout de migration vers Discriminated Union ne se justifie pas pour un gain theorique

### Implementation actuelle

**Fichier** : `apps/api/src/domains/agents/orchestration/schemas.py` (lines 17-35)

```python
class AgentResultData(BaseModel):
    """
    Base class for agent result data.

    **IMPORTANT**: Uses `extra='forbid'` to prevent Pydantic v2 Union coercion issues.
    Without this, a dict with arbitrary keys could be coerced to a domain-specific
    model (like PlacesResultData) when all its fields have default values, causing
    the dict's actual data (like step_results) to be silently discarded.
    """

    model_config = ConfigDict(extra="forbid")
```

### Comment ca protege

```python
# Dict avec champs inconnus
test_dict = {"step_results": [...], "unknown_field": "value"}

# SANS extra="forbid" :
PlacesResultData(**test_dict)  # → PlacesResultData(places=[], ...) - DATA LOST!

# AVEC extra="forbid" :
PlacesResultData(**test_dict)  # → ValidationError: Extra inputs are not permitted
# → Pydantic passe au type suivant dans l'Union
# → Finalement match dict[str, Any] correctement
```

---

## Consequences

### Positive

- ✅ **Zero migration** : Aucun changement de code necessaire
- ✅ **Systeme stable** : Fonctionne en production sans probleme
- ✅ **Pattern documente** : Commentaire explicite dans le code source
- ✅ **Heritage automatique** : Nouvelles classes protegees si elles heritent de `AgentResultData`

### Negative

- ⚠️ **Pattern implicite** : La protection depend de l'heritage, pas visible directement
- ⚠️ **Fragilite potentielle** : Si une nouvelle classe n'herite pas de `AgentResultData`, pas de protection

### Risks

- ⚠️ **Oubli d'heritage** : Une nouvelle `*ResultData` qui n'herite pas de `AgentResultData` serait vulnerable
- ⚠️ **Desynchronisation doc/code** : Si le commentaire est supprime, le "pourquoi" est perdu

### Mitigation des risques

1. **Code review** : Verifier que toute nouvelle `*ResultData` herite de `AgentResultData`
2. **Test unitaire** : Le test `test_agent_result_schemas.py` couvre les round-trips
3. **Documentation** : Cet ADR documente le raisonnement

---

## Conditions de Reconsideration

Migrer vers Discriminated Union si :

| Condition | Seuil | Rationale |
|-----------|-------|-----------|
| Nouveaux types `*ResultData` | ≥ 5 ajouts | Complexite Union croissante |
| Bug deserialisation | 1 occurrence | Preuve que protection insuffisante |
| Refactoring majeur schemas | N/A | Opportunite de migration "gratuite" |
| Performance validation | > 10ms | O(n) devient problematique |

---

## Validation

**Acceptance Criteria**:
- [x] ✅ `extra="forbid"` present sur `AgentResultData`
- [x] ✅ Commentaire explicatif documente le "pourquoi"
- [x] ✅ Tests round-trip passent (`test_agent_result_schemas.py`)
- [x] ✅ Aucun bug connu de coercion en production

---

## Related Decisions

- [ADR-012: Data Registry & StandardToolOutput Pattern](ADR-012-Data-Registry-StandardToolOutput-Pattern.md) - Utilise `AgentResult.data`
- [ADR-014: ExecutionPlan Parallel Executor](ADR-014-ExecutionPlan-Parallel-Executor.md) - Produit `AgentResult`

---

## References

### Source Code
- **AgentResultData** : `apps/api/src/domains/agents/orchestration/schemas.py:17-35`
- **AgentResult Union** : `apps/api/src/domains/agents/orchestration/schemas.py:237-244`
- **Mappers (instantiation)** : `apps/api/src/domains/agents/orchestration/mappers.py:719-850`
- **Tests** : `apps/api/tests/agents/test_agent_result_schemas.py`

### External Documentation
- [Pydantic v2 Discriminated Unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
- [Pydantic v2 extra="forbid"](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.extra)

---

**Fin de ADR-052** - Union Validation Strategy for AgentResult.data Decision Record.
