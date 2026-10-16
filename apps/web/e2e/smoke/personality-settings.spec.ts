/** Style de LIA: the complete catalogue, saved preference and responsive reading. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import type { PersonalityListItem, UserPersonalityResponse } from '../../src/types/personality';
import { EYE_STYLE_IDS } from '../../src/components/eyes/eye-styles';
import {
  test,
  expect,
  waitForHydration,
  waitForMockGate,
  idleNotificationStream,
  expectSessionCookie,
} from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
const CURRENT_ROUTE = '**/api/v1/personalities/current';
const CATALOGUE_ROUTE = '**/api/v1/personalities';

function copy(key: string): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}

/** The catalogue is instance-owned: fourteen entries deliberately exceed the old mock's six. */
function catalogue(): PersonalityListItem[] {
  const entries = [
    ['Normal', 'Un ton équilibré, clair et attentif pour les échanges du quotidien.', '⚖️'],
    [
      'Pragmatique',
      'Des réponses directes, des étapes concrètes et des décisions faciles à suivre.',
      '🤝',
    ],
    [
      'Chaleureuse',
      'Une présence bienveillante qui prend le temps de comprendre la situation.',
      '😊',
    ],
    [
      'Curieuse',
      'Des questions précises et des pistes nouvelles pour approfondir les sujets.',
      '🤔',
    ],
    [
      'Créative',
      'Des idées originales, des rapprochements inattendus et de nouvelles perspectives.',
      '✨',
    ],
    ['Pédagogue', 'Des explications progressives accompagnées d’exemples compréhensibles.', '🎓'],
    [
      'Enthousiaste',
      'Une énergie positive pour avancer dans les projets et les découvertes.',
      '🎉',
    ],
    ['Calme', 'Un rythme posé et des formulations simples pour prendre du recul.', '😌'],
    [
      'Complice',
      'Une conversation détendue, naturelle et ponctuée de petites touches d’humour.',
      '😉',
    ],
    [
      'Analytique',
      'Des faits, des nuances et un raisonnement structuré pour étudier chaque option.',
      '🧐',
    ],
    [
      'Discrète',
      'Des interventions sobres qui laissent la place aux informations essentielles.',
      '😐',
    ],
    [
      'Expressive',
      'Des formulations vivantes qui donnent du relief aux idées et aux échanges.',
      '😁',
    ],
    [
      'Décontractée',
      'Un style accessible et spontané, agréable pour discuter sans se presser.',
      '☕',
    ],
    [
      'Une personnalité au titre particulièrement long pour les conversations approfondies',
      'Une description détaillée, sans troncature : elle reste lisible sur petit écran, avec une police agrandie, et explique ce que ce style change dans la conversation sans masquer les dernières lignes.',
      '🌛',
    ],
  ];
  return entries.map(([title, description, emoji], index) => ({
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    code: index === 0 ? 'default' : `style_${index + 1}`,
    emoji,
    is_default: index === 0,
    title,
    description,
  }));
}

