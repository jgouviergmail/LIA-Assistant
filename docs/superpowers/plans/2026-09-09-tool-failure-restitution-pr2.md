# Restitution honnête des échecs d'outils — plan PR 2 (lots D, E)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (owner rule: no sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking. **No git action is ever performed by the assistant**: every « Point de contrôle » reports the evidence and the owner commits on request. **Prerequisite: PR 1 merged** (`FIELD_SUCCESS`, `http_status_to_error_code`, `detect_anti_bot`, baseline G2).

**Goal:** Que la trace « backstage » d'un message dise quelle étape a échoué (au fil de l'eau et après rechargement, sur téléphone comme sur bureau), et que le navigateur lise le statut HTTP au lieu de rendre un interstitiel anti-bot comme une page réussie.

**Architecture:** Lot D — l'issue d'un step outil est **dérivée là où elle est déjà connue** (`completed_steps` à la fin de `task_orchestrator` pour le pipeline, les `ToolMessage` à la fin de `react_execute_tools` pour ReAct), émise dans l'événement SSE `execution_step` existant (`status="completed"|"failed"`, valeurs déjà déclarées et jamais émises), capturée par `TraceCapture` qui **met à jour** l'entrée déjà vue, persistée dans `message_metadata`, et rendue par `ExecutionTraceDisclosure` avec un glyphe et un nom accessible traduit. Lot E — `session.navigate` lit `response.status`, lève des exceptions **typées** (`infrastructure/browser/errors.py`), et `browser_tools` classe par type et par `http_status_to_error_code` — les sept classifications par message disparaissent (la baseline G2 descend).

**Tech Stack:** Python 3.14 / LangChain messages / structlog ; Next.js 16, React 19, TypeScript strict, react-i18next, vitest ; Playwright (backend).

**Spec:** `docs/superpowers/specs/2026-09-09-tool-failure-restitution-design.md` (§3.9, §3.10)

## Global Constraints

