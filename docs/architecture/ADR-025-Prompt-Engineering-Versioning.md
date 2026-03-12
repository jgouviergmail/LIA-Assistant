# ADR-025: Prompt Engineering & Versioning

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Production-grade prompt management with A/B testing
**Related Documentation**: `docs/technical/PROMPTS.md`

---

## Context and Problem Statement

L'application LLM-based nécessitait une gestion robuste des prompts :

1. **Versioning** : Rollback rapide si nouvelle version échoue
2. **A/B Testing** : Comparer performance entre versions
3. **Template Variables** : Injection dynamique (datetime, context, tools)
4. **Caching** : Réduire I/O disque pour prompts fréquemment utilisés

**Question** : Comment implémenter une architecture de prompts maintenable et évolutive ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Versioning** : Fichiers v1/, v2/, vN/ sur filesystem
2. **Runtime Config** : Changement version via environnement
3. **Template Variables** : Python .format() pour injection
4. **Caching** : LRU cache pour performance

### Nice-to-Have:

- Hash-based integrity validation
- Dynamic few-shot loading
- i18n temporal context

---

## Decision Outcome

**Chosen option**: "**Python .format() + Filesystem Versioning + LRU Cache**"

### Architecture Overview

```mermaid
graph TB
    subgraph "PROMPT LOADING"
        PL[PromptLoader] --> LRU[@lru_cache<br/>maxsize=32]
        LRU --> FS[(Filesystem<br/>prompts/v1/*.txt)]
        PL --> HASH[SHA256 Validation<br/>Optional]
    end

    subgraph "VERSIONING"
        ENV[.env] --> CFG[Settings<br/>*_prompt_version]
        CFG --> V1[v1/]
        CFG --> V2[v2/]
        CFG --> VN[vN/]
    end

    subgraph "TEMPLATE VARIABLES"
        TPL[Template] --> FMT[.format()]
        FMT --> DT[current_datetime]
        FMT --> CTX[context_section]
        FMT --> CAT[catalogue_json]
        FMT --> FSH[fewshot_examples]
    end

    subgraph "FEW-SHOT LOADING"
        FSL[load_fewshot_examples] --> DOM[domain_operations<br/>list]
        DOM --> SEL[Selective Loading<br/>80% size reduction]
    end

    PL --> TPL
    FSL --> TPL

    style LRU fill:#4CAF50,stroke:#2E7D32,color:#fff
    style ENV fill:#2196F3,stroke:#1565C0,color:#fff
    style FMT fill:#FF9800,stroke:#F57C00,color:#fff
```

### Directory Structure

```
apps/api/src/domains/agents/prompts/
├── prompt_loader.py                    # Core loading module
└── v1/                                 # Version 1 (current)
    ├── router_system_prompt_template.txt
    ├── planner_system_prompt.txt
    ├── response_system_prompt_base.txt
    ├── hitl_classifier_prompt.txt
    ├── memory_extraction_prompt.txt
    ├── contacts_agent_prompt.txt
    ├── emails_agent_prompt.txt
    └── fewshot/                        # Few-shot examples
        ├── contacts_search.txt
        ├── contacts_details.txt
        ├── emails_search.txt
        └── emails_details.txt
```

### Prompt Loader with Caching

```python
# apps/api/src/domains/agents/prompts/prompt_loader.py

@lru_cache(maxsize=32)
def load_prompt(
    name: PromptName,
    version: PromptVersion = "v1",
    validate_hash: bool = False,
    expected_hash: str | None = None,
) -> str:
    """
    Load prompt from filesystem with LRU caching.

    Cache reduces disk I/O from ~1000 reads/min to ~10 at startup.
    """
    prompt_path = PROMPTS_DIR / version / f"{name}.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found for version '{version}'")

    content = prompt_path.read_text(encoding="utf-8")

    if validate_hash and expected_hash:
        actual_hash = calculate_prompt_hash(content)
        if actual_hash != expected_hash:
            raise ValueError(f"Hash mismatch for prompt '{name}'")

    return content


def calculate_prompt_hash(content: str) -> str:
    """SHA256 hash for tamper detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

### Dynamic Few-Shot Loading

```python
def load_fewshot_examples(
    domain_operations: list[tuple[str, str]],
    version: PromptVersion = "v1",
) -> str:
    """
    Load only relevant few-shot examples for detected domains.

    Reduces prompt size by ~80% for mono-domain queries.

    Args:
        domain_operations: List of (domain, operation) tuples
            Example: [("contacts", "search"), ("emails", "details")]
    """
    unique_pairs = sorted(set(domain_operations))
    examples_parts = []

    for domain, operation in unique_pairs:
        content = _load_fewshot_file(domain, operation, version)
        if content:
            examples_parts.append(content.strip())

    return "\n\n".join(examples_parts)
