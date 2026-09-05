# Chaîne d'autorité et registre des effets (ADR-263) — Plan d'implémentation, lots 0 et 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (owner rule: no sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Déclarer la politique de mutation de chaque outil (lot 0) et créer le registre durable des effets externes avec ses primitives claim/close (lot 1), sans aucun changement de comportement visible.

**Architecture:** Le lot 0 ajoute deux champs déclaratifs au manifeste d'outil (`mutation_policy`, `mutation_policy_reason`), une garde de complétude au boot (patron ADR-085/ADR-256) et une dérivation pour les outils MCP tiers. Le lot 1 ajoute une table `agent_effects` (une ligne par effet externe, claim avant effet, clôture conditionnée par un jeton), son repository et ses empreintes, réutilisant `compute_call_digest`. Rien ne branche encore les exécuteurs (lot 2) ni la surface de preuve (lot 3).

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, pytest (`asyncio_mode = "auto"`), Black/Ruff/MyPy strict.

**Spec:** `docs/superpowers/specs/2026-09-03-execution-authority-ledger-design.md` (lire §4.1, §4.2, §5, §6, §7).

## Global Constraints

- **Aucune commande git dans ce plan** : le propriétaire commite lui-même (règle projet). Chaque tâche se termine par une vérification, pas par un commit.
- **Inline uniquement**, pas de sous-agent.
- Fichiers gelés par le ratchet de taille (`apps/api/tests/unit/file_size_baseline.json`) : `response_node.py`, `parallel_executor.py`, `hitl_dispatch_node.py`, `task_orchestrator_node.py`, `agent_registry.py` — **ne pas y ajouter une ligne**. `react_nodes.py` est à 594/600 SLOC : interdit d'y toucher dans ces lots. `catalogue.py` est à 291 SLOC (marge suffisante).
- Toute datetime est `datetime.now(UTC)` ; aucun `utcnow()` (garde AST `test_no_hardcoded_timezone_guard`).
- Jamais de mutation JSONB en place (garde `test_jsonb_mutation_guard`) — le lot 1 n'a pas de colonne JSONB, par choix.
- Aucun `except: pass` ; `contextlib.suppress(SpecificError)` avec justification au-dessus.
- Chaînes visibles par l'utilisateur : aucune dans ces lots (les messages i18n ×6 arrivent au lot 2).
- Docstrings et commentaires en **anglais** ; réponses au propriétaire en français.
- Migration créée avec `task db:migrate:create -- "agent effects ledger (ADR-263)"` (jamais un id choisi à la main : piège de collision du 2026-09-03), `down_revision` = tête actuelle `e0f1a2b3c4d5`.
- Modèle enregistré dans `src/infrastructure/database/registry.py::import_all_models` (Alembic `env.py` et `startup/registries.py` l'importent tous deux de là).
- Gates minimales après chaque lot : `task lint`, `task test:backend:unit:fast`, et pour le lot 1 `task db:migrate:replay-check` + `task test:backend:integration`. `tests/agents/` n'est pas dans le hook : `cd apps/api && .venv/Scripts/pytest tests/agents -q -p no:cacheprovider --no-cov` explicitement.
- Décisions propriétaire figées (spec §7) : Hue et `browser_task_tool` = `reversible` ; aucun natif ne reçoit `confirm` ; résultat d'outil conservé chiffré (colonne prévue dès le lot 1) ; rétention jusqu'à suppression du compte (`ondelete="CASCADE"` sur `users.id`).

---

## Lot 0 — Doctrine déclarée

### Task 1: Le type `MutationPolicy` et ses deux champs sur `ToolManifest`

**Files:**
- Modify: `apps/api/src/domains/agents/registry/catalogue.py` (après `ToolCategory`, ~ligne 62 ; et dans `ToolManifest`, sous `tool_category`, ~ligne 553)
- Test: `apps/api/tests/unit/domains/agents/registry/test_mutation_policy.py` (nouveau)

**Interfaces:**
- Produces: `MutationPolicy = Literal["draft", "confirm", "reversible", "artefact", "sandboxed"]`, `MUTATION_POLICIES: frozenset[str]`, `POLICIES_REQUIRING_REASON: frozenset[str]`, champs `ToolManifest.mutation_policy: MutationPolicy | None = None` et `ToolManifest.mutation_policy_reason: str | None = None`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
"""Mutation policy is a DECLARATION on the manifest, never a guess (ADR-263).

A read never carries a policy; every non-read-only native manifest declares
one; a policy other than ``draft``/``confirm`` says WHY it is exempt from a
confirmation. The completeness assert (Task 2) enforces it at boot.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.catalogue import (
    MUTATION_POLICIES,
    POLICIES_REQUIRING_REASON,
    CostProfile,
    PermissionProfile,
    ToolManifest,
)

pytestmark = [pytest.mark.unit]


def _manifest(**overrides: object) -> ToolManifest:
    base: dict[str, object] = {
        "name": "control_hue_light_tool",
        "agent": "hue_agent",
        "description": "test",
        "parameters": [],
        "outputs": [],
        "cost": CostProfile(),
        "permissions": PermissionProfile(),
        "tool_category": "update",
    }
    base.update(overrides)
    return ToolManifest(**base)  # type: ignore[arg-type]


def test_policy_fields_default_to_none() -> None:
    manifest = _manifest()
    assert manifest.mutation_policy is None
    assert manifest.mutation_policy_reason is None


def test_policy_vocabulary_is_closed() -> None:
    assert MUTATION_POLICIES == frozenset({"draft", "confirm", "reversible", "artefact", "sandboxed"})
    assert POLICIES_REQUIRING_REASON == frozenset({"reversible", "artefact", "sandboxed"})


def test_policy_and_reason_are_carried() -> None:
    manifest = _manifest(mutation_policy="reversible", mutation_policy_reason="one call undoes it")
    assert manifest.mutation_policy == "reversible"
    assert manifest.mutation_policy_reason == "one call undoes it"
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ImportError: cannot import name 'MUTATION_POLICIES'`

- [ ] **Step 3: Ajouter le type et les constantes après `ToolCategory`**

Dans `catalogue.py`, juste après la fermeture du `Literal` de `ToolCategory` :

```python
# ADR-263: what confirmation a NON-read-only tool owes before it acts. A read
# never carries one; a policy other than draft/confirm must say why the tool
# is exempt from a confirmation (owner rule, 2026-09-03: confirm what modifies,
# deletes or communicates to a third party; never a read; no paranoia).
MutationPolicy = Literal[
    "draft",  # the tool returns a draft; the draft IS the confirmation (18 tools)
    "confirm",  # pre-execution confirmation card in both modes (MCP hitl_required)
    "reversible",  # executes, journaled; one call undoes it (Hue, labels, toggles)
    "artefact",  # produces a local artefact for the user, no third-party effect
    "sandboxed",  # runs inside the throwaway container (SEC-001)
]

MUTATION_POLICIES: frozenset[str] = frozenset(
    {"draft", "confirm", "reversible", "artefact", "sandboxed"}
)
#: Policies that exempt a mutation from a confirmation — the manifest must say why.
POLICIES_REQUIRING_REASON: frozenset[str] = frozenset({"reversible", "artefact", "sandboxed"})
```

- [ ] **Step 4: Ajouter les deux champs dans `ToolManifest`**

Sous la ligne `tool_category: ToolCategory | None = None` :

```python
    # ADR-263: declared confirmation policy of a non-read-only tool. None on a
    # read-only tool (a read owes nothing). Enforced at boot by
    # assert_mutation_policy_completeness().
    mutation_policy: MutationPolicy | None = None
    # Mandatory for reversible/artefact/sandboxed: the reason the tool is
    # exempt from a confirmation, in English, one sentence.
    mutation_policy_reason: str | None = None
```

- [ ] **Step 5: Vérifier le passage**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py -q -p no:cacheprovider --no-cov`
Expected: 3 passed

- [ ] **Step 6: MyPy sur le module**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/agents/registry/catalogue.py`
Expected: `Success: no issues found`

---

### Task 2: La garde de complétude `assert_mutation_policy_completeness`

**Files:**
- Modify: `apps/api/src/domains/agents/registry/catalogue.py` (après `assert_tool_category_completeness`, ~ligne 837)
- Test: `apps/api/tests/unit/domains/agents/registry/test_mutation_policy.py` (compléter)

**Interfaces:**
- Consumes: `is_read_only_tool(manifest)`, `MUTATION_POLICIES`, `POLICIES_REQUIRING_REASON` (Task 1).
- Produces: `assert_mutation_policy_completeness(manifests: Iterable[Any]) -> None` (lève `AssertionError` listant les noms fautifs).

- [ ] **Step 1: Ajouter les tests (même fichier)**

```python
from src.domains.agents.registry.catalogue import assert_mutation_policy_completeness


class TestCompleteness:
    def test_read_only_manifest_must_not_declare_a_policy(self) -> None:
        with pytest.raises(AssertionError, match="read-only .* declares"):
            assert_mutation_policy_completeness(
                [_manifest(name="get_emails_tool", tool_category="search", mutation_policy="reversible")]
            )

    def test_non_read_only_manifest_must_declare_a_policy(self) -> None:
        with pytest.raises(AssertionError, match="declare no mutation_policy: control_hue_light_tool"):
            assert_mutation_policy_completeness([_manifest()])

    def test_exempting_policy_needs_a_reason(self) -> None:
        with pytest.raises(AssertionError, match="without a reason"):
            assert_mutation_policy_completeness([_manifest(mutation_policy="reversible")])

    def test_hitl_required_implies_confirm(self) -> None:
        bad = _manifest(
            name="delegate_to_sub_agent_tool",
            permissions=PermissionProfile(hitl_required=True),
            mutation_policy="reversible",
            mutation_policy_reason="x",
        )
        with pytest.raises(AssertionError, match="hitl_required=True but policy"):
            assert_mutation_policy_completeness([bad])

    def test_draft_policy_forbids_hitl_required(self) -> None:
        bad = _manifest(
            name="send_email_tool",
            tool_category="send",
            permissions=PermissionProfile(hitl_required=True),
            mutation_policy="draft",
        )
        with pytest.raises(AssertionError, match="draft policy with hitl_required=True"):
            assert_mutation_policy_completeness([bad])

    def test_unknown_policy_value_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="unknown mutation_policy"):
            assert_mutation_policy_completeness([_manifest(mutation_policy="maybe")])  # type: ignore[arg-type]

    def test_complete_catalogue_passes(self) -> None:
        assert_mutation_policy_completeness(
            [
                _manifest(name="get_emails_tool", tool_category="search"),
                _manifest(mutation_policy="reversible", mutation_policy_reason="one call undoes it"),
                _manifest(name="send_email_tool", tool_category="send", mutation_policy="draft"),
            ]
        )

    def test_third_party_mcp_manifest_is_never_asserted(self) -> None:
        """Derived, not declared: a None policy on an mcp_ tool is not a defect."""
        assert_mutation_policy_completeness(
            [_manifest(name="mcp_era_cancel_subscription", tool_category="delete")]
        )
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ImportError: cannot import name 'assert_mutation_policy_completeness'`

- [ ] **Step 3: Implémenter la garde**

Après `assert_tool_category_completeness` dans `catalogue.py` :

```python
def assert_mutation_policy_completeness(manifests: Iterable[Any]) -> None:
    """Assert every NATIVE manifest carries the mutation policy it owes (ADR-263).

    Four rules, each closing a measured hole (spec 2026-09-03, simulation 1:
    13 non-read-only tools ran in both modes with no confirmation gate, and
    nothing said whether that was a decision or an omission):

    - a read-only tool declares NO policy (a read owes nothing);
    - a non-read-only tool declares one of ``MUTATION_POLICIES``;
    - ``reversible``/``artefact``/``sandboxed`` carry a reason;
    - ``hitl_required=True`` implies ``confirm``, and ``draft`` forbids
      ``hitl_required=True`` (the draft IS the confirmation — a pre-execution
      interrupt would ask twice, see test_hitl_required_consistency).

    Called from ``init_agent_registry`` right after the catalogue is loaded,
    like ``assert_tool_category_completeness`` — never from
    ``run_failfast_validations``, which runs over an empty registry.
    Third-party MCP tools never reach this: their policy is DERIVED from
    their declaration (``derive_mcp_mutation_policy``), not asserted.

    Args:
        manifests: Tool manifests currently registered in the catalogue.

    Raises:
        AssertionError: Listing every offending manifest name and rule.
    """
    problems: list[str] = []
    for m in manifests:
        name = str(getattr(m, "name", "<unnamed>"))
        if name.startswith("mcp_"):
            # Third-party: policy DERIVED by derive_mcp_mutation_policy, never
            # asserted — a None there means "the declaration says nothing".
            continue
        policy = getattr(m, "mutation_policy", None)
        reason = getattr(m, "mutation_policy_reason", None)
        hitl = bool(getattr(getattr(m, "permissions", None), "hitl_required", False))
        if policy is not None and policy not in MUTATION_POLICIES:
            problems.append(f"{name}: unknown mutation_policy {policy!r}")
            continue
        if is_read_only_tool(m):
            if policy is not None:
                problems.append(f"{name}: read-only tool declares a mutation_policy ({policy})")
            continue
        if policy is None:
            problems.append(f"declare no mutation_policy: {name}")
            continue
        if policy in POLICIES_REQUIRING_REASON and not (reason or "").strip():
            problems.append(f"{name}: policy {policy} without a reason")
        if hitl and policy != "confirm":
            problems.append(f"{name}: hitl_required=True but policy is {policy}")
        if policy == "draft" and hitl:
            problems.append(f"{name}: draft policy with hitl_required=True (asks twice)")
    if problems:
        raise AssertionError(
            f"{len(problems)} mutation policy problem(s): " + "; ".join(sorted(problems)) + ". "
            "A non-read-only tool must SAY what confirmation it owes — declaring "
            "nothing is how 13 tools came to run unconfirmed in both modes. See "
            "src/domains/agents/registry/catalogue.py (MutationPolicy)."
        )
```

- [ ] **Step 4: Vérifier le passage**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py -q -p no:cacheprovider --no-cov`
Expected: 11 passed

---

### Task 3: Déclarer la politique sur tout le catalogue natif (le test sur le catalogue chargé)

**Files:**
- Modify: chaque `catalogue_manifests.py` sous `apps/api/src/domains/agents/*/` dont le manifeste n'est pas lecture seule (liste ci-dessous, à confirmer par l'inventaire du Step 1)
- Test: `apps/api/tests/unit/domains/agents/registry/test_mutation_policy.py` (test sur le catalogue chargé)

**Interfaces:**
- Consumes: `assert_mutation_policy_completeness` (Task 2), fixture `catalogue` (patron save/restore de `test_tool_category_completeness.py`).

- [ ] **Step 1: Inventaire mesuré (script jetable, scratchpad)**

```python
"""Inventory: every non-read-only native manifest and its current policy."""
from src.domains.agents.registry.agent_registry import AgentRegistry, set_global_registry
from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

reg = AgentRegistry(); initialize_catalogue(reg); set_global_registry(reg)
for m in sorted(reg.list_tool_manifests(), key=lambda m: m.name):
    if not is_read_only_tool(m):
        print(f"{m.name:<34} category={m.tool_category or '(inferred)':<10} hitl={m.permissions.hitl_required} policy={m.mutation_policy}")
```

Run (env factice comme la sim. 1) : `cd apps/api && FK=$(.venv/Scripts/python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"); DATABASE_URL=postgresql+asyncpg://u:p@localhost/x REDIS_URL=redis://localhost:6379/0 SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef FERNET_KEY=$FK PYTHONPATH=. .venv/Scripts/python <chemin>/inventory.py 2>/dev/null | grep -v '^{'`
Expected: la liste des manifestes non lecture seule, tous `policy=None`.

- [ ] **Step 2: Ajouter le test sur le catalogue chargé (échoue tant que les manifestes ne déclarent rien)**

```python
from collections.abc import Iterator

from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue


@pytest.fixture
def catalogue() -> Iterator[AgentRegistry]:
    """Install a catalogue-populated global registry, then restore the previous one.

    Same save/restore as test_tool_category_completeness: the registry is a
    process-wide singleton and a sibling suite may already have loaded it.
    """
    previous = registry_module._global_registry
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        yield registry
    finally:
        registry_module._global_registry = previous


def test_native_catalogue_is_complete(catalogue: AgentRegistry) -> None:
    """The boot assert, run in CI over the real catalogue (ADR-085 placement)."""
    assert_mutation_policy_completeness(catalogue.list_tool_manifests())


# Owner decision 2026-09-03 (spec §7 n°2), pinned so a later edit is a visible
# decision: confirm what modifies/deletes/communicates; never a read; no
# paranoia — neither Hue nor the browser may rain cards on the user.
OWNER_PINNED_POLICIES: dict[str, str] = {
    "activate_hue_scene_tool": "reversible",
    "control_hue_light_tool": "reversible",
    "control_hue_room_tool": "reversible",
    "apply_labels_tool": "reversible",
    "remove_labels_tool": "reversible",
    "complete_task_tool": "reversible",
    "toggle_scheduled_action_tool": "reversible",
    "import_user_skill": "reversible",
    "browser_task_tool": "reversible",
    "generate_image": "artefact",
    "edit_image": "artefact",
    "generate_document": "artefact",
    "run_skill_script": "sandboxed",
    "run_python_tool": "sandboxed",
    "delegate_to_sub_agent_tool": "confirm",
    "send_email_tool": "draft",
    "claude_server_task_tool": "draft",
}


@pytest.mark.parametrize(("name", "policy"), sorted(OWNER_PINNED_POLICIES.items()))
def test_owner_pinned_policies(catalogue: AgentRegistry, name: str, policy: str) -> None:
    assert catalogue.get_tool_manifest(name).mutation_policy == policy


def test_no_native_tool_is_confirm_except_the_delegation(catalogue: AgentRegistry) -> None:
    """No native tool gained a pre-execution card by this lot (spec §4.1)."""
    confirm = sorted(
        m.name for m in catalogue.list_tool_manifests() if m.mutation_policy == "confirm"
    )
    assert confirm == ["delegate_to_sub_agent_tool"]


# The catalogue is built behind feature flags; a manifest gated OFF in the test
# environment would escape the guard in CI and refuse the boot in production
# (spec §9.2 — `place_phone_call_tool` was invisible to simulation 1 for that
# reason). Same list and same anti-vacuity assert as
# test_tool_category_completeness.TestTheGuardCannotRefuseAProductionBoot.
ALL_FLAGS = (
    "health_metrics_enabled",
    "sub_agents_enabled",
    "image_generation_enabled",
    "document_generation_enabled",
    "devops_enabled",
    "diagnostics_enabled",
    "python_sandbox_tool_enabled",
    "telephony_enabled",
    "peer_connections_enabled",
    "skills_enabled",
    "mcp_enabled",
)


def test_every_feature_flag_on_is_still_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings

    for flag in ALL_FLAGS:
        if hasattr(settings, flag):
            monkeypatch.setattr(settings, flag, True, raising=False)
    previous = registry_module._global_registry
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        manifests = registry.list_tool_manifests()
        assert len(manifests) > 96, f"only {len(manifests)} manifests — flags did not take"
        assert_mutation_policy_completeness(manifests)
        assert registry.get_tool_manifest("place_phone_call_tool").mutation_policy == "draft"
    finally:
        registry_module._global_registry = previous
```

- [ ] **Step 3: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py -q -p no:cacheprovider --no-cov`
Expected: `test_native_catalogue_is_complete` FAIL avec la liste complète des manifestes sans politique ; les `test_owner_pinned_policies` FAIL (None).

- [ ] **Step 4: Déclarer les politiques dans les manifestes**

Pour chaque manifeste listé par l'assertion, ajouter deux kwargs à l'appel `ToolManifest(...)` du `catalogue_manifests.py` correspondant, sous `tool_category=` quand il existe, sinon sous `permissions=`. Le mapping :

| Politique | Outils | `mutation_policy_reason` (anglais, une phrase) |
|---|---|---|
| `draft` | les 18 de `DRAFT_BASED_MUTATION_TOOLS` (`test_hitl_required_consistency.py`) + `write_spreadsheet_tool`, `append_document_text_tool`, `set_vacation_responder_tool`, `create_email_filter_tool`, `claude_server_task_tool`, `create_scheduled_action_tool`, `delete_file_tool` et tout autre manifeste que l'assertion nomme et dont l'outil retourne `requires_confirmation=True` | aucune |
| `confirm` | `delegate_to_sub_agent_tool` | aucune |
| `reversible` | `activate_hue_scene_tool`, `control_hue_light_tool`, `control_hue_room_tool` | `"A light state is undone by one more call; the owner refused a card per light."` |
| `reversible` | `apply_labels_tool`, `remove_labels_tool` | `"Labels are additive metadata; the opposite call restores them."` |
| `reversible` | `complete_task_tool` | `"A completed task is reopened by an update; nothing leaves the account."` |
| `reversible` | `toggle_scheduled_action_tool` | `"One message toggles it back; documented as direct and reversible."` |
| `reversible` | `import_user_skill` | `"Installs into the user's own skill library; removable from the settings."` |
| `reversible` | `browser_task_tool` | `"Navigation and form filling under the user's visible control; a submission to a third party gets a draft tool if one ever exists."` |
| `artefact` | `generate_image`, `edit_image`, `generate_document` | `"Produces a local artefact for the user; no effect at a third party."` |
| `sandboxed` | `run_skill_script`, `run_python_tool` | `"Runs inside the throwaway container (SEC-001); no network, no host filesystem."` |

Exemple, dans `apps/api/src/domains/agents/hue/catalogue_manifests.py` (les trois manifestes `tool_category="update"`) :

```python
    tool_category="update",
    mutation_policy="reversible",
    mutation_policy_reason="A light state is undone by one more call; the owner refused a card per light.",
```

Un outil que l'assertion nomme et qui n'est dans aucune ligne du tableau **est une question au propriétaire**, pas une décision à prendre seul : le noter et lui demander.

- [ ] **Step 5: Vérifier le passage**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/registry/test_mutation_policy.py tests/unit/domains/agents/registry/test_tool_category_completeness.py tests/unit/domains/agents/tools/test_hitl_required_consistency.py -q -p no:cacheprovider --no-cov`
Expected: tous verts (les deux suites voisines ne bougent pas).

- [ ] **Step 6: La liste manuelle du test HITL devient une dérivation**

Dans `tests/unit/domains/agents/tools/test_hitl_required_consistency.py`, remplacer la constante `DRAFT_BASED_MUTATION_TOOLS` par une dérivation du catalogue, en gardant les deux tests :

```python
def _draft_based_tools(registry: AgentRegistry) -> list[str]:
    """Derived from the catalogue (ADR-263): every manifest whose policy is draft."""
    return sorted(m.name for m in registry.list_tool_manifests() if m.mutation_policy == "draft")


def test_every_draft_based_tool_is_not_hitl_required(registry: AgentRegistry) -> None:
    names = _draft_based_tools(registry)
    assert len(names) >= 18, names  # the hand list this derivation replaced
    offenders = [n for n in names if registry.get_tool_manifest(n).permissions.hitl_required]
    assert not offenders, offenders
```

Supprimer le `parametrize` sur l'ancienne constante et l'ancienne constante elle-même ; conserver `HITL_REQUIRED_ALLOWLIST` et `test_hitl_required_set_is_within_allowlist` tels quels.

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/tools/test_hitl_required_consistency.py -q -p no:cacheprovider --no-cov`
Expected: 2 passed

---

### Task 4: La garde tourne au boot

**Files:**
- Modify: `apps/api/src/infrastructure/startup/agents.py:127-135` (le bloc `assert_tool_category_completeness`)
- Test: `apps/api/tests/unit/infrastructure/startup/test_agents_startup_policy_guard.py` (nouveau)

**Interfaces:**
- Consumes: `assert_mutation_policy_completeness` (Task 2).

- [ ] **Step 1: Test qui échoue**

```python
"""The mutation-policy assert refuses to boot on an incomplete catalogue (ADR-263)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.infrastructure.startup import agents as startup_agents

pytestmark = [pytest.mark.unit]


def test_boot_refuses_an_incomplete_policy_catalogue() -> None:
    with (
        patch.object(startup_agents, "initialize_catalogue"),
        patch(
            "src.domains.agents.registry.catalogue.assert_tool_category_completeness",
            return_value=None,
        ),
        patch(
            "src.domains.agents.registry.catalogue.assert_mutation_policy_completeness",
            side_effect=AssertionError("declare no mutation_policy: x_tool"),
        ),
        pytest.raises(RuntimeError, match="Mutation policy registry incomplete"),
    ):
        startup_agents.init_agent_registry()
```

Adapter le nom `init_agent_registry` et ses arguments à la signature réelle lue dans `startup/agents.py` (la fonction qui contient le bloc `assert_tool_category_completeness`) ; si elle exige un checkpointer/store, passer `None` comme le fait le test voisin de ce module s'il existe, sinon des `MagicMock()`.

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/startup/test_agents_startup_policy_guard.py -q -p no:cacheprovider --no-cov`
Expected: FAIL (aucun `RuntimeError` « Mutation policy … »)

- [ ] **Step 3: Brancher la garde juste après celle des catégories**

Dans `startup/agents.py`, après le bloc `except AssertionError as exc: ... raise RuntimeError(f"Tool category registry incomplete: {exc}") from exc` :

```python
        # ADR-263: a non-read-only tool must SAY what confirmation it owes.
        # Same placement and same reason as the category assert above: the
        # manifests only become checkable once the catalogue is loaded.
        try:
            from src.domains.agents.registry.catalogue import (
                assert_mutation_policy_completeness,
            )

            assert_mutation_policy_completeness(registry.list_tool_manifests())
        except AssertionError as exc:
            logger.error("mutation_policy_registry_incomplete", error=str(exc), exc_info=True)
            raise RuntimeError(f"Mutation policy registry incomplete: {exc}") from exc
```

- [ ] **Step 4: Vérifier le passage**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/startup/ -q -p no:cacheprovider --no-cov`
Expected: tous verts.

---

### Task 5: Politique dérivée pour les outils MCP tiers

**Files:**
- Modify: `apps/api/src/infrastructure/mcp/registration.py` (après `declared_tool_category`, ~ligne 466 ; et l'appel `ToolManifest(name=adapter_name, ...)` ~ligne 525-562, plus `build_mcp_react_task_manifest` ~ligne 573)
- Test: `apps/api/tests/unit/infrastructure/mcp/test_mutation_policy_derivation.py` (nouveau)

**Interfaces:**
- Produces: `derive_mcp_mutation_policy(hitl_required: bool, annotations: Any) -> MutationPolicy | None`.

- [ ] **Step 1: Test qui échoue**

```python
"""A third-party MCP tool's policy is DERIVED from its declaration (ADR-263 + ADR-255).

Tightening only: a declared mutation is acted upon (worst case one card too
many), a declared read-only is NOT believed (it would remove the tool from the
safety nets on the word of a third party).
"""

from __future__ import annotations

import pytest

from src.infrastructure.mcp.registration import derive_mcp_mutation_policy

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("hitl", "annotations", "expected"),
    [
        (True, None, "confirm"),
        (True, {"read_only_hint": True}, "confirm"),
        (False, {"destructive_hint": True}, "confirm"),
        (False, {"read_only_hint": False, "destructive_hint": False}, "reversible"),
        (False, {"read_only_hint": False}, "confirm"),  # destructiveHint defaults to TRUE
        (False, {"read_only_hint": True}, None),
        (False, None, None),
        (False, "garbage", None),
    ],
)
def test_derivation(hitl: bool, annotations: object, expected: str | None) -> None:
    assert derive_mcp_mutation_policy(hitl, annotations) == expected
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/mcp/test_mutation_policy_derivation.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ImportError`

- [ ] **Step 3: Implémenter la dérivation**

Après `declares_destructive_tool` dans `registration.py` :

```python
def derive_mcp_mutation_policy(hitl_required: bool, annotations: Any) -> MutationPolicy | None:
    """Derive the confirmation policy of a third-party MCP tool (ADR-263).

    Never more permissive than the declaration (ADR-255 doctrine, spec MUST:
    annotations are untrusted): the server's HITL setting or a declared
    destructive tool → ``confirm``; a tool declared not read-only AND not
    destructive → ``reversible`` ("performs only additive updates"); anything
    else → None, which leaves the name heuristic in charge exactly as today.

    Args:
        hitl_required: Resolved per-server HITL requirement.
        annotations: Normalised hints from :func:`extract_tool_annotations`.

    Returns:
        The derived policy, or None when the declaration says nothing this
        codebase may safely act on.
    """
    if hitl_required:
        return "confirm"
    category = declared_tool_category(annotations)
    if category == "delete":
        return "confirm"
    if category == "update":
        return "reversible"
    return None
