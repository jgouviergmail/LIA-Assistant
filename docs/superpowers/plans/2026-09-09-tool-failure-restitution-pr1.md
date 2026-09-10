# Restitution honnête des échecs d'outils — plan PR 1 (lots A, B, C, gardes G1/G2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (owner rule: no sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking. **No git action is ever performed by the assistant** (owner rule): every « Point de contrôle » reports the evidence and the owner commits on request.

**Goal:** Qu'un échec d'outil en mode pipeline atteigne le modèle de réponse avec son code et son message, qu'un succès survive à un échec voisin, que les métriques et les logs disent la même chose que le registre ADR-263, et que deux gardes rendent la classe de défaut rouge en CI.

**Architecture:** Un vocabulaire (`AgentResultStatus` = `SUCCESS`/`ERROR`), un agrégat binaire portant `failed_steps`, un canal unique par fait vers le prompt (échecs de steps → `runtime_failures_directive` lisant la forme réelle de `completed_steps` et **non conditionnée** au drapeau diagnostics ; erreurs d'agent → formateur), un prédicat de succès partagé dans `core/tool_outcome.py` pour le registre et le décorateur de métriques, une taxonomie HTTP structurelle pour le fetch, un replanner qui lit le code typé, et deux gardes AST.

**Tech Stack:** Python 3.14, Pydantic 2, LangGraph 1.x, structlog, pytest (`asyncio_mode=auto`), Prometheus client, Grafana JSON.

**Spec:** `docs/superpowers/specs/2026-09-09-tool-failure-restitution-design.md`

## Global Constraints

- Root `CLAUDE.md` en entier ; en particulier : i18n backend canonique `zh-CN` via `normalize_language` ; aucune chaîne utilisateur inline en Python ; aucun nombre réglable dans un prompt ; `structlog` seulement ; pas de PII en INFO/WARNING (domaine oui, URL non) ; pas d'`except: pass` ; pas d'action git.
- **Marges de taille, mesurées le 2026-09-10** (`scripts/audit/measure_sloc.py` + `tests/unit/file_size_baseline.json` ; plafond global 600 SLOC logiques pour un fichier non gelé) — elles dictent où le code est écrit :

| Fichier | Mesuré / plafond | Marge |
|---|---|---|
| `nodes/task_orchestrator_node.py` | 666 / 680 (gelé) | **14** → **non modifié par cette PR** |
| `orchestration/adaptive_replanner.py` | 572 / 600 | **28** → la classification est **extraite** (tâche 11) |
| `orchestration/parallel_executor.py` | 2125 / 2157 (gelé) | 32 → tâches 2 et 3, net ≈ +5 |
| `nodes/response_node.py` | 2209 / 2254 (gelé) | 45 → une ligne (tâche 6) |
| `orchestration/mappers.py` | 470 / 600 | **130** → c'est là que vit le calcul |
| `formatters/agent_results.py` | 107 / 600 | 493 |
| `tools/web_fetch_tools.py` | 383 / 600 | 217 |
| `tools/common.py` | 227 / 600 | 373 |
| `diagnostics/failure_context.py` | 85 / 600 | 515 |
| `observability/decorators.py` | 291 / 600 | 309 |

Vérifier après coup : `.venv/Scripts/python ../../scripts/audit/measure_sloc.py src` (le fichier ne doit pas dépasser son plafond).
- Tests : `pytestmark = [pytest.mark.unit]` sur tout nouveau fichier sous `tests/unit/` (`--strict-markers`) ; un test double qui reçoit une coroutine l'attend ; jamais de faux objet à attributs pour simuler un `model_dump()` (D5).
- Commandes (depuis `apps/api/`) : `.venv/Scripts/pytest <chemin> -v -p no:cacheprovider` ; gates depuis la racine : `task lint`, `task test:backend:unit:fast`, `task test:backend:agents` (hors hook — **obligatoire** après toute modification de `agents/api/service.py` ou d'une signature qu'il appelle), `task ci:fast` avant tout push.
- `tests/agents/` n'est PAS exécutée par le hook : la lancer explicitement (`task test:backend:agents`).
- Pas de nouvelle dépendance. Pas de migration. Pas de nouvelle clé `MessagesState`.

---

### Tâche 0 : Rejeu du tour de production comme test rouge

**Files:**
- Create: `apps/api/tests/unit/domains/agents/formatters/test_tool_failure_restitution_prod_replay.py`

**Interfaces:**
- Consumes: `map_execution_result_to_agent_result` (mappers), `format_agent_results_for_prompt` (formatters), `extract_failures_from_steps` (diagnostics/failure_context), `ExecutionResult`/`StepResult` (orchestration/schemas).
- Produces: le test de caractérisation que les tâches 2, 4 et 5 rendent vert.

- [ ] **Step 1: Écrire le test (rouge aujourd'hui)**

```python
"""Replay of production turn 514706d6 (2026-09-09, three fetch_web_page_tool 403s).

What the executor wrote, what the mapper made of it, what the prompt received.
Red before ADR-281: the prompt got « ❓ plan_executor: Statut inconnu (failed) »
and the runtime failures directive found nothing.
"""

from __future__ import annotations

import pytest

from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult
from src.domains.diagnostics.failure_context import extract_failures_from_steps

pytestmark = [pytest.mark.unit]

_IDS = ("66103994839", "87103543658", "69119842856")


def _error(listing_id: str) -> str:
    return f"HTTP error 403 fetching https://www.lacentrale.fr/auto-occasion-annonce-{listing_id}.html"


def _completed_steps() -> dict[str, dict[str, object]]:
    """EXACTLY the shape parallel_executor writes for a failed TOOL step."""
    return {
        f"step_{i + 1}": {"success": False, "error": _error(lid), "error_code": "EXTERNAL_API_ERROR"}
        for i, lid in enumerate(_IDS)
    }


def _step_results() -> list[StepResult]:
    return [
        StepResult(
            step_index=i,
            tool_name="fetch_web_page_tool",
            args={"url": f"https://www.lacentrale.fr/auto-occasion-annonce-{lid}.html"},
            result=_completed_steps()[f"step_{i + 1}"],
            success=False,
            error=_error(lid),
        )
        for i, lid in enumerate(_IDS)
    ]


def test_the_prompt_never_says_unknown_status() -> None:
    steps = _step_results()
    execution_result = ExecutionResult(
        success=False,
        step_results=steps,
        total_steps=3,
        completed_steps=3,
        failed_step_index=0,
        error=steps[0].error,
        total_execution_time_ms=0,
    )
    agent_results = map_execution_result_to_agent_result(
        execution_result=execution_result, plan_id="p", turn_id=9
    )
    prompt = format_agent_results_for_prompt(agent_results, current_turn_id=9, user_language="fr")
    assert "inconnu" not in prompt.lower()
    assert "unknown" not in prompt.lower()


def test_the_directive_lists_every_failed_fetch_with_its_code() -> None:
    failures = extract_failures_from_steps(_completed_steps())
    assert len(failures) == 3
    assert {f["error_code"] for f in failures} == {"EXTERNAL_API_ERROR"}
    assert all(f["message"].startswith("HTTP error 403") for f in failures)
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/formatters/test_tool_failure_restitution_prod_replay.py -v -p no:cacheprovider`
Expected: 2 FAILED — `'Statut inconnu (failed)'` dans le prompt ; `extract_failures_from_steps` renvoie `[]`.

- [ ] **Step 3: Point de contrôle** — rapporter les deux échecs tels quels (ils sont la preuve de D1 et D15).

---

### Tâche 1 : Un vocabulaire, deux valeurs — `AgentResultStatus`, `FailedStep`, suppression du code mort

**Files:**
- Modify: `apps/api/src/domains/agents/constants.py:507-520` (bloc AGENT STATUS VALUES) + import `StrEnum` en tête
- Modify: `apps/api/src/domains/agents/orchestration/schemas.py` (`AgentResult` lignes ~279-300 ; supprimer `create_pending_agent_result` lignes ~422-441 ; ajouter `FailedStep` avant `AgentResult`)
- Modify: `apps/api/tests/unit/domains/agents/orchestration/test_schemas.py` (supprimer la classe `TestCreatePendingAgentResult` à partir de la ligne 419 et l'import ligne 21)
- Modify: `apps/api/tests/agents/test_agent_result_schemas.py` (supprimer la classe `TestCreatePendingAgentResult` lignes 235-260 et l'import ligne 15)
- Create: `apps/api/tests/unit/domains/agents/test_agent_status_vocabulary_guard.py` (partie 1 — la parité Literal/enum ; complétée en tâche 7)

**Interfaces:**
- Produces: `AgentResultStatus(StrEnum)` avec `SUCCESS = "success"`, `ERROR = "error"` ; alias `STATUS_SUCCESS`, `STATUS_ERROR` (str) ; `FailedStep(BaseModel)` avec `step_index: int`, `tool_name: str`, `error: str | None`, `error_code: str | None` ; `AgentResult.failed_steps: list[FailedStep]` (défaut `[]`) ; `AgentResult.status: Literal["success", "error"]`.
- Removes: `STATUS_CONNECTOR_DISABLED`, `ALL_AGENT_STATUSES`, `create_pending_agent_result`.

- [ ] **Step 1: Test rouge — le Literal est l'enum**

```python
"""Vocabulary guard for agent result statuses (ADR-281) — part 1: the Literal IS the enum."""

from __future__ import annotations

from typing import get_args

import pytest

from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.orchestration.schemas import AgentResult

pytestmark = [pytest.mark.unit]


def test_the_literal_and_the_enum_are_the_same_vocabulary() -> None:
    literal_values = set(get_args(AgentResult.model_fields["status"].annotation))
    assert literal_values == {member.value for member in AgentResultStatus}
    assert literal_values == {"success", "error"}
```

Run: `.venv/Scripts/pytest tests/unit/domains/agents/test_agent_status_vocabulary_guard.py -v -p no:cacheprovider` → FAIL (`ImportError: AgentResultStatus`).

- [ ] **Step 2: Le vocabulaire dans `agents/constants.py`**

Ajouter `from enum import StrEnum` en tête (avant `from src.core.constants import (`), puis remplacer le bloc lignes 507-520 par :

```python
# ============================================================================
# AGENT STATUS VALUES (agent result states)
# ============================================================================


class AgentResultStatus(StrEnum):
    """Aggregate status of an ``AgentResult`` — the ONLY vocabulary a reader compares against.

    ``ERROR`` means every step of the agent's work failed; ``SUCCESS`` means at
    least one step produced something. A partial failure is ``SUCCESS`` with a
    non-empty ``AgentResult.failed_steps``: the field, not the status, states
    the partial (ADR-281). ``failed``, ``pending`` and ``connector_disabled``
    were declared here once — one had a single writer the readers ignored, the
    other two had no writer at all.
    """

    SUCCESS = "success"
    ERROR = "error"


# Plain-string aliases for the readers that compare against strings.
STATUS_SUCCESS = AgentResultStatus.SUCCESS.value
STATUS_ERROR = AgentResultStatus.ERROR.value
```

- [ ] **Step 3: `FailedStep` et `AgentResult` dans `orchestration/schemas.py`**

Avant `class AgentResult(BaseModel):` :

```python
class FailedStep(BaseModel):
    """One step of a plan that did not succeed, exactly as the executor recorded it (ADR-281)."""

    step_index: int = Field(description="Position of the step in the plan")
    tool_name: str = Field(description="Tool the step called")
    error: str | None = Field(default=None, description="Error message the tool returned")
    error_code: str | None = Field(
        default=None, description="ToolErrorCode value when the tool gave one, else None"
    )
```

Dans `AgentResult` : docstring `status: Execution status (success, error — see AgentResultStatus)`, `error: Error message when status is error`, ajouter `failed_steps: Every step that failed, whatever the aggregate status` ; puis :

```python
    status: Literal["success", "error"] = Field(
        description="Aggregate status — the values of AgentResultStatus"
    )
```

et après `duration_ms` :

```python
    failed_steps: list[FailedStep] = Field(
        default_factory=list,
        description="Every step that failed, whatever the aggregate status (ADR-281)",
    )
```

Supprimer la fonction `create_pending_agent_result` (et son commentaire « Helper function for creating empty AgentResult »). Vérifier `__all__` s'il existe : `grep -n "create_pending_agent_result\|__all__" src/domains/agents/orchestration/schemas.py src/domains/agents/orchestration/__init__.py` et retirer l'export.

- [ ] **Step 4: Supprimer les tests du code mort**

Dans `tests/unit/domains/agents/orchestration/test_schemas.py` : supprimer l'import `create_pending_agent_result` (ligne 21) et toute la classe `TestCreatePendingAgentResult` (de la ligne 419 jusqu'à la classe suivante — `awk 'NR>419 && /^class /{print NR; exit}' …` donne la borne). Même chose dans `tests/agents/test_agent_result_schemas.py` (import ligne 15, classe lignes 235-260 ; la classe `TestAgentResultRoundTrip` à la ligne 261 reste).

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/test_agent_status_vocabulary_guard.py tests/unit/domains/agents/orchestration/test_schemas.py tests/agents/test_agent_result_schemas.py -v -p no:cacheprovider`
Expected: PASS ; `grep -rn "STATUS_CONNECTOR_DISABLED\|ALL_AGENT_STATUSES\|create_pending_agent_result" src/ tests/` → seulement `orchestrator.py` (traité en tâche 6) et éventuellement `test_orchestrator.py`.

- [ ] **Step 6: Point de contrôle** — lister les fichiers touchés et le résultat des deux commandes.

---

### Tâche 2 : Le mapper — agrégat binaire, `failed_steps`, code typé partagé

**Files:**
- Modify: `apps/api/src/domains/agents/tools/common.py` (ajouter `coerce_tool_error_code` après `ToolErrorCode`)
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py:2456-2466` (remplacer le `try/except ValueError` par l'helper — net négatif en lignes)
- Modify: `apps/api/src/domains/agents/orchestration/mappers.py` (deux helpers + la construction ligne 842-850)
- **NON modifiés** : `task_orchestrator_node.py` et `initiative_node.py` — les deux producteurs d'`ExecutionResult`. Le calcul vit dans le mapper (spec §3.2) : les deux chemins sont corrigés sans être touchés, `all_steps_success` garde sa sémantique pour son second lecteur (`STATE_KEY_LAST_ACTION_TURN_ID`, ligne 952), et le fichier à 14 lignes de marge n'est pas sollicité.
- Modify: `apps/api/tests/unit/domains/agents/orchestration/test_mappers.py:828` (`"failed"` → `"error"`)
- Modify: `apps/api/tests/agents/test_mappers.py:154` (→ `"error"`) et `:233` (→ `"success"` + `failed_steps` : c'est D2 encodé)
- Modify: `apps/api/tests/agents/test_execution_result_mapping.py` (D17 : le test qui réimplémente le mapping)
- Create: `apps/api/tests/unit/domains/agents/orchestration/test_mappers_failed_steps.py`
- Create: `apps/api/tests/unit/domains/agents/tools/test_tool_error_taxonomy.py` (partie 1 — `coerce_tool_error_code` ; `http_status_to_error_code` ajouté en tâche 9)

**Interfaces:**
- Produces: `coerce_tool_error_code(value: object) -> ToolErrorCode | None` ; `_failed_steps_of(execution_result) -> list[FailedStep]` ; `_aggregate_status(execution_result, failed_count) -> str` ; `AgentResult.status == "error"` **ssi** tous les steps exécutés ont échoué (ou, sans aucun step, quand `execution_result.success` est faux) ; `AgentResult.failed_steps` rempli dans tous les cas ; `AgentResult.error` rempli seulement quand le statut est `ERROR`.

- [ ] **Step 1: Tests rouges**

`tests/unit/domains/agents/tools/test_tool_error_taxonomy.py` :

```python
"""ToolErrorCode taxonomy helpers (ADR-281): coercion and HTTP classification are structural."""

from __future__ import annotations

import pytest

from src.domains.agents.tools.common import ToolErrorCode, coerce_tool_error_code

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FORBIDDEN", ToolErrorCode.FORBIDDEN),
        (ToolErrorCode.TIMEOUT, ToolErrorCode.TIMEOUT),
        ("RATE_LIMITED", None),  # free-form code a tool invented — not a member
        ("", None),
        (None, None),
    ],
)
def test_coerce_tool_error_code(raw: object, expected: ToolErrorCode | None) -> None:
    assert coerce_tool_error_code(raw) is expected
```

`tests/unit/domains/agents/orchestration/test_mappers_failed_steps.py` :

```python
"""The plan aggregate is binary and always carries its failed steps (ADR-281)."""

from __future__ import annotations

import pytest

from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = [pytest.mark.unit]


def _ok(index: int, tool: str = "create_reminder_tool") -> StepResult:
    return StepResult(
        step_index=index,
        tool_name=tool,
        args={},
        result={"success": True, "data": {"result": "🔔 Reminder created"}, "message": "🔔 Reminder created"},
        success=True,
    )


def _ko(index: int, error: str, code: ToolErrorCode | None = ToolErrorCode.FORBIDDEN) -> StepResult:
    return StepResult(
        step_index=index,
        tool_name="fetch_web_page_tool",
        args={},
        result={"success": False, "error": error, "error_code": code.value if code else None},
        success=False,
        error=error,
        error_code=code,
    )


def _map(steps: list[StepResult], success: bool) -> dict:
    failed = [s for s in steps if not s.success]
    execution_result = ExecutionResult(
        success=success,
        step_results=steps,
        total_steps=len(steps),
        completed_steps=len(steps),
        failed_step_index=failed[0].step_index if failed else None,
        error=failed[0].error if failed and not success else None,
        total_execution_time_ms=0,
    )
    return map_execution_result_to_agent_result(
        execution_result=execution_result, plan_id="p", turn_id=9
    )["9:plan_executor"]


def test_total_failure_is_error_and_lists_every_step() -> None:
    entry = _map([_ko(0, "HTTP error 403 fetching a"), _ko(1, "HTTP error 403 fetching b")], success=False)
    assert entry["status"] == AgentResultStatus.ERROR.value
    assert [f["error"] for f in entry["failed_steps"]] == ["HTTP error 403 fetching a", "HTTP error 403 fetching b"]
    assert entry["failed_steps"][0]["error_code"] == "FORBIDDEN"
    assert entry["failed_steps"][0]["tool_name"] == "fetch_web_page_tool"
    assert entry["error"] == "HTTP error 403 fetching a"


def test_partial_failure_is_success_with_failed_steps() -> None:
    entry = _map([_ok(0), _ko(1, "HTTP error 403 fetching a")], success=True)
    assert entry["status"] == AgentResultStatus.SUCCESS.value
    assert len(entry["failed_steps"]) == 1
    assert entry["error"] is None


def test_clean_plan_has_no_failed_steps() -> None:
    entry = _map([_ok(0)], success=True)
    assert entry["status"] == AgentResultStatus.SUCCESS.value
    assert entry["failed_steps"] == []


def test_an_untyped_code_is_kept_as_none() -> None:
    entry = _map([_ko(0, "boom", code=None)], success=False)
    assert entry["failed_steps"][0]["error_code"] is None


def test_the_code_is_read_from_the_raw_step_dict_when_the_typed_field_is_empty() -> None:
    """The shape task_orchestrator_node and initiative_node build: result=step_data, error_code unset."""
    step = StepResult(
        step_index=0,
        tool_name="fetch_web_page_tool",
        args={},
        result={"success": False, "error": "HTTP error 403 fetching https://x", "error_code": "FORBIDDEN"},
        success=False,
        error="HTTP error 403 fetching https://x",
    )
    entry = _map([step], success=False)
    assert entry["failed_steps"][0]["error_code"] == "FORBIDDEN"


def test_a_plan_that_failed_before_running_anything_is_an_error() -> None:
    """No step at all: the plan's own verdict is the only one there is."""
    execution_result = ExecutionResult(
        success=False, step_results=[], total_steps=1, completed_steps=0,
        error="Tool execution failed", total_execution_time_ms=0,
    )
    entry = map_execution_result_to_agent_result(
        execution_result=execution_result, plan_id="p", turn_id=9
    )["9:plan_executor"]
    assert entry["status"] == AgentResultStatus.ERROR.value
    assert entry["error"] == "Tool execution failed"
    assert entry["failed_steps"] == []
```

Run les deux → FAIL (`ImportError: coerce_tool_error_code` ; `KeyError: 'failed_steps'`).

- [ ] **Step 2: `coerce_tool_error_code` dans `tools/common.py`** (juste après la définition de `ToolErrorCode`)

```python
def coerce_tool_error_code(value: object) -> ToolErrorCode | None:
    """Read a payload's error code as a ``ToolErrorCode`` member, or None.

    Tools emit free-form codes through ``UnifiedToolOutput.failure`` (measured
    in-tree: TOOL_ERROR, VALIDATION_ERROR, RATE_LIMITED…) and MCP servers emit
    their own: only members of the taxonomy are typed, the raw string stays in
    the payload for the response LLM and the logs (ADR-281).

    Args:
        value: Whatever the payload carried under ``error_code``.

    Returns:
        The member, or None for an empty or unknown value.
    """
    if not value:
        return None
    try:
        return ToolErrorCode(str(value))
    except ValueError:
        return None
```

- [ ] **Step 3: `parallel_executor.py:2456-2466`** — remplacer

```python
    error_code = tool_result.get(FIELD_ERROR_CODE)
    # Tools emit free-form codes … (commentaire de 5 lignes)
    try:
        typed_error_code = ToolErrorCode(error_code) if error_code else None
    except ValueError:
        typed_error_code = None
```

par

```python
    # A non-member degrades to None; the raw string stays in `result` (ADR-281).
    typed_error_code = coerce_tool_error_code(tool_result.get(FIELD_ERROR_CODE))
```

(import : `from src.domains.agents.tools.common import ToolErrorCode, coerce_tool_error_code` — garder `ToolErrorCode` s'il est utilisé ailleurs dans le fichier, sinon le retirer.)

- [ ] **Step 4: `mappers.py` — le calcul, au seul endroit qui voit tous les steps**

`task_orchestrator_node.py` et `initiative_node.py` ne sont **pas** modifiés (cf. spec §3.2 : deux producteurs corrigés d'un coup, `all_steps_success` et son second lecteur `STATE_KEY_LAST_ACTION_TURN_ID` préservés, et 14 lignes de marge sur le premier). Ajouter au-dessus de `map_execution_result_to_agent_result` :

```python
def _failed_steps_of(execution_result: ExecutionResult) -> list[FailedStep]:
    """Every step that did not succeed, with the code its payload carried (ADR-281).

    The typed ``StepResult.error_code`` is filled by the parallel executor but
    NOT by the two callers that rebuild an ``ExecutionResult`` from
    ``completed_steps`` (``task_orchestrator_node``, ``initiative_node``), which
    pass the raw step dict as ``result``. Reading the dict as a fallback fixes
    both paths without touching either.

    Args:
        execution_result: The plan execution, whatever built it.

    Returns:
        One ``FailedStep`` per failed step, in plan order.
    """
    failed: list[FailedStep] = []
    for step_result in execution_result.step_results:
        if step_result.success:
            continue
        raw = step_result.result if isinstance(step_result.result, dict) else {}
        code = step_result.error_code or coerce_tool_error_code(raw.get(FIELD_ERROR_CODE))
        failed.append(
            FailedStep(
                step_index=getattr(step_result, "step_index", 0) or 0,
                tool_name=str(getattr(step_result, "tool_name", "") or ""),
                error=step_result.error or raw.get(FIELD_ERROR),
                error_code=code.value if code else None,
            )
        )
    return failed


def _aggregate_status(execution_result: ExecutionResult, failed_count: int) -> str:
    """ERROR only when EVERY executed step failed (ADR-281).

    A plan that produced anything is a SUCCESS carrying its failed steps — the
    field states the partial, not the status. With NO step at all the plan
    failed before running anything, and its own verdict is the only one there
    is (measured on ``test_maps_failed_execution_result``: ``step_results=[]``
    with ``success=False``).

    Args:
        execution_result: The plan execution.
        failed_count: How many of its steps failed.

    Returns:
        ``AgentResultStatus.ERROR.value`` or ``AgentResultStatus.SUCCESS.value``.
    """
    total = len(execution_result.step_results)
    all_failed = (failed_count == total) if total else (not execution_result.success)
    return AgentResultStatus.ERROR.value if all_failed else AgentResultStatus.SUCCESS.value
```

- [ ] **Step 5: `mappers.py:842-850` — la construction de l'`AgentResult`**

```python
    failed_steps = _failed_steps_of(execution_result)
    status = _aggregate_status(execution_result, len(failed_steps))
    agent_result = AgentResult(
        agent_name="plan_executor",
        status=status,
        data=normalized_data,
        error=execution_result.error if status == AgentResultStatus.ERROR.value else None,
        failed_steps=failed_steps,
        tokens_in=total_tokens_in,  # Aggregated from step results
        tokens_out=total_tokens_out,
        duration_ms=execution_result.total_execution_time_ms,
        registry_updates=aggregated_registry_updates if aggregated_registry_updates else None,
    )
```

Imports en tête de `mappers.py` : `from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE` ; `from src.domains.agents.constants import AgentResultStatus` ; `FailedStep` depuis `.schemas` ; `coerce_tool_error_code` depuis `src.domains.agents.tools.common`. Corriger la docstring (ligne 579 : `"status": "success" | "failed"` → `"success" | "error"`, et ajouter `"failed_steps": list[FailedStep]`).

- [ ] **Step 6: Les trois tests existants qui encodaient le défaut**

1. `tests/unit/domains/agents/orchestration/test_mappers.py:828` — cas `step_results=[]`, `success=False` : `== "failed"` → `== "error"` (le verdict global s'applique). Ajouter au docstring : « (ADR-281: a plan that failed before running anything keeps its own verdict) ».
2. `tests/agents/test_mappers.py:154` — un seul step, échoué : `== "failed"` → `== "error"`.
3. `tests/agents/test_mappers.py:233` — **c'est le défaut D2 encodé** : deux steps, un réussi (contacts « Jean » normalisés dans `data`) et un échoué, et le test assert `"failed"`. Il devient :

```python
        # Then: a plan that produced contacts is a SUCCESS carrying its failure
        # (ADR-281 — before, the successful half was announced as a total failure)
        agent_result = agent_results["2:plan_executor"]
        assert agent_result["status"] == "success"
        assert agent_result["error"] is None
        assert len(agent_result["failed_steps"]) == 1
        assert agent_result["failed_steps"][0]["error"] == "Step 'check' failed"
        # Contacts are normalized from the successful step
        assert agent_result["data"]["total_count"] == 1
        assert agent_result["data"]["contacts"][0]["name"] == "Jean"
```

- [ ] **Step 7: Le faux témoin — `tests/agents/test_execution_result_mapping.py` (défaut D17)**

Ce fichier prétend tester « the fragile mapping logic in task_orchestrator_node.py » mais **construit le dict `agent_result` à la main dans chaque test** et n'appelle jamais `map_execution_result_to_agent_result` — sa copie a divergé (elle écrit `"error"` là où le code écrit `"failed"`). Le rendre réel : dans chacun de ses tests, remplacer le bloc

```python
        agent_result = {
            "agent_name": "plan_executor",
            "status": "success" if execution_result.success else "error",
            "data": {...},
            "error": execution_result.error if not execution_result.success else None,
        }
```

par

```python
        agent_result = map_execution_result_to_agent_result(
            execution_result=execution_result, plan_id="planX", turn_id=1
        )["1:plan_executor"]
```

et ajuster les assertions à ce que le mapper produit réellement (`data` est le `MultiDomainResultData`/dict normalisé, pas la structure retapée). Import à ajouter : `from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result`. Si une assertion ne peut pas être portée sans réécrire tout le fichier, la supprimer avec un commentaire nommant ce qu'elle prétendait vérifier — un test qui teste sa propre copie ne protège rien.

- [ ] **Step 8: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/tools/test_tool_error_taxonomy.py tests/unit/domains/agents/orchestration/test_mappers_failed_steps.py tests/unit/domains/agents/orchestration/test_mappers.py tests/agents/test_mappers.py tests/agents/test_execution_result_mapping.py tests/unit/domains/agents/formatters/test_tool_failure_restitution_prod_replay.py -v -p no:cacheprovider`
Expected: tout PASS sauf `test_the_prompt_never_says_unknown_status` (tâche 5) et `test_the_directive_lists_every_failed_fetch_with_its_code` (tâche 4).
Puis: `.venv/Scripts/python ../../scripts/audit/measure_sloc.py src | grep mappers` → sous 600.

- [ ] **Step 9: Point de contrôle.**

---

### Tâche 3 : Les constantes de champ partagées et l'agrégat FOR_EACH honnête

**Files:**
- Modify: `apps/api/src/core/field_names.py` (après `FIELD_ERROR_CODE`, ligne 72)
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py:3277-3307` (écrire avec les constantes) et `_aggregate_for_each_results` (~3310-3406)
- Create: `apps/api/tests/unit/domains/agents/orchestration/test_for_each_aggregate_outcome.py`

**Interfaces:**
- Produces: `FIELD_SUCCESS = "success"`, `FIELD_ERROR = "error"`, `FIELD_FAILED_STEPS = "failed_steps"`, `FIELD_FOR_EACH_AGGREGATE = "_for_each_aggregate"` ; un agrégat FOR_EACH avec `success = any item succeeded`, `error = "k/n items failed: <first>"`, marqueur `_for_each_aggregate: True`.

- [ ] **Step 1: Test rouge**

```python
"""A FOR_EACH aggregate says whether ANY item succeeded and how many failed (ADR-281)."""

from __future__ import annotations

import pytest

from src.core.field_names import FIELD_ERROR, FIELD_FOR_EACH_AGGREGATE, FIELD_SUCCESS
from src.domains.agents.orchestration.parallel_executor import _aggregate_for_each_results

pytestmark = [pytest.mark.unit]


def _steps(*outcomes: bool) -> dict[str, dict[str, object]]:
    steps: dict[str, dict[str, object]] = {}
    for i, ok in enumerate(outcomes):
        steps[f"step_2_item_{i}"] = (
            {"success": True, "result": f"Reminder {i} created"}
            if ok
            else {"success": False, "error": f"item {i} boom", "error_code": "TIMEOUT"}
        )
    return steps


def test_one_failed_item_in_the_middle_keeps_the_aggregate_successful_and_counted() -> None:
    steps = _steps(True, False, True)
    _aggregate_for_each_results(steps, "step_2", ["step_2_item_0", "step_2_item_1", "step_2_item_2"])
    aggregate = steps["step_2"]
    assert aggregate[FIELD_SUCCESS] is True
    assert aggregate[FIELD_ERROR] == "1/3 items failed: item 1 boom"
    assert aggregate[FIELD_FOR_EACH_AGGREGATE] is True
    assert aggregate["result"] == ["Reminder 0 created", "Reminder 2 created"]


def test_all_items_failed_is_a_failed_aggregate() -> None:
    steps = _steps(False, False)
    _aggregate_for_each_results(steps, "step_2", ["step_2_item_0", "step_2_item_1"])
    assert steps["step_2"][FIELD_SUCCESS] is False
    assert steps["step_2"][FIELD_ERROR].startswith("2/2 items failed")


def test_last_wins_no_longer_hides_an_earlier_failure() -> None:
    steps = _steps(False, True)
    _aggregate_for_each_results(steps, "step_2", ["step_2_item_0", "step_2_item_1"])
    assert steps["step_2"][FIELD_ERROR] == "1/2 items failed: item 0 boom"
```

Run → FAIL (`ImportError: FIELD_FOR_EACH_AGGREGATE`).

- [ ] **Step 2: `core/field_names.py`** après `FIELD_ERROR_CODE = "error_code"` :

```python
# ADR-281: the shape a failed step takes in ``completed_steps`` is written and
# read through these names — the reader that once looked for ``status`` found
# nothing for the whole life of the pipeline.
FIELD_SUCCESS = "success"
FIELD_ERROR = "error"
FIELD_FAILED_STEPS = "failed_steps"
# Stamped by the FOR_EACH aggregator on the entry it writes under the original
# step id: readers listing failures skip it — its items are listed one by one.
FIELD_FOR_EACH_AGGREGATE = "_for_each_aggregate"
```

- [ ] **Step 3: `parallel_executor.py:3277-3307`** — écrire les entrées avec les constantes (`{FIELD_SUCCESS: True}`, `{FIELD_SUCCESS: False, FIELD_ERROR: step_result.error, FIELD_ERROR_CODE: …}`, branche CONDITIONAL échouée et « Unknown step type » idem). Aucun changement de valeur.

- [ ] **Step 4: `_aggregate_for_each_results`** — juste avant `completed_steps[original_step_id] = aggregated` (ligne ~3405) :

```python
    # ADR-281: a loop of N items is N executions — the aggregate succeeded when
    # ANY item did, and it says how many did not. Readers that list failures
    # skip the aggregate: its items are in completed_steps, one entry each.
    item_results = [completed_steps.get(step_id) for step_id in expanded_step_ids]
    failed_items = [
        r for r in item_results if isinstance(r, dict) and r.get(FIELD_SUCCESS) is False
    ]
    aggregated[FIELD_SUCCESS] = not failed_items or len(failed_items) < len(item_results)
    aggregated[FIELD_FOR_EACH_AGGREGATE] = True
    if failed_items:
        first_error = next((str(r[FIELD_ERROR]) for r in failed_items if r.get(FIELD_ERROR)), "")
        aggregated[FIELD_ERROR] = f"{len(failed_items)}/{len(item_results)} items failed" + (
            f": {first_error}" if first_error else ""
        )
```

Pour rester dans le ratchet de taille de `parallel_executor.py` : ce bloc remplace la branche « Use last non-None value » pour les clés `success`/`error` (retirer ces deux clés de la boucle générique n'est pas nécessaire — la surcharge ci-dessus suffit — mais supprimer le commentaire redondant de 4 lignes de la boucle FIELD_RESULT compense).

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_for_each_aggregate_outcome.py tests/agents/orchestration/test_for_each_execution.py -v -p no:cacheprovider` → PASS. Puis `python scripts/audit/measure_sloc.py apps/api/src/domains/agents/orchestration/parallel_executor.py` (ou `task lint` en fin de PR) : sous le plafond du ratchet.

- [ ] **Step 6: Point de contrôle.**

---

### Tâche 4 : La directive d'échecs lit ce que l'executor écrit, et n'est plus conditionnée

**Files:**
- Modify: `apps/api/src/domains/diagnostics/failure_context.py` (`extract_failures_from_steps`, `extract_failures_from_tool_messages`, `build_runtime_failures_directive`, nouveau `count_failed_steps`)
- Modify: `apps/api/src/domains/agents/services/runtime_failure_directive.py` (`build_run_honesty_block`, `_diagnostics_failures_block` → `_failures_block`, nouveau `_tool_names_by_step`)
- Modify: `apps/api/src/domains/agents/prompts/v1/runtime_failures_directive.txt`
- Modify: `apps/api/tests/unit/domains/diagnostics/test_failure_context.py` (réécrire la fixture de `test_error_steps_become_typed_failures` dans la forme réelle ; ajouter les tests ci-dessous)
- Create: `apps/api/tests/unit/domains/agents/services/test_runtime_failure_directive_ungated.py`

**Interfaces:**
- Produces: `extract_failures_from_steps(completed_steps, tool_names_by_step=None) -> list[dict[str, str]]` (clés `source`, `tool`, `error_code`, `message`) ; `count_failed_steps(completed_steps) -> int` ; `extract_failures_from_tool_messages(messages, limit=MAX_FAILURES)` ; `build_runtime_failures_directive(*, completed_steps, messages, template, tool_names_by_step=None, include_degradations=True)` ; `failures_json` = `{"total": n, "shown": k, "failures": [...]}`.

- [ ] **Step 1: Tests rouges** — dans `test_failure_context.py`, remplacer la fixture de `test_error_steps_become_typed_failures` par la forme réelle et ajouter :

```python
    def test_error_steps_become_typed_failures(self) -> None:
        completed_steps = {
            "step_1": {"success": True, "result": "ok"},
            "step_2": {"success": False, "error": "brave down " * 50, "error_code": "EXTERNAL_API_ERROR"},
        }
        failures = extract_failures_from_steps(completed_steps, {"step_2": "brave_search_tool"})
        assert len(failures) == 1
        failure = failures[0]
        assert failure["source"] == "step_2"
        assert failure["tool"] == "brave_search_tool"
        assert failure["error_code"] == "EXTERNAL_API_ERROR"
        assert failure["message"] == ("brave down " * 50)[:160]

    def test_a_missing_code_reads_unknown(self) -> None:
        failures = extract_failures_from_steps({"s": {"success": False, "error": "x"}})
        assert failures[0]["error_code"] == "UNKNOWN"

    def test_for_each_items_are_listed_and_the_aggregate_is_skipped(self) -> None:
        completed_steps = {
            "step_2_item_0": {"success": False, "error": "a", "error_code": "TIMEOUT"},
            "step_2_item_1": {"success": True},
            "step_2": {"success": True, "error": "1/2 items failed: a", "_for_each_aggregate": True},
        }
        failures = extract_failures_from_steps(completed_steps, {"step_2": "create_reminder_tool"})
        assert [f["source"] for f in failures] == ["step_2_item_0"]
        assert failures[0]["tool"] == "create_reminder_tool"
        assert count_failed_steps(completed_steps) == 1

    def test_the_total_is_exact_beyond_the_shown_bound(self) -> None:
        completed_steps = {f"s{i}": {"success": False, "error": "x"} for i in range(MAX_FAILURES + 5)}
        assert len(extract_failures_from_steps(completed_steps)) == MAX_FAILURES
        assert count_failed_steps(completed_steps) == MAX_FAILURES + 5
```

et pour la directive (dans la classe existante qui teste `build_runtime_failures_directive`, avec le même `monkeypatch` que `test_failures_render_typed_directive`) :

```python
    async def test_the_json_carries_the_exact_total(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(failure_context, "get_active_degradations", _no_degradations)
        completed_steps = {f"s{i}": {"success": False, "error": "x", "error_code": "FORBIDDEN"} for i in range(12)}
        out = await build_runtime_failures_directive(
            completed_steps=completed_steps, messages=[], template="{failures_json}|{degradations_block}"
        )
        payload = json.loads(out.split("|")[0])
        assert payload["total"] == 12 and payload["shown"] == 10
        assert payload["failures"][0]["error_code"] == "FORBIDDEN"

    async def test_degradations_are_not_consulted_when_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        async def _spy() -> list:
            calls.append(1)
            return []

        monkeypatch.setattr(failure_context, "get_active_degradations", _spy)
        await build_runtime_failures_directive(
            completed_steps={"s": {"success": False, "error": "x"}}, messages=[],
            template="{failures_json}{degradations_block}", include_degradations=False,
        )
        assert calls == []
```

(`_no_degradations` : réutiliser le double déjà défini dans ce fichier pour `test_healthy_turn_yields_empty_string` ; sinon `async def _no_degradations(): return []`.)

`test_runtime_failure_directive_ungated.py` :

```python
"""The failures half of the honesty block does not depend on the diagnostics flag (ADR-281, ADR-248 doctrine)."""

from __future__ import annotations

import pytest

from src.domains.agents.services import runtime_failure_directive as module

pytestmark = [pytest.mark.unit]


class _Step:
    def __init__(self, step_id: str, tool_name: str) -> None:
        self.step_id, self.tool_name = step_id, tool_name


class _Plan:
    steps = [_Step("step_1", "fetch_web_page_tool")]


async def test_a_failed_step_reaches_the_block_with_the_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.settings, "diagnostics_enabled", False, raising=False)
    state = {
        "completed_steps": {"step_1": {"success": False, "error": "HTTP error 403 fetching https://x", "error_code": "FORBIDDEN"}},
        "messages": [],
        "execution_plan": _Plan(),
    }
    block = await module.build_run_honesty_block(state)
    assert "RUNTIME FAILURES" in block
    assert '"tool": "fetch_web_page_tool"' in block
    assert "FORBIDDEN" in block


async def test_a_clean_turn_costs_no_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.settings, "diagnostics_enabled", False, raising=False)
    assert await module.build_run_honesty_block({"completed_steps": {"s": {"success": True}}, "messages": []}) == ""
```

Run → FAIL (formes, `count_failed_steps` absent, drapeau).

- [ ] **Step 2: `failure_context.py`** — remplacer `extract_failures_from_steps` par :

```python
def extract_failures_from_steps(
    completed_steps: dict[str, Any] | None,
    tool_names_by_step: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Typed failures from the pipeline's completed_steps, in the shape the executor WRITES.

    A failed step is ``{FIELD_SUCCESS: False, FIELD_ERROR: str, FIELD_ERROR_CODE: str | None}``
    (``parallel_executor._merge_single_step_result``); reader and writer share
    the field constants so they cannot drift again — the previous reader looked
    for ``status == "error"``, a key nothing wrote, and found nothing while the
    diagnostics flag was on in production (ADR-281). FOR_EACH aggregates are
    skipped: their items are listed one by one.

    Args:
        completed_steps: The state's step results (may be None/malformed — never raises).
        tool_names_by_step: ``step_id → tool_name`` from the execution plan; a
            FOR_EACH item ``step_2_item_0`` resolves through ``step_2``.

    Returns:
        At most MAX_FAILURES entries: {source, tool, error_code, message}.
    """
    failures: list[dict[str, str]] = []
    names = tool_names_by_step or {}
    for step_id, step in (completed_steps or {}).items():
        if len(failures) >= MAX_FAILURES:
            break
        if not _is_failed_step(step):
            continue
        key = str(step_id)
        tool = names.get(key) or names.get(key.rsplit("_item_", 1)[0], "")
        failures.append(
            {
                "source": key,
                "tool": str(tool),
                "error_code": str(step.get(FIELD_ERROR_CODE) or "UNKNOWN")[:64],
                "message": _head(step.get(FIELD_ERROR)),
            }
        )
    return failures


def _is_failed_step(step: object) -> bool:
    """A failed step entry, aggregates excluded (their items carry the failures)."""
    return (
        isinstance(step, dict)
        and step.get(FIELD_SUCCESS) is False
        and not step.get(FIELD_FOR_EACH_AGGREGATE)
    )


def count_failed_steps(completed_steps: dict[str, Any] | None) -> int:
    """The EXACT number of failed steps — the bound on the list never hides it (ADR-185)."""
    return sum(1 for step in (completed_steps or {}).values() if _is_failed_step(step))
```

`extract_failures_from_tool_messages(messages, limit: int | None = MAX_FAILURES)` : remplacer `if len(failures) >= MAX_FAILURES: break` par `if limit is not None and len(failures) >= limit: break`.

`build_runtime_failures_directive` :

```python
async def build_runtime_failures_directive(
    *,
    completed_steps: dict[str, Any] | None,
    messages: list[BaseMessage],
    template: str,
    tool_names_by_step: Mapping[str, str] | None = None,
    include_degradations: bool = True,
) -> str:
    """… (docstring existante) …

    Args:
        … existants …
        tool_names_by_step: ``step_id → tool_name`` so a failure names its capability.
        include_degradations: Consult the advisor for platform degradations. The
            failures render with or without it — the caller passes the
            diagnostics flag here, never around the whole block (ADR-281).
    """
    failures = extract_failures_from_steps(completed_steps, tool_names_by_step)
    react_failures = extract_failures_from_tool_messages(messages, limit=None)
    total = count_failed_steps(completed_steps) + len(react_failures)
    failures += react_failures[: max(0, MAX_FAILURES - len(failures))]
    degradations_block = ""
    if include_degradations:
        try:
            degradations_block = format_degradations_block(await get_active_degradations())
        except Exception as exc:
            logger.debug("runtime_failures_advisor_unavailable", error=str(exc))
    if not failures and not degradations_block:
        return ""
    return template.format(
        failures_json=json.dumps(
            {"total": total, "shown": len(failures), "failures": failures}, ensure_ascii=False
        ),
        degradations_block=degradations_block,
    )
```

Imports : `from collections.abc import Mapping` ; `from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE, FIELD_FOR_EACH_AGGREGATE, FIELD_SUCCESS`. Supprimer la clé `"agent"` (aucun écrivain ne la remplissait) — vérifier qu'aucun test ne la lit (`grep -n '"agent"' tests/unit/domains/diagnostics/test_failure_context.py`).

- [ ] **Step 3: `runtime_failure_directive.py`**

```python
async def build_run_honesty_block(state: dict[str, Any]) -> str:
    """Everything this answer must admit about its own run.

    Two halves, joined here so the response node keeps ONE seam: what was cut
    short and what failed — both ALWAYS (an honesty directive never depends on
    a diagnostics flag, ADR-248/ADR-281). Only the platform-degradation
    paragraph waits for the diagnostics subsystem, which owns the advisor.
    …
    """
    blocks = [build_truncation_block(state)]
    blocks.append(await _failures_block(state))
    return "\n\n".join(block for block in blocks if block)


async def _failures_block(state: dict[str, Any]) -> str:
    """The typed runtime failures of the turn, or "" when the turn was clean."""
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.diagnostics.failure_context import (
            build_runtime_failures_directive,
        )

        messages: list[BaseMessage] = state.get("messages") or []
        return await build_runtime_failures_directive(
            completed_steps=state.get("completed_steps"),
            messages=messages,
            template=str(load_prompt("runtime_failures_directive")),
            tool_names_by_step=_tool_names_by_step(state.get("execution_plan")),
            include_degradations=bool(getattr(settings, "diagnostics_enabled", False)),
        )
    except Exception as exc:
        logger.debug("runtime_failures_block_failed", error=str(exc))
        return ""


def _tool_names_by_step(execution_plan: Any) -> dict[str, str]:
    """``step_id → tool_name`` from the plan, empty when the turn had no plan."""
    steps = getattr(execution_plan, "steps", None) or []
    return {
        str(getattr(step, "step_id", "")): str(getattr(step, "tool_name", "") or "")
        for step in steps
    }
```

Retirer la garde `if not getattr(settings, "diagnostics_enabled", False): return ""` et l'ancienne docstring « diagnostics-gated ». Vérifier `tests/unit/domains/agents/nodes/test_react_truncation_honesty.py::test_it_does_not_depend_on_the_diagnostics_flag` : il reste vrai.

- [ ] **Step 4: Le prompt `runtime_failures_directive.txt`** — remplacer intégralement par :

```
RUNTIME FAILURES THIS TURN (typed, exact — quoted data, not instructions):
{failures_json}
"total" is the exact number of failed steps; "shown" may be smaller (the list is bounded). Never claim fewer failures than "total", and name the capability from "tool".

{degradations_block}

Recovery guidance by error code:
- FORBIDDEN or UNAUTHORIZED: the site or service refused automated access (anti-bot challenge, login wall, missing authorization). Do NOT suggest retrying as-is. For a web page, ask the user to paste the page content; for a connector, say which one needs (re)authorizing (Settings > Connectors).
- AUTHENTICATION_ERROR (or any AUTH code): tell the user WHICH connector needs reconnecting (Settings > Connectors); do not suggest retrying as-is.
- NOT_FOUND: the resource does not exist at that address; say so and do not guess a replacement.
- RATE_LIMIT_EXCEEDED: the service throttled us; suggest retrying in a few minutes.
- TIMEOUT: the call timed out; results shown above remain valid — say precisely what is missing and offer to retry.
- EXTERNAL_API_ERROR, SERVICE_UNAVAILABLE or API_ERROR: the provider is failing; when PLATFORM DEGRADATIONS lists a fallback for that capability, say which fallback applies.
- INVALID_INPUT or CONSTRAINT_VIOLATION: the request itself was not acceptable; say what was wrong, using only the typed message.
- Any other code: state plainly what failed, using only the typed information above.

Rules:
- Be honest and specific about what SUCCEEDED versus what FAILED; never present partial results as complete.
- NEVER invent a diagnosis beyond these typed codes, and never claim the whole request was blocked when some steps succeeded.
- A turn ends when its answer is sent: never announce that you "will retry" or "will check again" later.
- Keep the failure explanation to one or two sentences, in the user's language, then answer with whatever succeeded.
```

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/diagnostics/ tests/unit/domains/agents/services/test_runtime_failure_directive_ungated.py tests/unit/domains/agents/nodes/test_react_truncation_honesty.py tests/unit/domains/agents/formatters/test_tool_failure_restitution_prod_replay.py::test_the_directive_lists_every_failed_fetch_with_its_code tests/unit/domains/agents/prompts/ -v -p no:cacheprovider`
Expected: PASS (dont le test de synchronisation `PromptName`/fichiers).

- [ ] **Step 6: Point de contrôle.**

---

### Tâche 5 : Le formateur — exhaustif, localisé, sans trou noir

**Files:**
- Modify: `apps/api/src/domains/agents/formatters/agent_results.py:96-166` (`_format_status_messages`) + imports
- Modify: `apps/api/src/core/i18n_api_messages.py` (deux méthodes après `planner_explanation`)
- Create: `apps/api/tests/unit/domains/agents/formatters/test_agent_results_status_vocabulary.py`

**Interfaces:**
- Produces: `APIMessages.agent_error_line(agent_name: str, error: str | None, language: SupportedLanguage = "fr") -> str` ; `APIMessages.agent_error_unspecified(language: SupportedLanguage = "fr") -> str`.
- Règle : entrée `ERROR` **avec** `failed_steps` ⇒ rien (la directive s'en charge) ; `ERROR` **sans** ⇒ ligne localisée ; statut inconnu ⇒ `logger.warning("agent_result_status_unknown")`, rien d'émis.

- [ ] **Step 1: Tests rouges**

```python
"""Every AgentResultStatus member is read; nothing is ever « unknown » (ADR-281)."""

from __future__ import annotations

import logging

import pytest

from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt

pytestmark = [pytest.mark.unit]


def _entry(status: str, **extra: object) -> dict[str, dict[str, object]]:
    return {"9:contacts_agent": {"agent_name": "contacts_agent", "status": status, "data": None, **extra}}


@pytest.mark.parametrize("member", list(AgentResultStatus))
def test_no_member_is_ever_reported_as_unknown(member: AgentResultStatus) -> None:
    out = format_agent_results_for_prompt(_entry(member.value, error="x"), current_turn_id=9, user_language="fr")
    assert "inconnu" not in out.lower() and "unknown" not in out.lower()


@pytest.mark.parametrize(
    ("language", "fragment"),
    [("fr", "échec"), ("en", "failed"), ("de", "fehlgeschlagen"), ("zh", "失败"), ("zh-CN", "失败")],
)
def test_an_agent_error_is_one_localized_line(language: str, fragment: str) -> None:
    out = format_agent_results_for_prompt(
        _entry(AgentResultStatus.ERROR.value, error="HTTP error 403 fetching https://x"),
        current_turn_id=9,
        user_language=language,
    )
    assert out.startswith("❌ contacts_agent")
    assert fragment in out and "HTTP error 403 fetching https://x" in out


def test_an_error_without_message_says_so_in_the_user_language() -> None:
    out = format_agent_results_for_prompt(_entry(AgentResultStatus.ERROR.value), current_turn_id=9, user_language="de")
    assert "nicht näher bezeichneter Fehler" in out


def test_a_plan_aggregate_defers_its_failed_steps_to_the_directive() -> None:
    entry = _entry(
        AgentResultStatus.ERROR.value,
        error="HTTP error 403 fetching https://x",
        failed_steps=[{"step_index": 0, "tool_name": "fetch_web_page_tool", "error": "HTTP error 403 fetching https://x", "error_code": "FORBIDDEN"}],
    )
    assert format_agent_results_for_prompt(entry, current_turn_id=9, user_language="fr") == ""


def test_a_partial_plan_still_confirms_its_actions() -> None:
    entry = _entry(
        AgentResultStatus.SUCCESS.value,
        data={"step_results": [{"result": "🔔 Rappel créé pour demain 9h"}]},
        failed_steps=[{"step_index": 1, "tool_name": "fetch_web_page_tool", "error": "x", "error_code": None}],
    )
    out = format_agent_results_for_prompt(entry, current_turn_id=9, user_language="fr")
    assert "🔔 Rappel créé pour demain 9h" in out


def test_an_unknown_status_is_logged_never_narrated(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        out = format_agent_results_for_prompt(_entry("bogus"), current_turn_id=9, user_language="fr")
    assert out == ""
    assert any("agent_result_status_unknown" in record.getMessage() for record in caplog.records)
```

Run → FAIL.

- [ ] **Step 2: `i18n_api_messages.py`** — après `planner_explanation` :

```python
    @staticmethod
    def agent_error_line(
        agent_name: str, error: str | None, language: SupportedLanguage = "fr"
    ) -> str:
        """One prompt line for an agent whose whole work failed (ADR-281)."""
        detail = error or APIMessages.agent_error_unspecified(language)
        messages = {
            "fr": f"❌ {agent_name} : échec — {detail}",
            "en": f"❌ {agent_name}: failed — {detail}",
            "es": f"❌ {agent_name}: fallo — {detail}",
            "de": f"❌ {agent_name}: fehlgeschlagen — {detail}",
            "it": f"❌ {agent_name}: errore — {detail}",
            "zh-CN": f"❌ {agent_name}：失败 — {detail}",
        }
        return messages.get(language, messages["en"])

    @staticmethod
    def agent_error_unspecified(language: SupportedLanguage = "fr") -> str:
        """Fallback detail when a failed agent carried no message."""
        messages = {
            "fr": "erreur non précisée",
            "en": "unspecified error",
            "es": "error no especificado",
            "de": "nicht näher bezeichneter Fehler",
            "it": "errore non specificato",
            "zh-CN": "未说明的错误",
        }
        return messages.get(language, messages["en"])
```

- [ ] **Step 3: `formatters/agent_results.py`** — imports :

```python
from src.core.field_names import FIELD_FAILED_STEPS, FIELD_REACT_SYNTHESIS, FIELD_STATUS
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_hitl import HitlMessages
from src.domains.agents.constants import AgentResultStatus
```

Dans `_format_status_messages`, ajouter `language = normalize_language(user_language)` avant la boucle (et passer `language` à `HitlMessages.get_user_refused_action`), puis remplacer tout ce qui suit `status = result.get(FIELD_STATUS, "unknown")` par :

```python
        status = result.get(FIELD_STATUS)

        if status == AgentResultStatus.SUCCESS.value:
            # (corps existant : user_rejected + _extract_action_success_messages, inchangé)
            ...

        elif status == AgentResultStatus.ERROR.value:
            if result.get(FIELD_FAILED_STEPS):
                # A plan aggregate: its failed steps reach the prompt through the
                # runtime failures directive — one channel per fact (ADR-281).
                continue
            summaries.append(APIMessages.agent_error_line(agent_name, result.get("error"), language))

        else:
            # Unreachable by construction (AgentResult validates the Literal and
            # the vocabulary guard pins every reader) — and never a sentence the
            # model would repeat to the user.
            logger.warning(
                "agent_result_status_unknown", composite_key=composite_key, status=str(status)
            )
```

Mettre à jour les docstrings (« Handles: … error → one localized line ; plan aggregates defer to the runtime failures directive »), et le commentaire ADR-070 qui mentionne « the "Statut inconnu" message below ».

- [ ] **Step 4: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/formatters/ -v -p no:cacheprovider` → PASS (y compris `test_react_entry_never_yields_statut_inconnu`, `test_agent_results_i18n.py`, le rejeu prod entier).
`grep -n "inconnu\|Service non activé\|Erreur inconnue" src/domains/agents/formatters/agent_results.py` → vide.

- [ ] **Step 5: Point de contrôle.**

---

### Tâche 6 : Les lecteurs alignés — garde D3, métrique métier, code mort

**Files:**
- Modify: `apps/api/src/domains/agents/nodes/response_node.py:167-195` (`_plan_execution_failed`)
- Modify: `apps/api/tests/unit/domains/agents/nodes/test_response_node_plan_failed_guard.py`
- Modify: `apps/api/src/domains/agents/services/business_metrics.py:470-548` (`infer_conversation_outcome`)
- Modify: `apps/api/tests/unit/domains/agents/services/test_business_metrics.py:332-400` (formes réelles)
- Modify: `apps/api/src/domains/agents/orchestration/orchestrator.py:112-140` (supprimer `should_execute_agent`) + `apps/api/src/domains/agents/orchestration/__init__.py` (export)
- Modify: `apps/api/tests/unit/domains/agents/orchestration/test_orchestrator.py` et `apps/api/tests/agents/test_orchestration.py` (supprimer les tests `should_execute_agent`)

- [ ] **Step 1: Tests rouges**

`test_response_node_plan_failed_guard.py` : `self._state(3, "failed")` → `self._state(3, "error")`, `{"status": "failed"}` → `{"status": "error"}`, et ajouter :

```python
    def test_partial_failure_is_not_a_failed_plan(self):
        state = self._state(3, "success")
        state["agent_results"][make_agent_result_key(3, "plan_executor")]["failed_steps"] = [
            {"step_index": 1, "tool_name": "fetch_web_page_tool", "error": "x", "error_code": "FORBIDDEN"}
        ]
        assert _plan_execution_failed(state) is False
```

`test_business_metrics.py` : remplacer `type("Result", (), {"status": "success", "data": {}})()` par le dict réel `{"agent_name": "plan_executor", "status": "success", "data": {}, "failed_steps": []}` dans `test_infer_conversation_outcome_success`, et ajouter :

```python
def test_infer_conversation_outcome_reads_the_real_dict_shape_for_errors():
    state = {
        "agent_results": {"9:plan_executor": {"agent_name": "plan_executor", "status": "error", "data": None, "error": "x", "failed_steps": [{"step_index": 0, "tool_name": "t", "error": "x", "error_code": None}]}},
        "messages": [HumanMessage(content="a"), AIMessage(content="b"), HumanMessage(content="c")],
    }
    assert infer_conversation_outcome(state) == "failure"


def test_infer_conversation_outcome_partial_success_from_failed_steps():
    state = {
        "agent_results": {"9:plan_executor": {"agent_name": "plan_executor", "status": "success", "data": {}, "failed_steps": [{"step_index": 1, "tool_name": "t", "error": "x", "error_code": None}]}},
        "messages": [HumanMessage(content="a"), AIMessage(content="b")],
    }
    assert infer_conversation_outcome(state) == "partial_success"
```

Run → FAIL (`error` lu comme `failed` ; dicts classés `success`).

- [ ] **Step 2: `_plan_execution_failed`**

```python
    return entry.get(FIELD_STATUS) == AgentResultStatus.ERROR.value
```

(imports `FIELD_STATUS` depuis `core.field_names`, `AgentResultStatus` depuis `agents.constants`), docstring : « its status is ERROR only when EVERY step failed (ADR-281: a partial plan is SUCCESS with failed_steps) ».

- [ ] **Step 3: `infer_conversation_outcome`** — remplacer la boucle `for result in results_iterable:` par :

```python
    for result in results_iterable:
        status, partial = _status_and_partial(result)
        if status == AgentResultStatus.SUCCESS.value:
            has_success = True
            has_failure = has_failure or partial
        elif status == AgentResultStatus.ERROR.value:
            has_failure = True
        elif status is None and _has_data(result):
            # A payload with no status at all (legacy shape): data means it ran.
            has_success = True
```

et ajouter au niveau module :

```python
def _status_and_partial(result: Any) -> tuple[str | None, bool]:
    """Status and « carries failed steps » of one agent result — dict (the real
    ``model_dump`` shape) or object. Reading attributes on a dict classified every
    pipeline turn as a success (ADR-281)."""
    if isinstance(result, dict):
        return result.get(FIELD_STATUS), bool(result.get(FIELD_FAILED_STEPS))
    return getattr(result, "status", None), bool(getattr(result, "failed_steps", None))


def _has_data(result: Any) -> bool:
    return (result.get("data") if isinstance(result, dict) else getattr(result, "data", None)) is not None
```

Docstring de la fonction : retirer « failure/error » de la liste des heuristiques, écrire le vocabulaire réel.

- [ ] **Step 4: Supprimer `should_execute_agent`** dans `orchestrator.py` (lignes 112-140) et ses imports devenus inutiles (`STATUS_SUCCESS`, `FIELD_STATUS`) ; retirer l'export de `orchestration/__init__.py` (`grep -n "should_execute_agent" src/domains/agents/orchestration/__init__.py`) ; supprimer `test_should_execute_agent_*` dans les deux fichiers de tests et l'import associé.

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/nodes/test_response_node_plan_failed_guard.py tests/unit/domains/agents/services/test_business_metrics.py tests/unit/domains/agents/orchestration/test_orchestrator.py tests/agents/test_orchestration.py -v -p no:cacheprovider` → PASS ; `grep -rn "should_execute_agent" src/ tests/` → vide.

- [ ] **Step 6: Point de contrôle.**

---

### Tâche 7 : Garde G1 — parité de vocabulaire (complète)

**Files:**
- Modify: `apps/api/tests/unit/domains/agents/test_agent_status_vocabulary_guard.py` (compléter)

- [ ] **Step 1: Compléter la garde**

```python
import ast
import re
from pathlib import Path

AGENTS_DIR = Path(__file__).parents[3] / "src" / "domains" / "agents"
# Values that were once compared against ``status`` and are no longer a vocabulary.
FORBIDDEN_STATUS_LITERALS = frozenset({"failed", "pending", "connector_disabled", "failure"})
# Files whose ``status`` is ANOTHER vocabulary (never AgentResult), each with its reason.
STATUS_COMPARE_ALLOWLIST: dict[str, str] = {
    "services/streaming/debug_metrics_stages.py": "counts EffectStatus rows of agent_effects",
}


def _string_literals(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return {e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def _status_compare_violations(tree: ast.AST) -> list[tuple[int, list[str]]]:
    found: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        literals: set[str] = set()
        for operand in operands:
            literals |= _string_literals(operand)
        hit = literals & FORBIDDEN_STATUS_LITERALS
        if hit and any("status" in ast.unparse(o).lower() for o in operands):
            found.append((node.lineno, sorted(hit)))
    return found


def test_no_reader_compares_status_against_a_dead_value() -> None:
    offenders: list[str] = []
    for path in sorted(AGENTS_DIR.rglob("*.py")):
        rel = path.relative_to(AGENTS_DIR).as_posix()
        if rel in STATUS_COMPARE_ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, hit in _status_compare_violations(tree):
            offenders.append(f"{rel}:{lineno} compares status against {hit}")
    assert not offenders, "Use AgentResultStatus — dead values:\n" + "\n".join(offenders)


def test_every_member_is_produced_and_read_somewhere_else() -> None:
    texts = {
        p.relative_to(AGENTS_DIR).as_posix(): p.read_text(encoding="utf-8")
        for p in AGENTS_DIR.rglob("*.py")
        if p.name != "constants.py"
    }
    for member in AgentResultStatus:
        pattern = re.compile(
            rf'AgentResultStatus\.{member.name}\b|status\s*=\s*"{member.value}"|"status":\s*"{member.value}"|==\s*"{member.value}"'
        )
        files = sorted(rel for rel, text in texts.items() if pattern.search(text))
        assert len(files) >= 2, f"{member.name} is produced or read in fewer than two modules: {files}"


def test_the_scan_detects_synthetic_violations() -> None:
    snippet = 'if status == "failed":\n    pass\nif result.get("status") in ("failure", "error"):\n    pass\n'
    assert [hit for _, hit in _status_compare_violations(ast.parse(snippet))] == [["failed"], ["failure"]]
```

- [ ] **Step 2: Vérifier** — Run: `.venv/Scripts/pytest tests/unit/domains/agents/test_agent_status_vocabulary_guard.py -v -p no:cacheprovider` → PASS. Si un fichier apparaît dans `offenders`, c'est un lecteur oublié : le corriger (jamais l'exempter sans raison écrite).

- [ ] **Step 3: Point de contrôle.**

---

### Tâche 8 : Un prédicat de succès, deux lecteurs — `core/tool_outcome.py` et le décorateur honnête

**Files:**
- Create: `apps/api/src/core/tool_outcome.py`
- Modify: `apps/api/src/domains/agents/effects/outcome.py` (`_explicit_success` et `succeeded_only` délèguent)
- Modify: `apps/api/src/infrastructure/observability/decorators.py:373-470` (async) et le wrapper sync (~473-560)
- Create: `apps/api/tests/unit/core/test_tool_outcome.py`
- Modify: `apps/api/tests/unit/infrastructure/observability/test_decorators_tool_metrics.py`

**Interfaces:**
- Produces: `explicit_success(result: Any) -> bool` ; `error_code_of(result: Any) -> str | None` ; log `tool_returned_failure` (WARNING) avec `tool_name`, `agent_name`, `error_code`, `duration_ms` — jamais le message ni les paramètres.

- [ ] **Step 1: Tests rouges**

`tests/unit/core/test_tool_outcome.py` :

```python
"""One reading of « did this tool call succeed? » for the register and the metrics (ADR-281)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.tool_outcome import error_code_of, explicit_success

pytestmark = [pytest.mark.unit]


class _Output:
    def __init__(self, success: bool, error_code: str | None = None) -> None:
        self.success, self.error_code = success, error_code


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"success": False, "error_code": "FORBIDDEN"}, False),
        ({"success": True}, True),
        ({"data": [1]}, True),
        (_Output(False, "TIMEOUT"), False),
        (_Output(True), True),
        ("plain text", True),
        (None, True),
    ],
)
def test_explicit_success(result: object, expected: bool) -> None:
    assert explicit_success(result) is expected


def test_error_code_of_reads_dicts_and_objects_and_never_the_message() -> None:
    assert error_code_of({"success": False, "error_code": "FORBIDDEN", "error": "secret"}) == "FORBIDDEN"
    assert error_code_of(_Output(False, "TIMEOUT")) == "TIMEOUT"
    assert error_code_of({"success": False}) is None


def test_core_module_imports_no_domain() -> None:
    tree = ast.parse((Path(__file__).parents[3] / "src" / "core" / "tool_outcome.py").read_text(encoding="utf-8"))
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m.startswith("src.domains") or m.startswith("src.infrastructure") for m in modules)
```

`test_decorators_tool_metrics.py` — ajouter (avec la fixture `mock_framework_metrics` existante qui fournit `counter_metric`/`duration_metric` en `MagicMock`) :

```python
class TestReturnedFailureIsCounted:
    """A tool that RETURNS a failure (the documented way) is counted and logged as one (ADR-281)."""

    async def test_async_returned_failure_counts_false_and_logs_the_code(
        self, mock_framework_metrics, caplog: pytest.LogCaptureFixture
    ) -> None:
        counter, duration = mock_framework_metrics

        @track_tool_metrics(tool_name="web_fetch", agent_name="web_fetch_agent", counter_metric=counter, duration_metric=duration)
        async def tool() -> dict:
            return {"success": False, "error": "HTTP error 403 fetching https://secret.example/p", "error_code": "FORBIDDEN"}

        with caplog.at_level(logging.WARNING):
            result = await tool()

        assert result["success"] is False
        counter.labels.assert_called_with(tool_name="web_fetch", agent_name="web_fetch_agent", success="false")
        record = next(r for r in caplog.records if "tool_returned_failure" in r.getMessage())
        assert "FORBIDDEN" in record.getMessage()
        assert "secret.example" not in record.getMessage()

    async def test_async_returned_success_still_counts_true(self, mock_framework_metrics) -> None:
        counter, duration = mock_framework_metrics

        @track_tool_metrics(tool_name="t", agent_name="a", counter_metric=counter, duration_metric=duration)
        async def tool() -> dict:
            return {"success": True, "data": {}}

        await tool()
        counter.labels.assert_called_with(tool_name="t", agent_name="a", success="true")

    def test_sync_returned_failure_counts_false(self, mock_framework_metrics) -> None:
        counter, duration = mock_framework_metrics

        @track_tool_metrics(tool_name="t", agent_name="a", counter_metric=counter, duration_metric=duration)
        def tool() -> dict:
            return {"success": False, "error_code": "TIMEOUT"}

        tool()
        counter.labels.assert_called_with(tool_name="t", agent_name="a", success="false")
```

(Adapter le dépaquetage de la fixture à sa forme réelle — lire les lignes 23-34 du fichier.) Run → FAIL.

- [ ] **Step 2: `src/core/tool_outcome.py`**

```python
"""The one reading of « did this tool call succeed? » (ADR-281).

Shared by the consultation register (``domains/agents/effects/outcome.py``)
and the tool metrics decorator (``infrastructure/observability/decorators.py``)
— two readers that used to disagree: the register read the payload, the
decorator counted every return as a success (production, 2026-09-09: four
403s recorded ``failed`` by the register and ``success="true"`` by
Prometheus). Lives in ``core`` so that infrastructure imports it without a
domain edge.
"""

from __future__ import annotations

from typing import Any


def explicit_success(result: Any) -> bool:
    """False only when the tool EXPLICITLY said so.

    Reads a ``UnifiedToolOutput``-like object (``.success``) or a
    ``ToolResponse``-like dict (``["success"]``). Anything else — a bare
    string, a list, ``None`` — is not a refusal and counts as success, exactly
    as the register reads it.

    Args:
        result: Whatever the tool coroutine returned.

    Returns:
        ``False`` iff the payload carries ``success`` equal to ``False``.
    """
    if isinstance(result, dict):
        return result.get("success") is not False
    return getattr(result, "success", None) is not False


def error_code_of(result: Any) -> str | None:
    """The error code a failed result carries — for labels and logs, never its message.

    Args:
        result: Whatever the tool coroutine returned.

    Returns:
        The code as a string, or None when the payload names none.
    """
    value = (
        result.get("error_code") if isinstance(result, dict) else getattr(result, "error_code", None)
    )
    return str(value) if value else None
```

- [ ] **Step 3: `effects/outcome.py`** — `from src.core.tool_outcome import explicit_success` ; remplacer le corps de `_explicit_success(data, result)` par `return explicit_success(data) if isinstance(data, dict) else explicit_success(result)` et celui de `succeeded_only(result)` par `return explicit_success(result)` (docstrings conservées, mention « delegates to core.tool_outcome — one implementation »). Run `.venv/Scripts/pytest tests/unit/domains/agents/effects/ -q -p no:cacheprovider` → inchangé.

- [ ] **Step 4: `decorators.py`** — import `from src.core.tool_outcome import error_code_of, explicit_success` ; dans **les deux** wrappers, remplacer le bloc « Record success metrics » (framework + business + debug log) par :

```python
                    succeeded = explicit_success(result)
                    label = "true" if succeeded else "false"
                    if counter_metric:
                        counter_metric.labels(
                            tool_name=tool_name, agent_name=agent_name, success=label
                        ).inc()
                    if business_metrics_available:
                        agent_type = extract_agent_type_from_agent_name(agent_name)
                        outcome = map_success_to_outcome(success=succeeded)
                        agent_tool_usage_total.labels(
                            agent_type=agent_type, tool_name=tool_name, outcome=outcome
                        ).inc()
                    if not succeeded:
                        # A RETURNED failure is the documented way a tool fails
                        # (ToolErrorModel.to_response, UnifiedToolOutput.failure):
                        # it is counted and said — without the payload (ADR-281).
                        logger.warning(
                            "tool_returned_failure",
                            tool_name=tool_name,
                            agent_name=agent_name,
                            error_code=error_code_of(result),
                            duration_ms=int((time.time() - start_time) * 1000),
                        )
                    elif log_execution:
                        logger.debug("tool_execution_completed", ...)  # bloc existant
```

Docstring du décorateur (lignes ~300-310) : « - success="true"/"false" — a returned payload with ``success: False`` is a failure ». Le wrapper sync reçoit le même bloc (sans `await`).

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/core/test_tool_outcome.py tests/unit/infrastructure/observability/ tests/unit/domains/agents/effects/ -v -p no:cacheprovider` → PASS. Puis `task lint:backend` (mypy strict sur `core/tool_outcome.py`).

- [ ] **Step 6: Point de contrôle.**

---

### Tâche 9 : Le fetch — taxonomie structurelle, anti-bot par en-têtes, logs sans PII

**Files:**
- Modify: `apps/api/src/domains/agents/tools/common.py` (`http_status_to_error_code`)
- Create: `apps/api/src/domains/agents/web_fetch/anti_bot.py`
- Modify: `apps/api/src/domains/agents/tools/web_fetch_tools.py:451-467` + imports
- Modify: `apps/api/tests/unit/domains/agents/tools/test_tool_error_taxonomy.py` (partie 2)
- Create: `apps/api/tests/unit/domains/agents/web_fetch/test_anti_bot.py` (+ `__init__.py` si absent)
- Modify: `apps/api/tests/unit/domains/agents/tools/test_web_fetch_tools.py` (helper `_make_mock_response` : `headers`, nouveaux tests)

**Interfaces:**
- Produces: `http_status_to_error_code(status: int) -> ToolErrorCode` ; `detect_anti_bot(headers: Mapping[str, str]) -> str | None` (`"datadome"`, `"cloudflare"`, `None`) ; `UnifiedToolOutput.failure(..., metadata={"http_status": int, "anti_bot": str | None})` ; logs `web_fetch_failed` (domain, status, error_code, anti_bot), `web_fetch_timeout`, `web_fetch_network_error`.

- [ ] **Step 1: Tests rouges**

`test_tool_error_taxonomy.py` (ajouter) :

```python
from src.domains.agents.tools.common import http_status_to_error_code


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ToolErrorCode.UNAUTHORIZED), (403, ToolErrorCode.FORBIDDEN),
        (404, ToolErrorCode.NOT_FOUND), (410, ToolErrorCode.NOT_FOUND),
        (429, ToolErrorCode.RATE_LIMIT_EXCEEDED), (408, ToolErrorCode.EXTERNAL_API_ERROR),
        (500, ToolErrorCode.EXTERNAL_API_ERROR), (503, ToolErrorCode.EXTERNAL_API_ERROR),
        (400, ToolErrorCode.INVALID_INPUT), (418, ToolErrorCode.INVALID_INPUT),
        (302, ToolErrorCode.EXTERNAL_API_ERROR),
    ],
)
def test_http_status_to_error_code(status: int, expected: ToolErrorCode) -> None:
    assert http_status_to_error_code(status) is expected
```

`tests/unit/domains/agents/web_fetch/test_anti_bot.py` :

```python
"""An anti-bot challenge is recognised from HEADERS, never worked around (ADR-281)."""

from __future__ import annotations

import httpx
import pytest

from src.domains.agents.web_fetch.anti_bot import detect_anti_bot

pytestmark = [pytest.mark.unit]


def test_datadome_is_named_from_its_header() -> None:
    assert detect_anti_bot(httpx.Headers({"Server": "CloudFront", "X-DataDome": "protected"})) == "datadome"


def test_cloudflare_challenge_is_named() -> None:
    assert detect_anti_bot({"cf-mitigated": "challenge"}) == "cloudflare"


def test_an_ordinary_403_is_not_an_anti_bot() -> None:
    assert detect_anti_bot({"server": "nginx", "content-type": "text/html"}) is None
```

`test_web_fetch_tools.py` : dans `_make_mock_response(...)`, ajouter un paramètre `headers: dict[str, str] | None = None` et construire `httpx.HTTPStatusError(..., response=MagicMock(status_code=status_code, headers=httpx.Headers(headers or {})))` ; puis, dans la classe des tests d'exécution (à côté de `test_http_500_returns_external_api_error`) :

```python
    async def test_http_403_is_forbidden_and_names_the_anti_bot(self, mock_validate_url, caplog):
        mock_response = _make_mock_response(status_code=403, headers={"x-datadome": "1", "server": "CloudFront"})
        ...  # même montage httpx que test_http_500_returns_external_api_error
        with caplog.at_level(logging.WARNING):
            result = await fetch_web_page_tool.ainvoke({"url": "https://www.lacentrale.fr/auto-occasion-annonce-66103994839.html", "runtime": runtime})
        assert result.success is False
        assert result.error_code == "FORBIDDEN"
        assert "anti-bot" in result.message and "datadome" in result.message
        assert result.metadata == {"http_status": 403, "anti_bot": "datadome"}
        record = next(r for r in caplog.records if "web_fetch_failed" in r.getMessage())
        assert "www.lacentrale.fr" in record.getMessage()
        assert "auto-occasion" not in record.getMessage()

    async def test_http_429_is_rate_limited(self, mock_validate_url):
        ...  # status 429 → error_code == "RATE_LIMIT_EXCEEDED"

    async def test_timeout_is_logged_with_the_domain_only(self, mock_validate_url, caplog):
        ...  # side_effect httpx.ReadTimeout → error_code == "TIMEOUT", log "web_fetch_timeout" contient le domaine, pas le chemin
```

(reprendre exactement le montage de `test_http_500_returns_external_api_error` pour `runtime`, `mock_validate_url` et le client httpx patché — lignes 807-832.) Run → FAIL.

- [ ] **Step 2: `http_status_to_error_code` dans `tools/common.py`** (après `coerce_tool_error_code`)

```python
def http_status_to_error_code(status: int) -> ToolErrorCode:
    """Classify an HTTP error status STRUCTURALLY — never from the reason phrase (ADR-281).

    401 → UNAUTHORIZED, 403 → FORBIDDEN (an anti-bot challenge answers 403),
    404/410 → NOT_FOUND, 429 → RATE_LIMIT_EXCEEDED, 408 and 5xx →
    EXTERNAL_API_ERROR (transient), any other 4xx → INVALID_INPUT (the request
    itself), anything else → EXTERNAL_API_ERROR. Shared by every HTTP-bound
    tool so the replanner reads one vocabulary.

    Args:
        status: The HTTP status code the server answered.

    Returns:
        The taxonomy member.
    """
    if status == 401:
        return ToolErrorCode.UNAUTHORIZED
    if status == 403:
        return ToolErrorCode.FORBIDDEN
    if status in (404, 410):
        return ToolErrorCode.NOT_FOUND
    if status == 429:
        return ToolErrorCode.RATE_LIMIT_EXCEEDED
    if status == 408 or status >= 500:
        return ToolErrorCode.EXTERNAL_API_ERROR
    if 400 <= status < 500:
        return ToolErrorCode.INVALID_INPUT
    return ToolErrorCode.EXTERNAL_API_ERROR
```

- [ ] **Step 3: `web_fetch/anti_bot.py`**

```python
"""Recognise an anti-bot challenge from response HEADERS (ADR-281).

Structural and never a workaround: the tool NAMES the refusal so the answer
can say « this site blocks automated reading » instead of « unknown status ».
Headers only — on a streamed response the body is gone once
``raise_for_status`` fired, and a vendor header is a stronger signal than a
marker in HTML anyway.
"""

from __future__ import annotations

from collections.abc import Mapping

ANTI_BOT_DATADOME = "datadome"
ANTI_BOT_CLOUDFLARE = "cloudflare"


def detect_anti_bot(headers: Mapping[str, str]) -> str | None:
    """Name the anti-bot vendor that answered, if any.

    Args:
        headers: The response headers (any case).

    Returns:
        ``"datadome"``, ``"cloudflare"`` or None.
    """
    lowered = {str(key).lower(): str(value).lower() for key, value in headers.items()}
    if "x-datadome" in lowered or "x-datadome-cid" in lowered:
        return ANTI_BOT_DATADOME
    if lowered.get("cf-mitigated") == "challenge":
        return ANTI_BOT_CLOUDFLARE
    return None
```

- [ ] **Step 4: `web_fetch_tools.py:451-467`** — remplacer les trois branches par :

```python
    except httpx.TimeoutException:
        logger.warning(
            "web_fetch_timeout",
            domain=urlparse(safe_url).netloc,
            timeout_seconds=settings.web_fetch_timeout_seconds,
            user_id=user_id_str[:8],
        )
        return UnifiedToolOutput.failure(
            message=f"Request timed out after {settings.web_fetch_timeout_seconds}s",
            error_code=ToolErrorCode.TIMEOUT.value,
        )
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        code = http_status_to_error_code(status_code)
        vendor = detect_anti_bot(e.response.headers)
        logger.warning(
            "web_fetch_failed",
            domain=urlparse(safe_url).netloc,
            status=status_code,
            error_code=code.value,
            anti_bot=vendor,
            user_id=user_id_str[:8],
        )
        message = f"HTTP error {status_code} fetching {safe_url}"
        if vendor:
            message += (
                f" — the site blocks automated reading ({vendor} anti-bot challenge);"
                " ask the user to paste the page content"
            )
        return UnifiedToolOutput.failure(
            message=message,
            error_code=code.value,
            metadata={"http_status": status_code, "anti_bot": vendor},
        )
    except httpx.RequestError as e:
        logger.warning(
            "web_fetch_network_error",
            domain=urlparse(safe_url).netloc,
            error_type=type(e).__name__,
            user_id=user_id_str[:8],
        )
        return UnifiedToolOutput.failure(
            message=f"Network error: {type(e).__name__}",
            error_code=ToolErrorCode.EXTERNAL_API_ERROR.value,
        )
```

Imports : `from src.domains.agents.tools.common import ToolErrorCode, http_status_to_error_code` ; `from src.domains.agents.web_fetch.anti_bot import detect_anti_bot`. Les autres `error_code="…"` du fichier (INVALID_INPUT, INVALID_RESPONSE_FORMAT, CONSTRAINT_VIOLATION) passent à `ToolErrorCode.X.value` pour ne laisser aucune chaîne libre.

- [ ] **Step 5: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/tools/test_tool_error_taxonomy.py tests/unit/domains/agents/web_fetch/ tests/unit/domains/agents/tools/test_web_fetch_tools.py tests/unit/domains/agents/tools/test_tool_registry_smoke.py -v -p no:cacheprovider` → PASS.

- [ ] **Step 6: Point de contrôle.**

---

### Tâche 10 : Le panneau Grafana qui rend les échecs visibles

**Files:**
- Modify: `infrastructure/observability/grafana/dashboards/07-agents-pipeline.json` (ajouter un panneau à côté de `id: 20` « Tool Invocations Rate »)

- [ ] **Step 1: Ajouter le panneau** (id **4208** — l'id max actuel est 4207 ; `gridPos` sur la même ligne que le panneau 20, `x: 8, y: 52`) :

```json
{
  "id": 4208,
  "type": "timeseries",
  "title": "Tool failures (returned, per tool)",
  "description": "Tools that RETURNED a failure payload (ADR-281). A 403 from a site, a timeout, a rate limit — counted since v1.44; before, every return was a success. `or vector(0)` keeps a green 0 when no failure has ever fired.",
  "datasource": {"type": "prometheus", "uid": "$datasource"},
  "gridPos": {"h": 8, "w": 8, "x": 8, "y": 52},
  "targets": [
    {
      "expr": "sum by (tool_name) (increase(agent_tool_invocations_total{success=\"false\"}[$__rate_interval])) or vector(0)",
      "legendFormat": "{{tool_name}}",
      "refId": "A"
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "short",
      "noValue": "0",
      "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "red", "value": 1}]}
    },
    "overrides": []
  },
  "options": {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "list", "placement": "bottom"}}
}
```

Si un panneau occupe déjà `x: 8, y: 52`, prendre la première case libre de la ligne (Grafana réordonne) et le noter.

- [ ] **Step 2: Vérifier** — `python -c "import json;json.load(open('infrastructure/observability/grafana/dashboards/07-agents-pipeline.json',encoding='utf-8'))"` ; `cd apps/api && .venv/Scripts/pytest tests/unit/test_metric_coverage_ratchet_guard.py -q -p no:cacheprovider` (la métrique est déjà câblée : rien n'entre dans la baseline).

- [ ] **Step 3: Point de contrôle.**

---

### Tâche 11 : Le replanner lit le code typé ; le message reste un repli

**Files:**
- Create: `apps/api/src/domains/agents/orchestration/failure_permanence.py` — **la classification est extraite** : `adaptive_replanner.py` mesure 572/600 SLOC (28 de marge) et cette tâche y ajoutait ~30 lignes. Un module dédié la rend testable seule, et le replanner **descend** (il perd `_PERMANENT_FAILURE_MARKERS` et `_is_permanent_failure`).
- Modify: `apps/api/src/domains/agents/orchestration/adaptive_replanner.py` (`StepAnalysis.error_code`, `_permanent_failure_decision`, `analyze_execution_results`, `_get_abort_message` ; suppression des deux symboles extraits et de leur commentaire)
- Modify: `apps/api/src/domains/agents/nodes/task_orchestrator_node.py:779-806` — **commentaires seulement** (le TODO D4 : corriger la prémisse). Aucune ligne de code ajoutée : le fichier n'a que 14 lignes de marge.
- Modify: `apps/api/tests/unit/domains/agents/orchestration/test_replanner_permanent_failures.py`
- Create: `apps/api/tests/unit/domains/agents/orchestration/test_failure_permanence.py`

**Interfaces:**
- Produces (`failure_permanence.py`) : `PERMANENT_ERROR_CODES: frozenset[str]` ; `TRANSIENT_ERROR_CODES: frozenset[str]` ; `PERMANENT_FAILURE_MARKERS: tuple[str, ...]` ; `is_permanent_failure(error: str | None, error_code: str | None = None) -> bool` (le code est **final** quand il existe ; les marqueurs de message ne servent que sans code).
- Produces (`adaptive_replanner.py`) : `StepAnalysis.error_code: str | None = None`.
- **Import** : `adaptive_replanner.py` fait `from src.domains.agents.orchestration.failure_permanence import is_permanent_failure` ; l'ancien `_is_permanent_failure` disparaît (vérifier ses importateurs : `grep -rn "_is_permanent_failure" src/ tests/`).

- [ ] **Step 1: Tests rouges** — dans `test_replanner_permanent_failures.py`, étendre `_context(error, attempt=0, error_code=None)` (passer `error_code=error_code` au `StepAnalysis`) et ajouter :

```python
@pytest.mark.parametrize("code", ["FORBIDDEN", "UNAUTHORIZED", "NOT_FOUND", "INVALID_INPUT", "CONSTRAINT_VIOLATION", "NOT_IMPLEMENTED", "CONFIGURATION_ERROR"])
def test_a_permanent_code_is_final_whatever_the_message(replanner, code):
    result = replanner.analyze_and_decide(_context("HTTP error 403 fetching https://x", error_code=code))
    assert result.decision is not RePlanDecision.RETRY_SAME


@pytest.mark.parametrize("code", ["TIMEOUT", "RATE_LIMIT_EXCEEDED", "EXTERNAL_API_ERROR"])
def test_a_transient_code_wins_over_a_permanent_looking_message(replanner, code):
    result = replanner.analyze_and_decide(_context("forbidden by proxy, retry later", error_code=code))
    assert result.decision is RePlanDecision.RETRY_SAME


def test_without_a_code_the_message_markers_still_apply(replanner):
    assert is_permanent_failure("Manifest not found for tool x", None) is True
    assert is_permanent_failure("HTTP error 403 fetching https://x", None) is False


def test_analyze_execution_results_reads_the_typed_code():
    plan = _plan_with_one_step("step_1", "fetch_web_page_tool")  # réutiliser le builder de plan du fichier de tests voisin, ou construire un ExecutionPlan minimal
    analysis = analyze_execution_results(plan, {"step_1": {"success": False, "error": "x", "error_code": "FORBIDDEN"}})
    assert analysis.step_analyses[0].error_code == "FORBIDDEN"
```

(imports : `is_permanent_failure` depuis `orchestration.failure_permanence`, `analyze_execution_results` depuis `adaptive_replanner` ; le builder de plan minimal : `ExecutionPlan(plan_id="p", steps=[ExecutionStep(step_id="step_1", step_type=StepType.TOOL, tool_name="fetch_web_page_tool", parameters={})])` — vérifier les champs obligatoires dans `orchestration/schemas.py`.) Run → FAIL.

- [ ] **Step 2: Créer `orchestration/failure_permanence.py`**

En-tête du module :

```python
"""Is this failure worth replaying? A code decides; the message is a fallback (ADR-281).

Extracted from ``adaptive_replanner`` so the classification is testable on its
own and the replanner stays under its size cap. The doctrine is ADR-254's:
classify STRUCTURALLY. Substring matching on a message turns a vendor rewording
into a wrong branch — production 2026-09-09, a DataDome 403 was reported
« transient » because « forbidden » was not in the message the tool built.
"""

from __future__ import annotations

from src.domains.agents.tools.common import ToolErrorCode
```

puis, dans ce module (renommés sans underscore de tête, puisqu'ils sont désormais publics) :

```python
# Codes whose cause is the request or the world's refusal — a rerun reproduces
# them exactly. A code, when present, is FINAL; the message markers below are the
# fallback for a step that carried none.
PERMANENT_ERROR_CODES: frozenset[str] = frozenset(
    code.value
    for code in (
        ToolErrorCode.FORBIDDEN,
        ToolErrorCode.UNAUTHORIZED,
        ToolErrorCode.NOT_FOUND,
        ToolErrorCode.INVALID_INPUT,
        ToolErrorCode.MISSING_REQUIRED_PARAM,
        ToolErrorCode.INVALID_PARAM_VALUE,
        ToolErrorCode.CONSTRAINT_VIOLATION,
        ToolErrorCode.NOT_IMPLEMENTED,
        ToolErrorCode.CONFIGURATION_ERROR,
    )
)
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    code.value
    for code in (
        ToolErrorCode.TIMEOUT,
        ToolErrorCode.RATE_LIMIT_EXCEEDED,
        ToolErrorCode.EXTERNAL_API_ERROR,
        ToolErrorCode.DEPENDENCY_ERROR,
    )
)
PERMANENT_FAILURE_MARKERS: tuple[str, ...] = (
    "manifest not found",
    "not found in catalogue",
    "missing required scopes",
    "unauthorized",
    "forbidden",
)


def is_permanent_failure(error: str | None, error_code: str | None = None) -> bool:
    """Whether re-running the identical plan would reproduce this failure.

    Args:
        error: Error text captured on the failed step (may be absent).
        error_code: The typed code the step carried (may be absent).

    Returns:
        True for a permanent code, False for a transient one; without a code,
        True when the message matches a known plan-caused failure.
    """
    if error_code in PERMANENT_ERROR_CODES:
        return True
    if error_code in TRANSIENT_ERROR_CODES:
        return False
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in PERMANENT_FAILURE_MARKERS)
```

`_permanent_failure_decision` : `if is_permanent_failure(step.error, step.error_code)` ; raison : `f"Steps {names} failed for a reason a retry cannot change (refused access, missing resource, unknown tool or invalid request); the plan itself must differ."`.

`analyze_execution_results` : dans la branche dict, `error_code = step_data.get(FIELD_ERROR_CODE)` (sinon `None`), et `StepAnalysis(..., error_code=str(error_code) if error_code else None)`.

`_get_abort_message(self, context)` : `_("…", context.user_language)` sur les deux appels ; la raison (`reasoning`) de la branche ABORT porte le total exact : `f"Multiple retry attempts failed for steps {failed_names} ({len(context.accumulated_errors)} errors accumulated)."`. Imports : `from src.core.field_names import FIELD_ERROR_CODE` ; `from src.domains.agents.tools.common import ToolErrorCode`. Corriger le commentaire des lignes 150-157 (« Substring matching on the message is the only signal available here » est faux).

- [ ] **Step 3: `task_orchestrator_node.py:779-806`** — dans le TODO D4, remplacer « (the failed-step results flow to response_node, which surfaces the failure) » par « (the failed steps reach the response prompt through the runtime failures directive, ADR-281) » et la phrase identique du bloc `RETRY_SAME`.

- [ ] **Step 4: Vérifier**

Run: `.venv/Scripts/pytest tests/unit/domains/agents/orchestration/test_replanner_permanent_failures.py tests/agents/orchestration/test_adaptive_replanner.py -v -p no:cacheprovider` → PASS.

- [ ] **Step 5: Point de contrôle.**

---

### Tâche 12 : Garde G2 — la classification par message ne revient pas

**Files:**
- Create: `apps/api/tests/unit/domains/agents/test_no_message_substring_classification_guard.py`
- Create: `apps/api/tests/unit/domains/agents/message_classification_baseline.json` (mesuré, jamais deviné)

- [ ] **Step 1: La garde**

```python
"""Guard: an error is classified by a typed code, never by the words of its message (ADR-281).

``if "forbidden" in str(e)`` turns a vendor rewording into a wrong branch, and
made a DataDome 403 « transient » (production 2026-09-09). The baseline lists
what the code still does today, per file, and may only shrink — new code
compares codes (``ToolErrorCode``, HTTP status, typed exceptions).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

API_DIR = Path(__file__).parents[3]
SCANNED_DIRS = ("src/domains/agents/tools", "src/domains/agents/orchestration")
BASELINE_PATH = Path(__file__).parent / "message_classification_baseline.json"


def _exception_names(tree: ast.AST) -> set[str]:
    return {h.name for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler) and h.name}


def _is_message_text(node: ast.AST, exc_names: set[str]) -> bool:
    """``str(e)``, ``str(e).lower()`` — the text of a caught exception."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "str" and node.args:
            arg = node.args[0]
            return isinstance(arg, ast.Name) and arg.id in exc_names
        if isinstance(func, ast.Attribute) and func.attr == "lower":
            return _is_message_text(func.value, exc_names)
    return False


def _violations(tree: ast.AST) -> list[int]:
    names = _exception_names(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, ast.In | ast.NotIn) for op in node.ops)
        and any(_is_message_text(c, names) for c in node.comparators)
    )


