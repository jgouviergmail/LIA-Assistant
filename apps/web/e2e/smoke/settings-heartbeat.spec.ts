/**
 * The proactive-notifications panel — the vocabulary the SERVER publishes.
 *
 * ADR-184 applied to a settings list: the client never re-declares which
 * sources exist, it renders `all_sources` in the server's order, so a source
 * added on the API side (habits, then the workboard) appears here with no
 * frontend release. Three claims only a browser proves:
 *
 * - every one of the thirteen published sources is a named switch, in the
 *   published order, and « Habits » is among them with its own glyph;
 * - availability is a fact ABOUT a source, never its state: a source the
 *   account cannot produce still renders ON with a « Not connected » note
 *   attached through `aria-describedby`, while an available one carries no
 *   note at all — a screen reader must never announce « Habits Not connected »
 *   as the switch's own state;
 * - refusing one source is ONE write carrying the FULL sorted refusal set,
 *   and the moment kinds (ADR-281) sit in their own block beside the sources.
 */
import type { Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

/** The server's own display order (heartbeat/source_policy.py). */
const ALL_SOURCES = [
  'calendar',
  'emails',
  'tasks',
  'weather',
  'interests',
  'memories',
  'journals',
  'health_signals',
  'birthdays',
  'open_loops',
  'departure',
  'habits',
  'workboard',
];

/** The labels the six-language vocabulary gives them in English. */
const LABELS: Record<string, string> = {
  calendar: 'Calendar',
  emails: 'Emails',
  tasks: 'Tasks',
  weather: 'Weather',
  interests: 'Interests',
  memories: 'Memories',
  journals: 'Journals',
  health_signals: 'Health',
  birthdays: 'Birthdays',
  open_loops: 'Commitments',
  departure: 'Leave-by advice',
  habits: 'Habits',
  workboard: 'Workboard',
};

/** Mirrors `HeartbeatSettings` (src/hooks/useHeartbeatSettings.ts). */
const SETTINGS = {
  heartbeat_enabled: true,
  heartbeat_min_per_day: 1,
  heartbeat_max_per_day: 3,
  heartbeat_push_enabled: true,
  heartbeat_notify_start_hour: 8,
  heartbeat_notify_end_hour: 22,
  // Habits ARE available (the profile computed); health signals are not.
  available_sources: ALL_SOURCES.filter(source => source !== 'health_signals'),
  disabled_sources: ['emails'],
  all_sources: ALL_SOURCES,
  source_dependencies: { departure: ['calendar'] },
  moment_kinds_disabled: [],
  all_moment_kinds: ['event_followup'],
  moment_kind_dependencies: {},
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/heartbeat/settings', method: 'GET', json: SETTINGS },
  { url: '**/api/v1/heartbeat/history**', json: { notifications: [], total: 0 } },
];

async function openTopics(page: Page): Promise<void> {
  const summary = page.locator('summary', { hasText: 'Notification topics' });
  await expect(summary).toBeVisible({ timeout: 20_000 });
  await summary.click();
  await expect(page.getByRole('switch', { name: 'Calendar' })).toBeVisible();
}

test.describe('heartbeat settings panel', () => {
  test('the thirteen published sources are named switches in the published order', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=heartbeat');
    await openTopics(page);

    // Order and count come from the payload, never from the client.
    const names = await page
      .locator('[role="switch"][id^="heartbeat-source-"]')
      .evaluateAll(nodes => nodes.map(node => node.id.replace('heartbeat-source-', '')));
    expect(names).toEqual(ALL_SOURCES);
    for (const source of ALL_SOURCES) {
      await expect(page.getByRole('switch', { name: LABELS[source] })).toBeVisible();
    }

    // The one refusal in the payload is the one switch that is off.
    await expect(page.getByRole('switch', { name: 'Emails' })).toHaveAttribute(
      'aria-checked',
      'false'
    );
    await expect(page.getByRole('switch', { name: 'Habits' })).toHaveAttribute(
      'aria-checked',
      'true'
    );
  });

  test('availability is a note about the source, never the name of its switch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=heartbeat');
    await openTopics(page);

    // Available: no note, nothing described.
    const habits = page.getByRole('switch', { name: 'Habits' });
    await expect(habits).not.toHaveAttribute('aria-describedby', /.+/);
    await expect(page.locator('#heartbeat-source-habits-note')).toHaveCount(0);

    // Unavailable: still ON (not refused), with the note attached by id.
    const health = page.getByRole('switch', { name: 'Health' });
    await expect(health).toHaveAttribute('aria-checked', 'true');
    await expect(health).toHaveAttribute('aria-describedby', 'heartbeat-source-health_signals-note');
    await expect(page.locator('#heartbeat-source-health_signals-note')).toHaveText(
      'Not connected'
    );
    // Exactly one source is unavailable in the payload — exactly one note.
    await expect(page.getByText('Not connected', { exact: true })).toHaveCount(1);

    // The moment kinds (ADR-281) are a block of their own beside the sources.
    const moments = page.locator('summary', { hasText: 'Anticipated moments' });
    await expect(moments).toBeVisible();
    await moments.click();
    await expect(page.getByRole('switch', { name: 'After a meeting' })).toBeVisible();
  });

  test('refusing habits is one write carrying the full sorted refusal set', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const writes: unknown[] = [];
    await authenticate({ language: 'en' });
    await mockApi([
      ...ROUTES,
      {
        url: '**/api/v1/heartbeat/settings',
        method: 'PATCH',
        handler: async route => {
          const body = route.request().postDataJSON() as { heartbeat_disabled_sources: string[] };
          writes.push(body);
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...SETTINGS, disabled_sources: body.heartbeat_disabled_sources }),
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=heartbeat');
    await openTopics(page);

    await page.getByRole('switch', { name: 'Habits' }).click();

    await expect.poll(() => writes.length, { timeout: 10_000 }).toBe(1);
    expect(writes[0]).toEqual({ heartbeat_disabled_sources: ['emails', 'habits'] });
    await expect(page.getByRole('switch', { name: 'Habits' })).toHaveAttribute(
      'aria-checked',
      'false'
    );
    // The fold's badge counts what is refused now.
    await expect(page.locator('summary', { hasText: 'Notification topics' })).toContainText('2');
  });
});