```

Importer `MutationPolicy` depuis `src.domains.agents.registry.catalogue` avec les imports existants du module.

- [ ] **Step 4: Passer la politique aux deux manifestes MCP**

Dans l'appel `ToolManifest(name=adapter_name, ...)` (celui qui contient déjà `tool_category=declared_tool_category(annotations)`), ajouter :

```python
        mutation_policy=derive_mcp_mutation_policy(hitl_required, annotations),
```

Dans `build_mcp_react_task_manifest(...)` (le sous-agent itératif par serveur), ajouter sous `permissions=PermissionProfile(hitl_required=hitl_required, ...)` :

```python
        mutation_policy="confirm" if hitl_required else None,
```

- [ ] **Step 5: Vérifier le passage et la non-régression MCP**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/mcp -q -p no:cacheprovider --no-cov`
Expected: tous verts (les suites ADR-255 ne bougent pas).

---

### Task 6: La porte d'approbation ne fabrique plus une approbation sans verdict

**Files:**
- Modify: `apps/api/src/domains/agents/nodes/approval_gate_node.py:101-107`
- Test: `apps/api/tests/unit/domains/agents/nodes/test_approval_gate_no_verdict.py` (nouveau)

**Interfaces:**
- Produces: sur `validation_result` absent, l'état reçoit `plan_approved: None` (inconnu) au lieu de `True`. Aucun lecteur existant ne distingue `None` de `True` (`response_node` teste `is True` pour la cohérence de rejet seulement ; le routeur ne lit jamais la clé) — le lot 2 lira cette valeur.

