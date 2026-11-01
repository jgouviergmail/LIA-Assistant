/**
 * HITL wire-payload normalizer (Lot 1 P1-V1).
 *
 * Single entry mapping the de-facto backend formats — the SSE
 * `hitl_interrupt_metadata` chunk metadata and the GET /agents/hitl/pending
 * body share the same shape — to the `NormalizedHitlPayload` the card UI and
 * the reducer consume. Shapes were pinned from REAL runtime captures
 * (Phase 0, scratchpad/t03-captures), not from the backend's aspirational
 * unified schema: emissions are hand-built dicts per interaction and differ
 * per kind.
 *
 * Contract:
 *  - V1 card kinds only (draft / tool / destructive / for_each) and the
 *    « which of these? » choice (ADR-367); anything else — clarification,
 *    plan approval, unknown, garbage — returns null and the flow stays
 *    text-only. Never throws.
 *  - Wire action ids pass through VERBATIM (e.g. "confirm_delete"): the
 *    backend canonicalizes aliases server-side, single source of truth.
 *  - The structured "edit" action is offered on draft cards only (P1-V2):
 *    it routes the live modification-instructions loop. On any other kind
 *    the server rejects it as stale, so it stays filtered there. Likewise
 *    "none" (« none of these ») exists on the choice card alone; its options
 *    are buttons of their own, each sending its position.
 */

import type {
  HitlActionOption,
  HitlCardKind,
  HitlChoiceOption,
  NormalizedHitlPayload,
} from '@/types/hitl';

const CARD_KINDS: readonly HitlCardKind[] = [
  'tool_confirmation',
  'draft_critique',
  'destructive_confirm',
  'for_each_confirmation',
  'entity_disambiguation',
];

const KNOWN_STYLES = new Set(['primary', 'secondary', 'destructive', 'ghost']);

/** Actions the structured resume path supports on every card kind. */
const SUPPORTED_ACTIONS = new Set([
  'confirm',
  'approve',
  'confirm_delete',
  'confirm_all',
  // ADR-298: the egress card's second answer — allowed, without the turn's
  // data. Absent here the button would vanish in silence and the person
  // could only allow WITH the data.
  'confirm_without_data',
  'cancel',
  'reject',
]);

/** Actions a single card kind adds: the draft's inline edit (P1-V2), the
 * choice's « none of these » (ADR-367). */
const KIND_ONLY_ACTIONS: Partial<Record<HitlCardKind, ReadonlySet<string>>> = {
  draft_critique: new Set(['edit']),
  entity_disambiguation: new Set(['none']),
};

const DEFAULT_ACTIONS: HitlActionOption[] = [
  { action: 'confirm', label: 'confirm', style: 'primary' },
  { action: 'cancel', label: 'cancel', style: 'destructive' },
];

/** A choice confirms nothing: its options choose, these two decline. */
const CHOICE_DEFAULT_ACTIONS: HitlActionOption[] = [
  { action: 'none', label: 'none', style: 'secondary' },
  { action: 'cancel', label: 'cancel', style: 'destructive' },
];

