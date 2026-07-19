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
 *  - V1 card kinds only (draft / tool / destructive / for_each); anything
 *    else — clarification, plan approval, unknown, garbage — returns null
 *    and the flow stays text-only. Never throws.
 *  - Wire action ids pass through VERBATIM (e.g. "confirm_delete"): the
 *    backend canonicalizes aliases server-side, single source of truth.
 *  - The structured "edit" action is offered on draft cards only (P1-V2):
 *    it routes the live modification-instructions loop. On any other kind
 *    the server rejects it as stale, so it stays filtered there.
 */

import type { HitlActionOption, HitlCardKind, NormalizedHitlPayload } from '@/types/hitl';

const CARD_KINDS: readonly HitlCardKind[] = [
  'tool_confirmation',
  'draft_critique',
  'destructive_confirm',
  'for_each_confirmation',
];

const KNOWN_STYLES = new Set(['primary', 'secondary', 'destructive', 'ghost']);

/** Actions the structured resume path supports on every card kind. */
const SUPPORTED_ACTIONS = new Set([
  'confirm',
  'approve',
  'confirm_delete',
  'confirm_all',
  'cancel',
  'reject',
]);

/** Actions supported only on draft cards (P1-V2 inline edit). */
const DRAFT_ONLY_ACTIONS = new Set(['edit']);

const DEFAULT_ACTIONS: HitlActionOption[] = [
  { action: 'confirm', label: 'confirm', style: 'primary' },
  { action: 'cancel', label: 'cancel', style: 'destructive' },
];

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
  if (!Array.isArray(raw)) return DEFAULT_ACTIONS;

  const allowsEdit = kind === 'draft_critique';
  const actions: HitlActionOption[] = [];
  for (const entry of raw) {
    if (!isRecord(entry)) continue;
    const action = asString(entry.action);
    if (!action) continue;
    if (!SUPPORTED_ACTIONS.has(action) && !(allowsEdit && DRAFT_ONLY_ACTIONS.has(action))) continue;
    const style = asString(entry.style);
    actions.push({
      action,
      // Label keys are translated via `hitl.actions.<label>`; the wire is
      // inconsistent on casing ("Confirm" vs "confirm") — normalize.
      label: (asString(entry.label) ?? action).toLowerCase(),
      style: style && KNOWN_STYLES.has(style) ? (style as HitlActionOption['style']) : 'secondary',
    });
  }
  return actions.length > 0 ? actions : DEFAULT_ACTIONS;
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

const KIND_NORMALIZERS: Record<HitlCardKind, KindNormalizer> = {
  tool_confirmation: normalizeToolConfirmation,
  draft_critique: normalizeDraftCritique,
  destructive_confirm: normalizeDestructiveConfirm,
  for_each_confirmation: normalizeForEachConfirmation,
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
