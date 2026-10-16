/** Réunions: real responsive geometry and native interactions through the hermetic API boundary. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import type { MeetingListResponse, MeetingSummary } from '../../src/types/meetings';
import { test, expect, waitForHydration, waitForMockGate } from '../fixtures';
import {
  MEETING_ACCOUNT_ZONE,
  MEETING_BROWSER_ZONE,
  MEETING_TIMELINE_NOW,
  meetingTimeline,
  meetingTimelineRoutes,
  observeMeetingRequests,
  prepareMeetingReadingView,
  type MeetingApiRequest,
  pagedMeetingTimeline,
  type MeetingPageRead,
} from '../fixtures/meeting-timeline';
import {
  MATERIAL_SYMBOLS_STYLESHEET_URL,
  MATERIAL_SYMBOLS_FONT_URL,
} from '../fixtures/offline-fonts';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const DETAILS = 'Détails';
// All remain DENIED by the proxy. The page's own external requests have a
// separate exact check against the two fulfilled offline-font mock URLs.
const EXPECTED_BLOCKED_BROWSER_TRANSPORTS = new Set([
  'CONNECT www.google.com:443', // Chromium proxy probe (api-isolation.spec.ts).
  'CONNECT fonts.googleapis.com:443', // Native preconnect in app/[lng]/layout.tsx.
  'CONNECT fonts.gstatic.com:443', // Native cross-origin font preconnect.
]);
const copy = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as Record<string, unknown>;
function translated(key: string): string {
  let value: unknown = copy;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French copy: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French copy: ${key}`);
  return value;
}

function title(meeting: MeetingSummary) {
  return meeting.title ?? translated('meetings.list.untitled');
}
function main(page: Page) {
  return page.getByRole('main');
}
function meetingLinks(page: Page) {
  return main(page).getByRole('link', { name: /^Réunion / });
}
function meetingLink(page: Page, meeting: MeetingSummary) {
  return main(page).getByRole('link', { name: title(meeting), exact: true });
}
function rowFor(page: Page, meeting: MeetingSummary) {
  return meetingLink(page, meeting).locator('xpath=ancestor::li[1]');
}
function startFor(row: Locator, meeting: MeetingSummary) {
  return row.locator(`time[datetime="${meeting.started_at}"]`);
}
function endFor(row: Locator, meeting: MeetingSummary) {
  return row.locator(`time[datetime="${meeting.stopped_at}"]`);
}
function summaryFor(row: Locator) {
  return row.locator('details > summary');
}

async function box(locator: Locator) {
  const result = await locator.boundingBox();
  expect(result, 'a measured element must render a real box').not.toBeNull();
  return result!;
}

/** Measure a visible text glyph, rather than the whole wrapped link/time target. */
async function textBox(locator: Locator, needle?: string, last = false) {
  return locator.evaluate(
    (element, options) => {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.textContent?.trim()) nodes.push(node as Text);
      }
      if (options.last) nodes.reverse();
      for (const node of nodes) {
        const value = node.data;
        const start =
          options.needle === undefined
            ? options.last
              ? value.search(/\S\s*$/)
              : value.search(/\S/)
            : value.indexOf(options.needle);
        if (start < 0) continue;
        const range = document.createRange();
        range.setStart(node, start);
        range.setEnd(node, start + (options.needle?.length ?? 1));
        const rect = range.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      }
      throw new Error(`Visible text not found: ${options.needle ?? 'glyph'}`);
    },
    { needle, last }
  );
}

function civilDay(instant: string, zone: string) {
  return new Intl.DateTimeFormat('fr', { dateStyle: 'full', timeZone: zone }).format(
    new Date(instant)
  );
}
function clock(instant: string, zone: string) {
  return new Intl.DateTimeFormat('fr', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: zone,
  }).format(new Date(instant));
}

async function readyList(page: Page, rows: readonly MeetingSummary[]) {
  await page.goto('/fr/dashboard/meetings');
  await waitForHydration(page, 'main');
  await expect(
    main(page).getByRole('button', { name: translated('meetings.list.record'), exact: true })
  ).toBeVisible();
  await expect(meetingLinks(page)).toHaveText(rows.map(title));
  await expect
    .poll(() =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim()
      )
    )
    .not.toBe('');
  await page.evaluate(() => document.fonts.ready);
}

