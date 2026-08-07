/**
 * Pure adapters from showroom decisions to the EXISTING chat contracts.
 *
 * Every mission reuses HitlActionCard and ExecutionTraceDisclosure verbatim:
 * these builders produce their input shapes from the immutable mission
 * definition plus caller-resolved translations. No timers, no telemetry
 * here — and never a prompt, secret, or raw fixture: only the bounded
 * display fields the cards actually render.
 */

import type { TFunction } from 'i18next';

import type {
  ShowroomDecisionKind,
  ShowroomDecisionSpec,
  ShowroomMissionId,
} from '@/components/showroom/types';
import type { ExecutionTrace } from '@/types/execution-trace';
import type { HitlCardState } from '@/types/hitl';

/** Action rows per decision kind (style mirrors the chat card contract). */
const ACTION_STYLE: Record<ShowroomDecisionKind, 'primary' | 'ghost' | 'secondary'> =
  {
    confirm: 'primary',
    edit: 'ghost',
    cancel: 'secondary',
  };

function actionsFor(spec: ShowroomDecisionSpec) {
  return spec.allowed.map((action) => ({
    action,
    label: action,
    style: ACTION_STYLE[action],
  }));
}

/**
 * Build the pending HitlActionCard state for one mission decision.
 *
 * Draft decisions render as `draft_critique` (confirm / edit / cancel; the
 * synthetic messageId is non-null on purpose — HitlActionCard's inline edit
 * toggle compares `editingForMessageId === payload.messageId`, so a null id
 * would silently disable editing). Tool decisions render as
 * `tool_confirmation` with translated arg labels/values.
 */
export function buildDecisionCard(
  runId: number,
  missionId: ShowroomMissionId,
  spec: ShowroomDecisionSpec,
  t: TFunction
): HitlCardState {
  const messageId = `showroom-${missionId}-${spec.id}-${runId}`;
  if (spec.kind === 'draft') {
    return {
      status: 'awaiting',
      resolution: null,
      submittedAction: null,
      payload: {
        messageId,
        kind: 'draft_critique',
        actions: actionsFor(spec),
        draftId: `showroom-draft-${missionId}-${spec.id}-${runId}`,
        draftType: 'email',
        draftContent: {
          to: spec.to,
          subject: t(spec.subjectKey),
          body: t(spec.bodyKey),
        },
      },
    };
  }
  return {
    status: 'awaiting',
    resolution: null,
    submittedAction: null,
    payload: {
      messageId,
      kind: 'tool_confirmation',
      actions: actionsFor(spec),
      toolName: t(spec.toolNameKey),
      toolArgs: Object.fromEntries(
        spec.args.map((arg) => [
          t(arg.labelKey),
          arg.value ?? (arg.valueKey ? t(arg.valueKey) : ''),
        ])
      ),
    },
  };
}

/**
 * Map a visitor decision onto the existing card lifecycle.
 *
 * An applied edit renders as a confirmed resolution: the bounded 'edit'
 * marker lives in the showroom reducer, and `HitlCardState.submittedAction`
 * stays inside its `'confirm' | 'cancel' | null` contract (never widened).
 */
export function resolveCard(
  card: HitlCardState,
  decision: ShowroomDecisionKind
): HitlCardState {
  const confirmed = decision !== 'cancel';
  return {
    ...card,
    status: 'resolved',
    resolution: confirmed ? 'confirmed' : 'cancelled',
    submittedAction: confirmed ? 'confirm' : 'cancel',
  };
}

/** Fixed emoji/category slots of the public storyboard trace. */
const TRACE_SLOTS = [
  { emoji: '🧭', category: 'system' },
  { emoji: '🔎', category: 'context' },
  { emoji: '🗺️', category: 'agent' },
  { emoji: '✍️', category: 'tool' },
] as const;

/**
 * Build the four-slot public ExecutionTrace. Labels arrive already
 * translated; reasoning is ALWAYS the empty string (the disclosure then
 * renders no reasoning block — the honesty contract of the program).
 */
export function buildShowroomTrace(
  stepLabels: readonly string[],
  durationMs: number
): ExecutionTrace {
  if (stepLabels.length < TRACE_SLOTS.length) {
    throw new Error(
      `showroom trace needs ${TRACE_SLOTS.length} labels, got ${stepLabels.length}`
    );
  }
  return {
    steps: TRACE_SLOTS.map((slot, i) => ({
      emoji: slot.emoji,
      label: stepLabels[i],
      category: slot.category,
    })),
    reasoning: '',
    durationMs,
  };
}
