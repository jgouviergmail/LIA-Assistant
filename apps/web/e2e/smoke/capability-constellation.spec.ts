/**
 * The capability constellation — reachable, drawn, and operable without a mouse.
 *
 * Two things this guards, both reported from use:
 *
 *  - **the door exists.** The map has no nav slot (the header row is at its
 *    width limit with six destinations), so its only permanent entry point is
 *    the dashboard's quick-access bar. A map nobody can reach is a map that
 *    does not exist;
 *  - **the drawing is decorative, the links are real.** Everything reachable
 *    is a `<a>` with a translated name; the chart itself is `aria-hidden`. A
 *    `<circle>` with an onClick would look identical and be unusable without a
 *    pointer.
 */

import { test, expect, type MockRoute } from '../fixtures';

const GENERATED_AT = '2026-08-04T08:00:00Z';
const EMPTY_SECTION = {
  status: 'empty',
  data: null,
  generated_at: GENERATED_AT,
  error_code: null,
  error_message: null,
  from_cache: false,
  stale_generated_at: null,
  last_attempt_at: null,
};

const ROUTES: MockRoute[] = [
  // The dashboard's own reads: without them the page never leaves its skeleton
  // and the quick-access bar — the map's only door — is never asserted on.
  {
    url: '**/api/v1/briefing/cards',
    json: {
      cards: {
        weather: EMPTY_SECTION,
        agenda: EMPTY_SECTION,
        mails: EMPTY_SECTION,
        birthdays: EMPTY_SECTION,
        health: EMPTY_SECTION,
        tasks: EMPTY_SECTION,
        documents: EMPTY_SECTION,
        reminders: EMPTY_SECTION,
        for_you: EMPTY_SECTION,
      },
    },
  },
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: 'Bonjour', synthesis: null, generated_at: GENERATED_AT, llm_usage: null },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
  {
    url: '**/api/v1/capabilities*',
    json: {
      nodes: [
        { key: 'connectors', active: true, detail: 3 },
        { key: 'memory', active: true, detail: 412 },
        { key: 'personality', active: true, detail: null },
        { key: 'voice', active: false, detail: null },
        { key: 'proactivity', active: true, detail: null },
        { key: 'interests', active: true, detail: 9 },
        { key: 'routines', active: false, detail: null },
        { key: 'relations', active: true, detail: 5 },
        { key: 'channels', active: false, detail: null },
        { key: 'spaces', active: false, detail: null },
        { key: 'journals', active: true, detail: 24 },
        { key: 'skills', active: false, detail: null },
      ],
      live: 7,
      total: 12,
    },
  },
];

test.describe('capability constellation', () => {
  test('the dashboard offers a permanent door to it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/fr/dashboard');

    const door = page.getByRole('link', { name: /Capacités/i });
    await expect(door, 'the map has no nav slot — this bar is its only door').toBeVisible({
      timeout: 30_000,
    });

    await door.click();
    await page.waitForURL(/\/dashboard\/capabilities/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { level: 1 })).toContainText(/Capacités/i);
  });

  test('the chart is decorative and every star is a real link', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/capabilities');

    const chart = page.locator('svg[viewBox="0 0 100 100"]');
    await expect(chart).toBeVisible({ timeout: 30_000 });
    await expect(chart).toHaveAttribute('aria-hidden', 'true');

    // One link per offered capability — the reachable layer, not the drawing.
    const stars = page.locator('a[aria-label*="—"]');
    await expect(stars).toHaveCount(12);

    // And the figure joins the LIVE ones: seven lit stars, one polygon.
    await expect(chart.locator('polygon')).toHaveCount(1);
  });

  test('a star is reachable and operable from the keyboard alone', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('/fr/dashboard/capabilities');

    const star = page.getByRole('link', { name: /Mémoire — active/i });
    await expect(star).toBeVisible({ timeout: 30_000 });

    await star.focus();
    await expect(star).toBeFocused();
    await page.keyboard.press('Enter');
    await page.waitForURL(/section=memories/, { timeout: 30_000 });
  });

  test('a phone gets the list, with the same destinations', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/fr/dashboard/capabilities');

    await expect(page.getByRole('list').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('svg[viewBox="0 0 100 100"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: /Mémoire/i })).toBeVisible();
  });
});