- [ ] **Step 1: Test qui échoue**

```python
"""No verdict is not an approval (ADR-263, `unknown ≠ pass`)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.nodes import approval_gate_node as gate

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_missing_verdict_yields_unknown_not_true() -> None:
    state = {"execution_plan": SimpleNamespace(plan_id="p1"), "validation_result": None}
    with patch.object(gate, "track_state_updates"):
        result = await gate.approval_gate_node(state, {})  # type: ignore[arg-type]
    assert result["plan_approved"] is None
```

Si `approval_gate_node` est synchrone, retirer `await` et le marqueur asyncio ; vérifier la signature réelle dans le fichier.

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes/test_approval_gate_no_verdict.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `assert True is None`

- [ ] **Step 3: Corriger la branche**

Remplacer :

```python
    if not validation_result:
        logger.warning(
            "approval_gate_no_validation_result",
            msg="No validation result, assuming approval not required",
        )
        result_no_validation: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: True}
```

par :

```python
    if not validation_result:
        # ADR-263: the absence of a verdict is not an approval. `None` keeps
        # the plan executing exactly as before (the router never reads this
        # key) while letting the effect gate of lot 2 tell "approved" from
        # "nobody looked".
        logger.warning(
            "approval_gate_no_verdict",
            plan_id=execution_plan.plan_id,
            msg="No validation result: plan approval left unknown, not granted",
        )
        result_no_validation: dict[str, Any] = {STATE_KEY_PLAN_APPROVED: None}
```