function defaultActions(kind: HitlCardKind): HitlActionOption[] {
  return kind === 'entity_disambiguation' ? CHOICE_DEFAULT_ACTIONS : DEFAULT_ACTIONS;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** Parse wire available_actions defensively; fall back to the canonical pair. */
function normalizeActions(raw: unknown, kind: HitlCardKind): HitlActionOption[] {
  if (!Array.isArray(raw)) return defaultActions(kind);

  const kindOnly = KIND_ONLY_ACTIONS[kind];
  const actions: HitlActionOption[] = [];
  for (const entry of raw) {
    if (!isRecord(entry)) continue;
    const action = asString(entry.action);
    if (!action) continue;
    if (!SUPPORTED_ACTIONS.has(action) && !kindOnly?.has(action)) continue;
    const style = asString(entry.style);
    actions.push({
      action,
      // Label keys are translated via `hitl.actions.<label>`; the wire is
      // inconsistent on casing ("Confirm" vs "confirm") — normalize.
      label: (asString(entry.label) ?? action).toLowerCase(),
      style: style && KNOWN_STYLES.has(style) ? (style as HitlActionOption['style']) : 'secondary',
    });
  }
  return actions.length > 0 ? actions : defaultActions(kind);
}

function normalizeSeverity(raw: unknown): NormalizedHitlPayload['severity'] {
  return raw === 'critical' || raw === 'warning' || raw === 'info' ? raw : undefined;
}

function asPreviewItems(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

type Wire = Record<string, unknown>;
type KindNormalizer = (
  base: NormalizedHitlPayload,
  request: Wire,
  input: Wire
) => NormalizedHitlPayload | null;

function normalizeToolConfirmation(
  base: NormalizedHitlPayload,
  request: Wire
): NormalizedHitlPayload {
  return {
    ...base,
    toolName: asString(request.tool_name),
    toolArgs: isRecord(request.tool_args) ? request.tool_args : undefined,
  };
}

function normalizeDraftCritique(
  base: NormalizedHitlPayload,
  request: Wire,
  input: Wire
): NormalizedHitlPayload | null {
  const draftId = asString(request.draft_id) ?? asString(input.draft_id);
  // Without a draft id the resume cannot target the draft — no card.
  if (!draftId) return null;
  return {
    ...base,
    draftId,
    draftType: asString(request.draft_type) ?? asString(input.draft_type),
    draftContent: isRecord(request.draft_content) ? request.draft_content : undefined,
  };
}

function normalizeDestructiveConfirm(
  base: NormalizedHitlPayload,
  request: Wire,
  input: Wire
): NormalizedHitlPayload {
  return {
    ...base,
    severity: normalizeSeverity(input.severity) ?? 'critical',
    operationType: asString(request.operation_type) ?? asString(input.operation_type),
    affectedCount: asNumber(request.affected_count) ?? asNumber(input.affected_count),
  };
}

function normalizeForEachConfirmation(
  base: NormalizedHitlPayload,
  request: Wire,
  input: Wire
): NormalizedHitlPayload {
  return {
    ...base,
    severity: normalizeSeverity(input.severity) ?? 'warning',
    affectedCount: asNumber(request.total_affected) ?? asNumber(input.total_affected),
    previewItems: asPreviewItems(request.item_previews) ?? asPreviewItems(input.item_previews),
  };
}

/** The options of « which of these? » (ADR-367): a position and a label each. */
function asChoiceOptions(value: unknown): HitlChoiceOption[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap(entry => {
    if (!isRecord(entry)) return [];
    const index = asNumber(entry.index);
    const label = asString(entry.label);
    return index !== undefined && Number.isInteger(index) && index > 0 && label
      ? [{ index, label }]
      : [];
  });
}

function normalizeEntityDisambiguation(
  base: NormalizedHitlPayload,
  request: Wire
): NormalizedHitlPayload | null {
  const options = asChoiceOptions(request.candidates);
  // Nothing to choose among — the typed answer stays the channel.
  return options.length > 0 ? { ...base, options } : null;
}

const KIND_NORMALIZERS: Record<HitlCardKind, KindNormalizer> = {
  tool_confirmation: normalizeToolConfirmation,
  draft_critique: normalizeDraftCritique,
  destructive_confirm: normalizeDestructiveConfirm,
  for_each_confirmation: normalizeForEachConfirmation,
  entity_disambiguation: normalizeEntityDisambiguation,
};

/**
 * Normalize a HITL interrupt payload (SSE chunk metadata or hydration body).
 *
 * Returns null for anything that must not render a card in V1 — the caller
 * simply skips card state and the conversational flow continues unchanged.
 */
export function normalizeHitlPayload(input: unknown): NormalizedHitlPayload | null {
  if (!isRecord(input)) return null;

  const requests = input.action_requests;
  if (!Array.isArray(requests) || requests.length === 0) return null;
  const request = requests[0];
  if (!isRecord(request)) return null;

  const kind = asString(request.type);
  if (!kind || !(CARD_KINDS as readonly string[]).includes(kind)) return null;
  const cardKind = kind as HitlCardKind;

  const base: NormalizedHitlPayload = {
    messageId: asString(input.message_id) ?? null,
    kind: cardKind,
    actions: normalizeActions(request.available_actions, cardKind),
    interruptTs: asString(input.interrupt_ts) ?? null,
  };

  return KIND_NORMALIZERS[cardKind](base, request, input);
}