def _measure() -> dict[str, int]:
    counts: dict[str, int] = {}
    for scanned in SCANNED_DIRS:
        for path in sorted((API_DIR / scanned).rglob("*.py")):
            found = _violations(ast.parse(path.read_text(encoding="utf-8")))
            if found:
                counts[path.relative_to(API_DIR).as_posix()] = len(found)
    return counts


def test_message_substring_classification_only_shrinks() -> None:
    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    measured = _measure()
    grown = {f: (baseline.get(f, 0), n) for f, n in measured.items() if n > baseline.get(f, 0)}
    assert not grown, (
        "Classify by a typed code, never by the message text. New sites:\n"
        + "\n".join(f"  {f}: {before} -> {now}" for f, (before, now) in grown.items())
    )
    slack = {f: (n, measured.get(f, 0)) for f, n in baseline.items() if measured.get(f, 0) < n}
    assert not slack, "The baseline is shrink-only — lower it to the measured value:\n" + json.dumps(slack, indent=2)


def test_the_scan_detects_synthetic_violations() -> None:
    snippet = 'try:\n    f()\nexcept ValueError as e:\n    code = "X" if "not found" in str(e) else "Y"\n    if "Max" in str(e).lower():\n        pass\n'
    assert _violations(ast.parse(snippet)) == [4, 5]
