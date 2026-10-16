/** Recent calls: real chronology, responsive details and read recovery without a backend. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page, TestInfo } from '@playwright/test';
import type { TelephonyCallSummary } from '../../src/types/telephony';
import {
  test,
  expect,
  waitForHydration,
  waitForMockGate,
  idleNotificationStream,
} from '../fixtures';
import { scanPage } from '../a11y/scan';
import { expectNoOverflow, prepareTheme } from './overflow-report';

// Calls retain the existing browser-local civil time, independently of account timezone.
const ACCOUNT_ZONE = 'Europe/Paris';
const BROWSER_ZONE = 'UTC';
const PREFIX = 'settings.telephony.calls';
const CALLS_ROUTE = /\/api\/v1\/telephony\/calls(?:\?.*)?$/;
const translations: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);

function copy(key: string): string {
  let value: unknown = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing French label: ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing French label: ${key}`);
  return value;
}

/** The public DTO intentionally has no phone-number field. */
function call(overrides: Partial<TelephonyCallSummary> = {}): TelephonyCallSummary {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    callee_display: 'Atelier des Tilleuls et service des rendez-vous spécialisés',
    objective:
      'Confirmer les disponibilités et demander le détail du devis avant toute réservation.',
    status: 'completed',
    outcome: 'partial',
    summary:
      'Un créneau a été proposé. Le supplément reste à ta décision ; aucune réservation faite.',
    debrief: {
      key_points: ['Le devis est disponible sur demande.'],
      commitments: ['Le secrétariat transmettra le devis écrit.'],
      follow_up_tasks: ['Comparer le devis avec la proposition initiale.'],
      follow_up_reminders: ['Vérifier la réception du devis demain.'],
      uncertainties: ['Le prix final dépend du matériel.'],
      follow_up_draft: 'Bonjour, pouvez-vous me transmettre le devis détaillé ?',
    },
    structured_data: {
      agreed: false,
      proposed_datetime: '2026-10-19T08:00:00+02:00',
      location: 'Atelier des Tilleuls',
      additional_costs: '35 €',
      pending_user_decision: 'Accepter le supplément de 35 € ?',
    },
    call_seconds: 300,
    created_at: '2026-10-15T22:30:00Z',
    completed_at: '2026-10-15T22:35:00Z',
    call_kind: 'third_party',
    call_mode: 'direct',
    relay_outcome: null,
    usage: {
      tokens_in: 1200,
      tokens_out: 240,
      tokens_cache: 0,
      cost_eur: 0.0123,
      google_api_requests: 1,
    },
    ...overrides,
  };
}

function recentCalls(): TelephonyCallSummary[] {
  return [
    call(),
    call({
      id: '00000000-0000-4000-8000-000000000002',
      callee_display: 'Conversation avec toi',
      created_at: '2026-10-15T22:00:00Z',
      completed_at: '2026-10-15T22:00:00.400Z',
      call_seconds: 0,
      call_kind: 'self',
      call_mode: 'delegated',
      relay_outcome: 'answered',
      structured_data: null,
      debrief: null,
      usage: null,
    }),
    ...Array.from({ length: 8 }, (_, index) => {
      const started = new Date(Date.UTC(2026, 9, index < 3 ? 15 : 14, 18 - index));
      return call({
        id: `00000000-0000-4000-8000-${String(index + 3).padStart(12, '0')}`,
        callee_display: `Service client ${index + 1}`,
        created_at: started.toISOString(),
        completed_at: new Date(started.getTime() + 45_000).toISOString(),
        call_seconds: 45,
        status: index === 0 ? 'no_answer' : index === 1 ? 'voicemail' : 'completed',
        outcome: index < 2 ? 'unreachable' : 'objective_met',
        debrief: null,
        structured_data: null,
        usage: null,
      });
    }),
  ];
}