function current(style: PersonalityListItem | null): UserPersonalityResponse {
  return { personality_id: style?.id ?? null, personality: style };
}
function section(page: Page): Locator {
  return page.locator('#settings-section-personality');
}
function choice(page: Page, style: PersonalityListItem): Locator {
  return section(page).getByRole('button', { name: style.title, exact: true });
}
function hero(page: Page): Locator {
  return section(page).getByRole('region', { name: copy('personality.current'), exact: true });
}
function headerChoice(page: Page, style: PersonalityListItem): Locator {
  return page.getByRole('button', {
    name: copy('personality.selector_label').replace('{{name}}', style.title),
    exact: true,
  });
}
async function open(page: Page): Promise<void> {
  const response = await page.goto('/fr/dashboard/settings?section=personality');
  expect(response?.status(), 'the actual settings document must load').toBe(200);
  await waitForHydration(page, '#settings-section-personality');
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
      ''
  );
  await page.evaluate(() => document.fonts.ready);
}
async function loaded(page: Page, styles: readonly PersonalityListItem[]): Promise<void> {
  for (const style of styles) {
    await expect(choice(page, style)).toBeVisible();
    await expect(choice(page, style)).toHaveAccessibleDescription(style.description);
  }
  await expect(section(page).locator('button[aria-pressed]')).toHaveCount(styles.length);
  await expect(section(page)).not.toContainText(/personality\.[a-z_]+|common\.[a-z_]+/);
}
async function selected(page: Page, style: PersonalityListItem): Promise<void> {
  await expect(choice(page, style)).toHaveAttribute('aria-pressed', 'true');
  await expect(section(page).locator('button[aria-pressed="true"]')).toHaveCount(1);
  await expect(hero(page)).toContainText(style.title);
  await expect(hero(page)).toContainText(style.description);
  await expect(headerChoice(page, style)).toBeVisible();
}
async function box(locator: Locator) {
  const result = await locator.boundingBox();
  expect(result, 'a visible element must have a measured box').not.toBeNull();
  return result!;
}
async function layout(
  page: Page,
  styles: readonly PersonalityListItem[],
  desktop: boolean
): Promise<void> {
  const boxes = await Promise.all(styles.map(style => box(choice(page, style))));
  for (const [index, bounds] of boxes.entries()) {
    expect(
      bounds.height,
      'every complete choice is a comfortable touch target'
    ).toBeGreaterThanOrEqual(44);
    expect(
      await choice(page, styles[index]).evaluate(
        element => element.scrollWidth <= element.clientWidth + 1
      ),
      'the style title and description remain inside the choice'
    ).toBe(true);
    const description = choice(page, styles[index]).getByText(styles[index].description, {
      exact: true,
    });
    expect(
      await description.evaluate(element => element.scrollHeight <= element.clientHeight + 1),
      'descriptions are fully readable rather than line-clamped'
    ).toBe(true);
    if (!desktop && index > 0) {
      expect(Math.abs(bounds.x - boxes[0].x), 'mobile choices share a left edge').toBeLessThan(2);
      expect(Math.abs(bounds.width - boxes[0].width), 'mobile choices share a width').toBeLessThan(
        2
      );
      expect(bounds.y).toBeGreaterThanOrEqual(boxes[index - 1].y + boxes[index - 1].height);
    }
  }
  if (desktop) {
    const currentBox = await box(hero(page));
    expect(
      Math.abs(currentBox.y - boxes[0].y),
      'the current style aligns with the first catalogue choice'
    ).toBeLessThan(2);
    expect(boxes[1].x, 'the desktop catalogue has a second column').toBeGreaterThanOrEqual(
      boxes[0].x + boxes[0].width + 8
    );
    expect(Math.abs(boxes[1].y - boxes[0].y)).toBeLessThan(2);
    expect(Math.abs(boxes[2].x - boxes[0].x)).toBeLessThan(2);
    expect(boxes[2].y).toBeGreaterThanOrEqual(boxes[0].y + boxes[0].height);
  }
  await expectNoOverflow(page, desktop ? 'personality desktop' : 'personality mobile');
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
  // Keep the real widget preference; no visual CSS injection or hidden application content.
  await page.addInitScript(() => {
    if (!localStorage.getItem('lia_eyes_widget_prefs')) localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    );
  });
  // authenticate() also seeds localhost for local HTTPS development; the proof origin may be IPv4.
  if (baseURL) {
    await context.addCookies([
      {
        name: 'lia_session',
        value: 'e2e-session',
        url: new URL(baseURL).origin,
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  }
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
  expect(observed.google, 'Google services are never requested by app pages or workers').toEqual(
    []
  );
  // Opaque browser-only services remain DENIED by the unchanged transport guard.
  const browserRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserRefusals.has(request))).toEqual(
    []
  );
});