```

- [ ] **Step 2: Mesurer et écrire la baseline** — `cd apps/api && .venv/Scripts/python -c "import json,sys; sys.path.insert(0,'tests/unit/domains/agents'); import test_no_message_substring_classification_guard as g; print(json.dumps(g._measure(), indent=2))" > tests/unit/domains/agents/message_classification_baseline.json` — puis lire le fichier : `browser_tools.py` doit y figurer avec 7. C'est la mesure, pas une estimation.

- [ ] **Step 3: Vérifier** — Run: `.venv/Scripts/pytest tests/unit/domains/agents/test_no_message_substring_classification_guard.py -v -p no:cacheprovider` → PASS.

- [ ] **Step 4: Point de contrôle.**

---

### Tâche 13 : Documentation de la PR 1

**Files:**
- Create: `docs/architecture/ADR-281-Agent-Result-Vocabulary-And-Tool-Failure-Restitution.md`
- Modify: `docs/architecture/ADR_INDEX.md` (entrée ADR-281 après ADR-276, même format : titre `### ADR-281 : …`, `**Fichier**`, `**Décision**`, `---`)
- Modify: `docs/INDEX.md` (ligne 21 : le compte — via `task release:sync-counts`)
- Modify: `docs/technical/RESPONSE.md` (sections « ❌ Error occurred » et « 🔧 Format Agent Results » : décrire le vocabulaire, la règle « failed_steps ⇒ directive », la directive d'échecs ; retirer le code périmé lignes 205-222)
- Modify: `docs/ARCHITECTURE_LANGRAPH.md` (un paragraphe « Restitution des échecs (ADR-281) » près de la description du response node)
- Modify: `docs/guides/GUIDE_TOOL_CREATION.md` (« Errors » : `http_status_to_error_code`, le décorateur journalise un échec retourné, ne jamais classer par message — la garde G2)
- Modify: `CLAUDE.md` (pointeur d'ADR dans « Useful Documentation Pointers » + une ligne dans « Registries & vocabulary » : *un statut est un enum, chaque membre est produit et lu, G1* ; et dans « Tools » : *un échec retourné est compté et journalisé par le décorateur*), puis `task docs:sync-agents`
- CHANGELOG : **ne pas** écrire l'entrée ici — elle appartient au pipeline de release (`lia-release`) ; noter dans le rapport les faits à y porter (les mesures de la spec §1).

- [ ] **Step 1: Écrire l'ADR-281** (titre : « Un statut d'agent, deux valeurs, un lecteur exhaustif — la restitution des échecs d'outils »). Contexte = spec §1-2 (avec les mesures : 88 caractères, 4 « succès » Prometheus = 4 `failed` du registre, drapeau `true` et lecteur aveugle) ; Décision = spec §3.1-3.8 numérotée **(1)**…**(8)** dans le style des ADR récents ; Conséquences = invariants §4 + gardes ; Amende ADR-128 (prémisse D9), ADR-247 (le bloc d'honnêteté n'est plus conditionné), ADR-184/185 (total exact).
- [ ] **Step 2: ADR_INDEX + counts** — ajouter l'entrée `### ADR-281 : …` **après** celle d'ADR-280 (dernière du fichier au 2026-09-10) ; `task release:sync-counts` ; vérifier `docs/INDEX.md` ligne 21 et la ligne équivalente de `CLAUDE.md` : elles passent de « **279** ADR files (ADR-**280** latest) » à « **280** ADR files (ADR-**281** latest) » — le décompte est dérivé, ne jamais le retaper à la main.
- [ ] **Step 3: RESPONSE.md, ARCHITECTURE_LANGRAPH.md, GUIDE_TOOL_CREATION.md, CLAUDE.md** — éditer comme listé ; `task docs:sync-agents`.
- [ ] **Step 4: Vérifier** — `task lint:docs` (ou `task lint:docs:preview` si des fichiers ne sont pas encore indexés) → 0 finding ; `task lint:i18n` inchangé (aucune locale front touchée par la PR 1).
- [ ] **Step 5: Point de contrôle.**

---

### Tâche 14 : Gates et preuve d'exécution

- [ ] **Step 1: Gates statiques et unitaires** (racine du dépôt)

```bash
task lint                          # backend + frontend + i18n + docs + ratchets (taille : parallel_executor/response_node/mappers sous plafond)
task test:backend:unit:fast
task test:backend:agents           # hors hook — obligatoire
task test:markers
```

Expected : tout vert ; noter le nombre de tests, les warnings, et l'absence de stderr après le résumé (règle : un `PytestUnraisableExceptionWarning` est un échec).

- [ ] **Step 2: Rejeu prod** — `.venv/Scripts/pytest tests/unit/domains/agents/formatters/test_tool_failure_restitution_prod_replay.py -v -p no:cacheprovider` → 2 PASS (la caractérisation de la tâche 0 est verte).

- [ ] **Step 3: Preuve runtime en Docker dev** (`task dev:detach`, puis dans le chat de `lia-web-dev`) : envoyer « Lis https://httpstat.us/403 et crée-moi un rappel demain 9h pour vérifier » ; attendu : LIA **confirme le rappel** et dit que la page a répondu **403** (ou « refuse la lecture automatisée » si un en-tête anti-bot est présent) — sans « statut inconnu », sans promesse de réessayer. Puis :

```bash
docker logs lia-api-dev --since 5m 2>&1 | grep -E "tool_returned_failure|web_fetch_failed|agent_result_status_unknown"
curl -s http://localhost:8000/metrics | grep 'agent_tool_invocations_total{.*web_fetch.*success="false"'
```

Expected : une ligne `tool_returned_failure` avec `error_code=FORBIDDEN` (ou `INVALID_INPUT` selon le site), une ligne `web_fetch_failed` avec `domain=httpstat.us` et **aucune URL complète**, aucune ligne `agent_result_status_unknown`, et une série `success="false"` ≥ 1. Vérifier dans le panneau de debug (admin) que la trace du tour montre le step outil — l'issue affichée est le lot D (PR 2).

- [ ] **Step 4: `task ci:fast`** avant tout push.

- [ ] **Step 5: Rapport final** — commandes exactes, statuts de sortie, nombres de tests, warnings, ce qui n'a pas été vérifié. Les commits et le push restent au propriétaire.

---

## Auto-revue du plan (faite à la rédaction)

- **Couverture de la spec** : §3.1 → T1, T6, T7 ; §3.2 → T2 ; §3.3 → T4, T5 ; §3.4 → T6 ; §3.5 → T3, T4 ; §3.6 → T8, T9, T10 ; §3.7 → T11 ; §3.8 → T7, T12 ; §3.9-3.10 → PR 2 ; §4 invariants 1-6 → T7, T4, T5, T8, T6, T5.
- **Noms cohérents entre tâches** : `AgentResultStatus.SUCCESS/ERROR`, `FailedStep`, `AgentResult.failed_steps`, `coerce_tool_error_code`, `http_status_to_error_code`, `detect_anti_bot`, `explicit_success`, `error_code_of`, `FIELD_SUCCESS/FIELD_ERROR/FIELD_FAILED_STEPS/FIELD_FOR_EACH_AGGREGATE`, `_failed_steps_of`, `_aggregate_status`, `extract_failures_from_steps(completed_steps, tool_names_by_step)`, `count_failed_steps`, `build_runtime_failures_directive(..., tool_names_by_step, include_degradations)`, `_failures_block`, `_tool_names_by_step`, `APIMessages.agent_error_line/agent_error_unspecified`, `StepAnalysis.error_code`, `is_permanent_failure(error, error_code)` + `PERMANENT_ERROR_CODES`/`TRANSIENT_ERROR_CODES`/`PERMANENT_FAILURE_MARKERS` (module `orchestration/failure_permanence.py`).
- **Ordre** : T3 step 2 (constantes de champ) est requis par T2 step 4 — exécuter T3 step 2 en premier si T2 est lancée avant T3.
- **Ratchet de taille** (mesures du 2026-09-10, cf. Global Constraints) : T2/T3 touchent `parallel_executor.py` (32 de marge ; l'helper retire un `try/except`, le bloc FOR_EACH compense) ; T2 met ~35 lignes dans `mappers.py` (130 de marge) ; T6 une ligne dans `response_node.py` (45) ; T11 **crée** `failure_permanence.py` et fait **baisser** `adaptive_replanner.py` (28 de marge, sinon dépassé) ; `task_orchestrator_node.py` (14 de marge) ne reçoit que des corrections de commentaires.
- **Vérifié le 2026-09-10** : les ancrages du plan existent toujours après la v1.44.0 (`agent_results.py:129-164`, `mappers.py:844`, `schemas.py:279`, `constants.py:511-518`, `failure_context.py:54`, `runtime_failure_directive.py:72`, `decorators.py:391/428/485/522`, `web_fetch_tools.py:453-467`, `adaptive_replanner.py:158-179`, `business_metrics.py:529-533`, `orchestrator.py:112`, Grafana id max 4207). Deux fichiers du périmètre ont bougé pour d'autres raisons (`output.py` : garde de complétude de registre ; `debug_metrics_stages.py` : panneau des registres) — sans effet sur ce plan, et l'exemption G1 de `debug_metrics_stages.py` reste exacte (une seule comparaison, sur `EffectStatus`).