function section(page: Page): Locator {
  return page.locator('#settings-section-telephony-calls');
}
function summary(page: Page, item: TelephonyCallSummary): Locator {
  // Native summary is DisclosureTriangle in Chromium's AX tree. Playwright's
  // ARIA-role engine deliberately does not alias that native role to button.
  return section(page)
    .locator('summary')
    .filter({ has: page.getByText(item.callee_display, { exact: true }) });
}
function row(page: Page, item: TelephonyCallSummary): Locator {
  return summary(page, item).locator('..');
}
function start(page: Page, item: TelephonyCallSummary): Locator {
  return row(page, item).locator(`summary time[datetime="${item.created_at}"]`);
}
function end(page: Page, item: TelephonyCallSummary): Locator {
  return row(page, item).locator(`summary time[datetime="${item.completed_at}"]`);
}
function civilDay(instant: string): string {
  return new Intl.DateTimeFormat('fr', { dateStyle: 'full', timeZone: BROWSER_ZONE }).format(
    new Date(instant)
  );
}
function clock(instant: string): string {
  return new Intl.DateTimeFormat('fr', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: BROWSER_ZONE,
  }).format(new Date(instant));
}
async function box(locator: Locator) {
  const bounds = await locator.boundingBox();
  expect(bounds, 'a visible element must have a real layout box').not.toBeNull();
  return bounds!;
}

async function open(page: Page): Promise<void> {
  const response = await page.goto('/fr/dashboard/settings?section=telephony-calls');
  expect(response?.status(), 'the actual settings document loads').toBe(200);
  await waitForHydration(page, '#settings-section-telephony-calls');
  await page.waitForFunction(
    () =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
      ''
  );
  await page.evaluate(() => document.fonts.ready);
}
async function loaded(page: Page, calls: readonly TelephonyCallSummary[]): Promise<void> {
  await expect(section(page)).not.toContainText(/settings\.telephony\.|common\./);
  for (const item of calls) {
    await expect(summary(page, item)).toBeVisible();
    await expect(summary(page, item)).toHaveAccessibleName(item.callee_display);
  }
  await expect(section(page).locator('details')).toHaveCount(calls.length);
  await expect(section(page).locator('details[open]')).toHaveCount(0);
}
async function groups(page: Page, calls: readonly TelephonyCallSummary[]): Promise<void> {
  const days = [...new Set(calls.map(item => civilDay(item.created_at)))];
  await expect(
    section(page)
      .getByRole('heading', { level: 4 })
      .filter({ hasNotText: copy(`${PREFIX}.title`) })
  ).toHaveText(days);
  for (const day of days) {
    const group = section(page)
      .getByRole('heading', { name: day, exact: true })
      .locator('xpath=ancestor::section[1]');
    await expect(group.locator('summary')).toHaveCount(
      calls.filter(item => civilDay(item.created_at) === day).length
    );
  }
}
async function geometry(
  page: Page,
  calls: readonly TelephonyCallSummary[],
  desktop: boolean
): Promise<void> {
  for (const item of calls) {
    const control = summary(page, item);
    const title = control.getByText(item.callee_display, { exact: true });
    const [target, titleBox, first] = await Promise.all([
      box(control),
      box(title),
      box(start(page, item)),
    ]);
    expect(
      target.height,
      'native disclosure has an accessible touch target'
    ).toBeGreaterThanOrEqual(44);
    expect(
      await title.evaluate(element => Number(getComputedStyle(element).fontWeight)),
      'names remain normal-weight instead of competing with day headings'
    ).toBeLessThan(600);
    await expect(start(page, item)).toContainText(clock(item.created_at));
    const state = control.getByText(copy(`${PREFIX}.status.${item.status}`), { exact: true });
    const stateBox = await box(state);
    if (desktop) {
      expect(stateBox.x, 'the status is aligned to the right of the name').toBeGreaterThan(
        titleBox.x
      );
      expect(target.x + target.width - (stateBox.x + stateBox.width)).toBeLessThanOrEqual(26);
    } else {
      expect(titleBox.y, 'phones present time before the callee name').toBeGreaterThanOrEqual(
        first.y + first.height - 2
      );
      await expect(control.locator('svg.lucide-phone, svg.lucide-phone-call')).toHaveCount(0);
      expect(stateBox.y, 'status stays in the temporal header').toBeLessThan(titleBox.y);
    }
    if (item.completed_at) {
      const last = await box(end(page, item));
      await expect(end(page, item)).toContainText(clock(item.completed_at));
      expect(await end(page, item).evaluate(element => getComputedStyle(element).fontSize)).toBe(
        await start(page, item).evaluate(element => getComputedStyle(element).fontSize)
      );
      if (desktop) expect(last.y).toBeGreaterThanOrEqual(first.y + first.height - 2);
      else
        expect(
          Math.abs(first.y - last.y),
          'mobile start and end share their line'
        ).toBeLessThanOrEqual(2);
    }
  }
  await expectNoOverflow(page, desktop ? 'recent calls desktop' : 'recent calls mobile');
}
async function capture(page: Page, info: TestInfo, name: string): Promise<void> {
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  const file = info.outputPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(name, { path: file, contentType: 'image/png' });
}

