# ADR-036: Personality System Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Customizable LLM personality per user
**Related Documentation**: `docs/technical/PERSONALITIES.md`

---

## Context and Problem Statement

L'assistant nécessitait un système de personnalités configurable :

1. **Multiple Personalities** : Tons différents (enthousiaste, professeur, ami)
2. **Per-User Selection** : Chaque utilisateur choisit sa personnalité
3. **i18n Support** : Traductions en 6 langues
4. **Prompt Injection** : Intégration dans les prompts LLM

**Question** : Comment permettre aux utilisateurs de personnaliser le ton de l'assistant ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **Database Models** : Personality + PersonalityTranslation
2. **User FK** : Sélection personnalité par utilisateur
3. **Prompt Injection** : `{personnalite}` placeholder
4. **Fallback Chain** : User → Default → Hardcoded

### Nice-to-Have:

- Auto-translation via GPT
- Admin management endpoints
- Frontend selector

---

## Decision Outcome

**Chosen option**: "**Database Models + Prompt Injection + Translation Fallback**"

### Architecture Overview

```mermaid
graph TB
    subgraph "DATABASE MODELS"
        PERS[Personality<br/>code, emoji, prompt_instruction]
        TRANS[PersonalityTranslation<br/>language_code, title, description]
        USER[User<br/>personality_id FK]
    end

    subgraph "SELECTION FLOW"
        API[PATCH /personalities/current]
        SVC[PersonalityService<br/>get_prompt_instruction_for_user]
        STATE[MessagesState<br/>personality_instruction]
    end

    subgraph "PROMPT INJECTION"
        RESP[response_node]
        PROMPT[get_response_prompt<br/>{personnalite} placeholder]
        LLM[LLM with personality tone]
    end

    PERS --> TRANS
    USER --> PERS
    API --> SVC
    SVC --> STATE
    STATE --> RESP
    RESP --> PROMPT
    PROMPT --> LLM

    style PERS fill:#4CAF50,stroke:#2E7D32,color:#fff
    style SVC fill:#2196F3,stroke:#1565C0,color:#fff
    style PROMPT fill:#FF9800,stroke:#F57C00,color:#fff
```

### Personality Model

```python
# apps/api/src/domains/personalities/models.py

class Personality(BaseModel):
    __tablename__ = "personalities"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    emoji: Mapped[str] = mapped_column(String(10))
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    prompt_instruction: Mapped[str] = mapped_column(Text)

    translations: Mapped[list["PersonalityTranslation"]] = relationship(
        back_populates="personality",
        cascade="all, delete-orphan",
    )

    def get_translation(self, language_code: str) -> PersonalityTranslation | None:
        """Get translation with fallback: requested → fr → en → first."""
        for lang in [language_code, "fr", "en"]:
            for t in self.translations:
                if t.language_code == lang:
                    return t
        return self.translations[0] if self.translations else None
```

### Default Personalities

| Code | Emoji | Default | Prompt Theme |
|------|-------|---------|--------------|
| `normal` | ⚖️ | YES | Balanced, professional, concise |
| `enthusiastic` | 🎉 | - | High energy, celebratory |
| `professor` | 🎓 | - | Pedagogical, step-by-step |
| `friend` | 🤝 | - | Warm, casual, empathetic |
| `influencer` | ✨ | - | Trendy, references followers |
| `philosopher` | 🤔 | - | Contemplative, nuanced |
| `cynic` | 😏 | - | Sarcastic, dark humor |

### User-Personality Relationship

```python
# apps/api/src/domains/auth/models.py

class User(BaseModel):
    personality_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personalities.id", ondelete="SET NULL"),
        nullable=True,
        comment="User's preferred LLM personality (NULL = use default)",
    )

    personality: Mapped["Personality | None"] = relationship(
        back_populates="users",
    )
```

### Personality Service

```python
# apps/api/src/domains/personalities/service.py

class PersonalityService:
    async def get_prompt_instruction_for_user(self, user_id: UUID) -> str:
        """Get personality instruction for prompt injection."""
        user = await self.user_repo.get(user_id)

        if user and user.personality_id:
            return await self.get_prompt_instruction(user.personality_id)

        # Fallback to default
        default = await self.get_default()
        if default:
            return default.prompt_instruction

        # Hardcoded fallback
        return DEFAULT_PERSONALITY_PROMPT
```

### Prompt Injection

```python
# apps/api/src/domains/agents/prompts.py

def get_response_prompt(
    personality_instruction: str | None = None,
    # ...other params
) -> ChatPromptTemplate:
    template = load_prompt("response_system_prompt_base")

    # Inject personality via {personnalite} placeholder
    formatted = template.format(
        personnalite=personality_instruction or DEFAULT_PERSONALITY_PROMPT,
        # ...
    )

    return ChatPromptTemplate.from_messages([
        ("system", formatted),
        # ...
    ])
```

### State Integration

```python
# apps/api/src/domains/agents/models.py

class MessagesState(TypedDict):
    personality_instruction: str | None  # LLM personality prompt

# apps/api/src/domains/agents/nodes/response_node.py

async def response_node(state: MessagesState, config: RunnableConfig):
    personality_instruction = state.get("personality_instruction")

    prompt = get_response_prompt(
        personality_instruction=personality_instruction,
    )
```

### API Endpoints

```python
# apps/api/src/domains/personalities/router.py

@router.get("")
async def list_personalities(user: User, language: str = "fr"):
    """List active personalities (localized)."""

@router.get("/current")
async def get_current_personality(user: User):
    """Get user's current personality."""

@router.patch("/current")
async def update_current_personality(user: User, data: UserPersonalityUpdate):
    """Update user's personality preference."""

# Admin endpoints
@router.post("/admin")
async def create_personality(user: User, data: PersonalityCreate):
    """Create new personality (admin only)."""

@router.post("/admin/{id}/auto-translate")
async def auto_translate_personality(user: User, id: UUID, source_lang: str):
    """Trigger GPT auto-translation to missing languages."""
```

### Translation Support

```python
# Supported languages
SUPPORTED_LANGUAGES = ["fr", "en", "es", "de", "it", "zh-CN"]

# Auto-translation via GPT-4.1-nano
async def trigger_auto_translation(personality_id: UUID, source_lang: str):
    """Auto-translate to missing languages using LLM."""
```

### Consequences

**Positive**:
- ✅ **7 Default Personalities** : Ready-to-use options
- ✅ **Per-User Selection** : Personalized experience
- ✅ **i18n Support** : 6 languages with fallback
- ✅ **Prompt Injection** : Seamless LLM integration
- ✅ **Auto-Translation** : GPT-powered localization
- ✅ **Admin Management** : CRUD via API

**Negative**:
- ⚠️ Prompt_instruction stored as raw text
- ⚠️ Translation fallback chain complexity

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Personality + Translation models
- [x] ✅ User FK with ondelete SET NULL
- [x] ✅ Default personality support
- [x] ✅ Prompt injection via placeholder
- [x] ✅ Translation fallback chain
- [x] ✅ API endpoints (user + admin)
- [x] ✅ Auto-translation service

---

## References

### Source Code
- **Models**: `apps/api/src/domains/personalities/models.py`
- **Service**: `apps/api/src/domains/personalities/service.py`
- **Router**: `apps/api/src/domains/personalities/router.py`
- **Migration**: `apps/api/alembic/versions/2025_12_03_0000-add_personalities.py`
- **Prompts**: `apps/api/src/domains/agents/prompts.py`

---

**Fin de ADR-036** - Personality System Architecture Decision Record.
