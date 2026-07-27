/**
 * Mobile visibility doctrine (S3) — which surfaces the narrow layout may drop.
 *
 * Product decision (2026-07-26): the desktop layout is allowed to be RICHER
 * than the mobile one. The codebase had already applied that seven times —
 * the message avatar, the per-message token counters, the audio duration, the
 * debug panel, the token toggle, the inline search field — without the rule
 * ever being written down. This table writes it down, and turns it into
 * assertions (see the sibling test) so "non-essential" cannot quietly become
 * "whatever is convenient to hide".
 *
 * The decision procedure, in order:
 *
 *   Q1. Could hiding it leave the user STUCK?
 *       → `blocking`. Never width-gated. A quota wall, a pending approval, a
 *         connector error: an invisible dead end is a bug, never a concession.
 *
 *   Q2. Does the information stay REACHABLE on mobile another way?
 *       → if not, it must be `substituted` (a short form, an icon with an
 *         accessible name, a popup) rather than dropped.
 *
 *   Q3. Is it OBSERVATION or ACTION?
 *       → observation and decoration may be dropped outright (`desktop-only`);
 *         an action may not, unless it carries a substitute.
 *
 * Two operational consequences, enforced by the tests:
 *  - `display:none` removes an element from the accessibility tree, so an
 *    element carrying INFORMATION is substituted, never suppressed;
 *  - a desktop-only surface that fetches, times or subscribes must be
 *    conditionally MOUNTED (matchMedia), not merely hidden in CSS — hiding it
 *    still pays the battery and the network. See `mountedOnly`.
 */

/** Why the surface exists, which decides whether it may be dropped (Q3). */
export type SurfaceKind = 'action' | 'observation' | 'decoration';

/** How the narrow layout treats it. */
export type SurfaceTier = 'blocking' | 'substituted' | 'desktop-only';

export interface MobileSurface {
  /** Stable identifier, used by the debt ratchet and the e2e probes. */
  id: string;
  /** Where it lives, for a reader who needs to find it. */
  location: string;
  kind: SurfaceKind;
  tier: SurfaceTier;
  /**
   * Narrowest viewport (px) at which the surface renders in full, or `null`
   * when it renders at every width.
   */
  minWidth: number | null;
  /** How the user reaches the same thing below `minWidth`; `null` when nothing does. */
  substitute: string | null;
  /** True when the surface is conditionally MOUNTED, not merely CSS-hidden. */
  mountedOnly?: boolean;
  /**
   * True when the surface does WORK on mount — a query, a timer, a
   * subscription, a websocket.
   *
   * `hidden` in CSS still mounts the component: it still fetches, still ticks,
   * still holds its listeners. On a phone that is battery and data spent on
   * something the user cannot see. A costly surface must therefore be
   * `mountedOnly` (matchMedia + conditional render), never merely hidden —
   * enforced in the sibling test.
   */
  costly?: boolean;
  reason: string;
}

/**
 * Surfaces whose visibility depends on the viewport.
 *
 * Scope: the authenticated application. The public landing page has its own
 * responsive design and its own overflow guard.
 */
