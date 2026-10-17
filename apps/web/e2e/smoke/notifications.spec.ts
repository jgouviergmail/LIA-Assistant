/** Notifications: real responsive geometry, lazy sources and independent bottom pagers. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import {
  NOTIFICATION_COUNTS,
  NOTIFICATION_LITERAL_MARKUP,
  NOTIFICATION_LONG_MESSAGE,
  NOTIFICATION_REMINDER,
  NOTIFICATION_UNKNOWN_SOURCE,
  notificationPeerName,
  notificationPeers,
  notificationProactive,
  notificationInterests,
  notificationRoutineName,
  notificationsRoutes,
  prepareNotificationReadingView,
  type NotificationRead,
} from '../fixtures/notifications';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import { scanPage } from '../a11y/scan';

type Family =
  | 'offers'
  | 'peer_messages'
  | 'proactive'
  | 'interests'
  | 'reminders'
  | 'scheduled'
  | 'workboard';
type Theme = 'light' | 'dark' | 'oled';

/** Select shipped translations rather than duplicating product copy in the harness. */
function copy(key: string): string {
  let value: unknown = JSON.parse(
    readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
  );
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object')
      throw new Error(`Missing shipped French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing shipped French label: ${key}`);
  return value;
}

function family(page: Page, key: Family): Locator {
  return page.locator('details').filter({
    has: page
      .locator('summary')
      .getByText(copy(`notifications_hub.sections.${key}.title`), { exact: true }),
  });
}

function familySummary(page: Page, key: Family): Locator {
  return family(page, key).locator(':scope > summary');
}

async function openFamily(page: Page, key: Family): Promise<Locator> {
  const section = family(page, key);
  await familySummary(page, key).click();
  await expect(section).toHaveAttribute('open', '');
  return section;
}

async function ready(page: Page): Promise<void> {
  if (process.env.NOTIFICATIONS_DIAGNOSTIC === '1') {
    page.on('console', message => {
      if (message.type() === 'error') console.log('[notifications-console]', message.text());
    });
    page.on('pageerror', error => console.log('[notifications-pageerror]', error.message));
    page.on('requestfailed', request =>
      console.log(
        '[notifications-requestfailed]',
        request.method(),
        request.url(),
        request.failure()?.errorText
      )
    );
    page.on('response', response =>
      console.log('[notifications-response]', response.status(), response.url())
    );
  }
  const response = await page.goto('/fr/dashboard/notifications');
  expect(response?.status(), 'the real Notifications document must load before UI assertions').toBe(
    200
  );
  await waitForHydration(page, 'main');
  await expect(
    page.getByRole('heading', { level: 1, name: copy('notifications_hub.title'), exact: true })
  ).toBeVisible();
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim()
        ),
      {
        message: 'The real application stylesheet must be applied before measuring UI',
      }
    )
    .not.toBe('');
  await page.evaluate(() => document.fonts.ready);
}