test('1440px light: complete catalogue, serialized keyboard autosave and shared header selection', async ({
  page,
  authenticate,
  mockApi,
  browserName,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepareTheme(page, 'light');
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await authenticate({ language: 'fr', theme: 'light' });
  const styles = catalogue();
  let saved = styles[0];
  const updates: unknown[] = [];
  const psycheReads: string[] = [];
  let release: () => void = () => undefined;
  const gate = new Promise<void>(resolve => {
    release = resolve;
  });
  await mockApi([
    { url: CATALOGUE_ROUTE, method: 'GET', json: { personalities: styles, total: styles.length } },
    {
      url: CURRENT_ROUTE,
      method: 'GET',
      handler: route => route.fulfill({ json: current(saved) }),
    },
    {
      url: CURRENT_ROUTE,
      method: 'PATCH',
      handler: async (route, signal) => {
        await expectSessionCookie(route.request(), browserName, 'lia_session=e2e-session');
        const body = route.request().postDataJSON() as { personality_id: string | null };
        updates.push(body);
        expect(Object.keys(body)).toEqual(['personality_id']);
        if (updates.length === 1 && !(await waitForMockGate(gate, signal))) return;
        const next = styles.find(style => style.id === body.personality_id);
        expect(next, 'only a real API catalogue entry is submitted').toBeDefined();
        saved = next!;
        await route.fulfill({ json: current(saved) });
      },
    },
    {
      url: /\/api\/v1\/psyche\/state(?:\?.*)?$/,
      method: 'GET',
      handler: async route => {
        psycheReads.push(route.request().url());
        await route.fulfill({ contentType: 'application/json', json: null });
      },
    },
  ]);
  await open(page);
  await loaded(page, styles);
  await selected(page, styles[0]);
  await layout(page, styles, true);
  await expect(hero(page).locator('img[src^="/animated-emoji/"]')).toHaveCount(1);
  const beforeStyleChange = psycheReads.length;
  const pragmatic = choice(page, styles[1]);
  await pragmatic.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => updates.length).toBe(1);
  await expect(pragmatic).toHaveAttribute('aria-disabled', 'true');
  await page.keyboard.press('Enter');
  await choice(page, styles[2]).click({ force: true });
  expect(updates).toEqual([{ personality_id: styles[1].id }]);
  await selected(page, styles[0]);
  await pragmatic.focus();
  await page.keyboard.press('Tab');
  await expect(choice(page, styles[2])).toBeFocused();
  await pragmatic.focus();
  release();
  await selected(page, styles[1]);
  await expect(pragmatic).toHaveAttribute('aria-disabled', 'false');
  await expect(pragmatic).toBeFocused();
  await pragmatic.press('Enter');
  expect(updates, 'selecting the current style does not save twice').toHaveLength(1);
  expect(psycheReads, 'a style-only panel does not reread an offscreen psyche').toHaveLength(beforeStyleChange);
  await headerChoice(page, styles[1]).click();
  await page.getByRole('menuitem').filter({ hasText: styles[2].title }).click();
  await selected(page, styles[2]);
  expect(updates).toEqual([{ personality_id: styles[1].id }, { personality_id: styles[2].id }]);
  expect(psycheReads.every(url => new URL(url).searchParams.get('initialize') === 'false')).toBe(
    true
  );
  await page.reload();
  await loaded(page, styles);
  await selected(page, styles[2]);
  await layout(page, styles, true);
  await capture(page, info, 'personality-desktop-light');
  const audit = await scanPage(page, info, 'personality-desktop-light');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});

test('320px light: initial catalogue failure retries; failed autosave retains the saved style', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 320, height: 950 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', theme: 'light' });
  const styles = catalogue();
  let catalogueAvailable = false;
  let saved = styles[0];
  let writes = 0;
  await mockApi([
    {
      url: CATALOGUE_ROUTE,
      method: 'GET',
      handler: route =>
        catalogueAvailable
          ? route.fulfill({ json: { personalities: styles, total: styles.length } })
          : route.fulfill({ status: 503, json: { detail: 'catalogue_temporarily_unavailable' } }),
    },
    {
      url: CURRENT_ROUTE,
      method: 'GET',
      handler: route => route.fulfill({ json: current(saved) }),
    },
    {
      url: CURRENT_ROUTE,
      method: 'PATCH',
      handler: async route => {
        writes += 1;
        if (writes === 1) {
          await route.fulfill({
            status: 503,
            json: { detail: 'preference_temporarily_unavailable' },
          });
          return;
        }
        const body = route.request().postDataJSON() as { personality_id: string };
        saved = styles.find(style => style.id === body.personality_id)!;
        await route.fulfill({ json: current(saved) });
      },
    },
  ]);
  await open(page);
  await expect(section(page).getByRole('alert')).toBeVisible();
  await expect(section(page).locator('button[aria-pressed]')).toHaveCount(0);
  catalogueAvailable = true;
  await section(page)
    .getByRole('button', { name: copy('common.retry'), exact: true })
    .click();
  await loaded(page, styles);
  await selected(page, styles[0]);
  await layout(page, styles, false);
  await choice(page, styles[13]).click();
  await expect(page.getByText(copy('personality.update_error'), { exact: true })).toBeVisible();
  await expect(choice(page, styles[13])).toHaveAttribute('aria-disabled', 'false');
  await selected(page, styles[0]);
  await choice(page, styles[13]).click();
  await selected(page, styles[13]);
  expect(writes).toBe(2);
  await layout(page, styles, false);
  await capture(page, info, 'personality-mobile-320-light');
});

