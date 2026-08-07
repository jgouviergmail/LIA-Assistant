/**
 * Product telemetry emitter (ADR-178 Phase 4).
 *
 * What must hold:
 * - inert by default (flag unset): no network call ever leaves;
 * - enabled: items post to /api/v1/product/events with the bounded shape;
 * - vitals prefer sendBeacon (page-hide survival), falling back to fetch;
 * - a network failure is swallowed (telemetry never throws).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  isTelemetryEnabled,
  trackProductEvent,
  trackSettingsSearch,
  trackShowroomEvent,
  trackVitals,
} from '@/lib/product-telemetry';

describe('product-telemetry', () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    fetchMock.mockClear();
  });

  it('is inert when the flag is unset', () => {
    expect(isTelemetryEnabled()).toBe(false);
    trackProductEvent('landing_view');
    trackSettingsSearch('results');
    trackVitals([{ metric: 'lcp', value: 1.2 }]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('posts a bounded funnel event when enabled', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    trackProductEvent('demo_started');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/product/events');
    expect(init.keepalive).toBe(true);
    expect(init.credentials).toBe('include');
    expect(JSON.parse(init.body)).toEqual({
      events: [{ kind: 'event', event_type: 'demo_started' }],
    });
  });

  it('posts search outcomes on the settings surface', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    trackSettingsSearch('zero_results');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      events: [{ kind: 'search', surface: 'settings', outcome: 'zero_results' }],
    });
  });

  it('prefers sendBeacon for vitals and falls back to fetch without it', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    const beacon = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'sendBeacon', {
      value: beacon,
      configurable: true,
    });
    trackVitals([{ metric: 'cls', value: 0.05 }]);
    expect(beacon).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();

    Object.defineProperty(navigator, 'sendBeacon', {
      value: undefined,
      configurable: true,
    });
    trackVitals([{ metric: 'lcp', value: 2.1 }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('swallows network failures', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    fetchMock.mockRejectedValueOnce(new Error('offline'));
    expect(() => trackProductEvent('landing_view')).not.toThrow();
  });

  it('sends nothing for an empty vitals batch', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    trackVitals([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  describe('trackShowroomEvent (credential-less collector)', () => {
    it('is inert when the flag is unset', () => {
      trackShowroomEvent('demo_viewed');
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('posts the bare enum WITHOUT credentials to the dedicated route', () => {
      vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
      trackShowroomEvent('demo_mission_started');
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe('/api/v1/product/showroom-events');
      expect(init.credentials).toBe('omit');
      expect(init.keepalive).toBe(true);
      expect(JSON.parse(init.body)).toEqual({
        events: ['demo_mission_started'],
      });
    });

    it('never uses sendBeacon, even when available', () => {
      vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
      const beacon = vi.fn().mockReturnValue(true);
      Object.defineProperty(navigator, 'sendBeacon', {
        value: beacon,
        configurable: true,
      });
      trackShowroomEvent('demo_completed');
      expect(beacon).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('swallows network failures', () => {
      vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
      fetchMock.mockRejectedValueOnce(new Error('offline'));
      expect(() => trackShowroomEvent('demo_viewed')).not.toThrow();
    });
  });
});
