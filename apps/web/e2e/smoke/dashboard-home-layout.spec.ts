/** Accueil: real DOM geometry and retained interactions through the hermetic API boundary. */
import { readFileSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import type { Locator, Page, Route } from '@playwright/test';
import type { BriefingSection, HealthData } from '../../src/types/briefing';
import { FONT_SIZE_CSS_VAR, fontSizeScale } from '../../src/constants/fonts';
import { test, expect, waitForHydration, waitForMockGate } from '../fixtures';
import {
  HOME_CAPS,
  HOME_GENERATED,
  HOME_GREETING,
  HOME_MEETING_RESULT_TITLE,
  HOME_NOW,
  HOME_ORDER,
  HOME_STATISTICS,
  HOME_SYNTHESIS,
  HOME_TIMEZONE,
  HOME_WORKBOARD_GROUPS,
  homeBriefing,
  homeItemName,
  homeMeetingResult,
  homeRoutes,
  homeWorkboardPreviewName,
} from '../fixtures/dashboard-home';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import { scanPage } from '../a11y/scan';

type Locale = 'fr' | 'de' | 'en';
type Theme = 'light' | 'dark' | 'oled';

const UPDATED_AGENDA_TITLE = 'Agenda actualisé · Dernière réunion internationale confirmée';

function refreshedAgenda() {
  const fresh = homeBriefing();
  const agenda = fresh.cards.agenda.data;
  if (!agenda) throw new Error('The full home fixture must contain agenda data');
  agenda.events[agenda.events.length - 1].title = UPDATED_AGENDA_TITLE;
  fresh.cards.agenda.generated_at = HOME_NOW;
  return fresh;
}

/** A refresh must retain the whole received page, not only its changed final event. */
async function assertRefreshedAgendaPage(scroll: Locator) {
  await expect(scroll.getByRole('listitem')).toHaveCount(HOME_CAPS.agenda);
  for (let index = 0; index < HOME_CAPS.agenda - 1; index += 1) {
    await expect(scroll.getByText(homeItemName('agenda', index), { exact: true })).toHaveCount(1);
  }
  await expect(scroll.getByText(UPDATED_AGENDA_TITLE, { exact: true })).toHaveCount(1);
}

/** Resolve the shipped copy; selectors do not create a competing translation dictionary. */
function translated(locale: Locale, key: string): string {
  let value: unknown = JSON.parse(
    readFileSync(path.join(__dirname, '../../locales', locale, 'translation.json'), 'utf8')
  );
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing ${locale} copy: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing ${locale} copy: ${key}`);
  return value;
}

/** Product contract: account-local weekday/day/month, deliberately without a year. */
function civilDate(instant: string, locale: Locale, zone: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: zone,
  }).format(new Date(instant));
}

/** Only the page title starts with a capital; agenda day labels keep Intl copy. */
function pageDate(instant: string, locale: Locale, zone: string): string {
  const value = civilDate(instant, locale, zone);
  return value.charAt(0).toLocaleUpperCase(locale) + value.slice(1);
}

function briefingRegion(page: Page, locale: Locale) {
  return page.getByRole('region', {
    name: translated(locale, 'dashboard.briefing.section_title'),
    exact: true,
  });
}

function briefingCard(page: Page, section: BriefingSection, locale: Locale) {
  return briefingRegion(page, locale).getByRole('region', {
    name: translated(locale, `dashboard.briefing.cards.${section}.title`),
    exact: true,
  });
}

function briefingCards(page: Page, locale: Locale) {
  // The daily point is now another named region inside « Mon dashboard ».
  // Its h3 is intentional too: the per-section refresh command identifies
  // real data cards without counting the daily point as an eleventh one.
  const refreshName = new RegExp(
    `^${translated(locale, 'dashboard.briefing.refresh_section').split('{{section}}').map(escapePattern).join('.+')}$`
  );
  return briefingRegion(page, locale)
    .getByRole('region')
    .filter({ has: page.getByRole('button', { name: refreshName }) });
}

function escapePattern(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function refreshControl(card: Locator, section: BriefingSection, locale: Locale) {
  const name = translated(locale, 'dashboard.briefing.refresh_section').replace(
    '{{section}}',
    translated(locale, `dashboard.briefing.cards.${section}.title`)
  );
  return card.getByRole('button', { name, exact: true });
}

async function readyHome(page: Page, locale: Locale, expectedCards = HOME_ORDER.length) {
  await page.goto(`/${locale}/dashboard`);
  await waitForHydration(page, 'main');
  await expect(page.getByText(HOME_GREETING, { exact: true })).toBeVisible();
  await expect(briefingCards(page, locale)).toHaveCount(expectedCards);
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim()
        ),
      { message: 'the real application stylesheet must be applied before measuring' }
    )
    .not.toBe('');
  await page.evaluate(() => document.fonts.ready);
}

async function box(locator: Locator) {
  const result = await locator.boundingBox();
  expect(result, 'the measured element must render a real box').not.toBeNull();
  return result!;
}

async function assertHeaderGeometry(page: Page, locale: Locale, width: number) {
  for (const name of HOME_ORDER) {
    const card = briefingCard(page, name, locale);
    await expect(card.getByRole('heading', { level: 3 })).toBeVisible();
    await expect(card.locator('time').first()).toBeVisible();
    await expect(refreshControl(card, name, locale)).toBeVisible();
    const [frame, title, freshness, refresh] = await Promise.all([
      box(card),
      box(card.getByRole('heading', { level: 3 })),
      box(card.locator('time').first()),
      box(refreshControl(card, name, locale)),
    ]);
    for (const [label, item] of Object.entries({ title, freshness, refresh })) {
      expect(item.x, `${name}: ${label} is inside its card`).toBeGreaterThanOrEqual(frame.x - 1);
      expect(item.x + item.width, `${name}: ${label} is inside the viewport`).toBeLessThanOrEqual(
        width + 1
      );
      expect(item.x + item.width, `${name}: ${label} is inside its card`).toBeLessThanOrEqual(
        frame.x + frame.width + 1
      );
    }
    expect(
      freshness.x + freshness.width,
      `${name}: freshness cannot cover refresh`
    ).toBeLessThanOrEqual(refresh.x + 1);
    expect(
      Math.abs(freshness.y + freshness.height / 2 - refresh.y - refresh.height / 2),
      `${name}: freshness and refresh share a row`
    ).toBeLessThanOrEqual(3);
    for (const [label, peer] of Object.entries({ freshness, refresh })) {
      const overlapX =
        Math.min(title.x + title.width, peer.x + peer.width) - Math.max(title.x, peer.x);
      const overlapY =
        Math.min(title.y + title.height, peer.y + peer.height) - Math.max(title.y, peer.y);
      expect(overlapX > 1 && overlapY > 1, `${name}: title cannot cover ${label}`).toBe(false);
    }
    expect(refresh.width, `${name}: refresh remains a touch target`).toBeGreaterThanOrEqual(36);
    expect(refresh.height).toBeGreaterThanOrEqual(36);
  }
}

/** Data labels, not copied grid classes, locate the left column and artwork. */
async function assertWeatherComposition(page: Page, locale: Locale) {
  const weather = briefingCard(page, 'weather', locale);
  const description = weather.getByText('Überwiegend bewölkt', { exact: true });
  const illustration = weather.getByTestId('weather-landscape');
  const descriptionBox = await box(description);
  const artBox = await box(illustration);
  const metrics = [
    weather.getByText(/15 km\/h/, { exact: false }),
    weather.getByText('35%', { exact: true }),
    weather.getByText(/18:30/, { exact: false }),
    weather.getByTestId('weather-air-quality'),
    weather.getByTestId('weather-pollen'),
  ];
  await expect(illustration).toHaveAttribute('aria-hidden', 'true');
  expect(artBox.width, 'the weather illustration keeps a visible right column').toBeGreaterThan(40);
  expect(descriptionBox.x + descriptionBox.width).toBeLessThanOrEqual(artBox.x + 1);
  for (const metric of metrics) {
    await expect(metric).toBeVisible();
    const metricBox = await box(metric);
    expect(metricBox.y, 'weather details follow the description').toBeGreaterThanOrEqual(
      descriptionBox.y + descriptionBox.height - 1
    );
    expect(metricBox.x, 'weather details start in the text column').toBeGreaterThanOrEqual(
      descriptionBox.x - 1
    );
    expect(
      metricBox.x + metricBox.width,
      'weather details never cover the illustration'
    ).toBeLessThanOrEqual(artBox.x + 1);
  }
}

async function assertAgendaRanges(page: Page, locale: Locale) {
  const agenda = briefingCard(page, 'agenda', locale);
  const first = agenda.getByRole('listitem').filter({
    has: page.getByText(homeItemName('agenda', 0), { exact: true }),
  });
  await expect(first.getByText('aujourd’hui 09:00 – 09:30', { exact: true })).toHaveCount(1);
  await expect(first.getByText('09:30', { exact: true })).toHaveCount(0);
  const tomorrow = agenda.getByRole('listitem').filter({
    has: page.getByText(homeItemName('agenda', 5), { exact: true }),
  });
  await expect(tomorrow.getByText('demain 09:00 – 09:30', { exact: true })).toHaveCount(1);
  // A cached payload with no new field still renders both old values.
  const legacy = agenda.getByRole('listitem').filter({
    has: page.getByText(homeItemName('agenda', HOME_CAPS.agenda - 1), { exact: true }),
  });
  await expect(legacy.getByText('13:00', { exact: true })).toHaveCount(1);
  await expect(legacy.getByText('13:30', { exact: true })).toHaveCount(1);
}

/** Label wrapping must not move a count relative to the other cells in its row. */
async function assertWorkboardFigureAlignment(page: Page, locale: Locale, width: number) {
  const figures = briefingCard(page, 'workboard', locale)
    .getByRole('list', { name: translated(locale, 'settings.workboard.glance'), exact: true })
    .getByRole('listitem');
  await expect(figures).toHaveCount(5);
  const cells = await figures.evaluateAll(items =>
    items.map(item => {
      const link = item.querySelector('a');
      const value = link?.firstElementChild;
      const label = link?.lastElementChild;
      if (!value || !label) throw new Error('Workboard figure needs its value and label');
      const range = document.createRange();
      range.selectNodeContents(label);
      const lines: number[] = [];
      for (const rect of range.getClientRects()) {
        if (rect.width > 0 && !lines.some(top => Math.abs(top - rect.top) <= 1))
          lines.push(rect.top);
      }
      return {
        top: item.getBoundingClientRect().top,
        numberTop: value.getBoundingClientRect().top,
        labelLines: lines.length,
      };
    })
  );
  const rows: (typeof cells)[] = [];
  for (const cell of cells) {
    const row = rows.find(group => Math.abs(group[0].top - cell.top) <= 1);
    if (row) row.push(cell);
    else rows.push([cell]);
  }
  const rowSizes = rows.map(row => row.length);
  expect(
    [[2, 2, 1], [5]],
    'the five counts keep a complete two- or five-column grid'
  ).toContainEqual(rowSizes);
  // At 390px the card can straddle its container breakpoint depending on
  // native scrollbar width. The narrowest viewport must still use two columns.
  if (width === 320) expect(rowSizes).toEqual([2, 2, 1]);
  if (width >= 1280) {
    expect(rowSizes).toEqual([5]);
    expect(
      rows[0].some(cell => cell.labelLines === 1),
      'the alignment sample has a one-line label'
    ).toBe(true);
    expect(
      rows[0].some(cell => cell.labelLines >= 2),
      'the alignment sample also has a wrapped label'
    ).toBe(true);
  }
  for (const row of rows) {
    const tops = row.map(cell => cell.numberTop);
    expect(
      Math.max(...tops) - Math.min(...tops),
      'numbers start at the same height within each row'
    ).toBeLessThanOrEqual(1);
  }
}

/** Inspect the painted card grounds and keep the home override outside global chrome. */
async function assertHomeCardPalette(
  page: Page,
  locale: Locale,
  theme: Theme,
  hero: Locator,
  radio: Locator
) {
  const main = page.getByRole('main');
  // Both home rubriques are sections named by their heading, never folded
  // (owner request 2026-10-21): their tiles are the children of their grids.
  const results = main
    .getByRole('region', { name: translated(locale, 'dashboard.results.title'), exact: true })
    .locator(':scope > div.grid > div');
  await expect(results).toHaveCount(4);
  const consumption = main.getByRole('table', {
    name: translated(locale, 'dashboard.statistics.consumption_title'),
    exact: true,
  });
  const limits = main
    .getByRole('region', {
      name: translated(locale, 'dashboard.statistics.consumption_title'),
      exact: true,
    })
    .locator(':scope > div.space-y-4 > div:last-child > div');
  const frames = [
    ...HOME_ORDER.map(name => briefingCard(page, name, locale)),
    hero,
    radio,
    ...Array.from({ length: 4 }, (_, index) => results.nth(index)),
    consumption.locator('xpath=ancestor::div[2]'),
    ...Array.from({ length: await limits.count() }, (_, index) => limits.nth(index)),
  ];
  for (const frame of frames) await expect(frame).toHaveCount(1);
  await expect
    .poll(
      async () => {
        const colors = await Promise.all(
          frames.map(frame => frame.evaluate(element => getComputedStyle(element).backgroundColor))
        );
        return {
          sample: colors.every(color => color === 'rgb(13, 26, 34)'),
          uniform: new Set(colors).size === 1,
        };
      },
      { message: 'all home card frames share the real dark sample, with light and OLED preserved' }
    )
    .toEqual({ sample: theme === 'dark', uniform: true });
  const home = main
    .locator(':scope > div')
    .filter({ has: page.getByRole('heading', { level: 1 }) });
  await expect(home).toHaveCount(1);
  const localCard = await home.evaluate(element =>
    getComputedStyle(element).getPropertyValue('--color-card').trim()
  );
  const outside = await page.getByRole('banner').evaluate(header => ({
    rootCard: getComputedStyle(document.documentElement).getPropertyValue('--color-card').trim(),
    headerCard: getComputedStyle(header).getPropertyValue('--color-card').trim(),
  }));
  expect(outside.rootCard).not.toBe('');
  expect(outside.headerCard, 'the shared header retains the global card palette').toBe(
    outside.rootCard
  );
  if (theme === 'dark')
    expect(localCard, 'the night sample belongs to home only').not.toBe(outside.rootCard);
  else expect(localCard, 'light and OLED retain their global card palette').toBe(outside.rootCard);
}

async function assertEveryReceivedItem(page: Page, locale: Locale) {
  for (const name of Object.keys(HOME_CAPS) as (keyof typeof HOME_CAPS)[]) {
    if (name === 'workboard') continue;
    const card = briefingCard(page, name, locale);
    const scroll = card.getByRole('group', {
      name: translated(locale, `dashboard.briefing.cards.${name}.title`),
      exact: true,
    });
    await expect(scroll).toHaveAttribute('tabindex', '0');
    for (let index = 0; index < HOME_CAPS[name]; index++) {
      await expect(scroll.getByText(homeItemName(name, index), { exact: false })).toHaveCount(1);
    }
    const received =
      name === 'agenda'
        ? scroll.getByRole('listitem')
        : scroll.getByRole('list').first().getByRole('listitem');
    await expect(received).toHaveCount(HOME_CAPS[name]);
    const last = received.last();
    await last.scrollIntoViewIfNeeded();
    await expect(last, `${name}: the full last received row is reachable`).toBeInViewport({
      ratio: 0.99,
    });
    await expect
      .poll(() => scroll.evaluate(element => element.scrollWidth - element.clientWidth), {
        message: `${name}: its content must not require horizontal scrolling`,
      })
      .toBeLessThanOrEqual(1);
  }
  const forecastDays = briefingCard(page, 'weather', locale).getByRole('listitem');
  await expect(forecastDays).toHaveCount(5);
  await forecastDays.last().scrollIntoViewIfNeeded();
  await expect(forecastDays.last()).toBeInViewport({ ratio: 0.99 });
  const health = briefingCard(page, 'health', locale);
  await expect(health.getByRole('listitem')).toHaveCount(2);
  // The native health presentation separates the large value and its unit/
  // period line. Measure both real boxes, never the display:contents <li>.
  const heart = health.getByRole('listitem').last();
  const finalMetric = heart.getByText('72', { exact: true });
  const unit = heart.getByText(
    `bpm · ${translated(locale, 'dashboard.briefing.cards.health.avg_window').replace('{{window}}', '14')}`,
    { exact: true }
  );
  // Read the actual final line through the card's native keyboard scroll.
  // scrollIntoViewIfNeeded tolerates subpixel clipping; End must expose all text.
  const healthScroll = health.getByRole('group', {
    name: translated(locale, 'dashboard.briefing.cards.health.title'),
    exact: true,
  });
  const hasHealthOverflow = await healthScroll.evaluate(
    element => element.scrollHeight > element.clientHeight
  );
  // End on a non-overflowing group scrolls the document in Firefox.
  if (hasHealthOverflow) {
    await healthScroll.focus();
    await healthScroll.press('End');
  }
  await unit.scrollIntoViewIfNeeded();
  await expect(finalMetric).toBeInViewport({ ratio: 0.99 });
  await expect(unit).toBeInViewport({ ratio: 0.99 });
  await expect(briefingCard(page, 'mails', locale).getByText('42', { exact: true })).toHaveCount(1);
  const boardFigures = briefingCard(page, 'workboard', locale)
    .getByRole('list')
    .first()
    .getByRole('listitem');
  await expect(boardFigures).toHaveCount(5);
  await expect(boardFigures.nth(2).getByRole('link')).toHaveAttribute(
    'href',
    /[?&]assignee=peer(?:&|$)/
  );
  // Exact aggregates stay independent of their bounded two-title previews.
  for (const [index, group] of HOME_WORKBOARD_GROUPS.entries()) {
    await expect(boardFigures.nth(index).getByRole('link').locator('span').first()).toHaveText(
      String(group.count)
    );
  }
  await assertWorkboardPreviews(page, locale);
}

async function assertWorkboardPreviews(page: Page, locale: Locale) {
  const card = briefingCard(page, 'workboard', locale);
  await expect(card.getByRole('heading', { level: 4 })).toHaveCount(5);
  for (const group of HOME_WORKBOARD_GROUPS) {
    const label = translated(locale, group.labelKey);
    await expect(card.getByRole('heading', { level: 4, name: label, exact: true })).toHaveCount(1);
    const list = card.getByRole('list', { name: label, exact: true });
    const titles = list.getByRole('link');
    await expect(titles).toHaveCount(2);
    for (let index = 0; index < 2; index += 1) {
      const title = titles.nth(index);
      const name = homeWorkboardPreviewName(group.key, index);
      await expect(title.getByText(name, { exact: true })).toBeVisible();
      await expect(title).toHaveAccessibleName(new RegExp(escapePattern(name)));
      await expect(title).toContainText(
        translated(
          locale,
          group.key === 'overdue' ? 'workboard.card.overdue' : 'workboard.columns.waiting'
        )
      );
      await expect(title).toHaveAttribute(
        'href',
        `/${locale}/dashboard/workboard/preview-${group.key}-${index}`
      );
      await title.scrollIntoViewIfNeeded();
      await expect(title).toBeInViewport({ ratio: 0.99 });
      await title.focus();
      await expect(title).toBeFocused();
      if (group.key === 'held_by_lia' && index === 0) {
        await expect(title.locator('time')).toHaveAttribute('datetime', '2026-10-16T09:45:00Z');
        await expect(title.locator('time')).toBeVisible();
      }
    }
  }
  for (let index = 0; index < HOME_CAPS.workboard; index += 1) {
    await expect(
      card.getByText(homeItemName('workboard', index), { exact: true }),
      'the legacy page is not duplicated below the previews'
    ).toHaveCount(0);
  }
}

interface MeasuredRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

const healthVisibility = new WeakMap<Page, object[]>();

/** Read the values through their unit/period labels; colour never substitutes for data. */
async function assertHealthReading(page: Page, locale: Locale, data: HealthData) {
  const card = briefingCard(page, 'health', locale);
  const colors: string[] = [];
  await expect(card.getByRole('listitem')).toHaveCount(data.items.length);
  for (const [index, item] of data.items.entries()) {
    const metric = card.getByRole('listitem').nth(index);
    const unit = translated(locale, `dashboard.briefing.cards.health.unit_${item.kind}`);
    const todayLabel = `${unit} · ${translated(locale, 'dashboard.briefing.cards.health.today')}`;
    const averageLabel = `${unit} · ${translated(locale, 'dashboard.briefing.cards.health.avg_window').replace('{{window}}', String(item.window_days))}`;
    const text = (value: number | null) =>
      value === null ? '—' : new Intl.NumberFormat(locale).format(value);
    const today = metric
      .getByText(todayLabel, { exact: true })
      .locator('..')
      .getByText(text(item.value_today), { exact: true });
    const average = metric
      .getByText(averageLabel, { exact: true })
      .locator('..')
      .getByText(text(item.value_avg_window), { exact: true });
    await expect(today).toHaveText(text(item.value_today));
    await expect(average).toHaveText(text(item.value_avg_window));
    await expect(metric.getByText(todayLabel, { exact: true })).toBeVisible();
    await expect(metric.getByText(averageLabel, { exact: true })).toBeVisible();
    for (const label of [
      today,
      average,
      metric.getByText(todayLabel, { exact: true }),
      metric.getByText(averageLabel, { exact: true }),
    ]) {
      await label.scrollIntoViewIfNeeded();
      const geometry = await label.evaluate(
        element =>
          new Promise<{
            text: string;
            isIntersecting: boolean;
            ratio: number;
            bounds: MeasuredRect;
            intersection: MeasuredRect;
            textRects: MeasuredRect[];
            clippingBounds: MeasuredRect;
            clippingAncestors: {
              tag: string;
              overflowX: string;
              overflowY: string;
              bounds: MeasuredRect;
            }[];
          }>(resolve => {
            const rect = (value: DOMRectReadOnly): MeasuredRect => ({
              left: value.left,
              top: value.top,
              right: value.right,
              bottom: value.bottom,
              width: value.width,
              height: value.height,
            });
            const observer = new IntersectionObserver(([entry]) => {
              const range = document.createRange();
              range.selectNodeContents(element);
              let left = 0;
              let top = 0;
              let right = window.innerWidth;
              let bottom = window.innerHeight;
              const clippingAncestors: {
                tag: string;
                overflowX: string;
                overflowY: string;
                bounds: MeasuredRect;
              }[] = [];
              for (let parent = element.parentElement; parent; parent = parent.parentElement) {
                // Root overflow clips the viewport, already bounded above;
                // its document-scrolled rectangle is not another clip box.
                if (parent === document.documentElement) continue;
                const style = getComputedStyle(parent);
                const clipsX = /^(auto|scroll|hidden|clip)$/.test(style.overflowX);
                const clipsY = /^(auto|scroll|hidden|clip)$/.test(style.overflowY);
                if (!clipsX && !clipsY) continue;
                const bounds = parent.getBoundingClientRect();
                const clientLeft = bounds.left + parent.clientLeft;
                const clientTop = bounds.top + parent.clientTop;
                const clientRight = clientLeft + parent.clientWidth;
                const clientBottom = clientTop + parent.clientHeight;
                if (clipsX) {
                  left = Math.max(left, clientLeft);
                  right = Math.min(right, clientRight);
                }
                if (clipsY) {
                  top = Math.max(top, clientTop);
                  bottom = Math.min(bottom, clientBottom);
                }
                clippingAncestors.push({
                  tag: parent.tagName.toLowerCase(),
                  overflowX: style.overflowX,
                  overflowY: style.overflowY,
                  bounds: {
                    left: clientLeft,
                    top: clientTop,
                    right: clientRight,
                    bottom: clientBottom,
                    width: parent.clientWidth,
                    height: parent.clientHeight,
                  },
                });
              }
              observer.disconnect();
              resolve({
                text: element.textContent ?? '',
                isIntersecting: entry.isIntersecting,
                ratio: entry.intersectionRatio,
                bounds: rect(entry.boundingClientRect),
                intersection: rect(entry.intersectionRect),
                textRects: Array.from(range.getClientRects(), rect),
                clippingBounds: {
                  left,
                  top,
                  right,
                  bottom,
                  width: right - left,
                  height: bottom - top,
                },
                clippingAncestors,
              });
            });
            observer.observe(element);
          })
      );
      const clippedEdges = (rect: MeasuredRect, clip: MeasuredRect) => ({
        left: Math.max(0, clip.left - rect.left),
        top: Math.max(0, clip.top - rect.top),
        right: Math.max(0, rect.right - clip.right),
        bottom: Math.max(0, rect.bottom - clip.bottom),
      });
      const boxEdgeErrors = clippedEdges(geometry.bounds, geometry.intersection);
      const textEdgeErrors = geometry.textRects.map(rect =>
        clippedEdges(rect, geometry.clippingBounds)
      );
      // Range includes font ascent/descent, not painted ink. Preserve its
      // clipping as diagnostics; assert the observed element box below.
      const samples = healthVisibility.get(page) ?? [];
      samples.push({ kind: item.kind, ...geometry, boxEdgeErrors, textEdgeErrors });
      healthVisibility.set(page, samples);
      expect(geometry.isIntersecting, `${item.kind}: ${geometry.text} intersects`).toBe(true);
      expect(geometry.intersection.width).toBeGreaterThan(0);
      expect(geometry.intersection.height).toBeGreaterThan(0);
      expect(geometry.clippingBounds.width).toBeGreaterThan(0);
      expect(geometry.clippingBounds.height).toBeGreaterThan(0);
      expect(geometry.textRects.length).toBeGreaterThan(0);
      for (const rect of [geometry.bounds, ...geometry.textRects]) {
        expect(rect.width).toBeGreaterThan(0);
        expect(rect.height).toBeGreaterThan(0);
      }
      // WebKit can round a native scroll edge by a fraction of a CSS pixel.
      // Bound each observed box edge; a ratio depends on the label's height
      // and overstates that same subpixel difference.
      for (const [edge, error] of Object.entries(boxEdgeErrors)) {
        expect(error, `${item.kind}: ${geometry.text}, clipped ${edge} edge`).toBeLessThanOrEqual(
          1
        );
      }
    }
    const separator = metric.locator(':scope > [aria-hidden="true"]');
    await expect(separator).toHaveCount(1);
    const painted = await Promise.all([box(today), box(average), box(separator)]);
    for (let first = 0; first < painted.length; first += 1) {
      for (let second = first + 1; second < painted.length; second += 1) {
        const a = painted[first],
          b = painted[second];
        const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
        const overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
        expect(
          overlapX > 1 && overlapY > 1,
          `${item.kind}: today, average and separator do not overlap`
        ).toBe(false);
      }
    }
    const todayStyle = await today.evaluate(element => ({
      font: parseFloat(getComputedStyle(element).fontSize),
      color: getComputedStyle(element).color,
    }));
    const averageFont = await average.evaluate(element =>
      parseFloat(getComputedStyle(element).fontSize)
    );
    expect(todayStyle.font, 'today remains visually larger than its average').toBeGreaterThan(
      averageFont
    );
    colors.push(todayStyle.color);
  }
  return colors;
}

async function assertConsumption(page: Page, locale: Locale) {
  const table = page.getByRole('table', {
    name: translated(locale, 'dashboard.statistics.consumption_title'),
    exact: true,
  });
  await expect(table).toBeVisible();
  await expect(table.getByRole('columnheader')).toHaveText([
    translated(locale, 'dashboard.statistics.consumption_title'),
    translated(locale, 'dashboard.statistics.period'),
    translated(locale, 'dashboard.statistics.total'),
  ]);
  // Preserve the existing application's shared-format convention: both
  // formatNumber and formatEuro default to French on this readout, even in DE.
  const number = (value: number) =>
    new Intl.NumberFormat('fr-FR').format(value).replace(/[\u202f\u00a0]/g, ' ');
  const money = (value: number) =>
    new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
      .format(value)
      .replace(/[\u202f\u00a0]/g, ' ');
  const rows: [string, string, string][] = [
    [
      'messages.title',
      number(HOME_STATISTICS.cycle_messages),
      number(HOME_STATISTICS.total_messages),
    ],
    ['tokens.title', number(1600), number(16000)],
    ['prompt_tokens', number(1200), number(12000)],
    ['completion_tokens', number(300), number(3000)],
    ['cached_tokens', number(100), number(1000)],
    ['google_api.title', number(8), number(108)],
    ['google_api_cost', money(0.12), money(1.23)],
    ['cost.title', money(2.34), money(23.45)],
  ];
  for (const [key, period, total] of rows) {
    const row = table.getByRole('row').filter({
      has: page.getByRole('rowheader', {
        name: translated(locale, `dashboard.statistics.${key}`),
        exact: true,
      }),
    });
    await expect(row.getByRole('cell')).toHaveText([period, total]);
  }
}

test.use({ timezoneId: 'Asia/Tokyo' });

// The base fixture's 501/transport guard is the authority; also make any caught
// API degradation fail this journey rather than quietly scanning its fallback.
const unexpectedApi = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  if (process.env.E2E_HOME_CLEAN_CAPTURES === '1') {
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: false }, version: 0 })
      );
    });
  }
  const failures: string[] = [];
  unexpectedApi.set(page, failures);
  page.on('response', response => {
    if (response.status() === 501 && response.url().includes('/api/v1/'))
      failures.push(response.url());
  });
  await page.clock.setFixedTime(new Date(HOME_NOW));
});
test.afterEach(async ({ page }, testInfo) => {
  const samples = healthVisibility.get(page);
  if (samples?.length) {
    await testInfo.attach('health-intersections', {
      body: Buffer.from(JSON.stringify(samples, null, 2)),
      contentType: 'application/json',
    });
  }
  expect(unexpectedApi.get(page) ?? [], 'every API read must have an explicit mock').toEqual([]);
});

for (const sample of [
  { width: 320, locale: 'fr', theme: 'light', font: 16 },
  { width: 320, locale: 'de', theme: 'oled', font: 20 },
  { width: 390, locale: 'fr', theme: 'dark', font: 16 },
  { width: 768, locale: 'de', theme: 'oled', font: 16 },
  { width: 1024, locale: 'de', theme: 'light', font: 20 },
  { width: 1440, locale: 'fr', theme: 'dark', font: 16 },
] satisfies { width: number; locale: Locale; theme: Theme; font: number }[]) {
  test(`home geometry and full received pages @ ${sample.width}px ${sample.locale} ${sample.theme} ${sample.font}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width: sample.width, height: 1000 });
    await prepareTheme(page, sample.theme);
    const user = await authenticate({
      language: sample.locale,
      timezone: HOME_TIMEZONE,
      theme: sample.theme,
      font_size: sample.font,
    });
    await mockApi(homeRoutes(user));
    await readyHome(page, sample.locale);
    const headingStyle = (heading: Locator) =>
      heading.evaluate(element => {
        const style = getComputedStyle(element);
        return {
          fontSize: style.fontSize,
          lineHeight: style.lineHeight,
          fontWeight: style.fontWeight,
          letterSpacing: style.letterSpacing,
        };
      });
    const shortcutHeading = page.getByRole('heading', {
      level: 2,
      name: translated(sample.locale, 'dashboard.quick_access_compact.title'),
      exact: true,
    });
    const dashboardHeading = page.getByRole('heading', {
      level: 2,
      name: translated(sample.locale, 'dashboard.briefing.section_title'),
      exact: true,
    });
    expect(await headingStyle(shortcutHeading)).toEqual(await headingStyle(dashboardHeading));

    await expect(page.locator('html')).toHaveClass(
      sample.theme === 'light' ? /^(?!.*\bdark\b)/ : /\bdark\b/
    );
    await expect(page.locator('html[data-oled]')).toHaveCount(sample.theme === 'oled' ? 1 : 0);
    // FontProvider scales text only: --text-base is 1rem * --lia-text-scale,
    // with fontSizeScale(px)=px/16. The root rem deliberately remains 16px so
    // icons, spacing and fixed card boxes keep their dimensions. Verify both
    // the published scale and its effect on a real text-base card heading.
    await expect
      .poll(() =>
        page.evaluate(
          cssVar =>
            Number(
              getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim() || '1'
            ),
          FONT_SIZE_CSS_VAR
        )
      )
      .toBe(fontSizeScale(sample.font));
    await expect
      .poll(() =>
        briefingCard(page, 'agenda', sample.locale)
          .getByRole('heading', { level: 3 })
          .evaluate(heading => parseFloat(getComputedStyle(heading).fontSize))
      )
      .toBe(sample.font);
    const expectedDate = pageDate(HOME_NOW, sample.locale, HOME_TIMEZONE);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(expectedDate);

    const agenda = briefingCard(page, 'agenda', sample.locale);
    const days = agenda.getByRole('heading', { level: 4 });
    await expect(days).toHaveText([
      civilDate('2026-10-15T19:00:00Z', sample.locale, HOME_TIMEZONE),
      civilDate('2026-10-16T19:00:00Z', sample.locale, HOME_TIMEZONE),
    ]);
    if (sample.width >= 1024) {
      const weatherBox = await box(briefingCard(page, 'weather', sample.locale));
      expect(
        (await box(agenda)).width,
        'agenda retains its two-column desktop timeline'
      ).toBeGreaterThan(weatherBox.width * 1.8);
    }

    const main = page.getByRole('main');
    const chat = main.getByRole('link', {
      name: translated(sample.locale, 'dashboard.actions.open_chat'),
      exact: true,
    });
    const services = main.getByRole('link', {
      name: translated(sample.locale, 'dashboard.actions.services'),
      exact: true,
    });
    const shortcuts = main.getByRole('navigation', {
      name: translated(sample.locale, 'dashboard.quick_access_compact.title'),
      exact: true,
    });
    const radio = main.getByRole('heading', { name: 'Hermetic Home Radio', exact: true });
    await expect(radio, 'one station card is mounted on home').toHaveCount(1);
    const radioFrame = radio.locator('xpath=ancestor::div[4]');
    const radioAction = radioFrame.getByRole('button', {
      name: translated(sample.locale, 'radio.header.start'),
      exact: true,
    });
    const [chatBox, servicesBox, shortcutsBox, radioBox, dateBox] = await Promise.all([
      box(chat),
      box(services),
      box(shortcuts),
      box(radioFrame),
      box(main.getByRole('heading', { level: 1 })),
    ]);
    expect(chatBox.y + chatBox.height).toBeLessThanOrEqual(servicesBox.y + 1);
    expect(servicesBox.y + servicesBox.height).toBeLessThanOrEqual(shortcutsBox.y + 1);
    expect(dateBox.y + dateBox.height).toBeLessThanOrEqual(radioBox.y + 1);
    expect(servicesBox.y + servicesBox.height).toBeLessThanOrEqual(radioBox.y + 1);
    expect(radioBox.y + radioBox.height).toBeLessThanOrEqual(shortcutsBox.y + 1);
    const radioActionBox = await box(radioAction);
    expect(
      Math.abs(radioActionBox.width - servicesBox.width),
      'radio and Services have the same width'
    ).toBeLessThanOrEqual(1);
    expect(
      Math.abs(radioActionBox.height - servicesBox.height),
      'radio and Services have the same height'
    ).toBeLessThanOrEqual(1);
    expect(radioActionBox.height).toBeGreaterThanOrEqual(44);
    expect(
      await radioFrame.evaluate(
        (element, greeting) =>
          element.previousElementSibling?.textContent?.includes(greeting) ?? false,
        HOME_GREETING
      ),
      'the station sits immediately after the welcome message'
    ).toBe(true);
    if (sample.width < 1024) {
      expect(Math.abs(chatBox.x - servicesBox.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(chatBox.width - servicesBox.width)).toBeLessThanOrEqual(1);
      expect(chatBox.width, 'both hero actions use the available mobile width').toBeGreaterThan(
        sample.width * 0.65
      );
    }
    await expect(main.getByText(HOME_SYNTHESIS, { exact: true })).toBeVisible();
    const synthesis = main.getByRole('region', {
      name: translated(sample.locale, 'dashboard.briefing.synthesis_title'),
      exact: true,
    });
    await expect(synthesis.getByRole('button', { expanded: true })).toBeVisible();
    await expect(synthesis).toHaveCount(1);
    await expect(
      synthesis.getByRole('heading', {
        level: 3,
        name: translated(sample.locale, 'dashboard.briefing.synthesis_title'),
        exact: true,
      })
    ).toBeVisible();
    const hero = main
      .getByText(HOME_GREETING, { exact: true })
      .locator('xpath=ancestor::div[.//a[contains(@href, "/dashboard/chat")]][1]');
    const heroFrame = hero.locator('../..');
    await expect(
      heroFrame.getByText(HOME_SYNTHESIS, { exact: true }),
      'the daily point no longer belongs to the welcome card'
    ).toHaveCount(0);
    const heroBox = await box(heroFrame);
    expect(dateBox.y + dateBox.height).toBeLessThanOrEqual(heroBox.y + 1);
    expect(heroBox.y + heroBox.height).toBeLessThanOrEqual(radioBox.y + 1);
    const pointBox = await box(synthesis);
    const commands = [
      dashboardHeading,
      briefingRegion(page, sample.locale).getByRole('link', {
        name: translated(sample.locale, 'dashboard.briefing.customize'),
        exact: true,
      }),
      briefingRegion(page, sample.locale).getByRole('button', {
        name: translated(sample.locale, 'dashboard.briefing.refresh_all'),
        exact: true,
      }),
    ];
    for (const command of commands) {
      const commandBox = await box(command);
      expect(
        commandBox.y + commandBox.height,
        'dashboard heading and commands precede the daily point'
      ).toBeLessThanOrEqual(pointBox.y + 1);
    }
    const firstCardBox = await box(briefingCard(page, 'weather', sample.locale));
    expect(
      pointBox.y + pointBox.height,
      'the daily point precedes the first briefing card'
    ).toBeLessThanOrEqual(firstCardBox.y + 1);
    const audio = synthesis.getByRole('button', {
      name: translated(sample.locale, 'dashboard.briefing.synthesis_listen'),
      exact: true,
    });
    const audioOwner = await audio.elementHandle();
    const collapse = synthesis.locator('button[aria-controls]');
    await expect(collapse).toHaveAttribute('aria-expanded', 'true');
    await collapse.focus();
    await collapse.press('Enter');
    await expect(collapse).toBeFocused();
    await expect(synthesis.getByText(HOME_SYNTHESIS, { exact: true })).toBeHidden();
    await expect(audio).toHaveCount(1);
    expect(
      await audioOwner!.evaluate(element => element.isConnected),
      'folding keeps the audio control mounted'
    ).toBe(true);
    await expect(collapse).toHaveAttribute('aria-expanded', 'false');
    await collapse.press('Enter');
    await expect(synthesis.getByText(HOME_SYNTHESIS, { exact: true })).toBeVisible();
    expect(await audioOwner!.evaluate(element => element.isConnected)).toBe(true);
    expect(
      (await box(hero)).height,
      'the welcome remains compact at the chosen text size'
    ).toBeLessThan(((sample.width < 640 ? 650 : 470) * sample.font) / 16);
    for (const title of ['dashboard.results.title', 'dashboard.statistics.consumption_title']) {
      // A rubrique of the home page, never folded (owner request 2026-10-21):
      // a region named by its own level-2 heading, with nothing to toggle.
      const name = translated(sample.locale, title);
      const region = main.getByRole('region', { name, exact: true });
      await expect(region, 'home rubriques are always laid out').toBeVisible();
      await expect(region.getByRole('heading', { level: 2, name, exact: true })).toBeVisible();
      await expect(region.locator('details, summary')).toHaveCount(0);
    }

    await assertHeaderGeometry(page, sample.locale, sample.width);
    if (sample.width >= 1024) {
      const heights = await briefingCards(page, sample.locale).evaluateAll(cards =>
        cards.map(card => card.getBoundingClientRect().height)
      );
      expect(
        Math.max(...heights) - Math.min(...heights),
        'desktop cards have equal height'
      ).toBeLessThanOrEqual(1);
    }
    await assertEveryReceivedItem(page, sample.locale);
    await assertAgendaRanges(page, sample.locale);
    await assertWeatherComposition(page, sample.locale);
    await assertConsumption(page, sample.locale);
    await assertWorkboardFigureAlignment(page, sample.locale, sample.width);
    await assertHomeCardPalette(page, sample.locale, sample.theme, heroFrame, radioFrame);
    await expectNoOverflow(page, `home ${sample.width}px ${sample.locale} ${sample.theme}`);
    // Scan the initial rows too: overdue tasks have a different semantic tone
    // from the final rows reached by the complete-page scrolling assertions.
    await briefingRegion(page, sample.locale)
      .getByRole('group')
      .evaluateAll(areas => {
        for (const area of areas) area.scrollTop = 0;
      });
    await main.getByRole('heading', { level: 1 }).scrollIntoViewIfNeeded();
    const accessibility = await scanPage(
      page,
      testInfo,
      `home-${sample.width}-${sample.locale}-${sample.theme}-${sample.font}`
    );
    expect(accessibility.blocking, accessibility.summary).toEqual([]);
    if (process.env.E2E_HOME_CAPTURE_DIR) {
      const folder = path.resolve(process.env.E2E_HOME_CAPTURE_DIR);
      await mkdir(folder, { recursive: true });
      const prefix = `home-${sample.width}-${sample.locale}-${sample.theme}-${sample.font}-${testInfo.project.name}`;
      const capture = async (name: string, target?: Locator, fullPage = false) => {
        const file = path.join(folder, `${prefix}-${name}.png`);
        if (target) await target.screenshot({ path: file });
        else await page.screenshot({ path: file, fullPage });
        await testInfo.attach(`home-${name}`, { path: file, contentType: 'image/png' });
      };
      await capture('layout', undefined, true);
      await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
      await capture('top');
      for (const section of ['weather', 'agenda', 'mails', 'workboard'] as const) {
        await capture(section, briefingCard(page, section, sample.locale));
      }
      if (sample.width >= 1024) await capture('grid', briefingRegion(page, sample.locale));
    }
  });
}