const observations = new WeakMap<Page, { api: string[]; errors: string[]; google: string[] }>();
test.use({ timezoneId: BROWSER_ZONE });
test.beforeEach(async ({ page, context, mockApi }) => {
  await page.addInitScript(() => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    );
  });
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
  // These opaque browser-only tunnels remain DENIED by the unchanged guard.
  const browserRefusals = new Set([
    'CONNECT www.google.com:443',
    'CONNECT content-autofill.googleapis.com:443',
  ]);
  expect(apiNetworkGuard.blockedRequests.filter(request => !browserRefusals.has(request))).toEqual(
    []
  );
});

test('1440px light: ten calls, browser-local days, folded data and keyboard disclosures', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', timezone: ACCOUNT_ZONE, theme: 'light' });
  const calls = recentCalls();
  const limits: string[][] = [];
  await mockApi([
    {
      url: CALLS_ROUTE,
      method: 'GET',
      handler: async route => {
        limits.push(new URL(route.request().url()).searchParams.getAll('limit'));
        await route.fulfill({ json: calls });
      },
    },
  ]);
  await open(page);
  await loaded(page, calls);
  expect(limits.length).toBeGreaterThanOrEqual(1);
  expect(limits.every(limit => limit.length === 1 && limit[0] === '10')).toBe(true);
  await groups(page, calls);
  await geometry(page, calls, true);
  await expect(summary(page, calls[1])).toContainText('0 s');
  for (const key of ['kind.self', 'relay.answered'])
    await expect(summary(page, calls[1])).toContainText(copy(`${PREFIX}.${key}`));
  await expect(summary(page, calls[1])).toContainText(
    copy('settings.telephony.identity.call_mode.delegated')
  );
  const first = summary(page, calls[0]);
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(first).toBeFocused();
  await expect(row(page, calls[0])).toHaveAttribute('open', '');
  await expect(row(page, calls[0]).getByText(calls[0].objective, { exact: true })).toBeVisible();
  await expect(row(page, calls[0]).getByText(calls[0].summary!, { exact: true })).toBeVisible();
  await expect(
    row(page, calls[0]).getByRole('button', {
      name: copy('settings.telephony.decisions.plan_meeting'),
      exact: true,
    })
  ).toBeVisible();
  for (const text of [
    'Le devis est disponible sur demande.',
    'Le secrétariat transmettra le devis écrit.',
    'Comparer le devis avec la proposition initiale.',
    'Vérifier la réception du devis demain.',
    'Le prix final dépend du matériel.',
  ])
    await expect(row(page, calls[0]).getByText(text, { exact: true })).toBeVisible();
  await expect(row(page, calls[0])).toContainText(/1\s?440\s+jetons/);
  await expect(row(page, calls[0])).toContainText(/0,0123\s?€/);
  await expect(
    row(page, calls[0]).getByRole('button', {
      name: copy('settings.telephony.debrief.use_draft'),
      exact: true,
    })
  ).toBeVisible();
  await expect(section(page).locator('details[open]')).toHaveCount(1);
  await expectNoOverflow(page, 'recent calls expanded desktop');
  await capture(page, info, 'recent-calls-desktop-light');
  const audit = await scanPage(page, info, 'recent-calls-desktop-light');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});

