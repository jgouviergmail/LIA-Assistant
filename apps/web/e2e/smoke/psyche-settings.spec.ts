/** Psyché: on-demand point, complete state, historical charts and safe settings/reset actions. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import type {
  PsycheHistoryEntry,
  PsycheSettings,
  PsycheSettingsUpdate,
  PsycheState,
} from '../../src/types/psyche';
import {
  test,
  expect,
  waitForHydration,
  waitForMockGate,
  idleNotificationStream,
} from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';
import { psycheEfficacyProfile } from '../fixtures/psyche-efficacy';

const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
const SUMMARY =
  'LIA aborde tes échanges avec sérénité et curiosité. Votre relation se renforce grâce aux conversations régulières et aux projets menés ensemble.';
const SETTINGS = '**/api/v1/psyche/settings';
const HISTORY = /\/api\/v1\/psyche\/history(?:\?.*)?$/;
const STATE = /\/api\/v1\/psyche\/state(?:\?.*)?$/;
const SUMMARY_ROUTE = '**/api/v1/psyche/summary';
const RESET = '**/api/v1/psyche/reset';
const CONTROLS = [
  'psyche.education.title',
  'psyche.settingsSection.title',
  'psyche.presentation.resets',
] as const;
const RANGES = [
  ['24h', 24, 100],
  ['7d', 168, 200],
  ['30d', 720, 300],
  ['90d', 2160, 500],
] as const;
const CHARTS = ['chartPad', 'chartEmotions', 'chartRelationship', 'chartDrives'] as const;

