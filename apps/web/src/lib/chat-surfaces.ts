/**
 * Priority rule for the conditional surfaces of the chat shell (S1).
 *
 * Between the message thread and the composer, up to five blocks can appear —
 * the usage banner, the HITL approval card, connector notices, the geolocation
 * prompt and the follow-up chips. Each is rendered independently and knows
 * nothing of the others.
 *
 * Measured (S0, 2026-07-26, 800 px viewport → 716 px shell): a pending HITL
 * card plus follow-up chips takes the chrome to 443 px, 62 % of the shell,
 * leaving 259 px of conversation — about four lines on a small phone. But the
 * height is the symptom; the defect is the combination itself: LIA asks the
 * user to confirm sending an email *while* offering three unrelated follow-up
 * questions right above it.
 *
 * This module is the single place that decides. It is pure and exhaustively
 * tested, per the repo doctrine (logic in a pure function, never in JSX).
 *
 * Deliberately NOT a pixel budget. Suppressing a block because the viewport is
 * short would eventually hide a blocking one — a quota wall or a pending
 * approval with no explanation — which is exactly the dead end this work set
 * out to remove. The rule arbitrates on MEANING, not on height.
 *
 * Tiers, highest first:
 *   1. blocking   — the user cannot proceed without reading it; never suppressed
 *   2. degrading  — explains why an answer is incomplete; always shown
 *   3. opportunistic / comfort — yields while a blocking surface awaits an action
 */

import type { HitlCardStatus } from '@/types/hitl';

/**
 * Does the approval card currently owe the user an action?
 *
 * Only `awaiting` and `submitting` do. The two end-of-life states are
 * deliberately excluded:
 *  - `resolved` / `expired` still RENDER (they carry the "Confirmé" / "Annulé"
 *    badge until the next turn) but nothing is expected from the user, so the
 *    comfort surfaces may come back.
 *  - `none` means no card at all.
 *
 * `submitting` counts: the decision is in flight and the card must not compete
 * with follow-up suggestions while the answer is being processed.
 */
export function hitlAwaitsUser(status: HitlCardStatus): boolean {
  return status === 'awaiting' || status === 'submitting';
}

/** Every conditional surface of the chat shell, in render order. */
export const CHAT_SURFACES = ['usage', 'hitl', 'connector', 'geolocation', 'followups'] as const;

export type ChatSurface = (typeof CHAT_SURFACES)[number];

export interface ChatSurfaceContext {
  /** The quota wall is up: the composer is disabled. */
  usageBlocked: boolean;
  /** An approval card is waiting for the user (`awaiting` / `submitting`). */
  hitlAwaitingAction: boolean;
  /** At least one connector notice is pending dismissal. */
  hasConnectorNotices: boolean;
  /**
   * The geolocation prompt is a candidate for the slot.
   *
   * Unlike the other surfaces, this one owns its own trigger: the component
   * derives visibility from the typed message, the browser permission state
   * and its dismissal. The arbiter therefore grants or withholds the SLOT —
   * callers pass `true` to mean "mount it if it wants to show", never "it is
   * showing".
   */
  wantsGeolocationPrompt: boolean;
  /** The latest answer carries follow-up suggestions. */
  hasFollowups: boolean;
}

/**
 * Decide which surfaces may render.
 *
 * Args:
 *   context: What each surface's own source reports as active.
 *
 * Returns:
 *   The surfaces that may take the slot. Two readings, on purpose:
 *
 *   - for the COMFORT surfaces (`geolocation`, `followups`) the set is
 *     binding: absent means not mounted — not merely hidden — so they cost no
 *     space and no work;
 *   - for the tier-1/tier-2 surfaces (`usage`, `hitl`, `connector`) it states
 *     that they hold the slot, never that they should disappear when they do
 *     not. `HitlActionCard` also carries the resolved/expired end-of-life
 *     badges, which `hitlAwaitingAction` excludes by design, and each of these
 *     components already owns its own empty early return. The consumer
 *     therefore mounts them unconditionally — see `ChatConditionalSurfaces`.
 *
 *   Modelling all five rather than only the two that yield is deliberate: the
 *   rule is "who is waiting for the user", and that question needs the blocking
 *   surfaces in it to be answerable.
 */
export function visibleChatSurfaces(context: ChatSurfaceContext): ReadonlySet<ChatSurface> {
  const visible = new Set<ChatSurface>();

  // Tier 1 — blocking. Hiding either would leave the user stuck with no reason
  // given, so they are shown whatever else competes for the space.
  if (context.usageBlocked) visible.add('usage');
  if (context.hitlAwaitingAction) visible.add('hitl');

  // Tier 2 — degrading. Explains why an answer is partial; cheap and always
  // worth its line (its multi-notice form is condensed, not dropped).
  if (context.hasConnectorNotices) visible.add('connector');

  // Tier 3 — opportunistic and comfort. While the user owes an answer to a
  // blocking surface, suggesting something else is noise: it competes for
  // attention with the very action that unblocks the conversation.
  const awaitingUser = context.usageBlocked || context.hitlAwaitingAction;
  if (!awaitingUser && context.wantsGeolocationPrompt) visible.add('geolocation');
  if (!awaitingUser && context.hasFollowups) visible.add('followups');

  return visible;
}