async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const file = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await testInfo.attach(name, { path: file, contentType: 'image/png' });
}
async function box(locator: Locator) {
  const measured = await locator.boundingBox();
  expect(measured, 'the element must have a rendered box').not.toBeNull();
  return measured!;
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Every box read in ONE frame. Separate `boundingBox()` calls can straddle a
 * reflow — a family opening above, the scrollbar appearing — and compare two
 * layouts that were never on screen together: this spec went flaky at 320, 390
 * and 1440 px on that alone (CI, 2026-10-13 to 2026-10-17).
 */
async function framedBoxes(page: Page, locators: readonly Locator[]): Promise<Rect[]> {
  const handles = await Promise.all(locators.map(locator => locator.elementHandle()));
  return page.evaluate(
    elements =>
      elements.map(element => {
        const rect = (element as Element).getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      }),
    handles
  );
}

/**
 * The stated order holds once the layout has settled. A real inversion stays
 * red after the poll's timeout; a reading taken mid-reflow is simply read again.
 */
async function expectLayout(
  page: Page,
  locators: readonly Locator[],
  holds: (boxes: Rect[]) => boolean,
  message: string
): Promise<void> {
  await expect.poll(async () => holds(await framedBoxes(page, locators)), { message }).toBe(true);
}

/** `lower` starts below the bottom edge of `upper` (one pixel of rounding allowed). */
function below(upper: Rect, lower: Rect): boolean {
  return lower.y >= upper.y + upper.height - 1;
}

async function pagerIsBelowRows(section: Locator): Promise<void> {
  const pager = section.getByRole('navigation', {
    name: copy('common.pagination.label'),
    exact: true,
  });
  await expect(pager).toHaveCount(1);
  const [lastRow, navigation] = await Promise.all([
    box(section.getByRole('listitem').last()),
    box(pager),
  ]);
  expect(navigation.y, 'pagination follows the complete visible page').toBeGreaterThanOrEqual(
    lastRow.y + lastRow.height - 1
  );
}

async function expectReadOnly(
  reads: NotificationRead[],
  expected: readonly string[]
): Promise<void> {
  await expect.poll(() => reads.map(read => read.path).sort()).toEqual([...expected].sort());
}

/** Metadata is measured in the actual flow, including narrow screens and long names. */
async function metadataIsReadable(page: Page, messages: Locator): Promise<void> {
  for (const index of [0, 1]) {
    const message = notificationPeers[index];
    const row = messages.getByRole('listitem').nth(index);
    const direction = row.getByText(
      copy(`notifications_hub.direction_${message.direction === 'received' ? 'received' : 'sent'}`),
      { exact: true }
    );
    const attribution = row.getByText(
      copy(
        `notifications_hub.${message.direction === 'received' ? 'from_peer' : 'to_peer'}`
      ).replace('{{name}}', message.peer_display_name),
      { exact: true }
    );
    await expect(attribution).toHaveCount(1);
    await expect(row.getByText(message.peer_display_name, { exact: true })).toHaveCount(0);
    const body = row.getByText(message.content ?? copy('notifications_hub.message_no_content'), {
      exact: true,
    });
    await expectLayout(
      page,
      [direction, attribution, body],
      ([badgeBox, contactBox, bodyBox]) =>
        contactBox.y >= badgeBox.y - 2 && below(contactBox, bodyBox),
      'contact attribution belongs beside the badge and before the message'
    );
    await expect(row.locator('svg')).toHaveCount(0);
  }

  const proactive = await openFamily(page, 'proactive');
  for (const [index, item] of notificationProactive.entries()) {
    const row = proactive.getByRole('listitem').nth(index);
    const date = row.locator(`time[datetime="${item.created_at}"]`);
    const badge = row.getByText(copy(`heartbeat.history.priority_${item.priority}`), {
      exact: true,
    });
    const feedback = row.getByText(
      copy(`heartbeat.history.feedback_${item.user_feedback ?? 'none'}`),
      { exact: true }
    );
    const body = row.getByText(item.content!, { exact: true });
    const expectedTone =
      item.user_feedback === 'thumbs_up'
        ? '--color-success'
        : item.user_feedback === 'thumbs_down'
          ? '--color-destructive'
          : '--color-muted-foreground';
    const feedbackColors = await feedback.evaluate((element, token) => {
      const reference = document.createElement('span');
      reference.style.color = `var(${token})`;
      reference.hidden = true;
      document.body.append(reference);
      const expected = getComputedStyle(reference).color;
      reference.remove();
      return { actual: getComputedStyle(element).color, expected };
    }, expectedTone);
    expect(feedbackColors.actual, 'feedback uses the accessible semantic verdict colour').toBe(
      feedbackColors.expected
    );
    await expectLayout(
      page,
      [date, badge],
      ([dateBox, badgeBox]) =>
        Math.abs(dateBox.y + dateBox.height / 2 - badgeBox.y - badgeBox.height / 2) <= 2,
      'date and priority share the first metadata line'
    );
    await expectLayout(
      page,
      [date, feedback, body],
      ([dateBox, feedbackBox, bodyBox]) =>
        below(dateBox, feedbackBox) && below(feedbackBox, bodyBox),
      'feedback follows the date and priority, and belongs before the message'
    );
    for (const source of item.sources_used) {
      const unknown = source === NOTIFICATION_UNKNOWN_SOURCE;
      const label = unknown ? source : copy(`heartbeat.history.source_${source}`);
      if (unknown) {
        await expect(row.getByText(source, { exact: true })).toBeVisible();
        await expect(
          row.getByText(`heartbeat.history.source_${source}`, { exact: true })
        ).toHaveCount(0);
      } else {
        await expect(row.getByText(source, { exact: true })).toHaveCount(0);
      }
      await expectLayout(
        page,
        [date, row.getByText(label, { exact: true }), body],
        ([dateBox, sourceBox, bodyBox]) => below(dateBox, sourceBox) && below(sourceBox, bodyBox),
        'the notification type follows the date and belongs before the message'
      );
    }
  }

  const interests = await openFamily(page, 'interests');
  const interest = notificationInterests[0];
  const interestRow = interests.getByRole('listitem').first();
  await expectLayout(
    page,
    [
      interestRow.getByText(interest.topic!, { exact: true }),
      interestRow.getByText(copy(`interests.history.source_${interest.source}`), { exact: true }),
      interestRow.getByText(interest.content!, { exact: true }),
    ],
    ([topicBox, sourceBox, contentBox]) =>
      below(topicBox, sourceBox) && below(sourceBox, contentBox),
    'the interest source follows its badge and stays above the interest content'
  );

  const workboard = await openFamily(page, 'workboard');
  const ticket = workboard.getByRole('link');
  const status = ticket.getByText(copy('workboard.columns.waiting'), { exact: true });
  const title = ticket.getByText(
    'Confirmer la proposition et les responsabilités avec les partenaires internationaux',
    { exact: true }
  );
  await expectLayout(
    page,
    [status, title],
    ([statusBox, titleBox]) => below(statusBox, titleBox),
    'ticket status precedes its title'
  );
  await expect(workboard.getByRole('listitem').locator('svg')).toHaveCount(0);
}

const matrix: readonly { width: number; theme: Theme }[] = [
  { width: 320, theme: 'light' },
  { width: 390, theme: 'dark' },
  { width: 390, theme: 'oled' },
  { width: 1440, theme: 'light' },
  { width: 1440, theme: 'dark' },
];

test.describe('Notifications — targeted presentation', () => {
  for (const { width, theme } of matrix) {
    test(`${width}px ${theme}: responsive registers, collapsed sources and bottom pagination`, async ({
      page,
      authenticate,
      mockApi,
      apiNetworkGuard,
    }, testInfo) => {
      const reads: NotificationRead[] = [];
      const unexpectedApi: string[] = [];
      page.on('response', response => {
        if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/v1/'))
          unexpectedApi.push(response.url());
      });
      await page.setViewportSize({ width, height: 900 });
      await prepareTheme(page, theme);
      await prepareNotificationReadingView(page);
      const user = await authenticate({ language: 'fr', timezone: 'Europe/Paris', theme });
      await mockApi(notificationsRoutes(user, reads));
      await ready(page);
      await expectReadOnly(reads, ['/notifications/hub-counts']);

      for (const key of Object.keys(NOTIFICATION_COUNTS) as Family[]) {
        await expect(family(page, key)).not.toHaveAttribute('open', '');
        await expect(
          familySummary(page, key).getByText(String(NOTIFICATION_COUNTS[key]), { exact: true })
        ).toBeVisible();
      }
      const upcoming = page.getByRole('region', {
        name: copy('notifications_hub.groups.upcoming'),
        exact: true,
      });
      const received = page.getByRole('region', {
        name: copy('notifications_hub.groups.received'),
        exact: true,
      });
      const [futureBox, receivedBox] = await Promise.all([box(upcoming), box(received)]);
      if (width < 1024) {
        expect(
          futureBox.y + futureBox.height,
          'future notifications precede received notifications on mobile'
        ).toBeLessThanOrEqual(receivedBox.y + 1);
      } else {
        expect(
          receivedBox.x + receivedBox.width,
          'received register is left of upcoming register'
        ).toBeLessThanOrEqual(futureBox.x + 1);
        expect(Math.abs(receivedBox.y - futureBox.y)).toBeLessThanOrEqual(1);
        expect(Math.abs(receivedBox.width - futureBox.width)).toBeLessThanOrEqual(1);
      }
      const activity = page.getByRole('link', { name: copy('activity.hub_cta'), exact: true });
      const [heading, action] = await Promise.all([
        box(page.getByRole('heading', { level: 1 })),
        box(activity),
      ]);
      expect(action.y).toBeGreaterThanOrEqual(heading.y + heading.height - 1);
      await expectNoOverflow(page, `${width}/${theme}: folded`);
      await capture(page, testInfo, 'notifications-folded');

      const pending = await openFamily(page, 'reminders');
      await expect(pending.getByText(NOTIFICATION_REMINDER, { exact: true })).toBeVisible();
      await expect(pending.getByRole('listitem')).toHaveCount(10);
      await pagerIsBelowRows(pending);
      const reminder = pending.getByRole('listitem').first();
      const reminderTime = reminder.locator('time');
      await expect(reminderTime).toHaveText(
        await reminderTime.evaluate(element =>
          new Intl.DateTimeFormat('fr', { dateStyle: 'medium', timeStyle: 'short' }).format(
            new Date(element.getAttribute('datetime')!)
          )
        )
      );
      expect(await reminder.textContent(), 'a reminder contains only its words and timestamp').toBe(
        `${NOTIFICATION_REMINDER}${await reminderTime.textContent()}`
      );
      await expect(pending.getByRole('listitem').locator('svg')).toHaveCount(0);
      const messages = await openFamily(page, 'peer_messages');
      await expect(messages.getByText(NOTIFICATION_LONG_MESSAGE, { exact: true })).toBeVisible();
      await expect(messages.getByText(NOTIFICATION_LITERAL_MARKUP, { exact: true })).toBeVisible();
      await expect(messages.locator('img')).toHaveCount(0);
      await expect(
        messages.getByText(copy('notifications_hub.message_no_content'), { exact: true })
      ).toBeVisible();
      await expect(messages.getByRole('listitem')).toHaveCount(10);
      await pagerIsBelowRows(messages);
      const fullText = messages.getByText(NOTIFICATION_LONG_MESSAGE, { exact: true });
      expect(
        await fullText.evaluate(element => element.scrollHeight <= element.clientHeight + 1),
        'timeline content must remain fully readable'
      ).toBe(true);
      await metadataIsReadable(page, messages);
      await expectReadOnly(reads, [
        '/notifications/hub-counts',
        '/reminders',
        '/peers/messages',
        '/heartbeat/history',
        '/interests/notifications/history',
        '/workboard/needs-me',
      ]);
      await expectNoOverflow(page, `${width}/${theme}: long notification pages`);
      await capture(page, testInfo, 'notifications-expanded');
      if ((width === 1440 && theme === 'light') || theme === 'oled') {
        const accessibility = await scanPage(page, testInfo, `notifications-${width}-${theme}`);
        expect(accessibility.blocking, accessibility.summary).toHaveLength(0);
      }
      expect(unexpectedApi, 'every API call must be explicitly mocked').toEqual([]);
      // Chromium may attempt its Google background CONNECT outside page routing.
      // The guard REFUSES it. No API or other unexpected transport may reach it.
      expect(
        apiNetworkGuard.blockedRequests.filter(request => request !== 'CONNECT www.google.com:443'),
        'no API or unexpected transport reached the strict guard'
      ).toEqual([]);
      await testInfo.attach('network-guard-refusals.json', {
        body: JSON.stringify({ refused: apiNetworkGuard.blockedRequests }),
        contentType: 'application/json',
      });
    });
  }

  test('offer decisions remain single-flight and return focus; other families retain their real rows', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const reads: NotificationRead[] = [];
    const decisions: string[] = [];
    let releaseDecision: () => void = () => {
      throw new Error('The test gate was not initialised');
    };
    const decisionGate = new Promise<void>(resolve => {
      releaseDecision = resolve;
    });
    await page.setViewportSize({ width: 390, height: 900 });
    await prepareTheme(page, 'light');
    await prepareNotificationReadingView(page);
    const user = await authenticate({ language: 'fr', theme: 'light' });
    await mockApi(
      notificationsRoutes(user, reads, {
        includeOffer: true,
        offerDecisionGate: decisionGate,
        offerDecisions: decisions,
      })
    );
    await ready(page);
    const offers = await openFamily(page, 'offers');
    const accept = offers.getByRole('button', {
      name: copy('notifications_hub.sections.offers.accept'),
      exact: true,
    });
    const dismiss = offers.getByRole('button', {
      name: copy('notifications_hub.sections.offers.dismiss'),
      exact: true,
    });
    await expect(accept).toBeVisible();
    await expect(dismiss).toBeVisible();
    const [acceptBox, dismissBox] = await Promise.all([box(accept), box(dismiss)]);
    expect(Math.abs(acceptBox.width - dismissBox.width)).toBeLessThanOrEqual(1);
    expect(dismissBox.y).toBeGreaterThanOrEqual(acceptBox.y + acceptBox.height - 1);
    await capture(page, testInfo, 'notifications-offer-mobile-light');
    await dismiss.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => decisions.length).toBe(1);
    await expect(dismiss).toHaveAttribute('aria-busy', 'true');
    await expect(dismiss).toHaveAccessibleName(copy('notifications_hub.sections.offers.dismiss'));
    await expect(dismiss).toBeFocused();
    await page.keyboard.press('Enter');
    expect(decisions).toEqual(['thumbs_down']);
    releaseDecision();
    await expect(
      offers.getByText(copy('notifications_hub.sections.offers.empty'), { exact: true })
    ).toBeVisible();
    await expect(familySummary(page, 'offers')).toBeFocused();
    await expect(page).toHaveURL(/\/(?:fr\/)?dashboard\/notifications$/);
    for (const key of ['proactive', 'interests', 'workboard'] as const) {
      const current = await openFamily(page, key);
      await expect(current.getByRole('listitem')).toHaveCount(NOTIFICATION_COUNTS[key]);
    }
    await expect(family(page, 'workboard').getByRole('link')).toHaveAttribute(
      'href',
      /\/fr\/dashboard\/workboard\/00000000-0000-4000-8000-000000000190$/
    );
    await expectNoOverflow(page, 'remaining real notification families');
    await capture(page, testInfo, 'notifications-families-mobile-light');
    const accessibility = await scanPage(
      page,
      testInfo,
      'notifications-other-families-mobile-light'
    );
    expect(accessibility.blocking, accessibility.summary).toHaveLength(0);
  });
  test('routine pages contain different rows without unsupported server pagination', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reads: NotificationRead[] = [];
    await prepareNotificationReadingView(page);
    const user = await authenticate({ language: 'fr' });
    await mockApi(notificationsRoutes(user, reads));
    await ready(page);
    const routines = await openFamily(page, 'scheduled');
    await expect(routines.getByRole('listitem')).toHaveCount(10);
    await expect(routines.getByText(notificationRoutineName(0), { exact: true })).toBeVisible();
    await expect(routines.getByText(notificationRoutineName(10), { exact: true })).toHaveCount(0);
    await expect(
      routines.getByText(copy('notifications_hub.routine_disabled'), { exact: true })
    ).toBeVisible();
    await expect(routines.getByText(/2027|2028/)).toHaveCount(0);
    await pagerIsBelowRows(routines);
    await expect(routines.getByRole('listitem').locator('svg')).toHaveCount(0);
    const pager = routines.getByRole('navigation', {
      name: copy('common.pagination.label'),
      exact: true,
    });
    await pager.getByRole('button', { name: copy('common.next'), exact: true }).click();
    await expect(routines.getByRole('listitem')).toHaveCount(2);
    await expect(routines.getByText(notificationRoutineName(10), { exact: true })).toBeVisible();
    await expect(routines.getByText(notificationRoutineName(0), { exact: true })).toHaveCount(0);
    await expectReadOnly(reads, ['/notifications/hub-counts', '/scheduled-actions']);
    await familySummary(page, 'scheduled').click();
    await openFamily(page, 'scheduled');
    await expect(routines.getByRole('listitem')).toHaveCount(10);
    await expect(routines.getByText(notificationRoutineName(0), { exact: true })).toBeVisible();
    await expectNoOverflow(page, 'routine pagination and reopen');
  });

  test('server-paged history changes rows and the highest-risk failed read recovers by reopening', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reads: NotificationRead[] = [];
    await page.setViewportSize({ width: 390, height: 900 });
    await prepareNotificationReadingView(page);
    const user = await authenticate({ language: 'fr' });
    await mockApi(notificationsRoutes(user, reads, { failInterestsOnce: true }));
    await ready(page);
    const messages = await openFamily(page, 'peer_messages');
    await expect(messages.getByText(NOTIFICATION_LONG_MESSAGE, { exact: true })).toBeVisible();
    await messages.getByRole('button', { name: copy('common.next'), exact: true }).click();
    await expect(messages.getByText(notificationPeerName(10), { exact: true })).toBeVisible();
    await expect(messages.getByRole('listitem')).toHaveCount(2);
    expect(reads.filter(read => read.path === '/peers/messages').map(read => read.query)).toEqual([
      'limit=10&offset=0',
      'limit=10&offset=10',
    ]);
    const interests = await openFamily(page, 'interests');
    await expect(interests.getByRole('alert')).toHaveText(
      copy('notifications_hub.sections.interests.error')
    );
    await expect(
      interests.getByText(copy('notifications_hub.sections.interests.empty'), { exact: true })
    ).toHaveCount(0);
    await familySummary(page, 'interests').click();
    const summary = familySummary(page, 'interests');
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(interests.getByRole('listitem')).toHaveCount(2);
    await expect(interests.getByRole('alert')).toHaveCount(0);
    await expect(summary).toBeFocused();
    expect(
      reads
        .filter(read => read.path === '/interests/notifications/history')
        .map(read => read.status)
    ).toEqual([503, 200]);
    await expectNoOverflow(page, 'recovered independent history');
  });

  test('removed advanced links stay absent and feature gates do not expose unavailable sources', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reads: NotificationRead[] = [];
    await page.setViewportSize({ width: 390, height: 900 });
    await prepareNotificationReadingView(page);
    const user = await authenticate({ language: 'fr' });
    await mockApi(notificationsRoutes(user, reads, { disableOptionalFeatures: true }));
    await ready(page);
    for (const key of ['offers', 'peer_messages', 'proactive', 'workboard'] as const)
      await expect(family(page, key)).toHaveCount(0);
    await expect(
      page.getByRole('link', { name: copy('activity.hub_cta'), exact: true })
    ).toHaveCount(0);
    await expect(
      page.getByText(copy('notifications_hub.advanced_title'), { exact: true })
    ).toHaveCount(0);
    for (const key of ['peer_messages', 'proactive', 'interests', 'scheduled', 'device']) {
      await expect(
        page.getByRole('link', {
          name: copy(`notifications_hub.advanced_links.${key}`),
          exact: true,
        })
      ).toHaveCount(0);
    }
    await expectReadOnly(reads, ['/notifications/hub-counts']);
    await expectNoOverflow(page, 'notifications without removed advanced links');
  });
});
