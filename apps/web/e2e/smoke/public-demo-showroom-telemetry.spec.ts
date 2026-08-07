/**
 * Guided showroom P0 — telemetry-ON contract oracle.
 *
 * Runs ONLY in the dedicated clean managed build
 * (`task test:e2e:showroom:telemetry`): variant=guided, telemetry=true,
 * NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0 (the layout emitter is neutralized so
 * this oracle stays deterministic — its ordinary credentialed stream is a
 * disclosed non-showroom limitation).
 *
 * What must hold:
 * - the ONLY API traffic is POST /api/v1/product/showroom-events;
 * - that request carries NO Cookie and NO Authorization header even when a
 *   session cookie exists in the browser;
 * - the body is the exact bounded enum shape; the mocked contract answers 202;
 * - the funnel sequence for the canonical path is exactly the expected
 *   at-most-once-per-run vocabulary.
 */

import { expect, test } from '@playwright/test';

// Pin the browser locale so the French role-name selectors are deterministic.
test.use({ locale: 'fr-FR' });

test('canonical run emits only credential-less showroom events', async ({ page, context }) => {
  // A session cookie EXISTS in the browser: the credential-less contract
  // must still keep it off the showroom request.
  await context.addCookies([
    { name: 'lia_session', value: 'e2e-should-never-be-sent', url: 'http://127.0.0.1:3000' },
  ]);

  const received: string[] = [];
  const offenders: string[] = [];

  await page.route('**/api/v1/**', async route => {
    const req = route.request();
    const url = req.url();
    // The lia_session cookie this test plants triggers the public shell's
    // ordinary auth hydration (GET /auth/me) — layout behavior, not the
    // mission's. Answer 401 (invalid cookie) and keep it out of the oracle:
    // the anonymous-visitor zero-request proof lives in the telemetry-OFF
    // spec, which plants no cookie and forbids every /api/v1 call.
    if (url.endsWith('/api/v1/auth/me') && req.method() === 'GET') {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'invalid session' }),
      });
      return;
    }
    if (url.endsWith('/api/v1/product/showroom-events') && req.method() === 'POST') {
      const headers = req.headers();
      expect(headers['cookie'], 'showroom POST must be cookie-free').toBeUndefined();
      expect(headers['authorization']).toBeUndefined();
      const body = req.postDataJSON() as { events: string[] };
      expect(Array.isArray(body.events)).toBe(true);
      expect(body.events).toHaveLength(1);
      received.push(body.events[0]);
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ accepted: 1, dropped: 0 }),
      });
      return;
    }
    offenders.push(`${req.method()} ${url}`);
    await route.abort();
  });

  await page.goto('/demo');
  await page.getByTestId('showroom-pick-overloaded_morning').click();
  await page.getByTestId('showroom-start').click();
  for (let i = 0; i < 6; i += 1) {
    await page.getByTestId('showroom-continue').click();
  }
  await page.getByTestId('showroom-decision-0').getByRole('button', { name: 'Confirmer' }).click();
  await page.getByTestId('showroom-decision-1').getByRole('button', { name: 'Annuler' }).click();
  await expect(page.getByTestId('showroom-receipt')).toBeVisible();
  await page.getByTestId('showroom-proof-open').click();
  await page.keyboard.press('Escape');

  // Give the last fire-and-forget attempts a beat to flush.
  await expect
    .poll(() => received.includes('demo_first_proof_opened'), { timeout: 5_000 })
    .toBe(true);

  expect(offenders, 'no other API path may be touched').toEqual([]);
  // Exact per-run funnel for the canonical path (order-insensitive on the
  // wire, at-most-once semantics asserted by counting).
  const counts = new Map<string, number>();
  for (const e of received) counts.set(e, (counts.get(e) ?? 0) + 1);
  expect(counts.get('demo_viewed')).toBe(1);
  expect(counts.get('demo_mission_started')).toBe(1);
  // Per-mission breakdown (bounded vocabulary, one per aggregate).
  expect(counts.get('demo_mission_started_overloaded_morning')).toBe(1);
  expect(counts.get('demo_completed_overloaded_morning')).toBe(1);
  expect(counts.get('demo_first_hitl_decided')).toBe(1);
  expect(counts.get('demo_hitl_confirm')).toBe(1);
  expect(counts.get('demo_hitl_cancel')).toBe(1);
  expect(counts.get('demo_completed')).toBe(1);
  expect(counts.get('demo_first_proof_opened')).toBe(1);
  // No stray vocabulary ever reaches the wire.
  for (const name of counts.keys()) {
    expect(name.startsWith('demo_')).toBe(true);
  }
});