test('320px light: initial503 is not an empty history; retry keeps its focused control until recovery', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 320, height: 950 });
  await prepareTheme(page, 'light');
  await authenticate({ language: 'fr', timezone: ACCOUNT_ZONE, theme: 'light' });
  const calls = recentCalls();
  let recovering = false;
  let reads = 0;
  let release: () => void = () => undefined;
  const gate = new Promise<void>(resolve => {
    release = resolve;
  });
  await mockApi([
    {
      url: CALLS_ROUTE,
      method: 'GET',
      handler: async (route, signal) => {
        reads += 1;
        expect(new URL(route.request().url()).searchParams.get('limit')).toBe('10');
        if (!recovering) {
          await route.fulfill({ status: 503, json: { detail: 'telephony_unavailable' } });
          return;
        }
        if (!(await waitForMockGate(gate, signal))) return;
        await route.fulfill({ json: calls });
      },
    },
  ]);
  await open(page);
  await expect(section(page).getByRole('alert')).toContainText(copy(`${PREFIX}.load_error`));
  await expect(section(page).locator('details')).toHaveCount(0);
  const retry = section(page).getByRole('button', { name: copy('common.retry'), exact: true });
  await retry.focus();
  recovering = true;
  const before = reads;
  await page.keyboard.press('Enter');
  await expect.poll(() => reads).toBe(before + 1);
  await expect(retry).toHaveAttribute('aria-disabled', 'true');
  await expect(retry).toBeFocused();
  await page.keyboard.press('Enter');
  expect(reads).toBe(before + 1);
  release();
  await loaded(page, calls);
  await expect(section(page).getByRole('alert')).toHaveCount(0);
  await groups(page, calls);
  await geometry(page, calls, false);
  await summary(page, calls[0]).click();
  await expect(row(page, calls[0]).getByText(calls[0].summary!, { exact: true })).toBeVisible();
  await expectNoOverflow(page, 'recent calls recovered and expanded at320px');
  await capture(page, info, 'recent-calls-mobile-320-light');
});

test('390px OLED20px: active polling retains open details and focus through503 then completion', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 390, height: 1050 });
  await prepareTheme(page, 'oled');
  await authenticate({ language: 'fr', timezone: ACCOUNT_ZONE, theme: 'oled', font_size: 20 });
  await page.clock.install({ time: new Date('2026-10-16T10:00:00Z') });
  const active = call({
    status: 'in_progress',
    completed_at: null,
    call_seconds: null,
    outcome: null,
    summary: null,
    structured_data: null,
    debrief: null,
    usage: null,
  });
  let state: 'active' | 'failure' | 'completed' = 'active';
  let reads = 0;
  await mockApi([
    {
      url: CALLS_ROUTE,
      method: 'GET',
      handler: async route => {
        reads += 1;
        expect(new URL(route.request().url()).searchParams.get('limit')).toBe('10');
        if (state === 'failure') {
          await route.fulfill({ status: 503, json: { detail: 'telephony_unavailable' } });
          return;
        }
        await route.fulfill({ json: [state === 'active' ? active : call()] });
      },
    },
  ]);
  await open(page);
  await loaded(page, [active]);
  await expect
    .poll(() =>
      section(page)
        .getByRole('heading', { name: copy(`${PREFIX}.title`), exact: true })
        .evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    )
    .toBe(20);
  await geometry(page, [active], false);
  const first = summary(page, active);
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(row(page, active)).toHaveAttribute('open', '');
  await expect(row(page, active).getByText(active.objective, { exact: true })).toBeVisible();
  await expect(row(page, active).locator('summary time')).toHaveCount(1);
  const original = await first.elementHandle();
  const before = reads;
  state = 'failure';
  await page.clock.runFor(15_100);
  await expect.poll(() => reads).toBeGreaterThan(before);
  await expect(section(page).getByRole('alert')).toContainText(copy(`${PREFIX}.refresh_error`));
  await expect(first).toBeFocused();
  expect(await first.evaluate((element, previous) => element === previous, original)).toBe(true);
  await expect(row(page, active)).toHaveAttribute('open', '');
  await expect(row(page, active).getByText(active.objective, { exact: true })).toBeVisible();
  state = 'completed';
  await page.clock.runFor(15_100);
  await expect(first.getByText(copy(`${PREFIX}.status.completed`), { exact: true })).toBeVisible();
  await expect(first).toBeFocused();
  await expect(row(page, active)).toHaveAttribute('open', '');
  await expect(row(page, active).getByText(call().summary!, { exact: true })).toBeVisible();
  await expect(section(page).getByRole('alert')).toHaveCount(0);
  await geometry(page, [call()], false);
  const endedReads = reads;
  await page.clock.runFor(30_100);
  expect(reads, 'completed history no longer polls').toBe(endedReads);
  await capture(page, info, 'recent-calls-mobile-oled-large-text');
  const audit = await scanPage(page, info, 'recent-calls-mobile-oled-large-text');
  expect(audit.blocking, audit.summary).toHaveLength(0);
});