test('390px OLED and20px text: all styles reflow; reduced motion and keyboard focus remain usable', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1050 });
  await prepareTheme(page, 'oled');
  await authenticate({ language: 'fr', theme: 'oled', font_size: 20 });
  const styles = catalogue();
  let saved = styles[13];
  await mockApi([
    { url: CATALOGUE_ROUTE, method: 'GET', json: { personalities: styles, total: styles.length } },
    {
      url: CURRENT_ROUTE,
      method: 'GET',
      handler: route => route.fulfill({ json: current(saved) }),
    },
    {
      url: CURRENT_ROUTE,
      method: 'PATCH',
      handler: async route => {
        const body = route.request().postDataJSON() as { personality_id: string };
        saved = styles.find(style => style.id === body.personality_id)!;
        await route.fulfill({ json: current(saved) });
      },
    },
  ]);
  await open(page);
  await loaded(page, styles);
  await selected(page, styles[13]);
  await expect
    .poll(() =>
      section(page)
        .getByRole('heading', { name: copy('personality.settings.title'), exact: true })
        .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    )
    .toBe(20);
  await expect(hero(page).locator('img[src^="/animated-emoji/"]')).toHaveCount(0);
  await layout(page, styles, false);
  await choice(page, styles[0]).focus();
  await page.keyboard.press('Tab');
  await expect(choice(page, styles[1])).toBeFocused();
  await page.keyboard.press('Enter');
  await selected(page, styles[1]);
  await expect(choice(page, styles[1])).toBeFocused();
  await layout(page, styles, false);
  await capture(page, info, 'personality-mobile-oled-large-text');
  const audit = await scanPage(page, info, 'personality-mobile-oled-large-text');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});

for (const [width, theme] of [[1440, 'light'], [320, 'oled']] as const) {
  test(`${width}px ${theme}: avatar catalogue, keyboard persistence and readable current choice`, async ({ page, authenticate }, info) => {
    await page.setViewportSize({ width, height: 1050 });
    await prepareTheme(page, theme);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await authenticate({ language: 'fr', theme });
    const response = await page.goto('/fr/dashboard/settings?section=eyes-style');
    expect(response?.status()).toBe(200);
    await waitForHydration(page, '#settings-section-eyes-style');
    const avatar = page.locator('#settings-section-eyes-style');
    const current = avatar.getByRole('region', { name: copy('settings.eyes_style.current'), exact: true });
    await expect(current).toBeVisible();
    for (const id of EYE_STYLE_IDS) {
      const option = avatar.getByRole('button', { name: copy(`eyes.styles.${id}.name`), exact: true });
      await expect(option).toBeVisible();
      await expect(option).toHaveAccessibleDescription(copy(`eyes.styles.${id}.description`));
    }
    const choice = avatar.getByRole('button', { name: copy('eyes.styles.smiley.name'), exact: true });
    await choice.focus();
    await page.keyboard.press('Enter');
    await expect(choice).toHaveAttribute('aria-current', 'true');
    await expect(choice).toBeFocused();
    await expect(current).toContainText(copy('eyes.styles.smiley.description'));
    await expect(avatar.locator('button[aria-current="true"]')).toHaveCount(1);
    await expect(avatar).not.toContainText(/settings\.eyes_style\.[a-z_]+/);
    if (width > 1000) {
      const selected = await box(current);
      const first = await box(avatar.getByRole('button', { name: copy(`eyes.styles.${EYE_STYLE_IDS[0]}.name`), exact: true }));
      expect(Math.abs(selected.y - first.y)).toBeLessThan(2);
      expect(first.x).toBeGreaterThanOrEqual(selected.x + selected.width);
    }
    await page.reload();
    await waitForHydration(page, '#settings-section-eyes-style');
    await expect(choice).toHaveAttribute('aria-current', 'true');
    await expect(current).toContainText(copy('eyes.styles.smiley.name'));
    await expectNoOverflow(page, `avatar ${width}px ${theme}`);
    await page.evaluate(() => window.scrollTo(0, 0));
    const name = `avatar-style-${width}-${theme}`;
    const file = info.outputPath(`${name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    await info.attach(name, { path: file, contentType: 'image/png' });
    const audit = await scanPage(page, info, name);
    expect(audit.blocking, audit.summary).toHaveLength(0);
  });
}