```

### Configuration-Driven Versioning

```python
# apps/api/src/core/config/agents.py

class AgentsSettings(BaseSettings):
    # Prompt Versioning (All Agents & Nodes)
    router_prompt_version: str = Field(
        default=ROUTER_PROMPT_VERSION_DEFAULT,
        description="Router system prompt version (for A/B testing and rollbacks)",
    )
    response_prompt_version: str = Field(
        default=RESPONSE_PROMPT_VERSION_DEFAULT,
        description="Response node system prompt version",
    )
    planner_prompt_version: str = Field(
        default=PLANNER_PROMPT_VERSION_DEFAULT,
        description="Planner system prompt version",
    )
    # ... all other agents
```

### Environment Variables

```bash
# .env
ROUTER_PROMPT_VERSION=v1
PLANNER_PROMPT_VERSION=v1
RESPONSE_PROMPT_VERSION=v1
CONTACTS_AGENT_PROMPT_VERSION=v1
EMAILS_AGENT_PROMPT_VERSION=v1
```

### Template Variables

```python
# apps/api/src/domains/agents/prompts.py

# Router Prompt
router_template.format(
    available_domains=available_domains,
    current_datetime=get_current_datetime_context(user_timezone, user_language),
    conversation_history=conversation_history,
    window_size=window_size,
)

# Planner Prompt
planner_template.format(
    catalogue_json=catalogue_json,       # 10-50KB tool definitions
    response_schemas=response_schemas,    # Tool response schemas
    context_section=context_section,      # Active contexts
    user_message=user_message,
    current_datetime=current_datetime,
    user_language=user_language,
)

# Response Prompt
response_template.format(
    fewshot_examples=fewshot_examples,    # Dynamically loaded
    psychological_profile=psychological_profile,  # From memory
    personality_instruction=personality,
)
```

### Datetime Context (i18n)

```python
def get_current_datetime_context(
    user_timezone: str = "Europe/Paris",
    user_language: str = "fr"
) -> str:
    """
    Format: "📅 Mercredi 29 octobre 2025, 15:30 (Après-midi) - Semaine - Automne"

    Supports 6 languages: fr, en, es, de, it, zh-CN
    """
    # Localized day names, month names, periods, seasons
```

### Double-Escaping for JSON

```python
# Prompts containing JSON examples use {{}} which becomes {} after .format()

# In planner_system_prompt.txt:
{{{{
  "steps": [{{{{
    "step_id": "search_1",
    ...
  }}}}]
}}}}

# Rendered output:
{{
  "steps": [{{
    "step_id": "search_1",
    ...
  }}]
}}
```

### Consequences

**Positive**:
- ✅ **A/B Testing** : Version switch via environment variable
- ✅ **Rollback Safety** : Quick fallback to previous version
- ✅ **Performance** : 98% reduction in disk I/O via LRU cache
- ✅ **Scalability** : Dynamic few-shot loading reduces tokens ~80%
- ✅ **Integrity** : SHA256 validation prevents tampering
- ✅ **i18n Ready** : 6-language temporal context

**Negative**:
- ⚠️ Double-escaping for JSON examples
- ⚠️ Python .format() limitations (no conditionals)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ LRU cache avec maxsize=32
- [x] ✅ SHA256 hash validation optional
- [x] ✅ Dynamic version detection (v1, v2, vN)
- [x] ✅ Environment-driven configuration
- [x] ✅ Dynamic few-shot loading
- [x] ✅ i18n temporal context (6 langues)
- [x] ✅ Double-escaping for JSON in prompts

---

## References

### Source Code
- **Prompt Loader**: `apps/api/src/domains/agents/prompts/prompt_loader.py`
- **Prompt Helpers**: `apps/api/src/domains/agents/prompts.py`
- **Config**: `apps/api/src/core/config/agents.py`
- **Constants**: `apps/api/src/core/constants.py`
- **Prompts Directory**: `apps/api/src/domains/agents/prompts/v1/`

---

**Fin de ADR-025** - Prompt Engineering & Versioning Decision Record.