- [ ] **Step 4: Vérifier le passage et les voisins**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/nodes -q -p no:cacheprovider --no-cov -k "approval or gate or routing or response"`
Expected: tous verts.

---

### Task 7: Documentation du lot 0

**Files:**
- Modify: `docs/technical/AGENT_MANIFEST.md` (section `PermissionProfile`, ~ligne 485-515 : ajouter `mutation_policy` / `mutation_policy_reason` à côté de `hitl_required` et le tableau des cinq valeurs)
- Modify: `docs/technical/HITL.md:52-58` (ajouter une phrase : en pipeline un outil **sans brouillon** dont le manifeste ou le serveur MCP exige la confirmation s'exécute aujourd'hui sans carte — corrigé au lot 2 par le point de passage ADR-263 ; renvoyer à la spec)
- Modify: `docs/guides/GUIDE_TOOL_CREATION.md` (à côté de la ligne 542 « HITL Classifier » : ajouter la règle de déclaration : tout outil non lecture seule déclare `mutation_policy`, la garde de boot refuse sinon)
- Modify: `CLAUDE.md` → section « Systemic Rules » / « Tools » : une règle (puis `task docs:sync-agents` pour `AGENTS.md`).

- [ ] **Step 1: Écrire la règle systémique dans `CLAUDE.md` (bloc « Tools »)**

```markdown
- **A non-read-only tool declares what confirmation it owes** (`mutation_policy` on the
  manifest: `draft`, `confirm`, `reversible`, `artefact`, `sandboxed`, with a written reason
  for the last three). Measured 2026-09-03: 13 native tools ran in both execution modes with
  no confirmation gate, and nothing said whether that was a decision. The boot assert
  `assert_mutation_policy_completeness` refuses a missing declaration; a third-party MCP
  tool's policy is DERIVED from its declaration and never more permissive than it (ADR-263).
