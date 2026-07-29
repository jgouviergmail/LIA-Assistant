'use client';

/**
 * Global product-telemetry wiring (ADR-178 Phase 4) — renders nothing.
 *
 * Mounted once in the [lng] layout. Wires, when telemetry is enabled:
 * - Web Vitals v1 (LCP + CLS) via native PerformanceObserver — sampled by
 *   NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE (arbitration b: default 1 = 100 %),
 *   flushed once when the page is hidden (sendBeacon path);
 * - PWA install signals (arbitration c): beforeinstallprompt / appinstalled.
 */

import { useEffect } from 'react';

import {
  isTelemetryEnabled,
  trackProductEvent,
  trackVitals,
  type VitalMetric,
} from '@/lib/product-telemetry';

function sampleRate(): number {
  const raw = Number(process.env.NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE ?? '1');
  if (Number.isNaN(raw)) return 1;
  return Math.min(1, Math.max(0, raw));
}

export function TelemetryBootstrap(): null {
  useEffect(() => {
    if (!isTelemetryEnabled()) return undefined;

    const onInstallPrompt = () => trackProductEvent('pwa_install_prompt');
    const onInstalled = () => trackProductEvent('pwa_installed');
    window.addEventListener('beforeinstallprompt', onInstallPrompt);
    window.addEventListener('appinstalled', onInstalled);

    const sampled = Math.random() < sampleRate();
    const vitals = new Map<VitalMetric, number>();
    const observers: PerformanceObserver[] = [];
    let flushed = false;

    if (sampled && typeof PerformanceObserver !== 'undefined') {
      try {
        const lcp = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const last = entries[entries.length - 1];
          if (last) vitals.set('lcp', last.startTime / 1000);
        });
        lcp.observe({ type: 'largest-contentful-paint', buffered: true });
        observers.push(lcp);

        const cls = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            const shift = entry as PerformanceEntry & {
              value: number;
              hadRecentInput: boolean;
            };
            if (!shift.hadRecentInput) {
              vitals.set('cls', (vitals.get('cls') ?? 0) + shift.value);
            }
          }
        });
        cls.observe({ type: 'layout-shift', buffered: true });
        observers.push(cls);
      } catch {
        // Older engines without these entry types: vitals silently absent.
      }
    }

    const flush = () => {
      if (flushed || document.visibilityState !== 'hidden') return;
      flushed = true;
      trackVitals([...vitals.entries()].map(([metric, value]) => ({ metric, value })));
    };
    document.addEventListener('visibilitychange', flush);

    return () => {
      window.removeEventListener('beforeinstallprompt', onInstallPrompt);
      window.removeEventListener('appinstalled', onInstalled);
      document.removeEventListener('visibilitychange', flush);
      observers.forEach((o) => o.disconnect());
    };
  }, []);

  return null;
}

/**
 * Emits one funnel event on mount — drop into any page to instrument a view
 * (landing_view, demo_started, signup_started…). Renders nothing.
 */
export function TrackView({ event }: { event: Parameters<typeof trackProductEvent>[0] }): null {
  useEffect(() => {
    trackProductEvent(event);
  }, [event]);
  return null;
}