function copy(key: string): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}
function state(): PsycheState {
  return {
    id: '00000000-0000-4000-8000-000000000101',
    user_id: '00000000-0000-4000-8000-000000000001',
    trait_openness: 0.73,
    trait_conscientiousness: 0.66,
    trait_extraversion: 0.48,
    trait_agreeableness: 0.81,
    trait_neuroticism: 0.24,
    mood_pleasure: 0.46,
    mood_arousal: 0.19,
    mood_dominance: 0.32,
    mood_label: 'serene',
    mood_color: '#38bdf8',
    active_emotions: [
      { name: 'curiosity', intensity: 0.64, triggered_at: '2026-10-16T08:00:00Z' },
      { name: 'joy', intensity: 0.41, triggered_at: '2026-10-16T07:55:00Z' },
      { name: 'serenity', intensity: 0.3, triggered_at: '2026-10-16T07:50:00Z' },
    ],
    relationship_stage: 'AFFECTIVE',
    relationship_depth: 0.56,
    relationship_warmth_active: 0.72,
    relationship_trust: 0.81,
    relationship_interaction_count: 127,
    drive_curiosity: 0.69,
    drive_engagement: 0.74,
    self_efficacy: {
      calendar: { score: 0.76, weight: 3 },
      emails: { score: 0.65, weight: 2 },
    },
    efficacy_profile: psycheEfficacyProfile(),
    created_at: '2026-08-01T08:00:00Z',
    updated_at: '2026-10-16T08:00:00Z',
  };
}
function settings(): PsycheSettings {
  return {
    psyche_enabled: true,
    psyche_display_avatar: true,
    psyche_sensitivity: 50,
    psyche_stability: 65,
  };
}
/** Real newest-first history shape, including a reset marker and multivalued emotions. */
function history(): PsycheHistoryEntry[] {
  return Array.from({ length: 8 }, (_, index) => ({
    id: `00000000-0000-4000-8000-${String(index + 201).padStart(12, '0')}`,
    snapshot_type: index === 4 ? 'reset_soft' : 'post_response',
    mood_pleasure: 0.46 - index * 0.03,
    mood_arousal: 0.19 + index * 0.02,
    mood_dominance: 0.32 - index * 0.01,
    dominant_emotion: index % 2 ? 'joy' : 'curiosity',
    relationship_stage: 'AFFECTIVE',
    trait_snapshot: {
      active_emotions: { curiosity: 0.64 - index * 0.03, joy: 0.41 + index * 0.02 },
      emotion_intensity: 0.64 - index * 0.03,
      relationship_depth: 0.56 - index * 0.01,
      relationship_warmth: 0.72 - index * 0.02,
      relationship_trust: 0.81 - index * 0.01,
      drive_curiosity: 0.69 - index * 0.02,
      drive_engagement: 0.74 - index * 0.01,
    },
    created_at: new Date(Date.UTC(2026, 9, 16, 8 - index)).toISOString(),
  }));
}
function section(page: Page): Locator {
  return page.locator('#settings-section-psyche');
}
function disclosure(page: Page, key: string): Locator {
  return section(page).getByRole('button', { name: copy(key), exact: true });
}
async function expanded(control: Locator, expected: boolean): Promise<void> {
  await expect(control).toHaveCount(1);
  await expect(control).toHaveAttribute('aria-expanded', String(expected));
}
async function reveal(page: Page, key: string): Promise<Locator> {
  const control = disclosure(page, key);
  await expect(control).toBeVisible();
  if ((await control.getAttribute('aria-expanded')) !== 'true') await control.click();
  await expanded(control, true);
  return control;
}
async function revealDetail(page: Page, key: string): Promise<Locator> {
  const control = section(page)
    .locator('summary')
    .filter({ hasText: copy(key) });
  await expect(control).toBeVisible();
  const details = control.locator('..');
  if (!(await details.evaluate(node => (node as HTMLDetailsElement).open))) {
    await control.focus();
    await page.keyboard.press('Enter');
  }
  await expect(details).toHaveAttribute('open', '');
  return details;
}
async function measured(locator: Locator) {
  const bounds = await locator.boundingBox();
  expect(bounds, 'a visible element must have a measured layout box').not.toBeNull();
  return bounds!;
}
async function open(page: Page): Promise<void> {
  const response = await page.goto('/fr/dashboard/settings?section=psyche');
  expect(response?.status(), 'the actual settings document must load').toBe(200);
  await waitForHydration(page, '#settings-section-psyche');
  await expect(
    section(page).getByRole('switch', { name: copy('psyche.enable'), exact: true })
  ).toBeChecked();
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
      ''
  );
  await page.evaluate(() => document.fonts.ready);
  await expect(section(page), 'visible interface labels are translated').not.toContainText(
    /\b(?:psyche|common)\.[a-zA-Z_]+/
  );
  // The user now asks the point to open on arrival, with one mocked summary read.
  const point = section(page)
    .locator('summary')
    .filter({ hasText: copy('psyche.presentation.point') });
  await expect(point).toBeVisible();
  await expect(point.locator('..')).toHaveAttribute('open', '');
}
async function presentation(page: Page, desktop: boolean): Promise<void> {
  const controls = await Promise.all(CONTROLS.map(key => measured(disclosure(page, key))));
  for (const [index, bounds] of controls.entries()) {
    expect(
      bounds.height,
      'settings disclosure is a comfortable touch target'
    ).toBeGreaterThanOrEqual(44);
    expect(Math.abs(bounds.x - controls[0].x), 'settings controls share a left edge').toBeLessThan(
      2
    );
    expect(
      Math.abs(bounds.width - controls[0].width),
      'settings controls share a width'
    ).toBeLessThan(2);
    if (index > 0)
      expect(bounds.y, 'commands remain in vertical order').toBeGreaterThanOrEqual(
        controls[index - 1].y + controls[index - 1].height
      );
  }
  const [title, toggle] = await Promise.all([
    measured(section(page).getByText(copy('psyche.title'), { exact: true })),
    measured(section(page).getByRole('switch', { name: copy('psyche.enable'), exact: true })),
  ]);
  expect(toggle.x, 'master activation is to the right of the title').toBeGreaterThan(title.x);
  expect(
    Math.abs(title.y + title.height / 2 - (toggle.y + toggle.height / 2)),
    'master activation aligns vertically with the title'
  ).toBeLessThan(8);
  await expect(
    section(page)
      .locator('summary')
      .filter({ hasText: copy('psyche.presentation.point') })
  ).toBeVisible();
  const point = await measured(
    section(page)
      .locator('summary')
      .filter({ hasText: copy('psyche.presentation.point') })
  );
  const mood = await measured(disclosure(page, 'psyche.presentation.mood'));
  const evolution = await measured(disclosure(page, 'psyche.presentation.evolution'));
  expect(mood.y, 'the point precedes mood and emotions').toBeGreaterThan(point.y);
  expect(evolution.y, 'evolution follows the mood section').toBeGreaterThan(mood.y);
  for (const key of [
    'psyche.presentation.mood',
    'psyche.presentation.relationship',
    'psyche.presentation.drivesTitle',
    'psyche.presentation.evolution',
  ])
    await expanded(disclosure(page, key), true);
  for (const key of CONTROLS) await expanded(disclosure(page, key), false);
  await expectNoOverflow(page, desktop ? 'psyche desktop' : 'psyche mobile');
}
async function capture(page: Page, info: TestInfo, name: string): Promise<void> {
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

const observations = new WeakMap<Page, { api: string[]; errors: string[]; google: string[] }>();
test.beforeEach(async ({ page, context, mockApi, baseURL }) => {
  if (baseURL)
    await context.addCookies([
      {
        name: 'lia_session',
        value: 'e2e-session',
        url: new URL(baseURL).origin,
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    )
  );
  await mockApi([
    { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
    { url: '**/api/v1/agents/runs/active', method: 'GET', json: { active: false } },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      method: 'GET',
      json: { enabled: false, user_access_available: false },
    },
    {
      url: '**/api/v1/habits/presence',
      method: 'POST',
      handler: route => route.fulfill({ status: 204, body: '' }),
    },
    idleNotificationStream,
  ]);
  const observed = { api: [] as string[], errors: [] as string[], google: [] as string[] };
  observations.set(page, observed);
  page.on('response', response => {
    if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/v1/'))
      observed.api.push(response.url());
  });
  page.on('pageerror', error => observed.errors.push(error.message));
  context.on('request', request => {
    if (
      ['www.google.com', 'content-autofill.googleapis.com'].includes(
        new URL(request.url()).hostname
      )
    )
      observed.google.push(request.url());
  });
});
test.afterEach(async ({ page, apiNetworkGuard }, info) => {
  const observed = observations.get(page)!;
  await info.attach('network-isolation.json', {
    body: JSON.stringify(
      { ...observed, blockedTransport: apiNetworkGuard.blockedRequests },
      null,
      2
    ),
    contentType: 'application/json',
  });
  expect(observed.api, 'every actual API operation is explicitly mocked').toEqual([]);
  expect(observed.errors, 'no uncaught page errors').toEqual([]);
  expect(
    observed.google,
    'Google services never originate from application pages or workers'
  ).toEqual([]);
  // These opaque browser services remain DENIED by the unchanged transport guard.
  const browserRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserRefusals.has(request))).toEqual(
    []
  );
});