/** A lone card is re-read on its own route (spec 2026-10-21 §5.8), one section back. */
const CARD_REFRESH = /\/api\/v1\/briefing\/sections\/[a-z_]+\/refresh$/;
function refreshedSection(route: Route): BriefingSection {
  return new URL(route.request().url()).pathname.split('/').at(-2) as BriefingSection;
}

test('a card refresh preserves its scroll area, keyboard focus and visible data', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
  await mockApi(homeRoutes(user));
  let release!: () => void;
  const gate = new Promise<void>(resolve => {
    release = resolve;
  });
  const requests: unknown[] = [];
  await mockApi([
    {
      url: CARD_REFRESH,
      method: 'POST',
      handler: async (route, signal) => {
        requests.push({ sections: [refreshedSection(route)] });
        if (!(await waitForMockGate(gate, signal))) return;
        await route.fulfill({ json: refreshedAgenda().cards[refreshedSection(route)] });
      },
    },
  ]);
  await readyHome(page, 'fr');
  const card = briefingCard(page, 'agenda', 'fr');
  const scroll = card.getByRole('group', {
    name: translated('fr', 'dashboard.briefing.cards.agenda.title'),
    exact: true,
  });
  await scroll.focus();
  await scroll.press('End');
  // Firefox's native End scroll continues after the key event. Observe its
  // final position before measuring whether a refresh moves the reader.
  let previousTop: number | undefined;
  await expect
    .poll(
      async () => {
        const top = await scroll.evaluate(element => element.scrollTop);
        const settled = top > 0 && top === previousTop;
        previousTop = top;
        return settled;
      },
      { intervals: [50, 100, 200] }
    )
    .toBe(true);
  const scrollHandle = await scroll.elementHandle();
  const refresh = refreshControl(card, 'agenda', 'fr');
  await refresh.focus();
  const before = await scroll.evaluate(element => element.scrollTop);
  const pageBefore = await page.evaluate(() => window.scrollY);
  try {
    await refresh.press('Enter');
    await expect(card).toHaveAttribute('aria-busy', 'true');
    await expect(refresh).toBeFocused();
    await expect(refresh).toHaveAttribute('aria-disabled', 'true');
    await expect(scroll.getByRole('listitem')).toHaveCount(HOME_CAPS.agenda);
    await expect(scroll.getByText(UPDATED_AGENDA_TITLE, { exact: true })).toHaveCount(0);
    await refresh.press('Enter');
    expect(requests).toEqual([{ sections: ['agenda'] }]);
    expect(await scroll.evaluate(element => element.scrollTop)).toBeCloseTo(before, 0);
    expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(pageBefore, 0);
  } finally {
    release();
  }
  await expect(card).toHaveAttribute('aria-busy', 'false');
  await expect(refresh).toBeFocused();
  await assertRefreshedAgendaPage(scroll);
  expect(await scrollHandle!.evaluate(element => element.isConnected)).toBe(true);
  // At the end, a shorter replacement title reduces the available scroll range.
  // Keep the exact offset when possible, otherwise the browser's new end.
  const afterScroll = await scroll.evaluate(element => ({
    top: element.scrollTop,
    max: element.scrollHeight - element.clientHeight,
  }));
  expect(afterScroll.top).toBeCloseTo(Math.min(before, afterScroll.max), 0);
  expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(pageBefore, 0);
  expect(requests).toEqual([{ sections: ['agenda'] }]);
});

