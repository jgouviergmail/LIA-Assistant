/**
 * HITL approval-card types (Lot 1 P1-V1).
 *
 * The normalized shape consumed by the card UI and the chat reducer's `hitl`
 * branch. Produced exclusively by `lib/hitl-payload.ts` from the de-facto
 * wire formats (SSE `hitl_interrupt_metadata` chunks and the
 * GET /agents/hitl/pending body) captured at runtime during Phase 0 —
 * NOT from the backend's aspirational unified schema.
 *
 * V1 scope: cards for draft_critique / destructive_confirm /
 * for_each_confirmation / tool_confirmation. Clarification and plan approval
 * stay text-only (chips are P1-V3) — the normalizer returns null for them.
 */

/** Interrupt kinds that render a card in V1. */
export type HitlCardKind =
  | 'tool_confirmation'
  | 'draft_critique'
  | 'destructive_confirm'
  | 'for_each_confirmation';

/** Backend-driven button descriptor (action_requests[].available_actions). */
export interface HitlActionOption {
  /** Action id sent back in hitl_decision (V1: 'confirm' | 'cancel'). */
  action: string;
  /** Backend label key — the UI translates via `hitl.actions.<label>`. */
  label: string;
  /** Visual variant, mirrors the backend HitlActionStyle vocabulary. */
  style: 'primary' | 'secondary' | 'destructive' | 'ghost';
}

/**
 * Structured decision sent in the chat request (Lot 1 option B wire).
 *
 * P1-V2 adds `modification_instructions`, required by the backend when
 * `action` is 'edit' on a draft card (routes the live draft_modifier loop).
 */
export interface HitlDecisionWire {
  message_id: string;
  action: string;
  modification_instructions?: string;
}

/** Normalized interrupt payload — single shape for all card kinds. */
export interface NormalizedHitlPayload {
  /** HITL session id — echoed in hitl_decision for the freshness check. */
  messageId: string | null;
  kind: HitlCardKind;
  /** Buttons, backend-driven with per-kind defensive defaults. */
  actions: HitlActionOption[];
  /** tool_confirmation: tool identity + arguments preview. */
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  /** draft_critique: draft identity + typed content (to/subject/body…). */
  draftId?: string;
  draftType?: string;
  draftContent?: Record<string, unknown>;
  /** destructive_confirm: scope severity display. */
  severity?: 'info' | 'warning' | 'critical';
  operationType?: string;
  affectedCount?: number;
  /** for_each_confirmation: iteration scale display. */
  iterationCount?: number;
  previewItems?: unknown[];
  /** Hydration only (GET /agents/hitl/pending): interrupt timestamp. */
  interruptTs?: string | null;
}

/** Card lifecycle — see chat-reducer transitions. */
export type HitlCardStatus = 'none' | 'awaiting' | 'submitting' | 'resolved' | 'expired';

/** How an awaiting card ended. */
export type HitlResolution = 'confirmed' | 'cancelled' | 'via_text' | null;

export interface HitlCardState {
  status: HitlCardStatus;
  /** Normalized payload — null only when status is 'none'. */
  payload: NormalizedHitlPayload | null;
  /** Set when the card leaves 'awaiting'/'submitting'. */
  resolution: HitlResolution;
  /** Action submitted via button — derives resolution at STREAM_DONE. */
  submittedAction: 'confirm' | 'cancel' | null;
}

export const initialHitlCardState: HitlCardState = {
  status: 'none',
  payload: null,
  resolution: null,
  submittedAction: null,
};