for (const layout of [
  { name: 'desktop-dark', width: 1440, theme: 'dark', fontSize: 16 },
  { name: 'mobile-light', width: 320, theme: 'light', fontSize: 16 },
  { name: 'mobile-oled-large-text', width: 390, theme: 'oled', fontSize: 20 },
] as const) {
  test(`efficacy: ${layout.name} keeps outcomes and usefulness separate and readable`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    await page.setViewportSize({ width: layout.width, height: 1050 });
    await prepareTheme(page, layout.theme);
    await authenticate({ language: 'fr', theme: layout.theme, font_size: layout.fontSize });
    let summaries = 0;
    await mockApi([
      { url: SETTINGS, method: 'GET', json: settings() },
      { url: STATE, method: 'GET', json: state() },
      { url: HISTORY, method: 'GET', json: history() },
      {
        url: SUMMARY_ROUTE,
        method: 'GET',
        handler: route => {
          summaries += 1;
          return route.fulfill({ json: { summary: SUMMARY } });
        },
      },
    ]);
    await open(page);
    await expect(section(page).getByText(SUMMARY, { exact: true })).toBeVisible();
    const efficacy = await revealDetail(page, 'psyche.education.drives.efficacy_title');
    await expect(efficacy.getByRole('heading', { level: 4 })).toHaveCount(7);
    const results = efficacy.getByRole('meter', {
      name: `${copy('psyche.domains.technical')} · ${copy('psyche.efficacy.results')}`,
      exact: true,
    });
    const usefulness = efficacy.getByRole('meter', {
      name: `${copy('psyche.domains.technical')} · ${copy('psyche.efficacy.usefulness')}`,
      exact: true,
    });
    await expect(results).toHaveAttribute('aria-valuenow', '71');
    await expect(usefulness).toHaveAttribute('aria-valuenow', '40');
    await expect(efficacy.getByRole('meter')).toHaveCount(2);
    await expect(
      efficacy.getByText(copy('psyche.efficacy.resultBasis_other').replace('{{count}}', '5'), {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      efficacy.getByText(copy('psyche.efficacy.feedbackBasis_other').replace('{{count}}', '3'), {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      efficacy.getByText(copy('psyche.efficacy.unassigned_other').replace('{{count}}', '2'), {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      efficacy
        .getByRole('region', { name: copy('psyche.domains.planning'), exact: true })
        .getByRole('meter')
    ).toHaveCount(0);
    const [resultBounds, feedbackBounds] = await Promise.all([
      measured(results),
      measured(usefulness),
    ]);
    if (layout.width < 768) {
      expect(
        feedbackBounds.y,
        'mobile axes stack into independently readable rows'
      ).toBeGreaterThan(resultBounds.y);
      expect(
        Math.abs(feedbackBounds.x - resultBounds.x),
        'mobile axes share a left edge'
      ).toBeLessThan(2);
    } else {
      expect(feedbackBounds.x, 'desktop axes have distinct aligned columns').toBeGreaterThan(
        resultBounds.x
      );
      expect(
        Math.abs(feedbackBounds.y - resultBounds.y),
        'desktop indices share a baseline'
      ).toBeLessThan(2);
    }
    expect(summaries, 'opening experience does not generate another point').toBe(1);
    await expectNoOverflow(page, `efficacy ${layout.name}`);
    const file = info.outputPath(`efficacy-${layout.name}.png`);
    await efficacy.screenshot({ path: file });
    await info.attach(`efficacy-${layout.name}`, { path: file, contentType: 'image/png' });
    const audit = await scanPage(page, info, `efficacy-${layout.name}`);
    expect(audit.blocking, audit.summary).toHaveLength(0);
  });
}

test('1440px light: one initially open point, refresh on demand and all four historical charts/periods retained', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1050 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', theme: 'light' });
  const preferences = settings();
  const styles = [
    {
      id: '00000000-0000-4000-8000-000000000501',
      code: 'normal',
      title: 'Normal',
      description: 'Équilibrée',
      emoji: '⚖️',
      is_default: true,
    },
    {
      id: '00000000-0000-4000-8000-000000000502',
      code: 'curious',
      title: 'Curieuse',
      description: 'Une curiosité affirmée',
      emoji: '🤔',
      is_default: false,
    },
  ];
  let currentStyle = styles[0];
  let observedState = state();
  const windows: { hours: number; limit: number }[] = [];
  let stateReads = 0;
  let summaries = 0;
  let release: () => void = () => undefined;
  const gate = new Promise<void>(resolve => {
    release = resolve;
  });
  await mockApi([
    {
      url: '**/api/v1/personalities',
      method: 'GET',
      json: { personalities: styles, total: styles.length },
    },
    {
      url: '**/api/v1/personalities/current',
      method: 'GET',
      handler: route =>
        route.fulfill({ json: { personality: currentStyle, personality_id: currentStyle.id } }),
    },
    {
      url: '**/api/v1/personalities/current',
      method: 'PATCH',
      handler: async route => {
        expect(route.request().postDataJSON()).toEqual({ personality_id: styles[1].id });
        currentStyle = styles[1];
        observedState = { ...observedState, trait_openness: 0.91, trait_conscientiousness: 0.37 };
        await route.fulfill({
          json: { personality: currentStyle, personality_id: currentStyle.id },
        });
      },
    },
    { url: SETTINGS, method: 'GET', handler: route => route.fulfill({ json: preferences }) },
    {
      url: STATE,
      method: 'GET',
      handler: async route => {
        expect(new URL(route.request().url()).searchParams.get('initialize')).toBe('false');
        stateReads += 1;
        await route.fulfill({ json: observedState });
      },
    },
    {
      url: HISTORY,
      method: 'GET',
      handler: async route => {
        const url = new URL(route.request().url());
        const hours = Number(url.searchParams.get('hours'));
        const limit = Number(url.searchParams.get('limit'));
        expect(
          RANGES.some(([, h, l]) => h === hours && l === limit),
          'every history window matches its established API limit'
        ).toBe(true);
        windows.push({ hours, limit });
        await route.fulfill({ json: history() });
      },
    },
    {
      url: SUMMARY_ROUTE,
      method: 'GET',
      handler: async (route, signal) => {
        summaries += 1;
        if (!(await waitForMockGate(gate, signal))) return;
        await route.fulfill({ json: { summary: SUMMARY } });
      },
    },
  ]);
  await open(page);
  await presentation(page, true);
  for (const key of [
    'psyche.presentation.mood',
    'psyche.presentation.relationship',
    'psyche.presentation.drivesTitle',
    'psyche.presentation.evolution',
  ])
    await reveal(page, key);
  await expect.poll(() => summaries).toBe(1);
  const point = section(page).getByRole('region', {
    name: copy('psyche.presentation.point'),
    exact: true,
  });
  await expect(point.getByRole('button')).toHaveCount(0);
  for (const key of CONTROLS) {
    const command = await reveal(page, key);
    await command.click();
    await expanded(command, false);
  }
  const moodControl = disclosure(page, 'psyche.presentation.mood');
  await moodControl.click();
  await expanded(moodControl, false);
  await expect(point).toBeVisible();
  await moodControl.click();
  await expanded(moodControl, true);
  expect(summaries, 'opening settings during generation does not invoke another model call').toBe(
    1
  );
  release();
  await expect(point.getByText(SUMMARY, { exact: true })).toBeVisible();
  const previousStateReads = stateReads;
  await section(page)
    .getByRole('button', { name: copy('common.refresh'), exact: true })
    .click();
  await expect.poll(() => stateReads).toBeGreaterThan(previousStateReads);
  await expect.poll(() => summaries).toBe(2);
  await expect(point.getByText(SUMMARY, { exact: true })).toBeVisible();
  for (const [range, hours, limit] of [RANGES[0], RANGES[2], RANGES[3], RANGES[1]]) {
    const button = section(page).getByRole('button', {
      name: copy(`psyche.history.tabs.${range}`),
      exact: true,
    });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => windows.at(-1)).toEqual({ hours, limit });
  }
  for (const chart of CHARTS) {
    const button = section(page).getByRole('button', {
      name: copy(`psyche.history.${chart}`),
      exact: true,
    });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
    const graph = section(page).getByRole('region', {
      name: `${copy(`psyche.history.${chart}`)} · ${copy('psyche.history.tabs.7d')}`,
      exact: true,
    });
    await expect(graph.locator('.recharts-wrapper > svg.recharts-surface')).toBeVisible();
  }
  expect(summaries, 'chart and period navigation do not regenerate prose').toBe(2);
  await expectNoOverflow(page, 'psyche desktop all historical controls');
  const beforeStyleChange = stateReads;
  await page
    .getByRole('button', {
      name: copy('personality.selector_label').replace('{{name}}', styles[0].title),
      exact: true,
    })
    .click();
  await page.getByRole('menuitem').filter({ hasText: styles[1].title }).click();
  await expect.poll(() => stateReads).toBeGreaterThan(beforeStyleChange);
  await revealDetail(page, 'psyche.education.traits.title');
  await expect(
    section(page).getByRole('meter', {
      name: copy('psyche.education.traits.openness'),
      exact: true,
    })
  ).toHaveAttribute('aria-valuenow', '91');
  await expect(
    section(page).getByRole('meter', {
      name: copy('psyche.education.traits.conscientiousness'),
      exact: true,
    })
  ).toHaveAttribute('aria-valuenow', '37');
  expect(summaries, 'a style change rereads traits without another model generation').toBe(2);
  await capture(page, info, 'psyche-desktop-light');
  const audit = await scanPage(page, info, 'psyche-desktop-light');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});

test('320px light: folded sections, preference error recovery and confirmed soft reset', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 320, height: 950 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', theme: 'light' });
  let preferences = settings();
  let current = state();
  let stateReads = 0;
  const patches: PsycheSettingsUpdate[] = [];
  const resets: unknown[] = [];
  let summaries = 0;
  await mockApi([
    { url: SETTINGS, method: 'GET', handler: route => route.fulfill({ json: preferences }) },
    {
      url: SETTINGS,
      method: 'PATCH',
      handler: async route => {
        const body = route.request().postDataJSON() as PsycheSettingsUpdate;
        patches.push(body);
        if (patches.length === 2) {
          await route.fulfill({
            status: 503,
            json: { detail: 'preference_temporarily_unavailable' },
          });
          return;
        }
        preferences = { ...preferences, ...body };
        await route.fulfill({ json: preferences });
      },
    },
    {
      url: STATE,
      method: 'GET',
      handler: route => {
        stateReads += 1;
        return route.fulfill({
          contentType: 'application/json',
          json: stateReads === 1 ? null : current,
        });
      },
    },
    { url: HISTORY, method: 'GET', json: history() },
    {
      url: SUMMARY_ROUTE,
      method: 'GET',
      handler: async route => {
        summaries += 1;
        await route.fulfill({ json: { summary: SUMMARY } });
      },
    },
    {
      url: RESET,
      method: 'POST',
      handler: async route => {
        resets.push(route.request().postDataJSON());
        current = {
          ...current,
          mood_label: 'neutral',
          mood_pleasure: 0,
          mood_arousal: 0,
          mood_dominance: 0,
          active_emotions: [],
        };
        await route.fulfill({ json: { status: 'reset', level: 'soft' } });
      },
    },
  ]);
  await open(page);
  await expect(disclosure(page, 'psyche.presentation.mood')).toBeVisible();
  await presentation(page, false);
  for (const key of CONTROLS) await expanded(disclosure(page, key), false);
  await expect.poll(() => summaries).toBe(1);
  expect(
    stateReads,
    'a first generated point makes the newly created state observable'
  ).toBeGreaterThanOrEqual(2);
  await expect(section(page).getByText(SUMMARY, { exact: true })).toBeVisible();
  await capture(page, info, 'psyche-mobile-320-initial');
  await reveal(page, 'psyche.settingsSection.title');
  const avatar = section(page).getByRole('switch', {
    name: copy('psyche.displayAvatar'),
    exact: true,
  });
  await expect(avatar).toBeChecked();
  await avatar.click();
  await expect(avatar).not.toBeChecked();
  await expect.poll(() => patches).toEqual([{ psyche_display_avatar: false }]);
  await avatar.click();
  await expect(page.getByText(copy('psyche.settingsError'), { exact: true })).toBeVisible();
  await expect(avatar).not.toBeChecked();
  expect(patches).toEqual([{ psyche_display_avatar: false }, { psyche_display_avatar: true }]);
  await avatar.click();
  await expect(avatar).toBeChecked();
  await expect.poll(() => patches.length).toBe(3);
  const sensitivity = section(page).getByRole('slider', {
    name: copy('psyche.sensitivity'),
    exact: true,
  });
  await sensitivity.focus();
  await page.keyboard.press('ArrowRight');
  await expect(sensitivity).toHaveAttribute('aria-valuenow', '55');
  await expect.poll(() => patches.at(-1)).toEqual({ psyche_sensitivity: 55 });
  expect(summaries, 'saving preferences never regenerates the point').toBe(1);
  await reveal(page, 'psyche.presentation.resets');
  await section(page)
    .getByRole('button', { name: copy('psyche.softReset'), exact: true })
    .click();
  const dialog = page.getByRole('alertdialog', {
    name: copy('psyche.softResetTitle'),
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: copy('common.cancel'), exact: true }).click();
  expect(resets, 'cancelling the confirmation never mutates state').toEqual([]);
  expect(summaries, 'cancelling a reset does not regenerate the point').toBe(1);
  await section(page)
    .getByRole('button', { name: copy('psyche.softReset'), exact: true })
    .click();
  await dialog.getByRole('button', { name: copy('psyche.softReset'), exact: true }).click();
  await expect.poll(() => resets).toEqual([{ level: 'soft' }]);
  await expect(dialog).toHaveCount(0);
  await reveal(page, 'psyche.presentation.mood');
  await expect(
    section(page).getByText(copy('psyche.moods.neutral'), { exact: true })
  ).toBeVisible();
  await expect.poll(() => summaries).toBe(2);
  await expect(section(page).getByText(SUMMARY, { exact: true })).toBeVisible();
  await expectNoOverflow(page, 'psyche mobile preferences and reset');
  await capture(page, info, 'psyche-mobile-320-controls');
});

test('390px OLED20px: initial point failure retries from page refresh; full metrics and charts reflow', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1050 });
  await prepareTheme(page, 'oled');
  await authenticate({ language: 'fr', theme: 'oled', font_size: 20 });
  let summaries = 0;
  await mockApi([
    { url: SETTINGS, method: 'GET', json: settings() },
    { url: STATE, method: 'GET', json: state() },
    { url: HISTORY, method: 'GET', json: history() },
    {
      url: SUMMARY_ROUTE,
      method: 'GET',
      handler: async route => {
        summaries += 1;
        if (summaries === 1)
          await route.fulfill({ status: 503, json: { detail: 'model_temporarily_unavailable' } });
        else await route.fulfill({ json: { summary: SUMMARY } });
      },
    },
  ]);
  await open(page);
  await presentation(page, false);
  await expect
    .poll(() =>
      section(page)
        .getByText(copy('psyche.title'), { exact: true })
        .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    )
    .toBe(20);
  await expect(section(page).getByRole('alert')).toContainText(copy('psyche.summary.error'));
  expect(summaries).toBe(1);
  await section(page)
    .getByRole('button', { name: copy('common.refresh'), exact: true })
    .click();
  await expect(section(page).getByText(SUMMARY, { exact: true })).toBeVisible();
  expect(summaries).toBe(2);
  await reveal(page, 'psyche.presentation.mood');
  await reveal(page, 'psyche.presentation.relationship');
  await reveal(page, 'psyche.presentation.drivesTitle');
  const pad = section(page).getByRole('img', {
    name: copy('psyche.presentation.padTitle'),
    exact: true,
  });
  await expect(pad).toBeVisible();
  await expect(pad).toHaveAccessibleDescription(/Plaisir.*Activation.*Dominance/);
  const observedPoint = pad.locator('circle').last();
  expect(
    Number(await observedPoint.getAttribute('cx')),
    'pleasure determines the actual horizontal coordinate'
  ).toBeCloseTo(171 + 0.46 * 121, 2);
  expect(
    Number(await observedPoint.getAttribute('cy')),
    'activation determines the actual vertical coordinate'
  ).toBeCloseTo(129 - 0.19 * 99, 2);
  await revealDetail(page, 'psyche.education.traits.title');
  const metrics = [
    ['psyche.tooltip.mood', 'psyche.education.mood.pleasure', 0.46],
    ['psyche.tooltip.mood', 'psyche.education.mood.arousal', 0.19],
    ['psyche.tooltip.mood', 'psyche.education.mood.dominance', 0.32],
    ['psyche.activeEmotion', 'psyche.emotions.curiosity', 64],
    ['psyche.activeEmotion', 'psyche.emotions.joy', 41],
    ['psyche.activeEmotion', 'psyche.emotions.serenity', 30],
    ['psyche.presentation.relationship', 'psyche.depth', 56],
    ['psyche.presentation.relationship', 'psyche.warmth', 72],
    ['psyche.presentation.relationship', 'psyche.trust', 81],
    ['psyche.education.traits.title', 'psyche.education.traits.openness', 73],
    ['psyche.education.traits.title', 'psyche.education.traits.conscientiousness', 66],
    ['psyche.education.traits.title', 'psyche.education.traits.extraversion', 48],
    ['psyche.education.traits.title', 'psyche.education.traits.agreeableness', 81],
    ['psyche.education.traits.title', 'psyche.education.traits.neuroticism', 24],
    ['psyche.presentation.drivesTitle', 'psyche.curiosityDrive', 69],
    ['psyche.presentation.drivesTitle', 'psyche.history.engagement', 74],
  ] as const;
  for (const [region, label, value] of metrics) {
    const scope =
      region === 'psyche.tooltip.mood' || region === 'psyche.education.traits.title'
        ? section(page)
        : section(page).getByRole('region', { name: copy(region), exact: true });
    const meter = scope.getByRole('meter', { name: copy(label), exact: true });
    await expect(meter).toBeVisible();
    await expect(meter).toHaveAttribute('aria-valuenow', String(value));
  }
  const efficacy = await revealDetail(page, 'psyche.education.drives.efficacy_title');
  for (const [axis, value] of [
    ['results', 71],
    ['usefulness', 40],
  ] as const) {
    const name = `${copy('psyche.domains.technical')} · ${copy(`psyche.efficacy.${axis}`)}`;
    await expect(efficacy.getByRole('meter', { name, exact: true })).toHaveAttribute(
      'aria-valuenow',
      String(value)
    );
  }
  await expect(efficacy.getByRole('meter')).toHaveCount(2);
  await expect(
    efficacy.getByText(copy('psyche.efficacy.resultBasis_other').replace('{{count}}', '5'), {
      exact: true,
    })
  ).toBeVisible();
  await expect(
    efficacy.getByText(copy('psyche.efficacy.feedbackBasis_other').replace('{{count}}', '3'), {
      exact: true,
    })
  ).toBeVisible();
  await expect(
    efficacy.getByText(copy('psyche.efficacy.unassigned_other').replace('{{count}}', '2'), {
      exact: true,
    })
  ).toBeVisible();
  await expectNoOverflow(page, 'psyche OLED20px independent experience axes');
  await expect(
    section(page).getByRole('region', {
      name: copy('psyche.presentation.relationship'),
      exact: true,
    })
  ).toContainText('127');
  await reveal(page, 'psyche.presentation.evolution');
  for (const chart of CHARTS) {
    const control = section(page).getByRole('button', {
      name: copy(`psyche.history.${chart}`),
      exact: true,
    });
    await control.click();
    await expect(control).toHaveAttribute('aria-pressed', 'true');
    await expectNoOverflow(page, `psyche OLED20px ${chart}`);
  }
  expect(summaries, 'opening live data and historical charts does not regenerate the point').toBe(
    2
  );
  await capture(page, info, 'psyche-mobile-oled-large-text');
  const audit = await scanPage(page, info, 'psyche-mobile-oled-large-text');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});