test('network error retains its stale page and Retry refreshes cards once without navigation', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
  const stale = homeBriefing();
  stale.cards.mails = {
    ...stale.cards.mails,
    status: 'error',
    error_code: 'connector_network',
    error_message: 'Le service de messagerie est temporairement indisponible.',
    stale_generated_at: '2026-10-15T21:00:00Z',
    last_attempt_at: HOME_GENERATED,
  };
  await mockApi(homeRoutes(user, stale));
  let release!: () => void;
  const gate = new Promise<void>(resolve => {
    release = resolve;
  });
  const requests: unknown[] = [];
  await mockApi([
    {
      url: CARD_REFRESH,
      method: 'POST',
      handler: async (route, signal) => {
        requests.push({ sections: [refreshedSection(route)] });
        if (!(await waitForMockGate(gate, signal))) return;
        await route.fulfill({ json: homeBriefing().cards[refreshedSection(route)] });
      },
    },
  ]);
  await readyHome(page, 'fr');
  const homeUrl = page.url(); // The default locale may canonicalize to /dashboard.
  const card = briefingCard(page, 'mails', 'fr');
  const list = card.getByRole('list');
  await expect(list.getByRole('listitem')).toHaveCount(HOME_CAPS.mails);
  await expect(card.locator('time')).toHaveAttribute(
    'datetime',
    stale.cards.mails.stale_generated_at!
  );
  const retry = card.getByRole('button', {
    name: translated('fr', 'dashboard.briefing.actions.retry'),
    exact: true,
  });
  try {
    await retry.focus();
    await retry.press('Enter');
    await expect(card).toHaveAttribute('aria-busy', 'true');
    await expect(retry).toBeFocused();
    await expect(list.getByRole('listitem')).toHaveCount(HOME_CAPS.mails);
    await retry.press('Enter');
    await expect(page).toHaveURL(homeUrl);
    expect(requests).toEqual([{ sections: ['mails'] }]);
  } finally {
    release();
  }
  await expect(card).toHaveAttribute('aria-busy', 'false');
  await expect(card.getByText(stale.cards.mails.error_message!)).toHaveCount(0);
  await expect(refreshControl(card, 'mails', 'fr')).toBeFocused();
  await expect(list.getByRole('listitem')).toHaveCount(HOME_CAPS.mails);
  await expect(page).toHaveURL(homeUrl);
  expect(requests).toEqual([{ sections: ['mails'] }]);
});