export const MOBILE_SURFACES: readonly MobileSurface[] = [
  // ---------------------------------------------------------------- blocking
  {
    id: 'chat-usage-banner',
    location: 'components/usage/UsageBlockedBanner',
    kind: 'action',
    tier: 'blocking',
    minWidth: null,
    substitute: null,
    reason: 'The composer is disabled; without the banner the app simply looks broken.',
  },
  {
    id: 'chat-hitl-card',
    location: 'components/chat/HitlActionCard',
    kind: 'action',
    tier: 'blocking',
    minWidth: null,
    substitute: null,
    reason: 'The conversation is suspended until the user answers this card.',
  },
  {
    id: 'chat-connector-notice',
    location: 'components/chat/ConnectorNoticeBanner',
    kind: 'action',
    tier: 'blocking',
    minWidth: null,
    substitute: null,
    reason: 'Explains why an answer is incomplete and links to the reconnect flow.',
  },
  {
    id: 'header-logout',
    location: 'app/[lng]/dashboard/layout',
    kind: 'action',
    tier: 'blocking',
    minWidth: null,
    substitute: null,
    reason: 'Signing out must be possible at every width (it was not, until S10).',
  },

  // ------------------------------------------------------------- substituted
  {
    id: 'chat-search-field',
    location: 'app/[lng]/dashboard/chat/page',
    kind: 'action',
    tier: 'substituted',
    minWidth: 880,
    substitute: 'A 🔍 toggle unfolds the search row of ChatSearchBar.',
    reason: 'An inline search field cannot share the header row with the status pill below 880 px.',
  },
  {
    id: 'header-personality-label',
    location: 'components/PersonalitySelector',
    kind: 'action',
    tier: 'substituted',
    minWidth: 1280,
    substitute: 'The personality emoji, with an aria-label stating the current value.',
    reason: 'The label cannot sit next to the nav below 1280 px; the control itself stays.',
  },
  {
    id: 'header-language-label',
    location: 'components/LanguageSelector',
    kind: 'action',
    tier: 'substituted',
    minWidth: 1280,
    substitute: 'The language flag, with an aria-label stating the current value.',
    reason: 'The label cannot sit next to the nav below 1280 px; the control itself stays.',
  },
  {
    id: 'chat-reset-label',
    location: 'app/[lng]/dashboard/chat/page',
    kind: 'action',
    tier: 'substituted',
    minWidth: 640,
    substitute: 'The trash icon keeps the action, with an aria-label naming it.',
    reason:
      'The label cannot share the chat header row with the spaces indicator below 640 px; ' +
      'the destructive action itself is never hidden.',
  },
  {
    id: 'settings-row-actions',
    location: 'components/settings/{Memory,Interests,MCPServers,ScheduledActions}Settings',
    kind: 'action',
    tier: 'substituted',
    minWidth: 1024,
    substitute: 'A per-row ⋯ button opens the same actions in a mobile dialog.',
    reason: 'Hover-revealed row actions have no equivalent on touch; the popup replaces them.',
  },

  // ------------------------------------------------------------ desktop-only
  {
    id: 'chat-message-avatar',
    location: 'components/chat/ChatMessage',
    kind: 'decoration',
    tier: 'desktop-only',
    minWidth: 880,
    substitute: null,
    reason: 'Purely decorative: the bubble alignment already identifies the speaker.',
  },
  {
    id: 'chat-message-token-metrics',
    location: 'components/chat/ChatMessage',
    kind: 'observation',
    tier: 'desktop-only',
    minWidth: 880,
    substitute: 'The context pill and the dashboard usage tile carry the same totals.',
    reason: 'Per-message IN/OUT/CACHE counters are analytics, not part of the conversation.',
  },
  {
    id: 'chat-message-audio-duration',
    location: 'components/chat/ChatMessage',
    kind: 'observation',
    tier: 'desktop-only',
    minWidth: 880,
    substitute: null,
    reason: 'Voice-cost telemetry; the 🎤 marker itself stays visible at every width.',
  },
  {
    id: 'chat-context-pill',
    location: 'app/[lng]/dashboard/chat/page',
    kind: 'observation',
    tier: 'desktop-only',
    minWidth: 880,
    substitute: 'The dashboard usage tile carries the same cycle totals.',
    reason:
      'Context-vs-compaction telemetry whose detail lives in a hover tooltip — an affordance ' +
      'touch does not have. The row needs the width for the search toggle, the spaces ' +
      'indicator and the destructive action (measured: 2 px short at 320 px, causing an overlap).',
  },
  {
    id: 'header-token-toggle',
    location: 'app/[lng]/dashboard/layout',
    kind: 'observation',
    tier: 'desktop-only',
    minWidth: 1280,
    substitute: 'The context pill exposes the same totals in its tooltip.',
    reason: 'Token counters only earn their width once the row has room for the labels.',
  },
  {
    id: 'header-nav-icons',
    location: 'app/[lng]/dashboard/layout',
    kind: 'decoration',
    tier: 'desktop-only',
    minWidth: 1280,
    substitute: null,
    reason: 'The nav label carries both the meaning and the accessible name; the icon is scenery.',
  },
  {
    id: 'chat-debug-panel',
    location: 'app/[lng]/dashboard/chat/page',
    kind: 'observation',
    tier: 'desktop-only',
    minWidth: 1024,
    substitute: null,
    mountedOnly: true,
    costly: true,
    reason:
      'Operator tooling gated by an admin setting. It accumulates per-request metrics, so it ' +
      'is conditionally MOUNTED via matchMedia rather than CSS-hidden — hiding it would keep ' +
      'the collection running on phones that never display it.',
  },
  {
    id: 'dashboard-nav',
    location: 'app/[lng]/dashboard/layout',
    kind: 'action',
    tier: 'substituted',
    minWidth: 768,
    substitute: 'The logo becomes a menu button (MobileNavMenu) listing the same destinations.',
    reason:
      'The nav row cannot fit next to the header controls below 768 px. It was the one ' +
      'unsubstituted amputation on this table — every section change detoured through the ' +
      'home page — until A2 turned the logo, already the only landmark up there, into the ' +
      'entry point rather than adding a burger the row has no width for.',
  },
] as const;

/**
 * Surfaces knowingly hidden on mobile with NO substitute, despite carrying an
 * action. Shrink-only: an entry may be removed once a substitute ships, never
 * added — a new entry is a new functional amputation on small screens.
 *
 * Empty since A2 shipped the mobile nav menu. Keeping the list (rather than
 * deleting the concept) is what makes the next amputation a deliberate,
 * reviewable act instead of a silent one.
 */
export const KNOWN_UNSUBSTITUTED: readonly string[] = [];

/**
 * What a viewport of `width` loses compared with the full layout.
 *
 * Args:
 *   width: Viewport width in CSS pixels.
 *
 * Returns:
 *   The surfaces that do not render at that width, in declaration order.
 */
export function surfacesHiddenBelow(width: number): MobileSurface[] {
  return MOBILE_SURFACES.filter(s => s.minWidth !== null && width < s.minWidth);
}