```

- [ ] **Step 2: Regénérer le miroir et vérifier les docs**

Run: `task docs:sync-agents && task lint:docs`
Expected: `lint:docs` vert (les nouveaux liens résolvent ; aucun compteur en prose).

- [ ] **Step 3: Gates du lot 0**

Run: `task lint && task test:backend:unit:fast && cd apps/api && .venv/Scripts/pytest tests/agents -q -p no:cacheprovider --no-cov`
Expected: tout vert. Consigner les sorties (commande, statut, nombre de tests) dans la mémoire du programme.

---

## Lot 1 — Le registre des effets

### Task 8: Empreintes d'arguments et de résultats

**Files:**
- Create: `apps/api/src/domains/agents/effects/__init__.py`
- Create: `apps/api/src/domains/agents/effects/digest.py`
- Test: `apps/api/tests/unit/domains/agents/effects/test_digest.py`

**Interfaces:**
- Consumes: `compute_call_digest(tool_name, arguments, secret)` (`src/domains/agents/utils/loop_guard.py:37`), `settings.secret_key`.
- Produces: `args_digest(tool_name: str, args: Mapping[str, Any] | None) -> str` (hex 64), `payload_digest(payload: Any) -> str` (hex 64, sha256 d'un JSON canonique, `default=str`), `draft_digest(draft_content: Mapping[str, Any]) -> str` (= `payload_digest`).

- [ ] **Step 1: Tests qui échouent**

```python
"""Digests are stable identities, never proofs of correctness (ADR-263)."""

from __future__ import annotations

import pytest

from src.domains.agents.effects.digest import args_digest, draft_digest, payload_digest

pytestmark = [pytest.mark.unit]


def test_args_digest_is_order_independent_and_keyed() -> None:
    a = args_digest("send_email_tool", {"to": "a@b.c", "subject": "s"})
    b = args_digest("send_email_tool", {"subject": "s", "to": "a@b.c"})
    assert a == b and len(a) == 64
    assert a != args_digest("send_email_tool", {"to": "a@b.c", "subject": "S"})
    assert a != args_digest("reply_email_tool", {"to": "a@b.c", "subject": "s"})


def test_payload_digest_survives_non_json_values() -> None:
    import uuid
    from datetime import UTC, datetime

    d = payload_digest({"id": uuid.UUID(int=1), "at": datetime(2026, 9, 3, tzinfo=UTC)})
    assert len(d) == 64
    assert d == payload_digest({"at": datetime(2026, 9, 3, tzinfo=UTC), "id": uuid.UUID(int=1)})


def test_draft_digest_changes_when_the_draft_is_edited() -> None:
    before = draft_digest({"to": "a@b.c", "body": "v1"})
    after = draft_digest({"to": "a@b.c", "body": "v2"})
    assert before != after
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_digest.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ModuleNotFoundError: src.domains.agents.effects`

- [ ] **Step 3: Implémenter**

`apps/api/src/domains/agents/effects/__init__.py` :

```python
"""Durable ledger of external effects (ADR-263).

One row per external effect the assistant performs: claimed BEFORE the effect,
closed from an explicit result, bound to the authority that allowed it. The
ledger is the source of FACTS about effects; LangGraph state carries intentions
and verdicts.
"""
```

`apps/api/src/domains/agents/effects/digest.py` :

```python
"""Stable identities for the ledger (ADR-263).

A digest answers "is this still exactly the same object?" — never "is this
object correct?". ``args_digest`` reuses the loop guard's keyed digest so the
same call hashes the same way in both places.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from src.core.config import settings
from src.domains.agents.utils.loop_guard import compute_call_digest


def args_digest(tool_name: str, args: Mapping[str, Any] | None) -> str:
    """Keyed digest of a tool call (name + normalised arguments).

    Args:
        tool_name: Tool name.
        args: Call arguments; None is treated as empty.

    Returns:
        64-character hex digest, identical for identical calls.
    """
    return compute_call_digest(tool_name, dict(args or {}), settings.secret_key)


def payload_digest(payload: Any) -> str:
    """SHA-256 of a canonical JSON rendering of ``payload``.

    Args:
        payload: Any JSON-renderable value; non-JSON values fall back to str().

    Returns:
        64-character hex digest.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def draft_digest(draft_content: Mapping[str, Any]) -> str:
    """Digest of the draft content the user was shown (ADR-092 binding).

    Args:
        draft_content: The ``draft_content`` mapping of a pending draft.

    Returns:
        64-character hex digest; an edit yields a new digest, hence a new claim.
    """
    return payload_digest(dict(draft_content))
```

- [ ] **Step 4: Vérifier le passage**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_digest.py -q -p no:cacheprovider --no-cov`
Expected: 3 passed

---

### Task 9: Le modèle `AgentEffect` et sa migration

**Files:**
- Create: `apps/api/src/domains/agents/effects/models.py`
- Modify: `apps/api/src/core/constants.py` (ajouter, dans une section « Agent effects ledger (ADR-263) » : `AGENT_EFFECT_SCHEMA_VERSION: int = 1` avec un commentaire « bump on every additive column; rows say which shape they were written in » et `AGENT_EFFECT_RESULT_PAYLOAD_MAX_BYTES_DEFAULT: int = 65_536`)
- Modify: `apps/api/src/infrastructure/database/registry.py:42-46` (un import de plus dans `import_all_models`)
- Create: migration via `task db:migrate:create -- "agent effects ledger (ADR-263)"`
- Test: `apps/api/tests/unit/domains/agents/effects/test_models.py`

**Interfaces:**
- Produces: `EffectStatus` (`CLAIMED`, `SUCCEEDED`, `FAILED`, `ABANDONED`, `REFUSED`), `EffectSource` (`user`, `scheduled`, `heartbeat`, `subagent`, `peer`), `AgentEffect` (table `agent_effects`), contrainte unique `(thread_id, idempotency_key)`.

- [ ] **Step 1: Test qui échoue**