/**
 * The existing layout can first mount with config absent, then replace its
 * fragment by RecorderShell when meetings becomes enabled. Bound that startup
 * to two reads, and require every subsequent presentation interaction to add none.
 */
function startupReads(reads: readonly MeetingPageRead[]): MeetingPageRead[] {
  expect(reads.length).toBeGreaterThanOrEqual(1);
  expect(reads.length).toBeLessThanOrEqual(2);
  for (const read of reads) expect(read).toEqual({ limit: 20, offset: 0 });
  return reads.map(read => ({ ...read }));
}
async function assertGroupsAndTimes(page: Page, rows: readonly MeetingSummary[], zone: string) {
  const days = [...new Set(rows.map(row => civilDay(row.started_at, zone)))];
  await expect(main(page).getByRole('heading', { level: 2 })).toHaveText(days);
  for (const day of days) {
    const group = main(page)
      .getByRole('heading', { level: 2, name: day, exact: true })
      .locator('xpath=ancestor::section[1]');
    await expect(group.getByRole('link', { name: /^Réunion / })).toHaveText(
      rows.filter(row => civilDay(row.started_at, zone) === day).map(title)
    );
  }
  for (const meeting of rows) {
    const row = rowFor(page, meeting);
    const start = startFor(row, meeting);
    await expect(start).toBeVisible();
    await expect(start).toContainText(clock(meeting.started_at, zone));
    if (meeting.stopped_at) {
      await expect(endFor(row, meeting)).toBeVisible();
      await expect(endFor(row, meeting)).toContainText(clock(meeting.stopped_at, zone));
    } else {
      await expect(row.locator('time')).toHaveCount(1);
    }
    // Stage takes precedence over status, exactly as MeetingStatusBadge does.
    const state = translated(
      meeting.stage ? `meetings.stage.${meeting.stage}` : `meetings.status.${meeting.status}`
    );
    await expect(row.getByText(state, { exact: true }).filter({ visible: true })).toHaveCount(1);
  }
}

/** Only the exposed definition list counts: desktop and mobile share data, not layout. */
function visibleFacts(row: Locator) {
  return row.locator('dl:visible').locator('dd');
}

