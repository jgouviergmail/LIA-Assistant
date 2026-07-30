/**
 * "Mes connecteurs" — no horizontal overflow on narrow phones.
 *
 * Regression context (2026-07-30, second occurrence reported by the owner):
 * the connector GROUP rows ("Connecteurs Google connectés (5) [Connecté]")
 * spilled past the right edge on restricted widths. Root cause was the shared
 * `AccordionTrigger` primitive: a `flex-1` item without `min-w-0` refuses to
 * shrink below the intrinsic width of its nowrap label row — the inner
 * `truncate`/`min-w-0` armor could not compensate, because the min-content
 * floor lives on the flex ITEM itself (`ui/accordion.tsx`).
 *
 * Hermetic: a realistic connectors payload (5 Google + 6 external, all
 * active) drives the exact rows from the owner's report; the deep link opens
 * the section for real (a collapsed section would make the sweep vacuously
 * green, hence the visibility assertion first).
 */
import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const CONNECTORS = [
  'google_contacts',
  'gmail',
  'google_calendar',
  'google_drive',
  'google_tasks',
  'openweathermap',
  'wikipedia',
  'perplexity',
  'brave_search',
  'google_places',
  'browser',
].map((connector_type, i) => ({
  id: `00000000-0000-4000-8000-0000000000${String(i).padStart(2, '0')}`,
  connector_type,
  status: 'active',
  created_at: '2026-07-01T10:00:00Z',
}));

for (const width of [320, 360, 390]) {
  test(`connector group rows stay within ${width}px`, async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      { url: '**/api/v1/connectors', json: { connectors: CONNECTORS } },
      { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
      { url: '**/api/v1/usage/**', json: {} },
    ]);
    await page.setViewportSize({ width, height: 800 });
    await page.goto('/fr/dashboard/settings?section=connectors');
    await awaitStyledPage(page, `/dashboard/settings?section=connectors @${width}px`);

    await expect(page.getByText('Connecteurs Google connectés')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Connecteurs externes connectés')).toBeVisible();

    await expectNoOverflow(page, `connectors section at ${width}px`);
  });
}