test('a failed refresh keeps the received page, focus and scroll until a successful retry', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
  await mockApi(homeRoutes(user));
  const requests: unknown[] = [];
  const synthesisReads: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/briefing/text'))
      synthesisReads.push(request.url());
  });
  await mockApi([
    {
      url: CARD_REFRESH,
      method: 'POST',
      handler: async route => {
        requests.push({ sections: [refreshedSection(route)] });
        if (requests.length === 1) {
          await route.fulfill({ status: 503, json: { detail: 'temporary hermetic failure' } });
        } else {
          await route.fulfill({ json: refreshedAgenda().cards[refreshedSection(route)] });
        }
      },
    },
  ]);
  await readyHome(page, 'fr');
  const card = briefingCard(page, 'agenda', 'fr');
  const scroll = card.getByRole('group', {
    name: translated('fr', 'dashboard.briefing.cards.agenda.title'),
    exact: true,
  });
  await scroll.getByRole('listitem').last().scrollIntoViewIfNeeded();
  await expect.poll(() => scroll.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  const retained = await scroll.elementHandle();
  const before = await scroll.evaluate(element => element.scrollTop);
  const readsBefore = synthesisReads.length;
  const refresh = refreshControl(card, 'agenda', 'fr');
  await refresh.focus();
  await refresh.press('Enter');
  const error = briefingRegion(page, 'fr').getByRole('alert');
  await expect(error).toContainText(translated('fr', 'dashboard.briefing.refresh_error'));
  await expect(card).toHaveAttribute('aria-busy', 'false');
  await expect(refresh).toBeFocused();
  await expect(scroll.getByRole('listitem')).toHaveCount(HOME_CAPS.agenda);
  await expect(scroll.getByText(UPDATED_AGENDA_TITLE, { exact: true })).toHaveCount(0);
  expect(await retained!.evaluate(element => element.isConnected)).toBe(true);
  expect(await scroll.evaluate(element => element.scrollTop)).toBeCloseTo(before, 0);
  await refresh.press('Enter');
  await expect(error).toHaveCount(0);
  await expect(card).toHaveAttribute('aria-busy', 'false');
  await expect(refresh).toBeFocused();
  await assertRefreshedAgendaPage(scroll);
  const afterRetry = await scroll.evaluate(element => ({
    top: element.scrollTop,
    max: element.scrollHeight - element.clientHeight,
  }));
  expect(afterRetry.top).toBeCloseTo(Math.min(before, afterRetry.max), 0);
  expect(requests).toEqual([{ sections: ['agenda'] }, { sections: ['agenda'] }]);
  expect(synthesisReads).toHaveLength(readsBefore);
});