```python
"""The ledger row: claimed before the effect, closed from a result (ADR-263)."""

from __future__ import annotations

import pytest

from src.domains.agents.effects.models import AgentEffect, EffectSource, EffectStatus

pytestmark = [pytest.mark.unit]


def test_status_vocabulary() -> None:
    assert {s.value for s in EffectStatus} == {"claimed", "succeeded", "failed", "abandoned", "refused"}


def test_source_vocabulary() -> None:
    assert {s.value for s in EffectSource} == {"user", "scheduled", "subagent"}


def test_idempotency_is_unique_per_thread() -> None:
    names = {c.name for c in AgentEffect.__table__.constraints}
    assert "uq_agent_effects_thread_idempotency" in names


def test_result_payload_is_opaque_text() -> None:
    col = AgentEffect.__table__.c.result_payload
    assert col.nullable is True
    assert "encrypted" in (col.comment or "").lower()


def test_label_is_encrypted_and_structured() -> None:
    """The human-readable register (spec §4.6) reads a key + values, never a frozen sentence."""
    col = AgentEffect.__table__.c.label
    assert col.nullable is True
    assert "encrypted" in (col.comment or "").lower()
    assert "i18n_key" in (col.comment or "")


def test_rows_carry_a_schema_version_and_a_truncation_flag() -> None:
    """Spec §9.3: additive evolution, bounded payloads."""
    from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION

    assert AGENT_EFFECT_SCHEMA_VERSION == 1
    assert AgentEffect.__table__.c.schema_version.nullable is False
    assert AgentEffect.__table__.c.result_truncated.nullable is False
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_models.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Écrire le modèle**

`apps/api/src/domains/agents/effects/models.py` :

```python
"""SQLAlchemy model of the effect ledger (ADR-263).

Design rules, each paid for by a measurement in the 2026-09-03 spec:

- The row is CLAIMED before the effect and closed from an explicit result:
  absence of an exception is not proof of delivery.
- ``(thread_id, idempotency_key)`` is unique: the same approval cannot be
  spent twice (simulations 2 and 4: a confirmed draft executed twice).
- ``claim_token`` conditions every close: a stale worker cannot close a row
  it does not own (fencing, Systemic Rules → Persistence).
- No JSONB: every field is a scalar, so nothing can be mutated in place.
- ``result_payload`` is encrypted with ``encrypt_data`` (owner decision n°6):
  it lets a ReAct resume be served from the ledger instead of re-executed.
- Retention: until the account is deleted (``ondelete="CASCADE"``), owner
  decision n°5.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION
from src.infrastructure.database.models import UUIDMixin
from src.infrastructure.database.session import Base


class EffectStatus(str, Enum):
    """Lifecycle of one external effect."""

    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"
    REFUSED = "refused"


class EffectSource(str, Enum):
    """Who asked for the turn that produced the effect.

    Deliberately three values (spec §9.3): the heartbeat runs no tool and a
    peer never mutates on someone else's behalf — two dead values removed
    before they were born.
    """

    USER = "user"
    SCHEDULED = "scheduled"
    SUBAGENT = "subagent"


class AgentEffect(Base, UUIDMixin):
    """One external effect: claimed before it happens, closed from its result."""

    __tablename__ = "agent_effects"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Acting user (retention: deleted with the account).",
    )
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="LangGraph thread the effect belongs to."
    )
    run_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Billing/correlation run id."
    )
    source: Mapped[EffectSource] = mapped_column(
        SAEnum(EffectSource, native_enum=False, length=20), nullable=False
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="pipeline | react | subagent"
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mutation_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Policy that applied when the effect was claimed."
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="tool_call_id (react) | draft_id (draft) | run_id:step_id (pipeline).",
    )
    args_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Keyed digest of tool name + arguments."
    )
    approval_kind: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="draft_critique | tool_confirmation | for_each | policy"
    )
    approval_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="message_id of the card, or draft_id."
    )
    draft_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Digest of the draft_content the user was shown."
    )
    status: Mapped[EffectStatus] = mapped_column(
        SAEnum(EffectStatus, native_enum=False, length=20), nullable=False, index=True
    )
    claim_token: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        comment="Owner token: every close is conditioned on it (fencing).",
    )
    provider_ref: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Provider-side id (message id, event id...)."
    )
    result_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_payload: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Encrypted (encrypt_data) tool result, to serve a resume."
    )
    label: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Encrypted (encrypt_data) JSON {i18n_key, values} built at claim time by "
            "EFFECT_LABEL_BUILDERS (lot 3b); rendered in the user's language at export."
        ),
    )
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    catalogue_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Digest of the catalogue that offered the tool."
    )
    retry_of: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_effects.id", ondelete="SET NULL"),
        nullable=True,
        comment="Previous FAILED/ABANDONED row this claim retries.",
    )
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Spec §9.3: the ledger evolves additively; every row says which shape it
    # was written in, so an export (and a model reading it) never guesses.
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=AGENT_EFFECT_SCHEMA_VERSION, server_default="1"
    )
    result_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True when result_payload was cut at effect_result_payload_max_bytes.",
    )

    __table_args__ = (
        UniqueConstraint("thread_id", "idempotency_key", name="uq_agent_effects_thread_idempotency"),
        Index("ix_agent_effects_user_claimed", "user_id", "claimed_at"),
        Index("ix_agent_effects_run", "run_id"),
    )
```

- [ ] **Step 4: Enregistrer le modèle**

Dans `src/infrastructure/database/registry.py::import_all_models`, à côté de `import src.domains.peers.models  # noqa: F401` :

```python
    import src.domains.agents.effects.models  # noqa: F401
```

- [ ] **Step 5: Vérifier le passage des tests unitaires**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_models.py tests/unit/infrastructure/database -q -p no:cacheprovider --no-cov`
Expected: verts (dont le test d'enregistrement des modèles, s'il existe dans ce dossier).

- [ ] **Step 6: Générer la migration**

Run: `task db:migrate:create -- "agent effects ledger (ADR-263)"`
Expected: un fichier `alembic/versions/2026_09_0X_HHMM-<id>_agent_effects_ledger_adr_260.py` avec `down_revision = "e0f1a2b3c4d5"`.

Vérifier que l'autogénération ne contient QUE `create_table("agent_effects", ...)`, ses deux index et la contrainte unique ; supprimer tout autre `op.*` (une dérive d'un autre modèle n'a rien à faire ici). Compléter le docstring de tête avec trois lignes : le pourquoi (registre des effets, ADR-263), « inert until lot 2 wires the gate », et la rétention (cascade sur `users`). `downgrade()` = `op.drop_table("agent_effects")` après les deux `op.drop_index`.

- [ ] **Step 7: Rejeu de migration et tête unique**

Run: `task db:migrate:replay-check && cd apps/api && .venv/Scripts/alembic heads`
Expected: replay vert, exactement une tête (le nouvel id).

---

### Task 10: Le repository : claim, close, abandon, lecture

**Files:**
- Create: `apps/api/src/domains/agents/effects/repository.py`
- Create: `apps/api/src/domains/agents/effects/schemas.py`
- Modify: `apps/api/src/core/config/agents.py` (nouveau champ `effect_result_payload_max_bytes: int = Field(default=AGENT_EFFECT_RESULT_PAYLOAD_MAX_BYTES_DEFAULT, ge=1_024, description="Cap on the encrypted tool result kept per ledger row; larger results are cut and flagged (ADR-263).")`, importer la constante depuis `src.core.constants`)
- Modify: `.env.example` et `.env.prod.example` (ligne `EFFECT_RESULT_PAYLOAD_MAX_BYTES=65536` avec le même commentaire, dans la section agents ; `task lint:hygiene` vérifie la parité des variables)
- Test (unit, sans base): `apps/api/tests/unit/domains/agents/effects/test_repository_contract.py`
- Test (intégration, PostgreSQL réel): `apps/api/tests/integration/domains/agents/effects/test_ledger_db.py`

**Interfaces:**
- Consumes: `AgentEffect`, `EffectStatus`, `EffectSource` (Task 9), `encrypt_data`/`decrypt_data` (`src/core/security/utils.py:216,230`), `BaseRepository` (`src/core/repository.py:45`).
- Produces:
  - `ClaimRequest` (pydantic): `user_id`, `thread_id`, `run_id`, `source`, `execution_mode`, `tool_name`, `mutation_policy`, `idempotency_key`, `args_digest`, `approval_kind=None`, `approval_ref=None`, `draft_digest=None`, `catalogue_fingerprint=None`, `retry_of=None`.
  - `ClaimOutcome` (dataclass frozen): `effect: AgentEffect`, `claimed: bool` (True = nouvelle ligne, False = ligne existante rendue), `claim_token: uuid.UUID | None` (None quand `claimed` est False).
  - `EffectLedgerRepository(db)` avec `claim(req) -> ClaimOutcome`, `close_success(effect_id, claim_token, *, provider_ref=None, result_payload=None) -> bool`, `close_failure(effect_id, claim_token, *, error_code) -> bool`, `refuse(req, *, error_code) -> AgentEffect`, `abandon_stale(effect_id, *, older_than: datetime) -> bool`, `list_for_run(run_id) -> list[AgentEffect]`, `list_for_user(user_id, *, limit, offset) -> tuple[list[AgentEffect], int]`, `decrypted_result(effect) -> Any | None`.

- [ ] **Step 1: Schémas et contrat (test unitaire qui échoue)**

```python
"""Contract of the ledger repository, without a database (ADR-263)."""

from __future__ import annotations

import uuid

import pytest

from src.domains.agents.effects.repository import ClaimOutcome, EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest

pytestmark = [pytest.mark.unit]


def test_claim_request_rejects_an_unknown_policy() -> None:
    with pytest.raises(ValueError):
        ClaimRequest(
            user_id=uuid.uuid4(), thread_id="t", run_id="r", source="user",
            execution_mode="pipeline", tool_name="x", mutation_policy="maybe",
            idempotency_key="k", args_digest="0" * 64,
        )


def test_outcome_without_claim_has_no_token() -> None:
    outcome = ClaimOutcome(effect=object(), claimed=False, claim_token=None)  # type: ignore[arg-type]
    assert outcome.claimed is False and outcome.claim_token is None


def test_repository_exposes_the_contract() -> None:
    for name in ("claim", "close_success", "close_failure", "refuse", "abandon_stale", "list_for_run", "list_for_user", "decrypted_result"):
        assert callable(getattr(EffectLedgerRepository, name))
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_repository_contract.py -q -p no:cacheprovider --no-cov`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Écrire `schemas.py`**

```python
"""Request/outcome shapes of the effect ledger (ADR-263)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.agents.registry.catalogue import MUTATION_POLICIES

EffectSourceName = Literal["user", "scheduled", "subagent"]


class ClaimRequest(BaseModel):
    """Everything a claim must know BEFORE the effect happens."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID = Field(description="Acting user.")
    thread_id: str = Field(min_length=1, max_length=100, description="LangGraph thread.")
    run_id: str = Field(min_length=1, max_length=100, description="Billing/correlation run id.")
    source: EffectSourceName = Field(description="Who asked for the turn.")
    execution_mode: str = Field(min_length=1, max_length=20, description="pipeline | react | subagent.")
    tool_name: str = Field(min_length=1, max_length=100, description="Tool about to act.")
    mutation_policy: str = Field(description="Policy that applies (one of MUTATION_POLICIES).")
    idempotency_key: str = Field(min_length=1, max_length=200, description="Unique per thread.")
    args_digest: str = Field(min_length=64, max_length=64, description="Keyed digest of the call.")
    approval_kind: str | None = Field(default=None, max_length=30, description="How it was approved.")
    approval_ref: str | None = Field(default=None, max_length=200, description="Card message_id or draft_id.")
    draft_digest: str | None = Field(default=None, min_length=64, max_length=64, description="Digest of the shown draft.")
    catalogue_fingerprint: str | None = Field(default=None, max_length=64, description="Digest of the offering catalogue.")
    retry_of: uuid.UUID | None = Field(default=None, description="Row this claim retries.")
    label: dict[str, Any] | None = Field(
        default=None,
        description="{i18n_key, values} built by EFFECT_LABEL_BUILDERS (lot 3b); stored encrypted.",
    )

    @field_validator("mutation_policy")
    @classmethod
    def _policy_is_known(cls, value: str) -> str:
        if value not in MUTATION_POLICIES:
            raise ValueError(f"unknown mutation_policy {value!r}")
        return value
```

- [ ] **Step 4: Écrire `repository.py`**

```python
"""Effect ledger repository: claim before effect, close from result (ADR-263).