async function assertMetadata(page: Page, rows: readonly MeetingSummary[]) {
  const durations = ['0:00', '0:17', '15:00', '30:00'];
  for (let index = 0; index < 4; index += 1) {
    const meeting = rows[index];
    const facts = visibleFacts(rowFor(page, meeting));
    await expect(facts.getByText(durations[index], { exact: true })).toBeVisible();
    for (const field of ['participants', 'actions'] as const) {
      const count =
        field === 'participants' ? meeting.participants_count : meeting.action_items_count;
      const label = translated(
        `meetings.list.${field}_${new Intl.PluralRules('fr').select(count)}`
      ).replace('{{count}}', String(count));
      await expect(facts.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(facts.getByText(meeting.template_name!, { exact: false }).first()).toBeVisible();
    for (const key of [
      `meetings.detail.format_selection.${meeting.template_selection}`,
      `meetings.banner.engine.${meeting.stt_provider}`,
      `meetings.detail.index_${meeting.index_state}`,
    ])
      await expect(facts.getByText(translated(key), { exact: false }).first()).toBeVisible();
  }
  await expect(
    visibleFacts(rowFor(page, rows[1])).getByRole('link', {
      name: translated('meetings.detail.derived_from'),
      exact: true,
    })
  ).toBeVisible();
  await expect(
    visibleFacts(rowFor(page, rows[1]))
      .getByText(/0,0123\s*€/)
      .first()
  ).toBeVisible();
  await expect(
    visibleFacts(rowFor(page, rows[1])).getByRole('link', {
      name: translated('meetings.detail.derived_from'),
      exact: true,
    })
  ).toHaveAttribute('href', `/dashboard/meetings/${rows[1].source_meeting_id}`);
  await expect(rowFor(page, rows[4])).not.toContainText('0:00');
  await expect(rowFor(page, rows[0])).not.toContainText('€');
  await expect(rowFor(page, rows[7])).not.toContainText(
    translated('meetings.banner.engine.elevenlabs')
  );
}
async function assertGeometry(page: Page, rows: readonly MeetingSummary[], width: number) {
  const heading = main(page).getByRole('heading', { level: 1, name: 'Réunions', exact: true });
  await expect(heading).toBeVisible();
  const record = main(page).getByRole('button', {
    name: translated('meetings.list.record'),
    exact: true,
  });
  const templates = main(page).getByRole('button', {
    name: translated('meetings.list.templates'),
    exact: true,
  });
  const [h, a, b] = await Promise.all([box(heading), box(record), box(templates)]);
  expect(a.y).toBeGreaterThanOrEqual(h.y + h.height);
  expect(b.y).toBeGreaterThanOrEqual(a.y + a.height);
  expect(Math.abs(a.x - b.x)).toBeLessThanOrEqual(2);
  for (const control of [a, b]) {
    expect(control.width).toBeGreaterThanOrEqual(44);
    expect(control.height).toBeGreaterThanOrEqual(44);
  }
  // The collection itself must not be behind a disclosure or a redundant open command.
  await expect(
    main(page)
      .locator('summary')
      .filter({ hasText: /^Enregistrements$/ })
  ).toHaveCount(0);
  await expect(main(page).getByRole('button', { name: /^Ouvrir(?: |$)/ })).toHaveCount(0);
  await expect(main(page).getByRole('button', { name: /^Suivant(?:,|$)/ })).toHaveCount(0);
  await expect(main(page).getByRole('heading', { level: 3 })).toHaveText([
    'Nuit',
    'Soir',
    'Nuit',
    'Soir',
  ]);
  await expect(main(page).locator('details:visible')).toHaveCount(width < 768 ? rows.length : 0);
  for (const meeting of rows) {
    const row = rowFor(page, meeting);
    const link = meetingLink(page, meeting);
    const check = row.getByRole('checkbox');
    const [frame, target, label, first, last, checkBox] = await Promise.all([
      box(row),
      box(link),
      box(check.locator('xpath=ancestor::label[1]')),
      textBox(link),
      textBox(link, undefined, true),
      box(check),
    ]);
    expect(target.height, 'the title keeps a keyboard/touch target').toBeGreaterThanOrEqual(44);
    expect(target.width).toBeGreaterThanOrEqual(44);
    expect(label.width).toBeGreaterThanOrEqual(44);
    expect(label.height).toBeGreaterThanOrEqual(44);
    expect(
      Math.abs(checkBox.y + checkBox.height / 2 - first.y - first.height / 2),
      'the checkbox follows the first title line'
    ).toBeLessThanOrEqual(4);
    expect(last.x + last.width, 'the full title remains inside its row').toBeLessThanOrEqual(
      frame.x + frame.width + 1
    );
    expect(last.y + last.height, 'a long title is not line-clamped away').toBeLessThanOrEqual(
      target.y + target.height + 1
    );
    const start = await textBox(
      startFor(row, meeting),
      clock(meeting.started_at, MEETING_BROWSER_ZONE)
    );
    const icon = await box(row.locator('svg').first());
    expect(icon.x + icon.width, 'the time icon precedes the start').toBeLessThanOrEqual(
      start.x + 1
    );
    if (meeting.stopped_at) {
      const hourStyles = await Promise.all(
        [startFor(row, meeting), endFor(row, meeting)].map(element =>
          element.evaluate(node => {
            const style = getComputedStyle(node);
            return {
              fontSize: style.fontSize,
              fontFamily: style.fontFamily,
              fontWeight: style.fontWeight,
              lineHeight: style.lineHeight,
            };
          })
        )
      );
      expect(hourStyles[1], 'start and end times share the same typography').toEqual(hourStyles[0]);
    }
    if (width < 768) {
      await expect(row.locator('details')).toHaveJSProperty('open', false);
      await expect(summaryFor(row)).toHaveAccessibleName(DETAILS);
      const disclosure = await box(summaryFor(row));
      expect(disclosure.height).toBeGreaterThanOrEqual(44);
      expect(disclosure.width).toBeGreaterThanOrEqual(44);
      await expect(summaryFor(row).locator('a, button, input')).toHaveCount(0);
      expect(first.y, 'the title follows the mobile hours').toBeGreaterThanOrEqual(
        start.y + start.height - 1
      );
      if (meeting.stopped_at) {
        const end = await textBox(
          endFor(row, meeting),
          clock(meeting.stopped_at, MEETING_BROWSER_ZONE)
        );
        expect(Math.abs(start.y - end.y), 'mobile hours remain on one line').toBeLessThanOrEqual(1);
        expect(end.x).toBeGreaterThan(start.x + start.width);
        const details = summaryFor(row);
        const caption = await textBox(details, translated('common.details'));
        expect(caption.x, 'the short mobile Details label is right-aligned').toBeGreaterThan(
          frame.x + frame.width / 2
        );
        expect(
          disclosure.x + disclosure.width - caption.x - caption.width,
          'only the disclosure chevron and its compact gap follow the label'
        ).toBeLessThanOrEqual(30);
        const styles = await Promise.all(
          [details, endFor(row, meeting)].map(element =>
            element.evaluate(node => {
              const style = getComputedStyle(node);
              return {
                fontSize: style.fontSize,
                fontFamily: style.fontFamily,
                fontWeight: style.fontWeight,
                lineHeight: style.lineHeight,
                color: style.color,
              };
            })
          )
        );
        expect(styles[0], 'Details shares the recorded end-time typography').toEqual(styles[1]);
      }
    } else {
      expect(first.x, 'the desktop title follows the separate time column').toBeGreaterThan(
        start.x + start.width
      );
      expect(Math.abs(first.y - start.y), 'start and first title line align').toBeLessThanOrEqual(
        4
      );
      if (meeting.stopped_at) {
        const end = await textBox(
          endFor(row, meeting),
          clock(meeting.stopped_at, MEETING_BROWSER_ZONE)
        );
        expect(Math.abs(start.x - end.x)).toBeLessThanOrEqual(2);
        expect(end.y).toBeGreaterThanOrEqual(start.y + start.height);
      }
    }
  }
  if (width >= 768) {
    await assertMetadata(page, rows);
    const duration = await box(visibleFacts(rowFor(page, rows[0])).filter({ hasText: /^0:00$/ }));
    const link = await box(meetingLink(page, rows[0]));
    expect(
      Math.abs(duration.x - link.x),
      'desktop metadata aligns with the title'
    ).toBeLessThanOrEqual(2);
  }
  await expectNoOverflow(page, `meetings ${width}px closed`);
}

async function capture(page: Page, info: TestInfo, name: string, target?: Locator) {
  const file = info.outputPath(`${name}.png`);
  if (target) await target.screenshot({ path: file });
  else await page.screenshot({ path: file });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

const failures = new WeakMap<Page, string[]>();
const detailReads = new WeakMap<Page, string[]>();
const meetingRequests = new WeakMap<Page, MeetingApiRequest[]>();
const externalPageRequests = new WeakMap<Page, string[]>();
test.use({ timezoneId: MEETING_BROWSER_ZONE });
test.beforeEach(async ({ page }) => {
  const unexpected: string[] = [];
  const details: string[] = [];
  failures.set(page, unexpected);
  detailReads.set(page, details);
  meetingRequests.set(page, observeMeetingRequests(page));
  const external: string[] = [];
  externalPageRequests.set(page, external);
  page.on('response', response => {
    if (response.status() === 501 && response.url().includes('/api/v1/'))
      unexpected.push(response.url());
  });
  page.on('request', request => {
    const url = new URL(request.url());
    if (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      url.hostname !== 'localhost' &&
      url.hostname !== '127.0.0.1'
    )
      external.push(request.url());
    if (/^\/api\/v1\/meetings\/[0-9a-f-]{36}$/.test(url.pathname))
      details.push(`${request.method()} ${url.pathname}`);
  });
  await page.clock.setFixedTime(new Date(MEETING_TIMELINE_NOW));
});
test.afterEach(async ({ page, apiNetworkGuard }, info) => {
  const external = externalPageRequests.get(page) ?? [];
  await info.attach('meeting-network-boundary', {
    body: JSON.stringify(
      {
        startupAndMeetings: meetingRequests.get(page) ?? [],
        externalPageRequests: external,
        blockedTransport: apiNetworkGuard.blockedRequests,
      },
      null,
      2
    ),
    contentType: 'application/json',
  });
  expect(failures.get(page) ?? [], 'all API reads need explicit hermetic mocks').toEqual([]);
  expect(
    external.filter(
      url => url !== MATERIAL_SYMBOLS_STYLESHEET_URL && url !== MATERIAL_SYMBOLS_FONT_URL
    ),
    'the page must not attempt an external provider request'
  ).toEqual([]);
  // Browser proxy probes and the layout's two font preconnects stay denied.
  // The page can request only the two fully mocked font URLs asserted above.
  // Keep its exact evidence in the attachment; every other blocked escape fails.
  expect(
    apiNetworkGuard.blockedRequests.filter(
      request => !EXPECTED_BLOCKED_BROWSER_TRANSPORTS.has(request)
    ),
    'no API or provider transport may escape page interception'
  ).toEqual([]);
});
for (const sample of [
  { width: 320, theme: 'light', font: 16 },
  { width: 390, theme: 'dark', font: 20 },
  { width: 768, theme: 'oled', font: 16 },
  { width: 1440, theme: 'light', font: 16 },
] as const) {
  test(`meeting timeline geometry @ ${sample.width}px fr ${sample.theme} ${sample.font}px`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize({ width: sample.width, height: 1000 });
    await prepareMeetingReadingView(page);
    await prepareTheme(page, sample.theme);
    const user = await authenticate({
      language: 'fr',
      timezone: MEETING_ACCOUNT_ZONE,
      theme: sample.theme,
      font_size: sample.font,
    });
    const rows = meetingTimeline();
    const reads: MeetingPageRead[] = [];
    await mockApi(meetingTimelineRoutes(user, rows, reads));
    await readyList(page, rows);
    const initialReads = startupReads(reads);
    await expect(
      page.getByRole('button', { name: translated('eyes.restore'), exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole('group', { name: translated('eyes.widget_label'), exact: true })
    ).toHaveCount(0);
    await expect(page.locator('html')).toHaveClass(
      sample.theme === 'light' ? /^(?!.*\bdark\b)/ : /\bdark\b/
    );
    await expect(page.locator('html[data-oled]')).toHaveCount(sample.theme === 'oled' ? 1 : 0);
    await expect(page.locator('html.dark[data-oled]')).toHaveCount(sample.theme === 'oled' ? 1 : 0);
    // FontProvider scales text, deliberately leaving the root rem at 16px.
    // Prove the preference reached both its published scale and a measured title:
    // fonts.ready alone would also pass if the 20px account preference were ignored.
    await expect
      .poll(() =>
        page.evaluate(() =>
          Number(
            getComputedStyle(document.documentElement)
              .getPropertyValue('--lia-text-scale')
              .trim() || '1'
          )
        )
      )
      .toBe(sample.font / 16);
    await expect
      .poll(() =>
        meetingLink(page, rows[0]).evaluate(element =>
          parseFloat(getComputedStyle(element).fontSize)
        )
      )
      .toBe(sample.font);
    const labelMetrics = await rowFor(page, rows[0])
      .getByRole('checkbox')
      .locator('xpath=ancestor::label[1]')
      .evaluate(element => {
        const style = getComputedStyle(element);
        return {
          fontSize: style.fontSize,
          lineHeight: style.lineHeight,
          height: style.height,
          width: style.width,
          targetHeight: element.getBoundingClientRect().height,
        };
      });
    await info.attach('meeting-checkbox-label-computed', {
      body: JSON.stringify(labelMetrics, null, 2),
      contentType: 'application/json',
    });
    if (sample.font === 20) {
      expect(labelMetrics.fontSize).toBe('20px');
      expect(labelMetrics.lineHeight).toBe('32.5px');
      expect(labelMetrics.height).toBe('52.5px');
      expect(labelMetrics.targetHeight).toBe(52.5);
    }
    await assertGroupsAndTimes(page, rows, MEETING_BROWSER_ZONE);
    await assertGeometry(page, rows, sample.width);
    // Distinct recorded instants survive the repeated local hour. The crossed offset is explicit.
    await expect(startFor(rowFor(page, rows[3]), rows[3])).toContainText('UTC+2');
    await expect(endFor(rowFor(page, rows[3]), rows[3])).toContainText('UTC+1');
    await expect(
      rowFor(page, rows[1]).getByText('26 oct. 2026', { exact: false }).first()
    ).toBeVisible();
    await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
    await capture(page, info, 'meeting-timeline-top');
    await capture(page, info, 'meeting-long-title', rowFor(page, rows[0]));
    if (sample.width < 768) {
      const row = rowFor(page, rows[0]);
      await summaryFor(row).click();
      await expect(row.locator('details')).toHaveJSProperty('open', true);
      await expect(visibleFacts(row).getByText('0:00', { exact: true })).toBeVisible();
      await expect(
        visibleFacts(row).getByText(rows[0].template_name!, { exact: false }).first()
      ).toBeVisible();
      await expectNoOverflow(page, `meetings ${sample.width}px expanded`);
      await capture(page, info, 'meeting-expanded-metadata', row);
    }
    if (sample.width === 390) {
      const report = await scanPage(page, info, 'meeting-timeline-390-dark');
      expect(report.blocking, report.summary).toEqual([]);
    }
    expect(reads).toEqual(initialReads);
    expect(detailReads.get(page), 'list metadata must not fetch per-record detail').toEqual([]);
  });
}

test('disclosure, selection and title navigation keep separate keyboard owners', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await prepareTheme(page, 'light');
  const user = await authenticate({
    language: 'fr',
    timezone: MEETING_ACCOUNT_ZONE,
    theme: 'light',
  });
  const rows = meetingTimeline();
  const reads: MeetingPageRead[] = [];
  await mockApi(meetingTimelineRoutes(user, rows, reads));
  await readyList(page, rows);
  const initialReads = startupReads(reads);
  const initialUrl = page.url();
  await expect(
    page.getByRole('group', { name: translated('eyes.widget_label'), exact: true })
  ).toBeVisible();
  // All retained fields can be read on mobile, without selecting or opening a report.
  for (const meeting of rows.slice(0, 4)) {
    const row = rowFor(page, meeting);
    await summaryFor(row).focus();
    await page.keyboard.press('Enter');
    await expect(summaryFor(row)).toBeFocused();
    await expect(row.locator('details')).toHaveJSProperty('open', true);
  }
  await assertMetadata(page, rows);
  const first = rowFor(page, rows[0]);
  const summary = summaryFor(first);
  const checkbox = first.getByRole('checkbox');
  await expect(checkbox).not.toBeChecked();
  await checkbox.focus();
  await page.keyboard.press('Space');
  await expect(checkbox).toBeChecked();
  await expect(checkbox).toBeFocused();
  await expect(first.locator('details')).toHaveJSProperty('open', true);
  const selectAll = main(page).getByRole('checkbox', {
    name: translated('meetings.list.select_all_page'),
    exact: true,
  });
  await expect(selectAll).toHaveJSProperty('indeterminate', true);
  await selectAll.focus();
  await page.keyboard.press('Space');
  for (const meeting of rows) {
    const check = rowFor(page, meeting).getByRole('checkbox');
    if (meeting.status === 'processing' || meeting.status === 'interrupted') {
      await expect(check).toBeDisabled();
      await expect(check).not.toBeChecked();
    } else await expect(check).toBeChecked();
  }
  await summary.focus();
  await page.keyboard.press('Space');
  await expect(first.locator('details')).toHaveJSProperty('open', false);
  await expect(summary).toBeFocused();
  await expect(checkbox).toBeChecked();
  expect(page.url()).toBe(initialUrl);
  expect(reads).toEqual(initialReads);
  expect(detailReads.get(page)).toEqual([]);
  await main(page)
    .getByRole('button', { name: translated('meetings.list.clear_selection'), exact: true })
    .click();
  await expect(checkbox).not.toBeChecked();
  await expect(
    main(page).getByRole('checkbox', {
      name: translated('meetings.list.select_all_page'),
      exact: true,
    })
  ).not.toBeChecked();
  await expect(
    main(page).getByRole('checkbox', {
      name: translated('meetings.list.select_all_page'),
      exact: true,
    })
  ).toHaveJSProperty('indeterminate', false);

  await expect(selectAll).toBeFocused();

  // Only this deliberate navigation may read a detail. A declared 404 is enough:
  // this lot tests the list's real destination, not the report implementation.
  const id = rows[0].id;
  await mockApi([
    {
      url: `**/api/v1/meetings/${id}`,
      method: 'GET',
      status: 404,
      json: { detail: 'meeting_not_found' },
    },
  ]);
  const link = meetingLink(page, rows[0]);
  await expect(link).toHaveAttribute('href', `/dashboard/meetings/${id}`);
  await link.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new URL(`/dashboard/meetings/${id}`, initialUrl).href);
  await expect(
    main(page).getByText(translated('meetings.detail.not_found'), { exact: true })
  ).toBeVisible();
  expect(detailReads.get(page)).toEqual([`GET /api/v1/meetings/${id}`]);
});

test('server pagination stays below each page and resets only the page selection', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await prepareMeetingReadingView(page);
  await prepareTheme(page, 'light');
  const user = await authenticate({
    language: 'fr',
    timezone: MEETING_ACCOUNT_ZONE,
    theme: 'light',
  });
  const rows = pagedMeetingTimeline();
  const reads: MeetingPageRead[] = [];
  await mockApi(meetingTimelineRoutes(user, rows, reads));
  await readyList(page, rows.slice(0, 20));
  const initialReads = startupReads(reads);
  const next = main(page).getByRole('button', { name: /^Suivant(?:,|$)/ });
  const previous = main(page).getByRole('button', {
    name: /^Précédent(?:,|$)/,
  });
  const pager = next.locator('xpath=ancestor::nav[1]');
  const afterList = async (received: readonly MeetingSummary[]) => {
    const last = await box(rowFor(page, received[received.length - 1]));
    expect((await box(pager)).y, 'pagination follows the last received row').toBeGreaterThanOrEqual(
      last.y + last.height
    );
  };
  await afterList(rows.slice(0, 20));
  await expect(previous).toBeDisabled();
  await rowFor(page, rows[0]).getByRole('checkbox').check();
  await next.click();
  await expect(meetingLinks(page)).toHaveText(rows.slice(20).map(title));
  await afterList(rows.slice(20));
  await expect(next).toBeDisabled();
  await expect(
    main(page).getByRole('checkbox', {
      name: translated('meetings.list.select_all_page'),
      exact: true,
    })
  ).not.toBeChecked();
  await expect(
    main(page).getByRole('checkbox', {
      name: translated('meetings.list.select_all_page'),
      exact: true,
    })
  ).toHaveJSProperty('indeterminate', false);
  for (const meeting of rows.slice(20))
    await expect(rowFor(page, meeting).getByRole('checkbox')).not.toBeChecked();
  await expectNoOverflow(page, 'meetings final partial page');
  await capture(page, info, 'meeting-last-page-pagination');
  await previous.click();
  await expect(meetingLinks(page)).toHaveText(rows.slice(0, 20).map(title));
  await expect(rowFor(page, rows[0]).getByRole('checkbox')).not.toBeChecked();
  expect(reads).toEqual([...initialReads, { limit: 20, offset: 20 }, { limit: 20, offset: 0 }]);
  expect(detailReads.get(page)).toEqual([]);
});

test.describe('the browser supplies the civil timezone', () => {
  test.use({ timezoneId: 'America/New_York' });
  test('groups and hours change with the browser rather than UTC or the account', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 1000 });
    await prepareTheme(page, 'light');
    const user = await authenticate({
      language: 'fr',
      timezone: MEETING_ACCOUNT_ZONE,
      theme: 'light',
    });
    const rows = meetingTimeline();
    await mockApi(meetingTimelineRoutes(user, rows));
    await readyList(page, rows);
    await assertGroupsAndTimes(page, rows, 'America/New_York');
    await expect(main(page).getByRole('heading', { level: 2 })).toHaveText([
      'dimanche 25 octobre 2026',
      'samedi 24 octobre 2026',
    ]);
    await expect(main(page).getByRole('heading', { level: 3 })).toHaveText([
      'Soir',
      'Soir',
      'Après-midi',
    ]);
    await expect(startFor(rowFor(page, rows[0]), rows[0])).toHaveText('20:15');
    await expect(startFor(rowFor(page, rows[2]), rows[2])).toHaveText('21:45');
    await expect(startFor(rowFor(page, rows[3]), rows[3])).toHaveText('20:45');
    expect(detailReads.get(page)).toEqual([]);
    await expectNoOverflow(page, 'meetings browser timezone');
  });
});