test('mixed unavailable, empty and failed cards keep the real content and navigation accessible', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await prepareTheme(page, 'light');
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE, theme: 'light' });
  const degraded = homeBriefing();
  degraded.cards.weather = {
    ...degraded.cards.weather,
    status: 'not_configured',
    data: null,
    error_code: 'connector_not_configured',
  };
  degraded.cards.agenda = { ...degraded.cards.agenda, status: 'empty', data: null };
  degraded.cards.mails = {
    ...degraded.cards.mails,
    status: 'error',
    data: null,
    from_cache: false,
    error_code: 'connector_network',
    error_message: 'La messagerie est temporairement indisponible.',
    last_attempt_at: HOME_GENERATED,
  };
  await mockApi(homeRoutes(user, degraded));
  // The payload still has all ten required sections; only the unconfigured
  // weather card disappears, and its real settings link explains its absence.
  await readyHome(page, 'fr', HOME_ORDER.length - 1);
  await expect(briefingCard(page, 'weather', 'fr')).toHaveCount(0);
  const configureWeather = briefingRegion(page, 'fr').getByRole('link', {
    name: translated('fr', 'dashboard.briefing.not_configured_cta').replace(
      '{{card}}',
      translated('fr', 'dashboard.briefing.cards.weather.title')
    ),
    exact: true,
  });
  await expect(configureWeather).toBeVisible();
  await expect(configureWeather).toHaveAttribute(
    'href',
    '/fr/dashboard/settings?section=connectors'
  );
  await configureWeather.focus();
  await expect(configureWeather).toBeFocused();

  const agenda = briefingCard(page, 'agenda', 'fr');
  await expect(
    agenda.getByText(translated('fr', 'dashboard.briefing.cards.agenda.empty'), { exact: true })
  ).toBeVisible();
  await expect(agenda.getByRole('listitem')).toHaveCount(0);
  const mails = briefingCard(page, 'mails', 'fr');
  await expect(mails.getByText(degraded.cards.mails.error_message!, { exact: true })).toBeVisible();
  await expect(
    mails.getByRole('button', {
      name: translated('fr', 'dashboard.briefing.actions.retry'),
      exact: true,
    })
  ).toBeVisible();
  await expect(mails.getByRole('listitem')).toHaveCount(0);
  await expect(
    mails.locator('time'),
    'a failure without retained data must not announce a data freshness'
  ).toHaveCount(0);
  await expect(briefingCard(page, 'reminders', 'fr').getByRole('listitem')).toHaveCount(
    HOME_CAPS.reminders
  );
  await expect(page.getByText(HOME_SYNTHESIS, { exact: true })).toBeVisible();

  const main = page.getByRole('main');
  for (const [key, href] of [
    ['open_chat', '/fr/dashboard/chat'],
    ['services', '/fr/dashboard/settings?section=connectors'],
  ]) {
    const link = main.getByRole('link', {
      name: translated('fr', `dashboard.actions.${key}`),
      exact: true,
    });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', href);
    await link.focus();
    await expect(link).toBeFocused();
  }
  await expect(
    main
      .getByRole('navigation', {
        name: translated('fr', 'dashboard.quick_access_compact.title'),
        exact: true,
      })
      .getByRole('link')
  ).toHaveCount(5);
  await expect(
    main.getByRole('heading', { name: 'Hermetic Home Radio', exact: true })
  ).toBeVisible();
  await assertConsumption(page, 'fr');
  await expectNoOverflow(page, 'home mixed degraded cards 390px');
  const accessibility = await scanPage(page, testInfo, 'home-mixed-degraded-390-fr-light');
  expect(accessibility.blocking, accessibility.summary).toEqual([]);
});