Every write is a single conditional statement so two workers cannot both win:
- ``claim`` is ``INSERT … ON CONFLICT DO NOTHING RETURNING`` on the unique
  ``(thread_id, idempotency_key)``; a lost race returns the existing row.
- every close is ``UPDATE … WHERE id = :id AND claim_token = :token AND
  status = 'claimed'`` — a stale owner, or a second close, updates 0 rows.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.repository import BaseRepository
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.models import AgentEffect, EffectSource, EffectStatus
from src.domains.agents.effects.schemas import ClaimRequest

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ClaimOutcome:
    """Result of a claim.

    Attributes:
        effect: The row — freshly inserted, or the one that already held the key.
        claimed: True when THIS call inserted the row.
        claim_token: Owner token to close the row; None when not claimed.
    """

    effect: AgentEffect
    claimed: bool
    claim_token: uuid.UUID | None


class EffectLedgerRepository(BaseRepository[AgentEffect]):
    """Atomic primitives over ``agent_effects``."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, AgentEffect)

    async def claim(self, req: ClaimRequest) -> ClaimOutcome:
        """Claim the right to perform one effect, exactly once per key.

        Args:
            req: What the effect is and under which authority.

        Returns:
            ``claimed=True`` with a token when this call won the key; otherwise
            the existing row (the caller decides: serve its result, retry a
            FAILED one with ``retry_of``, or abandon a stale CLAIMED one).
        """
        token = uuid.uuid4()
        stmt = (
            pg_insert(AgentEffect)
            .values(
                id=uuid.uuid4(),
                user_id=req.user_id,
                thread_id=req.thread_id,
                run_id=req.run_id,
                source=EffectSource(req.source),
                execution_mode=req.execution_mode,
                tool_name=req.tool_name,
                mutation_policy=req.mutation_policy,
                idempotency_key=req.idempotency_key,
                args_digest=req.args_digest,
                approval_kind=req.approval_kind,
                approval_ref=req.approval_ref,
                draft_digest=req.draft_digest,
                catalogue_fingerprint=req.catalogue_fingerprint,
                retry_of=req.retry_of,
                label=(
                    encrypt_data(json.dumps(req.label, default=str, ensure_ascii=False))
                    if req.label is not None
                    else None
                ),
                status=EffectStatus.CLAIMED,
                claim_token=token,
                claimed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_agent_effects_thread_idempotency")
            .returning(AgentEffect.id)
        )
        inserted_id = (await self.db.execute(stmt)).scalar_one_or_none()
        if inserted_id is not None:
            await self.db.flush()
            effect = await self.db.get(AgentEffect, inserted_id)
            assert effect is not None  # just inserted in this transaction
            return ClaimOutcome(effect=effect, claimed=True, claim_token=token)
        existing = (
            await self.db.execute(
                select(AgentEffect).where(
                    AgentEffect.thread_id == req.thread_id,
                    AgentEffect.idempotency_key == req.idempotency_key,
                )
            )
        ).scalar_one()
        logger.info(
            "effect_claim_lost",
            tool_name=req.tool_name,
            existing_status=existing.status.value,
            run_id=req.run_id,
        )
        return ClaimOutcome(effect=existing, claimed=False, claim_token=None)

    async def _close(
        self,
        effect_id: uuid.UUID,
        claim_token: uuid.UUID,
        *,
        status: EffectStatus,
        **values: Any,
    ) -> bool:
        stmt = (
            update(AgentEffect)
            .where(
                AgentEffect.id == effect_id,
                AgentEffect.claim_token == claim_token,
                AgentEffect.status == EffectStatus.CLAIMED,
            )
            .values(status=status, closed_at=datetime.now(UTC), **values)
        )
        result = await self.db.execute(stmt)
        return result.rowcount == 1

    async def close_success(
        self,
        effect_id: uuid.UUID,
        claim_token: uuid.UUID,
        *,
        provider_ref: str | None = None,
        result_payload: Any = None,
    ) -> bool:
        """Mark the effect SUCCEEDED from an explicit result.

        Args:
            effect_id: Row id returned by ``claim``.
            claim_token: Owner token returned by ``claim``.
            provider_ref: Provider-side identifier when the tool returns one.
            result_payload: Tool result to keep (encrypted) so a resume can be
                served without re-executing.

        Returns:
            True when this call closed the row; False for a stale owner or a
            row no longer CLAIMED.
        """
        encrypted: str | None = None
        truncated = False
        if result_payload is not None:
            rendered = json.dumps(result_payload, default=str, ensure_ascii=False)
            cap = settings.effect_result_payload_max_bytes
            raw = rendered.encode("utf-8")
            if len(raw) > cap:
                # Spec §9.3: a bounded ledger, and a row that SAYS it was cut.
                rendered = raw[:cap].decode("utf-8", errors="ignore")
                truncated = True
            encrypted = encrypt_data(rendered)
        return await self._close(
            effect_id,
            claim_token,
            status=EffectStatus.SUCCEEDED,
            provider_ref=provider_ref,
            result_digest=payload_digest(result_payload) if result_payload is not None else None,
            result_payload=encrypted,
            result_truncated=truncated,
        )

    async def close_failure(
        self, effect_id: uuid.UUID, claim_token: uuid.UUID, *, error_code: str
    ) -> bool:
        """Mark the effect FAILED (the effect did NOT happen, or is unknown to have)."""
        return await self._close(
            effect_id, claim_token, status=EffectStatus.FAILED, error_code=error_code[:50]
        )

    async def refuse(self, req: ClaimRequest, *, error_code: str) -> AgentEffect:
        """Record a REFUSED effect (authority missing) — no claim, no effect.

        A refusal is a fact worth keeping: it is what the answer will say, and
        what the operator will count. The unique key is suffixed so a later
        legitimate claim on the same operation is not blocked by its refusal.
        """
        row = AgentEffect(
            id=uuid.uuid4(),
            user_id=req.user_id,
            thread_id=req.thread_id,
            run_id=req.run_id,
            source=EffectSource(req.source),
            execution_mode=req.execution_mode,
            tool_name=req.tool_name,
            mutation_policy=req.mutation_policy,
            idempotency_key=f"{req.idempotency_key}#refused:{uuid.uuid4().hex[:8]}",
            args_digest=req.args_digest,
            approval_kind=req.approval_kind,
            approval_ref=req.approval_ref,
            draft_digest=req.draft_digest,
            catalogue_fingerprint=req.catalogue_fingerprint,
            status=EffectStatus.REFUSED,
            claim_token=uuid.uuid4(),
            error_code=error_code[:50],
            claimed_at=datetime.now(UTC),
            closed_at=datetime.now(UTC),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def abandon_stale(self, effect_id: uuid.UUID, *, older_than: datetime) -> bool:
        """Mark a CLAIMED row ABANDONED when its owner never closed it.

        Conditioned on ``claimed_at < older_than`` so a live claim (its owner
        still inside the tool's timeout) is never abandoned by a concurrent
        caller. The caller then claims again with ``retry_of``.
        """
        stmt = (
            update(AgentEffect)
            .where(
                AgentEffect.id == effect_id,
                AgentEffect.status == EffectStatus.CLAIMED,
                AgentEffect.claimed_at < older_than,
            )
            .values(status=EffectStatus.ABANDONED, closed_at=datetime.now(UTC))
        )
        return (await self.db.execute(stmt)).rowcount == 1

    async def list_for_run(self, run_id: str) -> list[AgentEffect]:
        """Every effect of one run, oldest first (the response node's facts)."""
        rows = await self.db.execute(
            select(AgentEffect).where(AgentEffect.run_id == run_id).order_by(AgentEffect.claimed_at)
        )
        return list(rows.scalars().all())

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[AgentEffect], int]:
        """One page of a user's effects, newest first, with the EXACT total (ADR-185)."""
        total = (
            await self.db.execute(
                select(func.count()).select_from(AgentEffect).where(AgentEffect.user_id == user_id)
            )
        ).scalar_one()
        rows = await self.db.execute(
            select(AgentEffect)
            .where(AgentEffect.user_id == user_id)
            .order_by(AgentEffect.claimed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total)

    @staticmethod
    def decrypted_result(effect: AgentEffect) -> Any | None:
        """Decrypt the kept result, or None when none was kept.

        A truncated payload is not valid JSON any more: it comes back as
        ``{"truncated": True, "text": <cut text>}`` so a caller can show it
        but never mistake it for the full result (a resume must re-execute).
        """
        if effect.result_payload is None:
            return None
        text = decrypt_data(effect.result_payload)
        if effect.result_truncated:
            return {"truncated": True, "text": text}
        return json.loads(text)
```

- [ ] **Step 5: Vérifier le passage du contrat**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects -q -p no:cacheprovider --no-cov`
Expected: verts.

- [ ] **Step 6: Tests d'intégration à deux acteurs (PostgreSQL réel)**

`apps/api/tests/integration/domains/agents/effects/test_ledger_db.py` (créer aussi les `__init__.py` du chemin si le dossier `tests/integration/domains/agents` n'en a pas) :

```python
"""The ledger against a real PostgreSQL: one winner per key, fenced closes (ADR-263)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    row = User(email=f"ledger-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", is_active=True)
    async_session.add(row)
    await async_session.flush()
    return row


def _req(user: User, key: str = "call-1", **overrides: object) -> ClaimRequest:
    base: dict[str, object] = {
        "user_id": user.id, "thread_id": "thread-A", "run_id": "run-1", "source": "user",
        "execution_mode": "react", "tool_name": "send_email_tool", "mutation_policy": "draft",
        "idempotency_key": key, "args_digest": "a" * 64,
    }
    base.update(overrides)
    return ClaimRequest(**base)  # type: ignore[arg-type]


async def test_same_key_claimed_once(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    first = await repo.claim(_req(user))
    second = await repo.claim(_req(user))
    assert first.claimed is True and first.claim_token is not None
    assert second.claimed is False and second.claim_token is None
    assert second.effect.id == first.effect.id


async def test_close_needs_the_owner_token(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    outcome = await repo.claim(_req(user, key="call-2"))
    assert await repo.close_success(outcome.effect.id, uuid.uuid4(), provider_ref="m1") is False
    assert await repo.close_success(outcome.effect.id, outcome.claim_token, provider_ref="m1", result_payload={"id": "m1"}) is True  # type: ignore[arg-type]
    assert await repo.close_success(outcome.effect.id, outcome.claim_token, provider_ref="m2") is False  # type: ignore[arg-type]
    await async_session.refresh(outcome.effect)
    assert outcome.effect.status is EffectStatus.SUCCEEDED
    assert outcome.effect.provider_ref == "m1"
    assert repo.decrypted_result(outcome.effect) == {"id": "m1"}
    assert outcome.effect.result_payload != '{"id": "m1"}'  # stored encrypted


async def test_stale_claim_is_abandoned_then_reclaimed_as_retry(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    stale = await repo.claim(_req(user, key="call-3"))
    assert await repo.abandon_stale(stale.effect.id, older_than=datetime.now(UTC) - timedelta(hours=1)) is False
    assert await repo.abandon_stale(stale.effect.id, older_than=datetime.now(UTC) + timedelta(seconds=1)) is True
    retry = await repo.claim(_req(user, key="call-3:retry-1", retry_of=stale.effect.id))
    assert retry.claimed is True and retry.effect.retry_of == stale.effect.id


async def test_refusal_does_not_block_a_later_claim(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    refused = await repo.refuse(_req(user, key="call-4"), error_code="no_verdict")
    assert refused.status is EffectStatus.REFUSED
    assert (await repo.claim(_req(user, key="call-4"))).claimed is True


async def test_user_page_carries_the_exact_total(async_session: AsyncSession, user: User) -> None:
    repo = EffectLedgerRepository(async_session)
    for i in range(3):
        await repo.claim(_req(user, key=f"page-{i}"))
    rows, total = await repo.list_for_user(user.id, limit=2, offset=0)
    assert len(rows) == 2 and total == 3


async def test_oversized_result_is_cut_and_flagged(
    async_session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "effect_result_payload_max_bytes", 1_024, raising=False)
    repo = EffectLedgerRepository(async_session)
    outcome = await repo.claim(_req(user, key="big-1"))
    big = {"body": "x" * 5_000}
    assert await repo.close_success(outcome.effect.id, outcome.claim_token, result_payload=big) is True  # type: ignore[arg-type]
    await async_session.refresh(outcome.effect)
    assert outcome.effect.result_truncated is True
    served = repo.decrypted_result(outcome.effect)
    assert served["truncated"] is True and len(served["text"]) <= 1_024
```

Adapter le constructeur `User(...)` aux colonnes obligatoires réelles (`grep -n "nullable=False" src/domains/users/models.py`) ; réutiliser la fixture de création d'utilisateur de `tests/integration/domains/peers/test_repository_db.py` si elle est importable.

- [ ] **Step 7: Lancer l'intégration**

Run: `task test:backend:integration -- tests/integration/domains/agents/effects -q`
Expected: 6 passed (PostgreSQL + Redis requis : conteneurs dev).

---

### Task 11: Documentation du lot 1 et gates

**Files:**
- Modify: `docs/technical/DATABASE_SCHEMA.md` (nouvelle sous-section « agent_effects » dans « Tables Core » ou la section agents existante, avec les colonnes, la contrainte unique, la rétention et le chiffrement de `result_payload`)
- Modify: `docs/superpowers/specs/2026-09-03-execution-authority-ledger-design.md` §4.2 (ajouter `claim_token`, `result_payload` et `REFUSED` au tableau pour qu'il décrive la table livrée)

- [ ] **Step 1: Écrire la section de schéma** (colonnes exactement celles du modèle, aucune valeur numérique inventée ; renvoyer à `apps/api/src/domains/agents/effects/models.py`).

- [ ] **Step 2: Gates du lot 1**

Run: `task lint && task test:backend:unit:fast && task db:migrate:replay-check && task test:backend:integration -- tests/integration/domains/agents/effects -q`
Expected: tout vert. Consigner les sorties dans la mémoire du programme.

- [ ] **Step 3: Preuve runtime Docker**

Run: `docker compose exec api alembic upgrade head` (ou `task db:migrate` selon la topologie dev), puis `docker compose exec db psql -U <user> -d <db> -c "\d agent_effects"`
Expected: la table, ses index et la contrainte unique existent dans `lia-db-dev` ; l'API redémarre saine (`/health` vert) avec la garde du lot 0 active (aucun `mutation_policy_registry_incomplete` dans les logs).

---

## Self-review (fait à la rédaction)

- **Couverture de la spec** : §4.1 (politique, raison, garde, MCP dérivé) → Tasks 1-5 ; §4.2 (registre, claim/close/abandon, digests, résultat chiffré, rétention) → Tasks 8-10 ; porte sans verdict → Task 6 ; docs lot 0/1 → Tasks 7 et 11 ; règle systémique CLAUDE.md → Task 7. Hors de ce plan, délibérément : le point de passage `authorize_effect`, le branchement des exécuteurs, le chemin `tool_confirmation` du pipeline, les sources non humaines, la liste blanche sous-agent, le leader Lua, la surface de preuve, les métriques, l'ADR-263 et les **registres exportables** (spec §4.6 : registre lisible utilisateur/admin, export technique JSONL pseudonymisé) — lots 2, 3 et 3b, plan suivant, qui consommera `EffectLedgerRepository.claim/close_success/close_failure/refuse/abandon_stale/list_for_user` et `ToolManifest.mutation_policy`. La colonne `label` (chiffrée, `{i18n_key, values}`) et le champ `ClaimRequest.label` sont créés dès ce lot pour qu'aucune seconde migration ne soit nécessaire ; personne ne les remplit avant le lot 3b.
- **Placeholders** : aucun « TBD » ; les deux points d'adaptation signalés (signature réelle d'`init_agent_registry`, colonnes obligatoires de `User`) sont des vérifications, avec la commande pour les lever.
- **Cohérence des types** : `MutationPolicy`/`MUTATION_POLICIES` (Task 1) sont lus par Tasks 2, 5 et 10 sous le même nom ; `ClaimRequest`/`ClaimOutcome`/`EffectLedgerRepository` (Task 10) portent les noms que le lot 2 utilisera ; `EffectStatus`/`EffectSource` (Task 9) sont ceux du repository.
