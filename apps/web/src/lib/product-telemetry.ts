/**
 * Product telemetry emitter (ADR-178 Phase 4).
 *
 * Inert unless NEXT_PUBLIC_PRODUCT_TELEMETRY === 'true' (build-time inlined:
 * dev, vitest and the hermetic e2e suite never emit). Fire-and-forget by
 * contract: fetch keepalive with credentials (authenticated attribution when
 * a session cookie exists), sendBeacon for the page-hide flush, every failure
 * swallowed — telemetry must never affect the UX. Payloads are enum-bounded
 * mirrors of the backend vocabulary (never free text).
 */

export type ProductFunnelEvent =
  | 'landing_view'
  | 'signup_started'
  | 'demo_started'
  | 'pwa_install_prompt'
  | 'pwa_installed';

/**
 * Bounded mission identifiers of the multi-mission guided showroom — the
 * exact mirror of the backend `SHOWROOM_MISSION_IDS` registry (guarded on
 * both sides). Adding a mission means adding it HERE and in the backend
 * vocabulary, or its per-mission events are schema-rejected (422).
 */
export const SHOWROOM_MISSION_IDS = [
  'overloaded_morning',
  'proactive_alert',
  'memory_dinner',
  'phone_booking',
  'daily_briefing',
  'config_tour',
] as const;

export type ShowroomMissionId = (typeof SHOWROOM_MISSION_IDS)[number];

/**
 * Showroom funnel vocabulary (P0 program) — accepted ONLY by the dedicated
 * credential-less collector, never by the ordinary /product/events route.
 * `demo_completed` moved here from the ordinary union: it was declared but
 * never emitted there, and the two vocabularies must stay disjoint.
 * Per-mission variants add the bounded mission dimension (which mission
 * engages / converts) without any free-text property.
 */
export type ShowroomFunnelEvent =
  | 'demo_viewed'
  | 'demo_mission_started'
  | 'demo_first_hitl_decided'
  | 'demo_hitl_confirm'
  | 'demo_hitl_edit'
  | 'demo_hitl_cancel'
  | 'demo_completed'
  | 'demo_first_proof_opened'
  | 'demo_source_clicked'
  | 'demo_release_clicked'
  | 'demo_install_guide_clicked'
  | `demo_mission_started_${ShowroomMissionId}`
  | `demo_completed_${ShowroomMissionId}`;

export type SearchOutcome = 'results' | 'zero_results' | 'result_used';

export type VitalMetric = 'lcp' | 'cls';

type TelemetryItem =
  | { kind: 'event'; event_type: ProductFunnelEvent }
  | { kind: 'search'; surface: 'settings'; outcome: SearchOutcome }
  | { kind: 'vital'; metric: VitalMetric; value: number };

export function isTelemetryEnabled(): boolean {
  return (
    typeof window !== 'undefined' && process.env.NEXT_PUBLIC_PRODUCT_TELEMETRY === 'true'
  );
}

function endpoint(): string {
  return `${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/product/events`;
}

function send(items: TelemetryItem[], useBeacon = false): void {
  if (!isTelemetryEnabled() || items.length === 0) return;
  try {
    const body = JSON.stringify({ events: items });
    if (useBeacon && typeof navigator.sendBeacon === 'function') {
      // Same-origin only (a cross-origin JSON beacon cannot preflight) —
      // fine in production where the API sits behind the same proxy.
      navigator.sendBeacon(endpoint(), new Blob([body], { type: 'application/json' }));
      return;
    }
    void fetch(endpoint(), {
      method: 'POST',
      body,
      keepalive: true,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => undefined);
  } catch {
    // Telemetry never throws.
  }
}

export function trackProductEvent(eventType: ProductFunnelEvent): void {
  send([{ kind: 'event', event_type: eventType }]);
}

/**
 * Fire-and-forget showroom emitter (P0 program).
 *
 * Contract differences from the ordinary path, all deliberate:
 * - `credentials: 'omit'` — the request NEVER carries the session cookie;
 * - dedicated enum-only endpoint (`/product/showroom-events`);
 * - never `sendBeacon`, whose same-origin credential behavior would violate
 *   the no-cookie contract;
 * - at-most-once attempt semantics live in the mission controller — this
 *   function guarantees nothing about delivery and swallows every failure.
 */
export function trackShowroomEvent(event: ShowroomFunnelEvent): void {
  if (!isTelemetryEnabled()) return;
  try {
    void fetch(
      `${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/product/showroom-events`,
      {
        method: 'POST',
        body: JSON.stringify({ events: [event] }),
        keepalive: true,
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json' },
      }
    ).catch(() => undefined);
  } catch {
    // Telemetry never throws.
  }
}

export function trackSettingsSearch(outcome: SearchOutcome): void {
  send([{ kind: 'search', surface: 'settings', outcome }]);
}

export function trackVitals(vitals: ReadonlyArray<{ metric: VitalMetric; value: number }>): void {
  send(
    vitals.map(({ metric, value }) => ({ kind: 'vital' as const, metric, value })),
    true
  );
}
