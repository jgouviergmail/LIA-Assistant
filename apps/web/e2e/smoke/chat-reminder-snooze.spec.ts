/**
 * A reminder that rang, postponed from its bubble (ADR-268 amendment 2026-11-16).
 *
 * The unit tests pin the component's states; this spec pins them in a real
 * browser: the bubble of a reminder whose occurrence was recorded offers the
 * three delays — and « stop » when it repeats — without overflowing a phone; a
 * keyboard press posts the choice, and the verdict takes the buttons' place AND
 * the focus; a bubble whose window closed offers nothing and asks the server
 * nothing.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Locator } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow } from './overflow-report';

const french: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);

/** Shipped French copy, its `{{placeholders}}` filled — never a copy in the harness. */
function copy(key: string, values: Record<string, string | number> = {}): string {
  let value: unknown = french;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = Object.entries(value).find(([name]) => name === part)?.[1];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match
  );
}

const FIRING = '00000000-0000-4000-8000-0000000f1a01';
const OPEN = '2099-01-01T00:00:00Z';
const CLOSED = '2000-01-01T00:00:00Z';

/** The archived bubble, as `reminder_notification._archive` writes it. */
function bubble(snoozableUntil: string) {
  return {
    id: '00000000-0000-4000-8000-0000000f1a02',
    role: 'assistant',
    content: '<p>🔔 C’est l’heure d’arroser les plantes.</p>',
    created_at: '2026-11-16T09:00:00Z',
    message_metadata: {
      type: 'reminder_notification',
      reminder_id: '00000000-0000-4000-8000-0000000f1a03',
      firing_id: FIRING,
      snoozable_until: snoozableUntil,
    },
  };
}

interface Seen {
  reads: number;
  presses: unknown[];
}

function routes(snoozableUntil: string, seen: Seen): MockRoute[] {
  return [
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [bubble(snoozableUntil)],
        conversation_id: '00000000-0000-4000-8000-00000000c0a1',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    {
      url: `**/api/v1/reminders/firings/${FIRING}`,
      handler: async route => {
        seen.reads += 1;
        await route.fulfill({
          json: {
            id: FIRING,
            fired_at: '2026-11-16T09:00:00Z',
            snoozable_until: snoozableUntil,
            snoozed_until: null,
            stoppable: true,
            short_minutes: 10,
            long_minutes: 60,
          },
        });
      },
    },
    {
      url: `**/api/v1/reminders/firings/${FIRING}/snooze`,
      method: 'POST',
      handler: async route => {
        seen.presses.push(route.request().postDataJSON());
        await route.fulfill({
          json: {
            outcome: 'snoozed',
            snoozed_until: '2026-11-16T09:10:00Z',
            next_occurrence_at: null,
          },
        });
      },
    },
  ];
}

/** Vertical centres within a pixel: the same row, not a line below or a margin off. */
async function expectCentredOn(item: Locator, reference: Locator): Promise<void> {
  const [box, ref] = await Promise.all([item.boundingBox(), reference.boundingBox()]);
  if (!box || !ref) throw new Error('Missing layout box');
  expect(Math.abs(box.y + box.height / 2 - (ref.y + ref.height / 2))).toBeLessThanOrEqual(1);
}

/** Right edges within a pixel: the group ends where its row ends. */
async function expectAtRightEnd(item: Locator, container: Locator): Promise<void> {
  const [box, outer] = await Promise.all([item.boundingBox(), container.boundingBox()]);
  if (!box || !outer) throw new Error('Missing layout box');
  expect(Math.abs(box.x + box.width - (outer.x + outer.width))).toBeLessThanOrEqual(1);
}

test.describe('a reminder that rang, from its bubble', () => {
  for (const width of [390, 1280] as const) {
    test(`offers the delays and a keyboard press leaves the focus on its verdict (${width})`, async ({
      page,
      authenticate,
      mockApi,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      await authenticate({ language: 'fr' });
      const seen: Seen = { reads: 0, presses: [] };
      await mockApi(routes(OPEN, seen));
      await page.goto('/fr/dashboard/chat');

      const row = page.getByRole('group', { name: copy('reminders.firing.actions_label') });
      await expect(row).toBeVisible();
      const short = row.getByRole('button', {
        name: copy('reminders.firing.in_minutes', { count: 10 }),
      });
      await expect(short).toBeVisible();
      await expect(
        row.getByRole('button', { name: copy('reminders.firing.in_hours', { count: 1 }) })
      ).toBeVisible();
      await expect(
        row.getByRole('button', { name: copy('reminders.firing.tomorrow_morning') })
      ).toBeVisible();
      await expect(row.getByRole('button', { name: copy('reminders.firing.stop') })).toBeVisible();
      await expectNoOverflow(page, `reminder snooze row ${width}`);
      // One row with the bubble's icons: the delays are centred on them, and
      // pushed to the row's right end on a desktop (owner request 2026-11-16).
      const actions = row.locator('xpath=..');
      const icon = actions.getByRole('button', { name: copy('chat.message.copy') });
      if (width >= 1024) {
        await expectCentredOn(short, icon);
        await expectAtRightEnd(row, actions);
      }
      const accessibility = await scanPage(page, testInfo, `chat-reminder-snooze-${width}`);
      expect(accessibility.blocking, accessibility.summary).toHaveLength(0);

      await short.focus();
      await page.keyboard.press('Enter');

      await expect.poll(() => seen.presses).toEqual([{ choice: 'short', surface: 'chat' }]);
      const verdict = row.getByRole('status');
      // The words before the instant: the instant itself is the browser's to format.
      await expect(verdict).toContainText(
        copy('reminders.firing.snoozed').split('{{when}}')[0].trim()
      );
      await expect(verdict).toBeFocused();
      // The verdict takes the delays' place in the same row, centred on the icons.
      if (width >= 1024) {
        await expectCentredOn(verdict, icon);
        await expectAtRightEnd(row, actions);
      }
      await expect(short).toHaveCount(0);
      // « Stop » stays: the series has a future of its own.
      await expect(row.getByRole('button', { name: copy('reminders.firing.stop') })).toBeVisible();
    });
  }

  test('a closed window offers nothing and asks the server nothing', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'fr' });
    const seen: Seen = { reads: 0, presses: [] };
    await mockApi(routes(CLOSED, seen));
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByText('C’est l’heure d’arroser les plantes.')).toBeVisible();
    await expect(
      page.getByRole('group', { name: copy('reminders.firing.actions_label') })
    ).toHaveCount(0);
    expect(seen.reads).toBe(0);
  });
});