test('the civil date follows the account zone when the browser resumes on its next day', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
  await mockApi(homeRoutes(user));
  const reads: string[] = [];
  page.on('request', request => {
    if (/\/briefing\/(cards|synthesis)$/.test(new URL(request.url()).pathname))
      reads.push(request.url());
  });
  await readyHome(page, 'fr');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    pageDate(HOME_NOW, 'fr', HOME_TIMEZONE)
  );
  expect(civilDate(HOME_NOW, 'fr', HOME_TIMEZONE)).not.toBe(
    civilDate(HOME_NOW, 'fr', 'Asia/Tokyo')
  );
  const before = reads.length;
  await page.clock.setFixedTime(new Date('2026-10-16T10:01:00Z'));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    pageDate('2026-10-16T10:01:00Z', 'fr', HOME_TIMEZONE)
  );
  expect(reads).toHaveLength(before);
});

for (const cache of ['absent', 'null'] as const) {
  test(`a legacy workboard cache (${cache} previews) shows its counts and invents no ticket group`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 320, height: 1000 });
    const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
    const payload = homeBriefing();
    const board = payload.cards.workboard.data;
    if (!board) throw new Error('The home fixture must contain workboard data');
    if (cache === 'null') board.previews = null;
    else delete board.previews;
    await mockApi(homeRoutes(user, payload));
    await readyHome(page, 'fr');
    const card = briefingCard(page, 'workboard', 'fr');
    // The counts stay; no set is drawn from a page that is not every set.
    await expect(
      card.getByRole('list', { name: translated('fr', 'settings.workboard.glance') })
    ).toBeVisible();
    await expect(card.getByRole('heading', { level: 4 })).toHaveCount(0);
    for (const group of HOME_WORKBOARD_GROUPS) {
      await expect(
        card.getByRole('list', { name: translated('fr', group.labelKey), exact: true })
      ).toHaveCount(0);
    }
    for (let index = 0; index < HOME_CAPS.workboard; index += 1) {
      await expect(card.getByText(homeItemName('workboard', index), { exact: true })).toHaveCount(
        0
      );
    }
    await expectNoOverflow(page, `legacy workboard ${cache} previews 320px`);
  });
}