test('a failed initial page retries without losing keyboard focus or rendering false emptiness', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await prepareMeetingReadingView(page);
  await prepareTheme(page, 'light');
  const user = await authenticate({
    language: 'fr',
    timezone: MEETING_ACCOUNT_ZONE,
    theme: 'light',
  });
  const rows = meetingTimeline();
  const attempts: { status: 503 | 200 | 'pending'; url: string }[] = [];
  const pageErrors: string[] = [];
  const consoleErrors: { text: string; url: string }[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error')
      consoleErrors.push({ text: message.text(), url: message.location().url });
  });
  let recoveryEnabled = false;
  let releaseRecovery!: () => void;
  const recoveryGate = new Promise<void>(resolve => {
    releaseRecovery = resolve;
  });
  await mockApi(meetingTimelineRoutes(user, rows));
  // Every startup mount fails, whether config arrival causes one read or two.
  // Only the explicit user retry may enter the externally suspended success.
  await mockApi([
    {
      url: /\/api\/v1\/meetings(?:\?.*)?$/,
      method: 'GET',
      handler: async (route, signal) => {
        const url = new URL(route.request().url());
        expect([...url.searchParams.entries()]).toEqual([
          ['limit', '20'],
          ['offset', '0'],
        ]);
        if (!recoveryEnabled) {
          attempts.push({ status: 503, url: url.href });
          await route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'meeting_service_unavailable' }),
          });
          return;
        }
        const attempt = { status: 'pending' as 503 | 200 | 'pending', url: url.href };
        attempts.push(attempt);
        if (!(await waitForMockGate(recoveryGate, signal))) return;
        attempt.status = 200;
        const response: MeetingListResponse = {
          items: rows,
          total: rows.length,
          limit: 20,
          offset: 0,
        };
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(response),
        });
      },
    },
  ]);
  await page.goto('/fr/dashboard/meetings');
  await waitForHydration(page, 'main');
  const heading = main(page).getByRole('heading', { level: 1, name: 'Réunions', exact: true });
  await expect(
    main(page).getByRole('button', { name: translated('meetings.list.record'), exact: true })
  ).toBeVisible();
  const alert = main(page).getByRole('alert');
  await expect(alert).toHaveText(translated('meetings.list.load_error'));
  await expect(
    main(page).getByText(translated('meetings.list.empty_title'), { exact: true })
  ).toHaveCount(0);
  await expect(meetingLinks(page)).toHaveCount(0);
  const initialAttempts = attempts.length;
  expect(initialAttempts).toBeGreaterThanOrEqual(1);
  expect(initialAttempts).toBeLessThanOrEqual(2);
  expect(attempts.every(attempt => attempt.status === 503)).toBe(true);
  await capture(page, info, 'meeting-error-503');

  const retry = main(page).getByRole('button', { name: translated('common.retry'), exact: true });
  await retry.focus();
  await expect(retry).toBeFocused();
  const originalRetry = await retry.elementHandle();
  expect(originalRetry).not.toBeNull();
  recoveryEnabled = true;
  await page.keyboard.press('Enter');
  await expect.poll(() => attempts.length).toBe(initialAttempts + 1);
  await expect(retry).toHaveAttribute('aria-busy', 'true');
  await expect(retry).toHaveAttribute('aria-disabled', 'true');
  await expect(retry).toBeFocused();
  expect(await retry.evaluate((element, original) => element === original, originalRetry)).toBe(
    true
  );
  await expect(alert).toBeVisible();
  await expect(meetingLinks(page)).toHaveCount(0);
  // A busy button remains the same focused native owner and suppresses duplicate reads.
  await page.keyboard.press('Enter');
  await page.keyboard.press('Space');
  await page.evaluate(
    () =>
      new Promise<void>(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      )
  );
  await expect(retry).toBeFocused();
  expect(attempts.length).toBe(initialAttempts + 1);
  await capture(page, info, 'meeting-retry-pending-focus');

  releaseRecovery();
  await expect(meetingLinks(page)).toHaveText(rows.map(title));
  await expect(alert).toHaveCount(0);
  await expect(
    main(page).getByText(translated('meetings.list.empty_title'), { exact: true })
  ).toHaveCount(0);
  await expect(heading).toBeFocused();
  await expect(retry).toHaveCount(0);
  expect(attempts.map(attempt => attempt.status)).toEqual([
    ...Array<503>(initialAttempts).fill(503),
    200,
  ]);
  expect(detailReads.get(page), 'error recovery still uses only the list DTO').toEqual([]);
  await expectNoOverflow(page, 'meetings recovered from 503');
  await capture(page, info, 'meeting-recovered-heading-focus');
  const unexpectedConsole = consoleErrors.filter(message => {
    if (
      message.text.includes('meetings_list_failed') &&
      message.text.includes('meeting_service_unavailable')
    )
      return false;
    try {
      return !(new URL(message.url).pathname === '/api/v1/meetings' && /503/.test(message.text));
    } catch {
      return true;
    }
  });
  await info.attach('meeting-503-recovery', {
    body: JSON.stringify({ attempts, consoleErrors, pageErrors }, null, 2),
    contentType: 'application/json',
  });
  expect(unexpectedConsole, 'only the attributed mocked503 console errors are expected').toEqual(
    []
  );
  expect(pageErrors, 'recovery must not produce uncaught page errors').toEqual([]);
});