- Root `CLAUDE.md` + `apps/web/CLAUDE.md` : jamais de chaîne `aria-label` en dur (locale), parité stricte des 6 locales (`zh` sans pluriel → dupliquer `_one`), builders de tests en `Partial<Props>` sans `as any`, oracle comportemental (rôle/nom accessible), ratchets front shrink-only, aucune validation runtime hors du conteneur `lia-web-dev`.
- Commandes front (depuis `apps/web/`) : `pnpm test`, `pnpm exec tsc --noEmit --incremental false`, `pnpm a11y:ratchet && pnpm react-hooks:ratchet && pnpm cc:ratchet` ; depuis la racine : `task lint:frontend`, `task test:frontend:coverage`, `task lint:i18n`.
- Backend : mêmes règles que la PR 1 (`pytestmark = [pytest.mark.unit]`, pas d'action git).
- **Marge de taille, mesurée le 2026-09-10** : `services/streaming/service.py` est à **1310 / 1326 SLOC (gelé) — 16 lignes de marge**. C'est la contrainte structurante du lot D : la construction des chunks vit dans `tool_step_outcomes.py` (fichier neuf) et le service ne gagne que **~6 lignes** au total. `trace_capture.py` (64/600) et le frontend n'ont aucune contrainte. Vérifier après coup : `.venv/Scripts/python ../../scripts/audit/measure_sloc.py src | grep "streaming.service"`.
- Rétro-compatibilité : une trace persistée sans `outcome` (toutes celles d'avant) se rend exactement comme aujourd'hui ; un client front ancien ignore le champ.

---

### Tâche D1 : L'issue d'un step outil, dérivée là où elle est connue (backend, streaming)

**Files:**
- Create: `apps/api/src/domains/agents/services/streaming/tool_step_outcomes.py`
- Modify: `apps/api/src/domains/agents/services/streaming/service.py` (`_emit_tool_execution_step` ~1691-1725, `_extract_pipeline_tool_steps` ~1608-1645, `_extract_react_tool_steps` ~1571-1607, et le dispatch ~1515-1535)
- Create: `apps/api/tests/unit/domains/agents/services/streaming/test_tool_step_outcomes.py`

**Interfaces:**
- Produces (module `tool_step_outcomes.py`) :
  - `ToolOutcome` = `Literal["completed", "failed"]`
  - `pipeline_tool_outcomes(execution_plan: Any, completed_steps: Mapping[str, Any] | None) -> dict[str, tuple[ToolOutcome, int, int]]` — par `tool_name` (ordre du plan) : `(outcome, failed_count, total_count)` ; `failed` ssi **tous** les steps de cet outil ont échoué ; un step absent de `completed_steps` compte comme non exécuté (exclu du total).
  - `react_tool_outcomes(messages: Sequence[Any]) -> dict[str, tuple[ToolOutcome, int, int]]` — par nom d'outil lu sur les `ToolMessage` (`message.name`) : échec quand `message.status == "error"` ou quand le contenu JSON porte `success: False` (même lecture que `diagnostics/failure_context.extract_failures_from_tool_messages`).
- `_emit_tool_execution_step(self, tool_name: str, status: ToolOutcome | Literal["started"] = "started", additional_data: dict[str, Any] | None = None) -> ChatStreamChunk | None`.

- [ ] **Step 1: Tests rouges**

```python
"""Tool step outcomes are derived from what the executor recorded (ADR-281, lot D)."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.domains.agents.services.streaming.tool_step_outcomes import (
    pipeline_tool_outcomes,
    react_tool_outcomes,
)

pytestmark = [pytest.mark.unit]


class _Step:
    def __init__(self, step_id: str, tool_name: str | None) -> None:
        self.step_id, self.tool_name = step_id, tool_name


class _Plan:
    def __init__(self, *steps: _Step) -> None:
        self.steps = list(steps)


def test_pipeline_all_failed_is_failed_with_counts() -> None:
    plan = _Plan(_Step("s1", "fetch_web_page_tool"), _Step("s2", "fetch_web_page_tool"), _Step("s3", "fetch_web_page_tool"))
    steps = {sid: {"success": False, "error": "HTTP error 403"} for sid in ("s1", "s2", "s3")}
    assert pipeline_tool_outcomes(plan, steps) == {"fetch_web_page_tool": ("failed", 3, 3)}


def test_pipeline_partial_is_completed_but_counted() -> None:
    plan = _Plan(_Step("s1", "create_reminder_tool"), _Step("s2", "fetch_web_page_tool"), _Step("s3", "fetch_web_page_tool"))
    steps = {"s1": {"success": True}, "s2": {"success": False, "error": "x"}, "s3": {"success": True}}
    assert pipeline_tool_outcomes(plan, steps) == {
        "create_reminder_tool": ("completed", 0, 1),
        "fetch_web_page_tool": ("completed", 1, 2),
    }


def test_pipeline_ignores_steps_that_never_ran_and_keeps_plan_order() -> None:
    plan = _Plan(_Step("s1", "b_tool"), _Step("s2", "a_tool"), _Step("s3", None))
    assert list(pipeline_tool_outcomes(plan, {"s2": {"success": True}})) == ["a_tool"]


def test_react_reads_tool_messages() -> None:
    messages = [
        AIMessage(content="", tool_calls=[{"name": "fetch_web_page_tool", "args": {}, "id": "c1"}]),
        ToolMessage(content=json.dumps({"success": False, "error_code": "FORBIDDEN"}), tool_call_id="c1", name="fetch_web_page_tool"),
        ToolMessage(content="ok", tool_call_id="c2", name="brave_search_tool"),
        ToolMessage(content="never ran", tool_call_id="c3", name="places_tool", status="error"),
    ]
    assert react_tool_outcomes(messages) == {
        "fetch_web_page_tool": ("failed", 1, 1),
        "brave_search_tool": ("completed", 0, 1),
        "places_tool": ("failed", 1, 1),
    }
```

Run → FAIL (module absent).

- [ ] **Step 2: `tool_step_outcomes.py`**

```python
"""Outcome of each tool of a turn, derived from what was recorded (ADR-281, lot D).

The SSE ``execution_step`` event always declared ``completed`` and ``failed``
and only ever emitted ``started`` — the trace showed a refused fetch exactly
like a successful one. The outcome is not observed anew: the pipeline already
holds it in ``completed_steps`` when ``task_orchestrator`` finishes, and ReAct
holds it in its ``ToolMessage``s when ``react_execute_tools`` finishes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from langchain_core.messages import ToolMessage

from src.core.field_names import FIELD_FOR_EACH_AGGREGATE, FIELD_SUCCESS

ToolOutcome = Literal["completed", "failed"]
OutcomeCounts = tuple[ToolOutcome, int, int]


def _outcome(failed: int, total: int) -> OutcomeCounts:
    return ("failed" if total and failed == total else "completed", failed, total)


def pipeline_tool_outcomes(
    execution_plan: Any, completed_steps: Mapping[str, Any] | None
) -> dict[str, OutcomeCounts]:
    """Per tool of the plan (plan order): (outcome, failed_count, total_count).

    ``failed`` only when EVERY executed step of that tool failed — a tool that
    produced anything reads as ``completed`` and carries its failed count.
    Steps with no entry in ``completed_steps`` never ran and are not counted;
    FOR_EACH aggregates carry their own ``success`` (any item succeeded).

    Args:
        execution_plan: The plan the turn executed (``.steps`` with ``step_id``/``tool_name``).
        completed_steps: What the executor recorded, or None.

    Returns:
        Ordered mapping ``tool_name → (outcome, failed_count, total_count)``.
    """
    counts: dict[str, list[int]] = {}
    recorded = completed_steps or {}
    for step in getattr(execution_plan, "steps", None) or []:
        tool_name = getattr(step, "tool_name", None)
        entry = recorded.get(str(getattr(step, "step_id", "")))
        if not tool_name or entry is None:
            continue
        failed = isinstance(entry, dict) and entry.get(FIELD_SUCCESS) is False
        bucket = counts.setdefault(str(tool_name), [0, 0])
        bucket[0] += int(failed)
        bucket[1] += 1
    return {name: _outcome(failed, total) for name, (failed, total) in counts.items()}


def react_tool_outcomes(messages: Sequence[Any]) -> dict[str, OutcomeCounts]:
    """Per tool named by the turn's ToolMessages: (outcome, failed_count, total_count).

    A ToolMessage failed when it carries ``status="error"`` (ADR-248's
    explicit close of an abandoned call) or a JSON payload with ``success: False``
    (the shape every tool error uses).

    Args:
        messages: The messages of the node delta (or the whole run).

    Returns:
        Mapping ``tool_name → (outcome, failed_count, total_count)`` in first-seen order.
    """
    counts: dict[str, list[int]] = {}
    for message in messages:
        if not isinstance(message, ToolMessage) or not getattr(message, "name", None):
            continue
        bucket = counts.setdefault(str(message.name), [0, 0])
        bucket[0] += int(_tool_message_failed(message))
        bucket[1] += 1
    return {name: _outcome(failed, total) for name, (failed, total) in counts.items()}


def _tool_message_failed(message: ToolMessage) -> bool:
    if getattr(message, "status", None) == "error":
        return True
    try:
        payload = json.loads(str(message.content))
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get(FIELD_SUCCESS) is False and not payload.get(FIELD_FOR_EACH_AGGREGATE)
```

- [ ] **Step 3: Le constructeur de chunks, dans le module (pas dans le service)**

`service.py` n'a que **16 lignes** de marge : la boucle qui fabrique les chunks vit dans `tool_step_outcomes.py` et reçoit la méthode d'émission en paramètre. Ajouter à la fin du module :

```python
def outcome_steps(
    outcomes: Mapping[str, OutcomeCounts],
    emit: Callable[..., Any],
) -> list[tuple[Any, str]]:
    """Build the SSE chunks announcing each tool's outcome.

    Lives here rather than in the streaming service so the service keeps its
    size budget; ``emit`` is the service's own
    ``_emit_tool_execution_step(tool_name, status=..., additional_data=...)``.

    Args:
        outcomes: What :func:`pipeline_tool_outcomes` or :func:`react_tool_outcomes` returned.
        emit: The chunk factory; a falsy return is skipped (tool absent from the catalogue).

    Returns:
        ``(chunk, "")`` pairs, in the order the outcomes were computed.
    """
    steps: list[tuple[Any, str]] = []
    for tool_name, (outcome, failed_count, total_count) in outcomes.items():
        chunk = emit(
            tool_name,
            status=outcome,
            additional_data={"failed_count": failed_count, "total_count": total_count},
        )
        if chunk:
            steps.append((chunk, ""))
    return steps
```

(imports du module : `from collections.abc import Callable, Mapping, Sequence`.)

- [ ] **Step 4: `streaming/service.py` — six lignes**

`_emit_tool_execution_step(self, tool_name, status="started", additional_data=None)` : passer `status=status, additional_data=additional_data` à `build_execution_step_event` (2 lignes de signature + 2 d'appel, **net +2**).

`_extract_pipeline_tool_steps(self, accumulated_state)` : remplacer la boucle sur `steps` (et les variables `seen_tools`/`steps`) par **deux** lignes — **net négatif** :

```python
        outcomes = pipeline_tool_outcomes(execution_plan, accumulated_state.get("completed_steps"))
        tool_steps = outcome_steps(outcomes, self._emit_tool_execution_step)
```

Docstring : « Emitted when task_orchestrator completes, with the outcome the executor recorded (ADR-281) ».

Dispatch (~1527) : ajouter après la branche `react_call_model` — **net +4** :

```python
        elif node_name == "react_execute_tools":
            # ADR-281: the outcome of the calls announced at react_call_model,
            # read from the ToolMessages this node produced.
            outcomes = react_tool_outcomes((state_delta or {}).get("messages") or [])
            sse_chunks.extend(outcome_steps(outcomes, self._emit_tool_execution_step))
```

(vérifier le nom exact de la variable de delta et la forme de `sse_chunks` autour de la ligne 1527 ; `_extract_react_tool_steps` reste tel quel — il annonce les appels avec `started`.) Import : `from src.domains.agents.services.streaming.tool_step_outcomes import outcome_steps, pipeline_tool_outcomes, react_tool_outcomes`.

Vérifier immédiatement : `.venv/Scripts/python ../../scripts/audit/measure_sloc.py src | grep "streaming.service"` → **≤ 1326**.

- [ ] **Step 5: Vérifier** — `.venv/Scripts/pytest tests/unit/domains/agents/services/streaming/ tests/agents/test_agent_service_stream_characterization.py -v -p no:cacheprovider` → PASS (la caractérisation lit les chunks : si elle pinnait `status: "started"` sur les steps pipeline, mettre à jour l'attendu avec justification ADR-281).

- [ ] **Step 6: Point de contrôle.**

---

### Tâche D2 : `TraceCapture` met à jour l'entrée déjà vue

**Files:**
- Modify: `apps/api/src/domains/agents/services/streaming/trace_capture.py` (`observe`, `snapshot`)
- Modify: `apps/api/tests/unit/domains/agents/services/streaming/test_trace_capture.py`

**Interfaces:**
- Produces: une entrée de trace persistée `{"emoji", "i18n_key", "category", "outcome"?: "failed"}` — `outcome` présent **seulement** quand l'issue est `failed` (une trace ancienne ne change pas de forme).

- [ ] **Step 1: Tests rouges** (dans la classe existante)

```python
    def test_a_failed_outcome_marks_the_step_already_seen(self) -> None:
        capture = TraceCapture(max_steps=10)
        capture.observe("execution_step", {"i18n_key": "fetch_web_page", "emoji": "🌐", "category": "tool", "status": "started"})
        capture.observe("execution_step", {"i18n_key": "fetch_web_page", "emoji": "🌐", "category": "tool", "status": "failed", "failed_count": 3, "total_count": 3})
        assert capture.snapshot() == [{"emoji": "🌐", "i18n_key": "fetch_web_page", "category": "tool", "outcome": "failed"}]

    def test_a_failed_outcome_on_first_sight_is_kept(self) -> None:
        capture = TraceCapture(max_steps=10)
        capture.observe("execution_step", {"i18n_key": "fetch_web_page", "emoji": "🌐", "category": "tool", "status": "failed"})
        assert capture.snapshot()[0]["outcome"] == "failed"

    def test_a_completed_outcome_adds_nothing(self) -> None:
        capture = TraceCapture(max_steps=10)
        capture.observe("execution_step", {"i18n_key": "fetch_web_page", "emoji": "🌐", "category": "tool", "status": "completed"})
        assert "outcome" not in capture.snapshot()[0]
```

Run → FAIL.

- [ ] **Step 2: `trace_capture.py`** — dans `observe`, remplacer `if key in self._seen_keys: return` par

```python
        failed = metadata.get("status") == "failed"
        if key in self._seen_keys:
            if failed:
                # ADR-281: the outcome arrives after the announcement — mark the
                # step already captured instead of adding a second one.
                for step in self._steps:
                    if step["i18n_key"] == key:
                        step["outcome"] = "failed"
            return
        self._seen_keys.add(key)
        category = metadata.get("category")
        step: dict[str, str] = {
            "emoji": metadata.get("emoji") or "⚙️",
            "i18n_key": key,
            "category": category if category in _TRACE_CATEGORIES else "system",
        }
        if failed:
            step["outcome"] = "failed"
        self._steps.append(step)
```

(le type de `self._steps` reste `list[dict[str, str]]`.) Docstring de module : une phrase sur `outcome`.

- [ ] **Step 3: Vérifier** — `.venv/Scripts/pytest tests/unit/domains/agents/services/streaming/test_trace_capture.py -v -p no:cacheprovider` → PASS.

- [ ] **Step 4: Point de contrôle.**

---

### Tâche D3 : La trace rendue dit ce qui a échoué (frontend)

**Files:**
- Modify: `apps/web/src/types/execution-trace.ts` (`ExecutionTraceStep.outcome?: 'failed'`)
- Modify: `apps/web/src/lib/sse-handlers/types.ts` (`ProgressMessageMetadata.status?: string`, `failed_count?: number`, `total_count?: number`)
- Modify: `apps/web/src/lib/sse-handlers/handlers.ts` (`buildTraceStep`, `handleExecutionStep`)
- Modify: `apps/web/src/lib/execution-trace-hydration.ts` (`hydrateStep`)
- Modify: `apps/web/src/components/chat/ExecutionTraceDisclosure.tsx` (rendu du step)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (`chat.trace.step_failed`)
- Modify: `apps/web/src/lib/sse-handlers/__tests__/handlers.progress.test.ts`, `apps/web/src/lib/__tests__/execution-trace-hydration.test.ts`, `apps/web/src/components/chat/__tests__/ExecutionTraceDisclosure.test.tsx`

**Interfaces:**
- Produces: `ExecutionTraceStep.outcome?: 'failed'` ; `markTraceStepFailed(steps: ExecutionTraceStep[], label: string): void` (dans `handlers.ts`, exporté pour le test) ; clé i18n `chat.trace.step_failed` (en: `"failed"`, fr: `"échec"`, de: `"fehlgeschlagen"`, es: `"fallo"`, it: `"errore"`, zh: `"失败"`).

- [ ] **Step 1: Tests rouges**

`handlers.progress.test.ts` — nouveau `describe('handleExecutionStep — outcomes (ADR-281)')` :

```ts
  it('marks the trace step failed when the outcome event arrives for a key already shown', () => {
    const { context, dispatch } = createHandlerFixture({ progressMessageId: 'p1' });
    handleExecutionStep(makeChunk({ i18n_key: 'fetch_web_page', emoji: '🌐', category: 'tool', status: 'started' }), context, dispatch);
    handleExecutionStep(makeChunk({ i18n_key: 'fetch_web_page', emoji: '🌐', category: 'tool', status: 'failed', failed_count: 3, total_count: 3 }), context, dispatch);
    expect(context.traceStepsRef.current).toHaveLength(1);
    expect(context.traceStepsRef.current[0].outcome).toBe('failed');
  });

  it('keeps a completed outcome unmarked', () => {
    const { context, dispatch } = createHandlerFixture({ progressMessageId: 'p1' });
    handleExecutionStep(makeChunk({ i18n_key: 'create_reminder', emoji: '🔔', category: 'tool', status: 'completed' }), context, dispatch);
    expect(context.traceStepsRef.current[0].outcome).toBeUndefined();
  });
```

(`createHandlerFixture` et `makeChunk` : réutiliser les helpers de `context-fixture.ts` et du fichier — adapter les noms exacts.)

`execution-trace-hydration.test.ts` :

```ts
  it('hydrates a persisted failed outcome and ignores an unknown one', () => {
    const trace = executionTraceFromMetadata(
      { execution_trace: { steps: [
        { emoji: '🌐', i18n_key: 'fetch_web_page', category: 'tool', outcome: 'failed' },
        { emoji: '🔔', i18n_key: 'create_reminder', category: 'tool', outcome: 'weird' },
        { emoji: '🧭', i18n_key: 'router_decision', category: 'system' },
      ] } },
      t,
    );
    expect(trace?.steps.map(s => s.outcome)).toEqual(['failed', undefined, undefined]);
  });
```

`ExecutionTraceDisclosure.test.tsx` :

```ts
  it('names a failed step for assistive technology and marks it visibly', async () => {
    render(<ExecutionTraceDisclosure trace={makeTrace({ steps: [
      { emoji: '🌐', label: 'Reading a web page', category: 'tool', outcome: 'failed' },
      { emoji: '🔔', label: 'Creating a reminder', category: 'tool' },
    ] })} />);
    await userEvent.click(screen.getByRole('button', { name: /details/i }));
    const failed = screen.getByText('Reading a web page').closest('li');
    expect(failed).toHaveTextContent('✗');
    expect(within(failed as HTMLElement).getByLabelText('chat.trace.step_failed')).toBeInTheDocument();
    expect(screen.getByText('Creating a reminder').closest('li')).not.toHaveTextContent('✗');
  });
```

(`makeTrace` : builder `Partial<ExecutionTrace>` → `ExecutionTrace` déjà présent dans le fichier ou à ajouter ; le `t` de test rend la clé.) Run `pnpm test -- handlers.progress execution-trace-hydration ExecutionTraceDisclosure` → FAIL.

- [ ] **Step 2: Types**

`execution-trace.ts` :

```ts
export interface ExecutionTraceStep {
  emoji: string;
  label: string;
  category: TraceStepCategory;
  /**
   * Outcome the backend recorded for the step (ADR-281). Present only when the
   * step FAILED — an older trace, or a step that succeeded, carries nothing.
   */
  outcome?: 'failed';
}
```

`sse-handlers/types.ts` (`ProgressMessageMetadata`) : `status?: string; failed_count?: number; total_count?: number;` avec un commentaire « execution_step outcome (ADR-281) ».

- [ ] **Step 3: `handlers.ts`**

`buildTraceStep` : après le calcul de `label`, retourner `{ emoji, label, category, ...(metadata.status === 'failed' ? { outcome: 'failed' as const } : {}) }`.

Ajouter et exporter :

```ts
/** Mark the already-captured trace step (same translated label) as failed (ADR-281). */
export function markTraceStepFailed(steps: ExecutionTraceStep[], label: string): void {
  for (const step of steps) {
    if (step.label === label) step.outcome = 'failed';
  }
}
```

Dans `handleExecutionStep`, avant le `return` de dédup (`if (metadata?.i18n_key && emittedStepKeysRef.current.has(metadata.i18n_key))`) :

```ts
    if (metadata?.status === 'failed' && metadata.i18n_key) {
      const label = t(`execution.steps.${metadata.i18n_key}`, { defaultValue: '' });
      if (label) markTraceStepFailed(context.traceStepsRef.current, label);
    }
```

(la dédup par clé continue de protéger la bulle de progression ; le premier passage d'une clé avec `status: 'failed'` crée le step déjà marqué via `buildTraceStep`.)

- [ ] **Step 4: `execution-trace-hydration.ts`** — dans `hydrateStep`, retourner aussi `...(step.outcome === 'failed' ? { outcome: 'failed' as const } : {})`. Mettre à jour le commentaire d'en-tête (« `{steps: [{emoji, i18n_key, category, outcome?}], duration_ms}` »).

- [ ] **Step 5: `ExecutionTraceDisclosure.tsx`** — dans le `<li>` :

```tsx
                  <li
                    key={`${step.label}-${i}`}
                    className={cn(
                      'flex items-start gap-1.5 text-xs',
                      step.outcome === 'failed' ? 'text-destructive' : 'text-foreground/80'
                    )}
                  >
                    <span aria-hidden="true">{step.emoji}</span>
                    <span>{step.label}</span>
                    {step.outcome === 'failed' && (
                      <span role="img" aria-label={t('chat.trace.step_failed')} className="ml-auto shrink-0">
                        ✗
                      </span>
                    )}
                  </li>
```

(un glyphe d'un caractère, pas de largeur ajoutée — la ligne reste sur une colonne à 360 px.)

- [ ] **Step 6: Locales** — ajouter `"step_failed"` sous `chat.trace` dans les 6 fichiers (valeurs ci-dessus), à la même position que `aria_toggle`.

- [ ] **Step 7: Vérifier**

```bash
cd apps/web && pnpm test -- handlers.progress execution-trace-hydration ExecutionTraceDisclosure
pnpm exec tsc --noEmit --incremental false
cd ../.. && task lint:frontend && task lint:i18n && task test:frontend:coverage
```

Expected : vert ; seuils de couverture tenus (les trois fichiers touchés gagnent des tests).

- [ ] **Step 8: Point de contrôle.**

---

### Tâche D4 : Preuve runtime de la trace

- [ ] **Step 1** — `docker restart lia-web-dev` (pas de hot reload fiable), puis dans le chat : « Lis https://httpstat.us/403 et crée-moi un rappel demain 9h ». Ouvrir le détail « backstage » du message : « 🌐 … » porte **✗** en rouge, « 🔔 … » non. Recharger la page : même rendu (hydratation). Sur un viewport 360 px (outils de dev du navigateur) : aucune coupure de ligne parasite.
- [ ] **Step 2** — Mode ReAct (bascule dans l'en-tête du chat) : même requête ; le step outil est annoncé puis marqué ✗ à l'exécution.
- [ ] **Step 3: Point de contrôle** — captures et description.

---

### Tâche E1 : Le navigateur lit son statut et lève des exceptions typées

**Files:**
- Create: `apps/api/src/infrastructure/browser/errors.py`
- Modify: `apps/api/src/infrastructure/browser/session.py` (`navigate` ~95-145 ; les `raise ValueError("URL blocked: …")` et homologues)
- Modify: `apps/api/src/infrastructure/browser/pool.py` (les `raise ValueError("Max concurrent…")`, `"Max navigations…"`, `"No page…"` — `grep -n "raise ValueError" src/infrastructure/browser/*.py` donne la liste exacte)
- Modify: `apps/api/src/domains/agents/tools/browser_tools.py:351,454-457,530,594,660,724` (classification par type)
- Modify: `apps/api/tests/unit/domains/agents/message_classification_baseline.json` (browser_tools.py : 7 → 0)
- Create: `apps/api/tests/unit/infrastructure/browser/test_session_http_status.py`, `apps/api/tests/unit/domains/agents/tools/test_browser_tools_errors.py`

**Interfaces:**
- Produces (`errors.py`) :

```python
class BrowserError(Exception): """Base of the browser layer's typed failures (ADR-281)."""
class BrowserUrlBlockedError(BrowserError): """The URL failed SSRF/Web-Risk screening."""
class BrowserSessionLimitError(BrowserError): """Max concurrent sessions or navigations reached."""
class BrowserNoPageError(BrowserError): """The session has no open page."""
class BrowserElementNotFoundError(BrowserError): """The referenced element does not exist."""
class BrowserActionNotAllowedError(BrowserError): """The action is refused by policy."""
class BrowserHttpError(BrowserError):
    def __init__(self, status: int, url: str, anti_bot: str | None = None) -> None
    status: int; url: str; anti_bot: str | None
```

- `session.navigate` : `response = await self.page.goto(...)` ; si `response is not None and response.status >= 400` → `browser_actions_total.labels(action_type="navigate", status="http_error").inc()` puis `raise BrowserHttpError(response.status, url, detect_anti_bot(response.headers))` (import `detect_anti_bot` depuis `domains/agents/web_fetch/anti_bot` — **inversion de couche** : déplacer `anti_bot.py` dans `src/core/anti_bot.py` d'abord, et faire réexporter `web_fetch/anti_bot.py` ; une implémentation).
- `browser_navigate_tool` : `except BrowserHttpError as e: return UnifiedToolOutput.failure(message=f"HTTP error {e.status} navigating to {e.url}" + (anti-bot suffix), error_code=http_status_to_error_code(e.status).value, metadata={"http_status": e.status, "anti_bot": e.anti_bot})` ; `except BrowserUrlBlockedError → INVALID_INPUT` ; `except BrowserSessionLimitError → RATE_LIMIT_EXCEEDED` ; `except BrowserNoPageError → DEPENDENCY_ERROR` ; `except BrowserElementNotFoundError → NOT_FOUND` ; `except BrowserActionNotAllowedError → INVALID_INPUT` ; le reste inchangé (`CONFIGURATION_ERROR`).

- [ ] **Step 1: Tests rouges**

`test_session_http_status.py` : monter une `BrowserSession` avec `page = AsyncMock()` dont `goto` renvoie `SimpleNamespace(status=403, headers={"x-datadome": "1"})` ; `await session.navigate("https://www.lacentrale.fr/x")` → `pytest.raises(BrowserHttpError)` avec `.status == 403`, `.anti_bot == "datadome"` ; un `goto` à 200 → pas d'exception, `get_page_content` appelé ; un `goto` renvoyant `None` (navigation same-document) → pas d'exception. Vérifier le constructeur de `BrowserSession` (lignes 40-95) pour l'instancier sans Playwright réel.

`test_browser_tools_errors.py` : patcher `_get_session` pour renvoyer `(pool, session)` dont `session.navigate` lève `BrowserHttpError(403, "https://x", "datadome")` → `result.error_code == "FORBIDDEN"`, `"anti-bot" in result.message`, `metadata["anti_bot"] == "datadome"` ; lève `BrowserSessionLimitError("Max concurrent sessions")` → `RATE_LIMIT_EXCEEDED` ; lève `BrowserUrlBlockedError("…")` → `INVALID_INPUT`. Run → FAIL.

- [ ] **Step 2: `core/anti_bot.py`** (déplacement du fichier de la PR 1 ; `web_fetch/anti_bot.py` devient `from src.core.anti_bot import ANTI_BOT_CLOUDFLARE, ANTI_BOT_DATADOME, detect_anti_bot` + `__all__`).

- [ ] **Step 3: `errors.py`, `session.py`, `pool.py`** — écrire les classes ; remplacer chaque `raise ValueError("…")` par l'exception typée correspondante (table ci-dessus) ; dans `navigate` :

```python
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is not None and response.status >= 400:
                # ADR-281: an interstitial (anti-bot, login wall, 404 page) is a
                # refusal, not content — never hand it to the model as a page.
                browser_actions_total.labels(action_type="navigate", status="http_error").inc()
                raise BrowserHttpError(response.status, url, detect_anti_bot(response.headers))
```

(placé avant `wait_for_load_state` ; le bloc `except Exception as nav_error` existant ferme la page et relève — conserver ; `BrowserHttpError` traverse ce bloc puisqu'il relève tel quel.)

- [ ] **Step 4: `browser_tools.py`** — remplacer les sept classifications par message par des `except` typés (ordre : typés d'abord, `ValueError` générique ensuite s'il reste un producteur, puis `Exception`). Les messages restent en anglais (contrat des outils), sans URL complète dans les logs (`url=url[:200]` existant : remplacer par `domain=urlparse(url).netloc`).

- [ ] **Step 5: Baseline G2** — relancer `.venv/Scripts/pytest tests/unit/domains/agents/test_no_message_substring_classification_guard.py` : il échoue sur « lower it to the measured value » → mettre `browser_tools.py` à `0` (ou retirer l'entrée) dans `message_classification_baseline.json`. C'est le sens du ratchet.

- [ ] **Step 6: Vérifier** — `.venv/Scripts/pytest tests/unit/infrastructure/browser/ tests/unit/domains/agents/tools/test_browser_tools* tests/unit/domains/agents/tools/test_tool_registry_smoke.py tests/unit/domains/agents/test_no_message_substring_classification_guard.py -v -p no:cacheprovider` → PASS ; `task lint:backend` (mypy strict sur les nouvelles classes) ; ratchet métriques : `browser_actions_total` est déjà câblée (label supplémentaire, pas de nouvelle métrique).

- [ ] **Step 7: Preuve runtime** — dans Docker dev, mode ReAct : « Ouvre https://www.lacentrale.fr/auto-occasion-annonce-66103994839.html avec le navigateur et dis-moi ce que tu vois » → LIA dit que le site refuse la lecture automatisée (403, DataDome) ; le log `browser_navigate_*` porte le domaine, pas le chemin ; `browser_actions_total{action_type="navigate",status="http_error"}` ≥ 1 sur `/metrics`.

- [ ] **Step 8: Point de contrôle.**

---

### Tâche E2 : Documentation de la PR 2

- [ ] **Step 1** — `grep -rln "execution_trace\|backstage\|ExecutionTraceDisclosure" docs/` → mettre à jour le document qui décrit la trace (ADR-133 V2 / « Lot 2 P2-V1 ») : le champ `outcome`, sa rétro-compatibilité, la règle « failed = tous les steps de l'outil ont échoué ».
- [ ] **Step 2** — `grep -rln "browser_navigate_tool\|BrowserSession" docs/` → mettre à jour (statut HTTP lu, exceptions typées, `http_error`).
- [ ] **Step 3** — ADR-281 : section « Amendements » (lot D : la trace ; lot E : le navigateur) plutôt qu'un nouvel ADR — même décision, deux surfaces de plus.
- [ ] **Step 4** — `task docs:sync-agents` si `CLAUDE.md` a bougé ; `task lint:docs` → 0.
- [ ] **Step 5: Point de contrôle.**

---

### Tâche E3 : Gates et rapport

- [ ] `task lint` ; `task test:backend:unit:fast` ; `task test:backend:agents` ; `task test:frontend:coverage` ; `pnpm a11y:ratchet && pnpm react-hooks:ratchet && pnpm cc:ratchet` (depuis `apps/web/`) ; `task ci:fast`.
- [ ] Rapport : commandes, statuts, nombres, ce qui a été vu dans le navigateur (bureau + 360 px), ce qui n'a pas été vérifié. Commits et push au propriétaire ; release et CHANGELOG via `lia-release`, déploiement via `lia-deploy-prod` (arbre propre, verdict CI, commit vérifié dans le conteneur, un tour d'action échouant sur l'instance).

---

## Auto-revue du plan

- **Couverture** : §3.9 → D1-D4 ; §3.10 → E1 ; docs → E2 ; gates → E3.
- **Noms** : `pipeline_tool_outcomes`, `react_tool_outcomes`, `outcome_steps(outcomes, emit)`, `ToolOutcome`, `OutcomeCounts`, `_emit_tool_execution_step(tool_name, status, additional_data)`, `outcome: 'failed'`, `markTraceStepFailed`, `chat.trace.step_failed`, `BrowserHttpError(status, url, anti_bot)`, `core/anti_bot.detect_anti_bot`, label `http_error`.
- **Vérifié le 2026-09-10** (post-v1.44.0) : les ancrages tiennent — `service.py` (`_emit_tool_execution_step` 1691, `_extract_pipeline_tool_steps` 1608, `_extract_react_tool_steps` 1571, dispatch 1527), `trace_capture.py` (`observe` 70, dédup 94-99), `execution_metadata.py:279` (le `Literal` à trois valeurs, toujours deux jamais émises), `session.py:121` (`goto` sans lecture de statut), `browser_tools.py` (7 classifications par message), et côté front `execution-trace.ts` sans `outcome`, `buildTraceStep` ligne 156, `chat.trace` sans `step_failed`. Deux fichiers voisins ont bougé pour le panneau des registres (`deferred_debug.py`, `register_debug.py`, `debug_metrics_stages.py`) — hors périmètre.
- **Rétro-compatibilité** : trace sans `outcome` (D3 hydratation testée), clients anciens (champ ignoré), `browser_actions_total` (label ajouté, métrique existante).
- **Risque restant nommé** : la caractérisation `tests/agents/test_agent_service_stream_characterization.py` peut pinner `status: "started"` sur les steps pipeline — c'est attendu, la mise à jour est justifiée par ADR-281 et se fait avec le test, jamais en affaiblissant l'oracle.