test('health thresholds retain their numbers and units through refresh, including zero and no data', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  const user = await authenticate({ language: 'fr', timezone: HOME_TIMEZONE });
  const samples = [
    { steps: 5000, heart: 70, tones: ['red', 'green'] },
    { steps: 5001, heart: 71, tones: ['orange', 'orange'] },
    { steps: 9999, heart: 89, tones: ['orange', 'orange'] },
    { steps: 10000, heart: 90, tones: ['green', 'red'] },
    { steps: 0, heart: 0, tones: ['red', 'green'] },
    { steps: null, heart: null, tones: ['neutral', 'neutral'] },
  ];
  const payloadFor = (sample: (typeof samples)[number]) => {
    const payload = homeBriefing();
    const health = payload.cards.health.data;
    if (!health) throw new Error('The home fixture must contain health data');
    health.items = health.items.map(item => ({
      ...item,
      value_today: item.kind === 'steps' ? sample.steps : sample.heart,
    }));
    return payload;
  };
  let current = payloadFor(samples[0]);
  await mockApi(homeRoutes(user, current));
  const requests: unknown[] = [];
  await mockApi([
    {
      url: CARD_REFRESH,
      method: 'POST',
      handler: async route => {
        requests.push({ sections: [refreshedSection(route)] });
        await route.fulfill({ json: current.cards[refreshedSection(route)] });
      },
    },
  ]);
  const textReads: string[] = [];
  page.on('request', request => {
    if (/\/briefing\/(synthesis|synthesis\/audio)$/.test(new URL(request.url()).pathname))
      textReads.push(request.url());
  });
  await readyHome(page, 'fr');
  const textReadCount = textReads.length;
  const tones = new Map<string, string>();
  for (const [index, sample] of samples.entries()) {
    current = payloadFor(sample);
    if (index > 0) {
      const refresh = refreshControl(briefingCard(page, 'health', 'fr'), 'health', 'fr');
      await refresh.focus();
      await refresh.press('Enter');
      await expect.poll(() => requests.length).toBe(index);
      await expect(briefingCard(page, 'health', 'fr')).toHaveAttribute('aria-busy', 'false');
      await expect(refresh).toBeFocused();
    }
    const health = current.cards.health.data;
    if (!health) throw new Error('The home fixture must contain health data');
    const colors = await assertHealthReading(page, 'fr', health);
    sample.tones.forEach((tone, metric) => {
      const previous = tones.get(tone);
      if (previous)
        expect(colors[metric], `the ${tone} boundary uses one stable tone`).toBe(previous);
      else tones.set(tone, colors[metric]);
    });
  }
  expect(
    new Set(tones.values()).size,
    'the four bands are visually distinct in addition to their readable values'
  ).toBe(4);
  expect(requests).toEqual(
    Array.from({ length: samples.length - 1 }, () => ({ sections: ['health'] }))
  );
  expect(textReads, 'health refresh does not request synthesis or paid audio').toHaveLength(
    textReadCount
  );
  await expectNoOverflow(page, 'health thresholds 390px');
});

