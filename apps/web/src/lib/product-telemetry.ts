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
  | 'demo_completed'
  | 'pwa_install_prompt'
  | 'pwa_installed';

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

export function trackSettingsSearch(outcome: SearchOutcome): void {
  send([{ kind: 'search', surface: 'settings', outcome }]);
}

export function trackVitals(vitals: ReadonlyArray<{ metric: VitalMetric; value: number }>): void {
  send(
    vitals.map(({ metric, value }) => ({ kind: 'vital' as const, metric, value })),
    true
  );
}