for (const width of [320, 1440]) {
  test(`large health values stay readable without overlap @ ${width}px 20px Fira Code`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepareTheme(page, 'oled');
    const user = await authenticate({
      language: 'fr',
      timezone: HOME_TIMEZONE,
      theme: 'oled',
      font_size: 20,
    });
    const payload = homeBriefing();
    const health = payload.cards.health.data;
    if (!health) throw new Error('The home fixture must contain health data');
    health.items = health.items.map(item =>
      item.kind === 'steps'
        ? { ...item, value_today: 50000, value_avg_window: 10000 }
        : { ...item, value_today: 100, value_avg_window: 100 }
    );
    // This is the existing account preference, not a style injected by the test.
    const fontUser = { ...user, font_family: 'fira-code' };
    await mockApi(homeRoutes(fontUser, payload));
    await readyHome(page, 'fr');
    await expect(page.locator('html')).toHaveAttribute('data-font', 'fira-code');
    await page.evaluate(() => document.fonts.ready);
    const card = briefingCard(page, 'health', 'fr');
    await expect
      .poll(() =>
        card
          .getByRole('heading', { level: 3 })
          .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
      )
      .toBe(20);
    const font = await card.evaluate(element => {
      const family = getComputedStyle(element).fontFamily.replace(/["']/g, '').toLowerCase();
      const declared = getComputedStyle(document.documentElement)
        .getPropertyValue('--font-fira-code')
        .trim()
        .split(',')[0]
        .replace(/["']/g, '')
        .toLowerCase();
      return { family, declared, loaded: document.fonts.check(`20px "${declared}"`) };
    });
    expect(font.declared, 'the real self-hosted font variable is available').not.toBe('');
    expect(font.family, 'Fira Code is actually inherited by the measured card').toContain(
      font.declared
    );
    expect(font.loaded, 'the measured self-hosted font has loaded').toBe(true);
    await assertHealthReading(page, 'fr', health);
    await expectNoOverflow(page, `health five-digit values ${width}px 20px Fira Code OLED`);
    await testInfo.attach(`health-large-values-${width}-20-fira`, {
      body: await card.screenshot(),
      contentType: 'image/png',
    });
    if (process.env.E2E_HOME_CLEAN_CAPTURES === '1') {
      await card.getByRole('group').evaluate(element => {
        element.scrollTop = 0;
      });
      await testInfo.attach(`health-large-values-${width}-20-fira-top`, {
        body: await card.screenshot(),
        contentType: 'image/png',
      });
    }
  });
}

for (const sample of [
  { width: 320, locale: 'fr', status: 'ready' },
  { width: 320, locale: 'en', status: 'failed' },
  { width: 1440, locale: 'fr', status: 'failed' },
  { width: 1440, locale: 'en', status: 'ready' },
] satisfies { width: number; locale: Locale; status: 'ready' | 'failed' }[]) {
  test(`native meeting result toast keeps readable text above its action @ ${sample.width}px ${sample.locale} ${sample.status}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 1000 });
    const user = await authenticate({ language: sample.locale, timezone: HOME_TIMEZONE });
    await mockApi(homeRoutes(user));
    let release!: () => void;
    const gate = new Promise<void>(resolve => {
      release = resolve;
    });
    const detail = homeMeetingResult(sample.status);
    await mockApi([
      {
        url: '**/api/v1/config',
        json: {
          ...appConfig,
          features: { ...appConfig.features, radio_enabled: true, meetings_enabled: true },
          capabilities: { radio: { enabled: true, family: 'media' } },
        },
      },
      {
        url: '**/api/v1/meetings/toast-result',
        method: 'GET',
        handler: async (route, signal) => {
          if (!(await waitForMockGate(gate, signal))) return;
          await route.fulfill({ json: detail });
        },
      },
      // A default reconciliation can run before the persisted processing state
      // hydrates; it still reaches only this deterministic read-only boundary.
      { url: '**/api/v1/meetings/active', method: 'GET', json: null },
    ]);
    await page.addInitScript(
      ({ ownerId, startedAt }) => {
        localStorage.setItem(
          'lia_meeting_recorder',
          JSON.stringify({
            state: {
              ownerId,
              phase: 'processing',
              limits: null,
              recording: {
                meetingId: 'toast-result',
                startedAt,
                audioFormat: 'webm_opus',
                mimeType: null,
                segmentSeconds: 30,
                nextSequence: 1,
              },
            },
            version: 0,
          })
        );
      },
      { ownerId: user.id, startedAt: HOME_GENERATED }
    );
    try {
      await readyHome(page, sample.locale);
    } finally {
      release();
    }
    const title = page.getByText(
      translated(sample.locale, `meetings.toasts.${sample.status}_title`),
      { exact: true }
    );
    await expect(title).toBeVisible();
    const notification = title.locator('xpath=ancestor::*[@data-sonner-toast][1]');
    await notification.hover();
    const description = notification.getByText(
      sample.status === 'ready'
        ? HOME_MEETING_RESULT_TITLE
        : translated(sample.locale, 'meetings.errors.synthesis_failed'),
      { exact: true }
    );
    const action = notification.getByRole('button', {
      name: translated(sample.locale, 'meetings.banner.open_minutes'),
      exact: true,
    });
    const close = notification.getByRole('button', {
      name: translated(sample.locale, 'common.close'),
      exact: true,
    });
    await expect(description).toBeVisible();
    await expect(action).toBeVisible();
    const [frame, titleBox, descriptionBox, actionBox, closeBox] = await Promise.all([
      box(notification),
      box(title),
      box(description),
      box(action),
      box(close),
    ]);
    expect(
      titleBox.y + titleBox.height,
      'notification action follows the title'
    ).toBeLessThanOrEqual(actionBox.y + 1);
    expect(
      descriptionBox.y + descriptionBox.height,
      'notification description is above the action'
    ).toBeLessThanOrEqual(actionBox.y + 1);
    expect(frame.x).toBeGreaterThanOrEqual(0);
    expect(frame.x + frame.width).toBeLessThanOrEqual(sample.width + 1);
    expect(
      Math.abs(actionBox.x + actionBox.width / 2 - (frame.x + frame.width / 2)),
      'the notification action is horizontally centered'
    ).toBeLessThanOrEqual(1);
    for (const item of [titleBox, descriptionBox, actionBox, closeBox]) {
      expect(item.x).toBeGreaterThanOrEqual(frame.x - 1);
      expect(item.x + item.width).toBeLessThanOrEqual(frame.x + frame.width + 1);
    }
    expect(closeBox.width).toBeGreaterThanOrEqual(44);
    expect(closeBox.height).toBeGreaterThanOrEqual(44);
    // The title reserves the close corner with padding; its border box is not
    // the visible text. Inspect every rendered text line rather than that box.
    const titleLines = await title.evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      return Array.from(range.getClientRects(), rect => ({
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      }));
    });
    expect(titleLines.length).toBeGreaterThan(0);
    for (const line of titleLines) {
      const overlapX =
        Math.min(line.x + line.width, closeBox.x + closeBox.width) - Math.max(line.x, closeBox.x);
      const overlapY =
        Math.min(line.y + line.height, closeBox.y + closeBox.height) - Math.max(line.y, closeBox.y);
      expect(overlapX > 1 && overlapY > 1, 'the close control does not cover title text').toBe(
        false
      );
    }
    await expect(notification.locator('xpath=ancestor::*[@aria-live][1]')).toHaveAttribute(
      'aria-live',
      'polite'
    );
    await action.focus();
    await expect(action).toBeFocused();
    await close.focus();
    await close.press('Enter');
    await expect(notification).toBeHidden();
    await expectNoOverflow(page, `native home notification ${sample.width}px ${sample.locale}`);
  });
}
